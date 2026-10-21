#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""Aggregation helpers for the /api/koreader/* endpoints."""

import logging

from sqlalchemy import func

from webserver import loader, site_time
from webserver.base.formatter import BookFormatter
from webserver.constants import CALIBRE_COLUMN_CATEGORY
from webserver.i18n import _
from webserver.models import BookReadingStats, ReadingState, Reader
from webserver.services import reading_dashboard_service
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
