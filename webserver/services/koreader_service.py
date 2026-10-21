#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""Aggregation helpers for the /api/koreader/* endpoints."""

import datetime
import hashlib
import logging
import time

from sqlalchemy import func

from webserver import loader, site_time
from webserver.base.formatter import BookFormatter
from webserver.constants import CALIBRE_COLUMN_CATEGORY
from webserver.i18n import _
from webserver.models import (
    BookReadingStats,
    KoreaderPosition,
    Reading,
    ReadingRecord,
    ReadingState,
    Reader,
)
import tornado.ioloop

from webserver.services import reading_dashboard_service
from webserver.services.cfi_gen.launcher import CfiBatchError, generate_cfis
from webserver.services.reading_stats_service import FINISH_PROGRESS_THRESHOLD, MANUAL_READING_MAX_SECONDS, ReadingStatsService
from webserver.services.sync_service import MyReaderSyncService
from webserver.version import VERSION

CONF = loader.get_settings()

MAX_STATE_IDS = 200
READING_NOW_LIMIT = 20


def is_enabled():
    return bool(CONF.get("ENABLE_KOREADER_SERVICE", True))


def disabled_error():
    return {"err": "koreader.disabled", "msg": _("KOReader 服务未启用")}


def _iso_utc(value):
    return value.isoformat() + "Z" if value else None


def avatar_url(handler, user):
    if not user.avatar:
        return ""
    if user.avatar.startswith("http"):
        gravatar_url = "https://www.gravatar.com"
        return user.avatar.replace("http://", "https://").replace(gravatar_url, CONF.get("avatar_service", ""))
    return handler.site_url + "/avatar/%s" % user.avatar


def session_payload(handler):
    user = handler.current_user
    return {
        "err": "ok",
        "api": 1,
        "server": {
            "version": VERSION,
            "site_title": CONF.get("site_title", "MyBooks"),
            "site_url": handler.site_url,
        },
        "timezone": site_time.resolve_timezone_name(),
        "today": site_time.site_today().isoformat(),
        "user": {
            "userId": user.id,
            "username": user.username,
            "nickname": user.name or user.username,
            "avatar": avatar_url(handler, user),
        },
        "capabilities": {"annotations": True, "states": True, "readingSeconds": True, "match": True},
        "allowed": {"read": user.can_read(), "download": user.can_save(), "can_save": user.can_save()},
    }


def _home_counts_job(session, reader_id):
    rows = session.query(ReadingState.read_state, ReadingState.wants, ReadingState.favorite).filter(ReadingState.reader_id == reader_id).all()
    counts = {"favorites": 0, "wants": 0, "read_done": 0}
    for read_state, wants, favorite in rows:
        if favorite:
            counts["favorites"] += 1
        if wants:
            counts["wants"] += 1
        if read_state == 2:
            counts["read_done"] += 1
    return counts


def _reading_now_ids(session, reader_id, limit):
    last_read_subq = (
        session.query(
            BookReadingStats.book_id.label("book_id"),
            func.max(BookReadingStats.update_time).label("last_read_time"),
        )
        .filter(BookReadingStats.reader_id == reader_id)
        .group_by(BookReadingStats.book_id)
        .subquery()
    )
    rows = (
        session.query(ReadingState.book_id)
        .outerjoin(last_read_subq, last_read_subq.c.book_id == ReadingState.book_id)
        .filter(ReadingState.reader_id == reader_id, ReadingState.read_state == 1)
        .order_by(func.coalesce(last_read_subq.c.last_read_time, ReadingState.read_date).desc())
        .limit(limit)
        .all()
    )
    return [row[0] for row in rows]


def _progress_job(session, reader_id, ids):
    if not ids:
        return {}
    rows = (
        session.query(
            BookReadingStats.book_id,
            func.max(BookReadingStats.progress_percent),
        )
        .filter(BookReadingStats.reader_id == reader_id, BookReadingStats.book_id.in_(ids))
        .group_by(BookReadingStats.book_id)
        .all()
    )
    return {book_id: round(float(percent or 0), 2) for book_id, percent in rows}


def _book_summary(handler, book, progress):
    data = BookFormatter(handler, book).format(include_comments=False)
    return {
        "id": data.get("id"),
        "title": data.get("title"),
        "author": data.get("author"),
        "img": data.get("img"),
        "thumb": data.get("thumb"),
        "series": data.get("series"),
        "series_index": data.get("series_index"),
        "progress_percent": progress.get(data.get("id"), 0),
    }


async def home_payload(handler):
    user = handler.current_user
    today = site_time.site_today()

    def stats_job(session):
        reader = session.get(Reader, user.id)
        if reader is None:
            return None
        return reading_dashboard_service.get_stats(session, reader, handler.calibre_db)

    stats = await handler.run_sqlite_async(stats_job)
    if stats is None:
        return {"err": "failed", "msg": _("用户不存在")}

    heatmap_days = (stats.get("heatmap") or {}).get("days") or []
    today_seconds = 0
    if heatmap_days and heatmap_days[-1].get("date") == today.isoformat():
        today_seconds = heatmap_days[-1].get("reading_seconds", 0)

    counts = await handler.run_sqlite_async(_home_counts_job, user.id)
    book_ids = await handler.run_sqlite_async(_reading_now_ids, user.id, READING_NOW_LIMIT)
    progress = await handler.run_sqlite_async(_progress_job, user.id, book_ids)

    reading_now = []
    if book_ids:
        books = await handler.get_books_for_list_async(ids=book_ids)
        by_id = {book["id"]: book for book in books}
        for book_id in book_ids:
            book = by_id.get(book_id)
            if book:
                reading_now.append(_book_summary(handler, book, progress))

    sections = [
        {"kind": "favorites", "title": _("我的收藏"), "count": counts["favorites"]},
        {"kind": "wants", "title": _("我的待读"), "count": counts["wants"]},
        {"kind": "read_done", "title": _("我的已读"), "count": counts["read_done"]},
        {"kind": "categories", "title": _("分类"), "count": await _category_count(handler)},
        {"kind": "tags", "title": _("标签"), "count": await _meta_count(handler, "tag")},
        {"kind": "authors", "title": _("作者"), "count": await _meta_count(handler, "author")},
        {"kind": "recent", "title": _("最新"), "count": None},
    ]

    return {
        "err": "ok",
        "profile": {"nickname": user.name or user.username, "avatar": avatar_url(handler, user)},
        "stats": {
            "total_seconds": (stats.get("totals") or {}).get("total_reading_seconds", 0),
            "today_seconds": today_seconds,
            "streak": stats.get("streak") or {"current": 0, "best": 0},
            "book_status": stats.get("book_status") or {"reading": 0, "to_read": 0, "finished": 0},
        },
        "reading_now": reading_now,
        "sections": sections,
    }


async def _category_count(handler):
    if CALIBRE_COLUMN_CATEGORY not in handler.calibre_db.field_metadata:
        return 0
    try:
        return await handler.run_calibre_async(handler.get_custom_category_count)
    except Exception as e:
        logging.warning("[koreader] category count failed: %s", e)
        return None


async def _meta_count(handler, meta):
    try:
        items = await handler.get_category_with_count_async(meta)
        return len(items)
    except Exception as e:
        logging.warning("[koreader] %s count failed: %s", meta, e)
        return None


def parse_book_ids(raw):
    ids = []
    seen = set()
    for part in (raw or "").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            book_id = int(part)
        except ValueError:
            continue
        if book_id <= 0 or book_id in seen:
            continue
        seen.add(book_id)
        ids.append(book_id)
        if len(ids) >= MAX_STATE_IDS:
            break
    return ids


def _states_job(session, reader_id, ids):
    result = {}
    for state in session.query(ReadingState).filter(ReadingState.reader_id == reader_id, ReadingState.book_id.in_(ids)).all():
        result[state.book_id] = {
            "read_state": state.read_state or 0,
            "favorite": bool(state.favorite),
            "wants": bool(state.wants),
            "download": bool(state.download),
            "read_date": state.read_date,
        }
    if not ids:
        return result
    rows = (
        session.query(
            BookReadingStats.book_id,
            func.max(BookReadingStats.progress_percent),
            func.sum(BookReadingStats.total_seconds),
            func.max(BookReadingStats.update_time),
        )
        .filter(BookReadingStats.reader_id == reader_id, BookReadingStats.book_id.in_(ids))
        .group_by(BookReadingStats.book_id)
        .all()
    )
    for book_id, percent, seconds, last_read in rows:
        item = result.setdefault(book_id, {})
        item["progress_percent"] = round(float(percent or 0), 2)
        item["total_seconds"] = int(seconds or 0)
        item["stats_last_read"] = last_read
    return result


async def batch_states(handler, ids):
    if not ids:
        return {}
    reader_id = handler.current_user.id
    raw = await handler.run_sqlite_async(_states_job, reader_id, ids)

    def _formats_job():
        cache = handler.calibre_db_cache
        return {book_id: (cache.formats(book_id, verify_formats=False) or []) for book_id in ids if cache.has_id(book_id)}

    formats = await handler.run_calibre_read_async(_formats_job)

    states = {}
    for book_id in ids:
        if book_id not in formats:
            continue
        item = raw.get(book_id) or {}
        last_read = item.get("stats_last_read") or item.get("read_date")
        states[str(book_id)] = {
            "read_state": item.get("read_state", 0),
            "favorite": item.get("favorite", False),
            "wants": item.get("wants", False),
            "download": item.get("download", False),
            "progress_percent": item.get("progress_percent", 0),
            "total_seconds": item.get("total_seconds", 0),
            "last_read": _iso_utc(last_read),
            "formats": [str(fmt).lower() for fmt in formats[book_id]],
        }
    return states


def _search_book(book, state):
    formats = state.get("formats") or [str(item.get("format", "")).lower() for item in book.get("files") or [] if item.get("format")]
    return {
        "id": book.get("id"),
        "title": book.get("title"),
        "author": book.get("author"),
        "thumb": book.get("thumb"),
        "formats": formats,
        "progress_percent": state.get("progress_percent", 0),
        "read_state": state.get("read_state", 0),
        "favorite": state.get("favorite", False),
        "total_seconds": state.get("total_seconds", 0),
    }


async def trim_search_response(handler, rsp):
    books = rsp.get("books") or []
    ids = [book["id"] for book in books if book.get("id")]
    states = await batch_states(handler, ids)
    trimmed = [_search_book(book, states.get(str(book.get("id")), {})) for book in books]
    total = rsp.get("total", len(trimmed))
    start = handler.get_argument_start()
    try:
        size = int(handler.get_argument("size", "0"))
    except (TypeError, ValueError):
        size = 0
    step = size if size > 0 else CONF.get("DEFAULT_PAGE_SIZE", 60)
    next_offset = start + step
    return {
        "err": "ok",
        "total": total,
        "books": trimmed,
        "next": next_offset if next_offset < total else None,
    }


SECONDS_BATCH_LIMIT = 500
SECONDS_DEDUP_TTL = 24 * 3600
_SECONDS_DEDUP = {}


def _timestamp(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _client_ms(value):
    ts = _timestamp(value)
    if ts is None:
        return None
    return ts * 1000 if ts < 100000000000 else ts


def _iso_now():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _iso_to_ms(text):
    if not text:
        return 0
    try:
        parsed = datetime.datetime.fromisoformat(str(text).strip().replace("Z", "+00:00"))
    except ValueError:
        return 0
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.timezone.utc)
    return int(parsed.timestamp() * 1000)


def _percent(value):
    try:
        return max(0.0, min(100.0, float(value)))
    except (TypeError, ValueError):
        return None


def _normalize_progress(payload):
    raw = payload.get("progress")
    if isinstance(raw, (list, tuple)) and len(raw) == 2:
        try:
            current, total = int(raw[0]), int(raw[1])
            if total > 0:
                return current, total
        except (TypeError, ValueError):
            pass
    percent = _percent(payload.get("percent"))
    if percent is None:
        return None
    return int(round(percent * 100)), 10000


def _progress_percent(progress, fallback=None):
    if progress and progress[1] > 0:
        return round(progress[0] * 100.0 / progress[1], 2)
    return fallback


def normalize_format(value):
    fmt = str(value or "").strip().lower()
    if not fmt or not fmt.replace("-", "").isalnum():
        return None
    return fmt[:16]


def _book_id(value):
    try:
        book_id = int(value)
    except (TypeError, ValueError):
        return None
    return book_id if book_id > 0 else None


def _access_error(handler):
    if not handler.current_user or not handler.current_user.can_read():
        return "book.forbidden"
    return None


async def _exists(handler, book_id):
    try:
        return bool(await handler.run_calibre_read_async(handler.calibre_db_cache.has_id, book_id))
    except Exception as e:
        logging.warning("[koreader] book %s lookup failed: %s", book_id, e)
        return False


async def _check_book(handler, book_id):
    if book_id is None:
        return "params.invalid"
    error = _access_error(handler)
    if error:
        return error
    if not await _exists(handler, book_id):
        return "book.not_found"
    return None


def _position_job(session, reader_id, book_id, fmt):
    row = session.get(KoreaderPosition, (reader_id, book_id, fmt))
    return row.format_dict() if row else None


def _save_position(session, reader_id, book_id, fmt, xpointer, percent, client_updated_at, device):
    row = session.get(KoreaderPosition, (reader_id, book_id, fmt))
    now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    if row is None:
        row = KoreaderPosition(reader_id=reader_id, book_id=book_id, format=fmt)
        session.add(row)
    elif client_updated_at is not None and row.client_updated_at is not None and client_updated_at <= row.client_updated_at:
        return False, row.format_dict()
    if xpointer is not None:
        row.xpointer = xpointer
    if percent is not None:
        row.percent = percent
    if client_updated_at is not None:
        row.client_updated_at = client_updated_at
    row.device_id = device.get("id") or row.device_id
    row.device_name = device.get("name") or row.device_name
    row.update_time = now
    session.add(row)
    session.commit()
    return True, row.format_dict()


def _apply_implicit_state(session, reader_id, book_id, percent, client_ts=None):
    if percent is None or percent <= 0:
        return
    state = session.query(ReadingState).filter(ReadingState.reader_id == reader_id, ReadingState.book_id == book_id).first()
    if state is None:
        state = ReadingState(book_id, reader_id)
        session.add(state)
    if client_ts is not None and state.read_date is not None and client_ts <= int(state.read_date.timestamp() * 1000):
        return
    current = state.read_state or 0
    target = 2 if percent >= FINISH_PROGRESS_THRESHOLD else 1
    if target > current:
        state.set_read_state(target)
        session.add(state)
        session.commit()


def _seconds_fingerprint(reader_id, book_id, fmt, date, seconds, seq):
    raw = "|".join(str(item) for item in (reader_id, book_id, fmt, date, seconds, seq))
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def _dedup_hit(key):
    now = time.time()
    for old in [k for k, ts in _SECONDS_DEDUP.items() if now - ts > SECONDS_DEDUP_TTL]:
        _SECONDS_DEDUP.pop(old, None)
    if key in _SECONDS_DEDUP:
        return True
    _SECONDS_DEDUP[key] = now
    return False


def _report_seconds(reader_id, book_id, fmt, entries, progress, client_ts):
    applied = 0
    for entry in entries:
        seq = entry.get("seq")
        if seq is None:
            seq = client_ts
        date_text = str(entry.get("date") or "").strip()
        try:
            date = datetime.date.fromisoformat(date_text)
        except ValueError:
            continue
        try:
            seconds = int(entry.get("seconds") or 0)
        except (TypeError, ValueError):
            continue
        seconds = min(max(seconds, 0), MANUAL_READING_MAX_SECONDS)
        if seconds <= 0:
            continue
        key = _seconds_fingerprint(reader_id, book_id, fmt, date_text, seconds, seq)
        if _dedup_hit(key):
            continue
        ReadingStatsService.report_duration(reader_id, book_id, Reading.PROTOCOL_KOREADER, date, seconds, fmt=fmt, progress=progress)
        applied += 1
    return applied


async def _state_for(handler, book_id):
    states = await batch_states(handler, [book_id])
    return states.get(str(book_id), {})


async def update_progress(handler, payload):
    book_id = _book_id(payload.get("book_id"))
    error = await _check_book(handler, book_id)
    if error:
        return {"err": error, "msg": _("书籍不存在或无权限")}
    reader_id = handler.current_user.id
    fmt = normalize_format(payload.get("format")) or "epub"
    progress = _normalize_progress(payload)
    percent = _progress_percent(progress, _percent(payload.get("percent")))
    client_ts = _client_ms(payload.get("client_updated_at"))
    location = payload.get("location") or {}
    xpointer = location.get("xpointer")
    device = payload.get("device") or {}
    session = handler.sqlite_session

    entries = payload.get("reading_seconds") or []
    if entries:
        _report_seconds(reader_id, book_id, fmt, entries, progress, client_ts)

    if xpointer is not None or percent is not None:
        applied, position = _save_position(session, reader_id, book_id, fmt, xpointer, percent, client_ts, device)
        if not applied:
            state = await _state_for(handler, book_id)
            return {
                "err": "ok",
                "book_id": book_id,
                "applied": False,
                "progress_percent": position.get("percent") if position.get("percent") is not None else state.get("progress_percent", 0),
                "progress": None,
                "location": {"xpointer": position.get("xpointer"), "client_updated_at": position.get("client_updated_at"), "device_id": position.get("device_id")},
                "read_state": state.get("read_state", 0),
                "total_seconds": state.get("total_seconds", 0),
                "server_time": int(time.time()),
            }

    if not entries and not payload.get("skip_heartbeat"):
        ReadingStatsService.heartbeat(reader_id, book_id, Reading.PROTOCOL_KOREADER, fmt=fmt, progress=progress)
    _apply_implicit_state(session, reader_id, book_id, percent, client_ts)

    state = await _state_for(handler, book_id)
    position = await handler.run_sqlite_async(_position_job, reader_id, book_id, fmt) or {}
    stored = position.get("percent")
    return {
        "err": "ok",
        "book_id": book_id,
        "applied": True,
        "progress_percent": stored if stored is not None else state.get("progress_percent", percent or 0),
        "progress": list(progress) if progress else None,
        "location": {
            "xpointer": position.get("xpointer"),
            "client_updated_at": position.get("client_updated_at"),
            "device_id": position.get("device_id"),
        },
        "read_state": state.get("read_state", 0),
        "total_seconds": state.get("total_seconds", 0),
        "server_time": int(time.time()),
    }


async def update_reading_seconds(handler, payload):
    reader_id = handler.current_user.id
    entries = payload.get("entries") or []
    if not isinstance(entries, list) or len(entries) > SECONDS_BATCH_LIMIT:
        return {"err": "params.invalid", "msg": _("条目数量超出限制")}
    applied = 0
    skipped = []
    for entry in entries:
        book_id = _book_id(entry.get("book_id"))
        error = await _check_book(handler, book_id)
        if error:
            skipped.append({"book_id": book_id, "reason": error})
            continue
        fmt = normalize_format(entry.get("format")) or "epub"
        progress = _normalize_progress(entry)
        percent = _progress_percent(progress, _percent(entry.get("percent")))
        count = _report_seconds(reader_id, book_id, fmt, [entry], progress, _client_ms(payload.get("client_updated_at")))
        if count:
            applied += 1
            if percent is not None:
                _apply_implicit_state(handler.sqlite_session, reader_id, book_id, percent, _client_ms(payload.get("client_updated_at")))
        else:
            skipped.append({"book_id": book_id, "reason": "duplicate"})
    return {"err": "ok", "applied": applied, "skipped": skipped}


def _apply_state(session, reader_id, book_id, payload, client_ts):
    state = session.query(ReadingState).filter(ReadingState.reader_id == reader_id, ReadingState.book_id == book_id).first()
    if state is None:
        state = ReadingState(book_id, reader_id)
        session.add(state)

    def newer(existing):
        if client_ts is None or existing is None:
            return True
        return client_ts > int(existing.timestamp() * 1000)

    if "favorite" in payload and newer(state.favorite_date):
        state.set_favorite(bool(payload.get("favorite")))
    if "wants" in payload and newer(state.wants_date):
        state.set_wants(bool(payload.get("wants")))
    if "read_state" in payload:
        try:
            target = int(payload.get("read_state"))
        except (TypeError, ValueError):
            target = None
        if target in (0, 1, 2) and newer(state.read_date):
            if not (target == 1 and (state.read_state or 0) == 2):
                state.set_read_state(target)
    if "download" in payload:
        state.set_download(bool(payload.get("download")))
    session.add(state)
    session.commit()


async def update_state(handler, payload):
    book_id = _book_id(payload.get("book_id"))
    error = await _check_book(handler, book_id)
    if error:
        return {"err": error, "msg": _("书籍不存在或无权限")}
    reader_id = handler.current_user.id
    _apply_state(handler.sqlite_session, reader_id, book_id, payload, _client_ms(payload.get("client_updated_at")))
    state = await _state_for(handler, book_id)
    state["book_id"] = book_id
    return {"err": "ok", "state": state}


async def get_progress(handler, book_id, fmt):
    error = await _check_book(handler, book_id)
    if error:
        return {"err": error, "msg": _("书籍不存在或无权限")}
    reader_id = handler.current_user.id
    fmt = normalize_format(fmt) or "epub"
    position = await handler.run_sqlite_async(_position_job, reader_id, book_id, fmt)
    state = await _state_for(handler, book_id)
    return {
        "err": "ok",
        "book_id": book_id,
        "format": fmt,
        "progress_percent": state.get("progress_percent", 0),
        "read_state": state.get("read_state", 0),
        "total_seconds": state.get("total_seconds", 0),
        "last_read": state.get("last_read"),
        "location": position or {},
    }


def _quote(text):
    return '"' + str(text).replace("\\", "\\\\").replace('"', '\\"') + '"'


def _match_job(cache, title, author, limit):
    found = []
    seen = set()

    def add(ids, score, reason):
        for book_id in ids:
            book_id = int(book_id)
            if book_id in seen:
                continue
            seen.add(book_id)
            found.append((book_id, score, reason))

    try:
        if title:
            add(list(cache.search(f"title:={_quote(title)}"))[:limit], 1.0, "title")
        if author:
            add(list(cache.search(f"authors:={_quote(author)}"))[:limit], 0.9, "author")
        if len(found) < limit and title:
            add(list(cache.search(f"title:{_quote(title)}"))[:limit], 0.7, "title_fuzzy")
        if len(found) < limit and author:
            add(list(cache.search(f"authors:{_quote(author)}"))[:limit], 0.6, "author_fuzzy")
    except Exception as e:
        logging.warning("[koreader] match search failed: %s", e)
    return found[:limit]


async def match_books(handler, payload):
    title = str(payload.get("title") or "").strip()
    author = str(payload.get("author") or "").strip()
    if not title and not author:
        return {"err": "params.invalid", "msg": _("请提供书名或作者")}
    try:
        limit = max(1, min(int(payload.get("limit") or 10), 30))
    except (TypeError, ValueError):
        limit = 10
    found = await handler.run_calibre_read_async(_match_job, handler.calibre_db_cache, title, author, limit)
    ids = [item[0] for item in found]
    books = await handler.get_books_for_list_async(ids=ids) if ids else []
    by_id = {book["id"]: book for book in books}
    states = await batch_states(handler, ids)
    candidates = []
    for book_id, score, reason in found:
        book = by_id.get(book_id)
        if not book:
            continue
        state = states.get(str(book_id), {})
        summary = _book_summary(handler, book, {book_id: state.get("progress_percent", 0)})
        summary.update({
            "book_id": book_id,
            "formats": state.get("formats", []),
            "read_state": state.get("read_state", 0),
            "score": score,
            "reason": reason,
        })
        candidates.append(summary)
    return {"err": "ok", "candidates": candidates}


NOTES_LIMIT = 500


def _book_hash(book_id, fmt):
    return f"cloud-{book_id}-{fmt}"


def _normalize_note(note, uid):
    note_id = str(note.get("id") or "").strip()
    if not note_id:
        return None
    clean = dict(note)
    clean["id"] = note_id
    owner = clean.get("uid")
    if owner is not None:
        try:
            if int(owner) != uid:
                return None
        except (TypeError, ValueError):
            return None
    clean["uid"] = uid
    for source, target in (("createdAt", "created_at"), ("updatedAt", "updated_at"), ("deletedAt", "deleted_at")):
        if source in clean and clean.get(source) is not None:
            try:
                clean[target] = int(clean[source])
            except (TypeError, ValueError):
                clean.pop(target, None)
    if not clean.get("updated_at"):
        clean["updated_at"] = clean.get("created_at") or int(time.time() * 1000)
    return clean


def _note_items(records, since, always=None):
    items = []
    always = always or set()
    for payload in records.values():
        if not isinstance(payload, dict):
            continue
        if payload.get("id") not in always and not MyReaderSyncService._changed_since(payload, since):
            continue
        item = dict(payload)
        if not item.get("xpointer0"):
            item["unresolvable"] = True
        items.append(item)
    items.sort(key=lambda item: (max(item.get("updated_at") or 0, item.get("deleted_at") or 0), item.get("id") or ""))
    return items[:NOTES_LIMIT]


async def exchange_annotations(handler, payload):
    book_id = _book_id(payload.get("book_id"))
    error = await _check_book(handler, book_id)
    if error:
        return {"err": error, "msg": _("书籍不存在或无权限")}
    fmt = normalize_format(payload.get("format")) or "epub"
    raw_notes = payload.get("notes") or []
    if not isinstance(raw_notes, list) or len(raw_notes) > NOTES_LIMIT:
        return {"err": "params.invalid", "msg": _("标注数量超出限制")}
    uid = handler.current_user.id
    notes = [item for item in (_normalize_note(note, uid) for note in raw_notes if isinstance(note, dict)) if item]
    book_hash = _book_hash(book_id, fmt)
    db = ReadingRecord._session()
    if notes:
        try:
            MyReaderSyncService._push_book_records(db, uid, book_hash, "notes", notes)
            MyReaderSyncService.flush_now()
        except Exception as e:
            db.rollback()
            logging.error("[koreader] notes push failed for user %s book %s: %s", uid, book_id, e, exc_info=True)
            return {"err": "failed", "msg": _("标注写入失败")}

    since = _iso_to_ms(payload.get("ack"))
    records = MyReaderSyncService._effective_records(db, uid, "notes", book_hash)
    items = _note_items(records, since, {note["id"] for note in notes})
    if notes:
        await _schedule_cfi(handler, uid, book_id, fmt, book_hash, notes)
    return {"err": "ok", "ack": _iso_now(), "notes": items, "pending": len(items)}


async def _schedule_cfi(handler, uid, book_id, fmt, book_hash, notes):
    anchors = []
    stamps = {}
    for note in notes:
        if not note.get("text") or note.get("cfi"):
            continue
        anchor = {"id": note["id"], "text": note.get("text") or ""}
        if note.get("chapter"):
            anchor["chapterHint"] = note["chapter"]
        anchors.append(anchor)
        stamps[note["id"]] = note.get("updated_at") or 0
    if not anchors:
        return

    def _path():
        for candidate in (fmt, "epub", "EPUB"):
            try:
                path = handler.calibre_db_cache.format_abspath(book_id, candidate)
            except Exception:
                continue
            if path:
                return path
        return None

    path = await handler.run_calibre_read_async(_path)
    if not path:
        return
    tornado.ioloop.IOLoop.current().spawn_callback(_generate_cfis, uid, book_hash, path, anchors[:2000], stamps)


async def _generate_cfis(uid, book_hash, path, anchors, stamps):
    try:
        results = await generate_cfis(path, anchors)
    except CfiBatchError as e:
        logging.warning("[koreader] cfi generation failed for %s: %s", book_hash, e)
        return
    except Exception as e:
        logging.warning("[koreader] cfi generation crashed for %s: %s", book_hash, e)
        return
    updates = [
        {"id": result.get("id"), "uid": uid, "cfi": result["cfi"], "updated_at": stamps.get(result.get("id"), 0)}
        for result in results
        if result.get("status") == "ok" and result.get("cfi")
    ]
    if not updates:
        return
    db = ReadingRecord._session()
    try:
        MyReaderSyncService._push_book_records(db, uid, book_hash, "notes", updates)
        MyReaderSyncService.flush_now()
    except Exception:
        db.rollback()
        logging.error("[koreader] cfi store failed for %s", book_hash, exc_info=True)
