"""SQLite 写锁诊断日志（webserver/base/db_diagnosis.py）回归测试。

覆盖：锁错误识别 / 锁被他人持有时探针报 FAILED / 锁空闲时探针能拿到
BEGIN IMMEDIATE 并回滚 / 诊断过程本身不抛异常、不改数据。
"""
import os
import sqlite3
import tempfile
import unittest

from sqlalchemy import create_engine, event, text

from webserver.base import db_diagnosis


class DbDiagTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "diag.db")
        conn = sqlite3.connect(self.db_path, isolation_level=None)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("CREATE TABLE scanfiles (id INTEGER PRIMARY KEY, name TEXT)")
        conn.close()

        # 缩短采样窗口，让用例保持秒级
        self._old_window, self._old_step = db_diagnosis.SAMPLE_WINDOW_S, db_diagnosis.SAMPLE_STEP_S
        db_diagnosis.SAMPLE_WINDOW_S, db_diagnosis.SAMPLE_STEP_S = 0.3, 0.1
        db_diagnosis._last_dump_at = 0.0

        self.engine = create_engine("sqlite:///" + self.db_path)

        @event.listens_for(self.engine, "connect")
        def _pragma(dbapi_conn, record):
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA busy_timeout=300")
            cur.close()

    def tearDown(self):
        db_diagnosis.SAMPLE_WINDOW_S, db_diagnosis.SAMPLE_STEP_S = self._old_window, self._old_step
        self.engine.dispose()

    def _dump(self):
        with self.assertLogs(level="ERROR") as captured:
            db_diagnosis._dump(self.engine, "TestThread", "INSERT INTO scanfiles (name) VALUES ('x')", "()", 30.0)
        return "\n".join(captured.output)

    def test_is_lock_error(self):
        self.assertTrue(db_diagnosis._is_lock_error(sqlite3.OperationalError("database is locked")))
        self.assertTrue(db_diagnosis._is_lock_error(Exception("(sqlite3.OperationalError) database is locked")))
        self.assertFalse(db_diagnosis._is_lock_error(sqlite3.OperationalError("no such table: foo")))
        self.assertFalse(db_diagnosis._is_lock_error(None))

    def test_probe_reports_holder(self):
        holder = sqlite3.connect(self.db_path, isolation_level=None, check_same_thread=False)
        holder.execute("BEGIN IMMEDIATE")
        holder.execute("INSERT INTO scanfiles (name) VALUES ('held')")
        try:
            output = self._dump()
        finally:
            holder.execute("ROLLBACK")
            holder.close()

        self.assertIn("[DB-LOCK] database is locked", output)
        self.assertIn("write_lock: FAILED", output)
        self.assertIn("journal   : wal", output)
        self.assertIn("waited    : 30.000s", output)
        self.assertIn("files     : -wal", output)

    def test_probe_reports_writer_free_and_does_not_write(self):
        output = self._dump()
        self.assertIn("write_lock: ACQUIRED", output)

        # 探针必须回滚，不能留下任何数据
        check = sqlite3.connect(self.db_path)
        try:
            count = check.execute("SELECT COUNT(*) FROM scanfiles").fetchone()[0]
        finally:
            check.close()
        self.assertEqual(count, 0)

    def test_failed_write_still_raises_original_error(self):
        """诊断钩子不能吞掉异常：调用方还要按原有逻辑回滚。"""
        db_diagnosis.install(self.engine)   # 幂等性无关，此处只验证不会二次抛错
        holder = sqlite3.connect(self.db_path, isolation_level=None, check_same_thread=False)
        holder.execute("BEGIN IMMEDIATE")
        holder.execute("INSERT INTO scanfiles (name) VALUES ('held')")
        try:
            with self.assertRaises(Exception):
                with self.engine.begin() as conn:
                    conn.execute(text("INSERT INTO scanfiles (name) VALUES ('x')"))
        finally:
            holder.execute("ROLLBACK")
            holder.close()
        # 等后台诊断线程打完，避免 tearDown 时日志句柄已关闭
        import time
        time.sleep(1.0)


if __name__ == "__main__":
    unittest.main()
