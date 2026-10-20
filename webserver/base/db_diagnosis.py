#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""SQLite 写锁现场诊断
* 用一条独立短超时连接试 ``BEGIN IMMEDIATE``：成功说明此刻没人持写锁，失败
  说明确实有写者；试完立刻 ``ROLLBACK``，不改任何数据。
* 采样 ``PRAGMA data_version`` 与 ``-wal`` 文件大小：有变化说明期间有别的
  连接提交过（= 正在写）。
* dump 本进程所有线程栈，标出卡在 sqlalchemy/pysqlite 里的线程。
* 扫 ``/proc/<pid>/fd``，列出还打开着 db/-wal/-shm 的进程，用来发现“第二个
  实例 / 容器 / 外部 sqlite 客户端”。

诊断在后台线程里跑并且使用独立连接。同一进程 15 秒内只打一份完整 dump。
"""

import logging
import os
import sqlite3
import sys
import threading
import time
import traceback

LOG_PREFIX = "[DB-LOCK]"

# 探针连接的忙等上限：只想知道“现在有没有人持锁”，不想再等一轮 busy_timeout。
PROBE_TIMEOUT_S = 0.2
# data_version / -wal 大小的采样窗口。
SAMPLE_WINDOW_S = 2.5
SAMPLE_STEP_S = 0.5
# 完整 dump 的最小间隔（秒）。两次导入失败相隔 30s 时应该各留一份。
DUMP_MIN_INTERVAL_S = 15.0
# dump 体量上限，避免线程特别多时把日志刷爆。
MAX_STACK_LINES = 240
MAX_THREADS = 40

_tl = threading.local()
_state_lock = threading.Lock()
_last_dump_at = 0.0


def install(engine) -> None:
    """在 engine 上挂诊断钩子。只在 SQLite 上调用一次。"""
    from sqlalchemy import event

    @event.listens_for(engine, "before_cursor_execute")
    def _mark_start(conn, cursor, statement, parameters, context, executemany):
        # 只是为了算出“这条语句等了多久”。一次属性赋值，开销可忽略。
        _tl.started_at = time.monotonic()

    @event.listens_for(engine, "handle_error")
    def _on_error(context):
        try:
            if not _is_lock_error(getattr(context, "original_exception", None)):
                return
            started = getattr(_tl, "started_at", None)
            waited = (time.monotonic() - started) if started else None
            threading.Thread(
                target=_dump,
                args=(
                    engine,
                    threading.current_thread().name,
                    _shorten(getattr(context, "statement", "") or "", 400),
                    _shorten(repr(getattr(context, "parameters", "")), 400),
                    waited,
                ),
                name="db-lock-diagnosis",
                daemon=True,
            ).start()
        except Exception:  # 诊断绝不能影响主流程
            logging.debug("%s failed to start diagnostics", LOG_PREFIX, exc_info=True)


def _is_lock_error(exc) -> bool:
    if exc is None:
        return False
    text = str(exc).lower()
    return "database is locked" in text or "database table is locked" in text


def _shorten(value, limit: int) -> str:
    text = str(value).replace("\n", " ")
    return text if len(text) <= limit else text[:limit] + "..."


def _dump(engine, thread_name, statement, params, waited) -> None:
    global _last_dump_at
    now = time.monotonic()
    with _state_lock:
        throttled = (now - _last_dump_at) < DUMP_MIN_INTERVAL_S
        if not throttled:
            _last_dump_at = now

    db_path = _db_path(engine)
    if throttled:
        logging.warning(
            "%s database is locked again (thread=%s, db=%s) — full dump throttled",
            LOG_PREFIX, thread_name, db_path,
        )
        return

    try:
        lines = _collect(engine, db_path, thread_name, statement, params, waited)
        logging.error("%s database is locked — diagnostics\n%s", LOG_PREFIX, "\n".join(lines))
    except Exception:
        logging.warning("%s diagnostics failed", LOG_PREFIX, exc_info=True)


def _collect(engine, db_path, thread_name, statement, params, waited) -> list:
    lines = [
        "time      : %s" % time.strftime("%Y-%m-%d %H:%M:%S"),
        "thread    : %s" % thread_name,
        "db        : %s" % db_path,
        "sqlite    : %s" % sqlite3.sqlite_version,
        "statement : %s" % statement,
        "params    : %s" % params,
    ]
    if waited is not None:
        lines.append("waited    : %.3fs（busy_timeout 用尽）" % waited)
    lines.append("pool      : %s" % _pool_status(engine))
    lines.extend(_file_info(db_path))
    lines.extend(_probe(db_path))
    lines.extend(_stack_dump(exclude_ident=threading.get_ident()))
    lines.extend(_proc_holders(db_path))
    return lines


def _db_path(engine):
    try:
        path = engine.url.database
    except Exception:
        return ""
    if not path:
        return ""
    return os.path.abspath(path)


def _pool_status(engine) -> str:
    try:
        return str(engine.pool.status())
    except Exception as exc:
        return "unavailable: %s" % exc


def _file_info(db_path) -> list:
    if not db_path:
        return ["files     : no db path"]
    out = []
    for suffix in ("", "-wal", "-shm"):
        path = db_path + suffix
        try:
            stat = os.stat(path)
        except OSError:
            out.append("files     : %-4s missing" % (suffix or "db"))
            continue
        out.append(
            "files     : %-4s %12d bytes  mtime=%s" % (
                suffix or "db", stat.st_size,
                time.strftime("%H:%M:%S", time.localtime(stat.st_mtime)),
            )
        )
    return out


def _probe(db_path) -> list:
    """独立连接做三件事：读 PRAGMA、采样 data_version、试抢写锁。"""
    if not db_path or not os.path.exists(db_path):
        return ["probe     : db file not found, skip"]

    try:
        conn = sqlite3.connect(db_path, timeout=PROBE_TIMEOUT_S, isolation_level=None)
    except Exception as exc:
        return ["probe     : connect failed: %s" % exc]

    out = []
    try:
        conn.execute("PRAGMA busy_timeout=200")
        out.append("journal   : %s" % _scalar(conn, "PRAGMA journal_mode"))

        dv0 = _scalar(conn, "PRAGMA data_version")
        wal0 = _wal_size(db_path)
        deadline = time.monotonic() + SAMPLE_WINDOW_S
        while time.monotonic() < deadline:
            time.sleep(SAMPLE_STEP_S)
        dv1 = _scalar(conn, "PRAGMA data_version")
        wal1 = _wal_size(db_path)
        changed = "yes（期间有其它连接提交，说明有人正在写）" if dv0 != dv1 else "no"
        out.append("data_ver  : %s -> %s  changed=%s" % (dv0, dv1, changed))
        out.append("wal_bytes : %s -> %s  (%+d during %.1fs)" % (
            wal0, wal1, (wal1 or 0) - (wal0 or 0), SAMPLE_WINDOW_S,
        ))

        started = time.monotonic()
        try:
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            out.append(
                "write_lock: ACQUIRED in %.0fms → 此刻没人持写锁（已 ROLLBACK，未改数据）"
                % ((time.monotonic() - started) * 1000)
            )
        except sqlite3.OperationalError as exc:
            out.append(
                "write_lock: FAILED after %.0fms → %s（此刻确实有连接/进程持写锁）"
                % ((time.monotonic() - started) * 1000, exc)
            )
        except Exception as exc:
            out.append("write_lock: probe error: %s" % exc)

        try:
            row = conn.execute("PRAGMA wal_checkpoint(PASSIVE)").fetchone()
            out.append("checkpoint: busy=%s log=%s checkpointed=%s" % tuple(row))
        except Exception as exc:
            out.append("checkpoint: %s" % exc)
    finally:
        try:
            conn.close()
        except Exception:
            pass
    return out


def _scalar(conn, sql):
    try:
        row = conn.execute(sql).fetchone()
        return row[0] if row else None
    except Exception as exc:
        return "err:%s" % exc


def _wal_size(db_path) -> int:
    try:
        return os.path.getsize(db_path + "-wal")
    except OSError:
        return 0


def _stack_dump(exclude_ident) -> list:
    frames = sys._current_frames()
    names = {}
    for thread in threading.enumerate():
        names[thread.ident] = thread.name
    out = ["threads   : %d" % len(frames)]
    emitted = 0
    for ident, frame in frames.items():
        if ident == exclude_ident:
            continue
        if emitted >= MAX_THREADS:
            out.append("threads   : ...（已达 %d 个线程上限）" % MAX_THREADS)
            break
        emitted += 1
        stack = traceback.format_stack(frame, limit=20)
        text = "".join(stack)
        hot = any(k in text for k in ("sqlalchemy", "pysqlite", "sqlite3"))
        out.append("--- %s (ident=%s)%s" % (
            names.get(ident, "?"), ident, "  <== 疑似卡在 SQL 上" if hot else "",
        ))
        for line in stack:
            if len(out) > MAX_STACK_LINES:
                out.append("    ...（栈输出已达 %d 行上限）" % MAX_STACK_LINES)
                return out
            out.append("    " + line.rstrip("\n"))
    return out


def _proc_holders(db_path) -> list:
    """谁还打开着这个库。同进程的连接也会列出来（标 self），便于区分第二实例。"""
    if not db_path or not os.path.isdir("/proc"):
        return ["holders   : /proc 不可用，跳过"]
    targets = set()
    for suffix in ("", "-wal", "-shm"):
        targets.add(os.path.realpath(db_path + suffix))

    self_pid = str(os.getpid())
    out = []
    scanned = 0
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        fd_dir = "/proc/%s/fd" % pid
        try:
            fds = os.listdir(fd_dir)
        except OSError:
            continue
        for fd in fds:
            scanned += 1
            if scanned > 20000:
                break
            try:
                link = os.readlink(os.path.join(fd_dir, fd))
            except OSError:
                continue
            if not link or not link.startswith("/"):
                continue
            try:
                real = os.path.realpath(link)
            except OSError:
                continue
            if real in targets:
                out.append("holders   : pid=%s%s comm=%s fd=%s -> %s" % (
                    pid, " (self)" if pid == self_pid else "", _comm(pid), fd, link,
                ))
                break
    if not out:
        out.append("holders   : 没有进程打开该库（连接可能已关闭）")
    return out


def _comm(pid) -> str:
    try:
        with open("/proc/%s/comm" % pid, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read().strip()
    except OSError:
        return "?"
