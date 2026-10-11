"""autofill 限流暂停+定时续跑回归测试（C1，配合 douban v2 内置 RequestCounter）。

覆盖：RequestCounter 窗口剩余秒数 / DoubanV2.throttle_wait_seconds /
BookSearch.throttle_wait_seconds 只聚合启用源 / auto_fill_all 暂停→恢复→完成 /
暂停开关关闭走旧静默路径 / 暂停上限中止 / qpm 读 CONF。
Windows 直跑（无 calibre 依赖）。
"""
import time
import unittest
from unittest import mock

from webserver import loader
from webserver.base.request_counter import RequestCounter
from webserver.plugins.meta.douban_v2 import DoubanV2MetaPlugin
from webserver.services import autofill as autofill_module
from webserver.services.autofill import AutoFillService
from webserver.services.book_search import BookSearch

CONF = loader.get_settings()


class FakeBookMeta:
    def __init__(self):
        self.title = "t"
        self.authors = ["a"]
        self.author_sort = "a"
        self.publisher = ""
        self.tags = []
        self.comments = None
        self.cover_data = (None, None)
        self.isbn = ""
        self.languages = []
        self.title_sort = ""

    def smart_update(self, other, replace_metadata=False):
        for attr in ("title", "authors", "publisher", "tags", "comments", "isbn", "languages", "title_sort"):
            value = getattr(other, attr, None)
            if value:
                setattr(self, attr, value)


class FakeDB:
    def __init__(self):
        self.set_meta_calls = []

    def get_metadata(self, book_id, index_is_id=True):
        return FakeBookMeta()

    def set_metadata(self, book_id, mi, ignore_errors=True):
        self.set_meta_calls.append(book_id)
        return True


def _exhausted_counter():
    counter = RequestCounter(180)  # 1 分钟窗口，limit 3，突发 2 倍=6
    for _ in range(6):
        counter.record()
    return counter


class RequestCounterWindowTest(unittest.TestCase):
    def test_seconds_until_window_end_fresh_counter(self):
        counter = RequestCounter(180)
        self.assertFalse(counter.is_exceeded())
        remain = counter.seconds_until_window_end()
        self.assertGreaterEqual(remain, 0)
        self.assertLessEqual(remain, 60)

    def test_seconds_until_window_end_after_exhaust(self):
        counter = _exhausted_counter()
        self.assertTrue(counter.is_exceeded())
        remain = counter.seconds_until_window_end()
        self.assertGreater(remain, 0)
        self.assertLessEqual(remain, 60)


class ThrottleSignalTest(unittest.TestCase):
    def test_douban_v2_wait_none_when_fresh(self):
        with mock.patch.object(DoubanV2MetaPlugin, "_counter", RequestCounter(180)):
            self.assertIsNone(DoubanV2MetaPlugin.throttle_wait_seconds())

    def test_douban_v2_wait_positive_when_exhausted(self):
        with mock.patch.object(DoubanV2MetaPlugin, "_counter", _exhausted_counter()):
            self.assertGreater(DoubanV2MetaPlugin.throttle_wait_seconds(), 0)

    def test_booksearch_aggregates_enabled_sources_only(self):
        # 预算耗尽 + 源启用 → 返回等待；同一计数器下源未启用 → None（没请求谈不上超限）。
        counter = _exhausted_counter()
        with mock.patch.object(DoubanV2MetaPlugin, "_counter", counter):
            with mock.patch.dict(CONF, {"META_SELECTED_SOURCES": ["douban_v2"]}):
                self.assertGreater(BookSearch.throttle_wait_seconds(), 0)
            with mock.patch.dict(CONF, {"META_SELECTED_SOURCES": ["douban"]}):
                self.assertIsNone(BookSearch.throttle_wait_seconds())


class AutoFillPauseFlowTest(unittest.TestCase):
    def setUp(self):
        self._conf_backup = dict(CONF)
        CONF["auto_fill_meta"] = True
        CONF["auto_fill_qpm"] = 600
        CONF["auto_fill_pause_on_throttle"] = True

    def tearDown(self):
        CONF.clear()
        CONF.update(self._conf_backup)

    def _run(self, idlist, throttle_side_effect, extra_patches=None):
        svc = AutoFillService()
        svc.db = FakeDB()
        svc.task_id = 1
        mock_bg = mock.MagicMock()
        patches = [
            mock.patch.object(autofill_module.AsyncService, "async_mode", lambda self: False),
            # register_service 包装器每次调用会 ins.setup(基类单例的占位 scoped_session)
            # → self.session 变成占位字符串；本服务路径不用 session，直接 no-op 掉。
            mock.patch.object(AutoFillService, "setup", lambda self, *a, **k: None),
            mock.patch.object(autofill_module, "BackgroundService", mock_bg),
            mock.patch.object(autofill_module.BookSearch, "search_best_book", return_value=FakeBookMeta()),
            mock.patch.object(AutoFillService, "plugin_search_book_tag", return_value=None),
            mock.patch.object(autofill_module.BookSearch, "throttle_wait_seconds", side_effect=throttle_side_effect),
            mock.patch.object(autofill_module, "PAUSE_SLICE_SECONDS", 0.05),
        ]
        if extra_patches:
            patches.extend(extra_patches)
        for patcher in patches:
            patcher.start()
        try:
            svc.auto_fill_all(idlist)
        finally:
            for patcher in patches:
                patcher.stop()
        return svc, mock_bg

    def _paused_calls(self, mock_bg):
        return [
            c for c in mock_bg.return_value.update_progress.call_args_list
            if (c.kwargs.get("progress_data") or {}).get("stage") == "paused"
        ]

    def test_pause_then_resume_completes_all(self):
        # 第 1 本前预算耗尽（等待 1s，切片 0.05s）→ 指示器 stage=paused + resume_at，
        # 预算恢复后自动续跑；第 2 本无暂停。两本全部完成。
        svc, mock_bg = self._run([1, 2], throttle_side_effect=[1, None, None])
        self.assertEqual(svc.count_done, 2)
        paused_calls = self._paused_calls(mock_bg)
        self.assertEqual(len(paused_calls), 1)
        data = paused_calls[0].kwargs["progress_data"]
        self.assertEqual(data["pause_reason"], "douban_v2_rate_limit")
        self.assertGreaterEqual(data["resume_at"], int(time.time()) - 60)
        restored = [
            c for c in mock_bg.return_value.update_progress.call_args_list
            if (c.kwargs.get("progress_data") or {}).get("stage") == "importing"
        ]
        self.assertTrue(restored)
        mock_bg.return_value.complete_task.assert_called_once()

    def test_pause_disabled_keeps_legacy_skip(self):
        # 开关关闭：预算耗尽也不暂停（插件层静默跳过的旧行为），无 paused 上报。
        CONF["auto_fill_pause_on_throttle"] = False
        svc, mock_bg = self._run([1], throttle_side_effect=[1] * 10)
        self.assertEqual(svc.count_done, 1)
        self.assertEqual(self._paused_calls(mock_bg), [])

    def test_pause_cap_aborts_remaining(self):
        # 单次等待超上限（此处把上限 patch 成 0.02s、等待恒 61s）：立即中止本轮，
        # 已完成保留，任务照常 complete 收尾（剩余书目下轮重扫或手动触发）。
        svc, mock_bg = self._run(
            [1, 2, 3],
            throttle_side_effect=[61] * 10,
            extra_patches=[mock.patch.object(autofill_module, "PAUSE_MAX_SECONDS", 0.02)],
        )
        self.assertEqual(svc.count_done, 0)
        mock_bg.return_value.complete_task.assert_called_once()

    def test_qpm_from_conf(self):
        # qpm 未显式给定时读 CONF auto_fill_qpm：600 → 每本 0.1s 间隔。
        CONF["auto_fill_qpm"] = 600
        sleeps = []
        svc = AutoFillService()
        svc.db = FakeDB()
        svc.task_id = 1
        patchers = [
            mock.patch.object(autofill_module.AsyncService, "async_mode", lambda self: False),
            mock.patch.object(AutoFillService, "setup", lambda self, *a, **k: None),
            mock.patch.object(autofill_module, "BackgroundService"),
            mock.patch.object(autofill_module.BookSearch, "search_best_book", return_value=FakeBookMeta()),
            mock.patch.object(AutoFillService, "plugin_search_book_tag", return_value=None),
            mock.patch.object(autofill_module.BookSearch, "throttle_wait_seconds", side_effect=[None] * 10),
            mock.patch.object(autofill_module.time, "sleep", side_effect=sleeps.append),
        ]
        for patcher in patchers:
            patcher.start()
        try:
            svc.auto_fill_all([1])
        finally:
            for patcher in patchers:
                patcher.stop()
        self.assertEqual(svc.count_done, 1)
        self.assertTrue(sleeps)
        self.assertLessEqual(max(sleeps), 0.2)


if __name__ == "__main__":
    unittest.main()
