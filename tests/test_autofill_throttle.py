"""autofill 限流暂停+定时续跑回归测试（C1，配合 douban v2 内置 RequestCounter）。

覆盖：RequestCounter 窗口/突发后果的剩余秒数（假时钟精确断言）/
DoubanV2.throttle_wait_seconds / BookSearch.throttle_wait_seconds 只聚合启用源 /
auto_fill_all 事后暂停→预算恢复→重试→完成 / 暂停开关关闭走旧静默路径 /
暂停上限中止不虚计 / qpm 读 CONF（精确节拍）。
Windows 直跑（无 calibre 依赖）。
"""
import time
import unittest
from unittest import mock

from webserver import loader
from webserver.base import request_counter as request_counter_module
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
    def test_fresh_counter_budget_available_is_zero(self):
        counter = RequestCounter(180)
        self.assertFalse(counter.is_exceeded())
        self.assertEqual(counter.seconds_until_budget_available(), 0)
        remain = counter.seconds_until_window_end()
        self.assertGreaterEqual(remain, 0)
        self.assertLessEqual(remain, 60)

    def test_exact_waits_with_fake_clock(self):
        # 假 monotonic 控钟：精确断言向上取整，恒返满窗/错窗的实现跑不过本用例。
        fake = {"t": 1000.0}
        with mock.patch.object(request_counter_module.time, "monotonic", side_effect=lambda: fake["t"]):
            counter = RequestCounter(180)  # 60s 窗口，limit 3
            fake["t"] = 1030.7
            for _ in range(6):  # 突发 6 次 → 超限
                counter.record()
            self.assertTrue(counter.is_exceeded())
            # 本窗剩 29.3s：窗口尾 30；突发耗尽后下一窗整体拒绝 → 30+60=90
            self.assertEqual(counter.seconds_until_window_end(), 30)
            self.assertEqual(counter.seconds_until_budget_available(), 90)
            # 跨过窗口边界：进入被拒窗（_blocked）→ 只等本窗剩余（60）
            fake["t"] = 1060.05
            self.assertTrue(counter.is_exceeded())
            self.assertEqual(counter.seconds_until_window_end(), 60)
            self.assertEqual(counter.seconds_until_budget_available(), 60)
            # 被拒窗结束 → 预算恢复
            fake["t"] = 1120.01
            self.assertFalse(counter.is_exceeded())
            self.assertEqual(counter.seconds_until_budget_available(), 0)


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

    def _run(self, idlist, search_side_effect, throttle_side_effect=None, throttle_signal=None, extra_patches=None):
        svc = AutoFillService()
        svc.db = FakeDB()
        svc.task_id = 1
        mock_bg = mock.MagicMock()
        throttle_patch = mock.patch.object(
            autofill_module.BookSearch, "throttle_wait_seconds",
            side_effect=throttle_signal if throttle_signal is not None else throttle_side_effect,
        )
        patches = [
            mock.patch.object(autofill_module.AsyncService, "async_mode", lambda self: False),
            # register_service 包装器每次调用会 ins.setup(基类单例的占位 scoped_session)
            # → self.session 变成占位字符串；本服务路径不用 session，直接 no-op 掉。
            mock.patch.object(AutoFillService, "setup", lambda self, *a, **k: None),
            mock.patch.object(autofill_module, "BackgroundService", mock_bg),
            mock.patch.object(autofill_module.BookSearch, "search_best_book", side_effect=search_side_effect),
            mock.patch.object(AutoFillService, "plugin_search_book_tag", return_value=None),
            throttle_patch,
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

    def test_pause_then_retry_completes_all(self):
        # 第 1 本首取落空且预算耗尽 → 暂停真实等待 1s（切片睡眠，elapsed 断言
        # 钉住"必须真等"）→ 第 3 次检查起预算恢复 → 重试成功；第 2 本直接成功。
        # 两本全部完成，暂停轮数在恢复后清零（间歇性限流不累计触发保险丝）。
        start = time.time()
        state = {"checks": 0}

        def throttle_signal():
            state["checks"] += 1
            # 事前判定 + 暂停首轮复查超限，之后恢复
            return 1 if state["checks"] <= 2 else None

        search_results = [None, FakeBookMeta(), FakeBookMeta()]
        svc, mock_bg = self._run([1, 2], search_side_effect=search_results, throttle_signal=throttle_signal)
        self.assertEqual(svc.count_done, 2)
        self.assertGreaterEqual(time.time() - start, 0.8)  # 暂停路径真实等待过
        self.assertEqual(svc._throttle_pause_rounds, 0)  # 恢复后清零
        self.assertEqual(state["checks"], 3)  # 事前判定 1 次 + 暂停循环 2 次
        paused_calls = self._paused_calls(mock_bg)
        self.assertEqual(len(paused_calls), 1)
        data = paused_calls[0].kwargs["progress_data"]
        self.assertEqual(data["pause_reason"], "douban_v2_rate_limit")
        # resume_at = 暂停决策时刻 + 1s 等待（既不远未来也不过去）
        self.assertGreaterEqual(data["resume_at"], start + 0.5)
        self.assertLessEqual(data["resume_at"], start + 3)
        restored = [
            c for c in mock_bg.return_value.update_progress.call_args_list
            if (c.kwargs.get("progress_data") or {}).get("stage") == "importing"
        ]
        self.assertTrue(restored)
        mock_bg.return_value.complete_task.assert_called_once()

    def test_healthy_fetch_never_pauses(self):
        # 事后暂停语义：所有书都取到元数据（后备源健康）→ 限流信号一次都不查，
        # 零暂停零重试（douban v2 根本没被请求）。
        throttle_mock = mock.MagicMock(return_value=1)
        search_results = [FakeBookMeta(), FakeBookMeta()]
        svc, mock_bg = self._run([1, 2], search_side_effect=search_results, throttle_side_effect=throttle_mock)
        self.assertEqual(svc.count_done, 2)
        throttle_mock.assert_not_called()
        self.assertEqual(self._paused_calls(mock_bg), [])

    def test_pause_disabled_keeps_legacy_skip(self):
        # 开关关闭：落空也不检查限流（插件层静默跳过的旧行为），无暂停无重试。
        CONF["auto_fill_pause_on_throttle"] = False
        throttle_mock = mock.MagicMock(return_value=1)
        search_results = [None, FakeBookMeta()]  # 落空后不再重试
        svc, mock_bg = self._run([1, 2], search_side_effect=search_results, throttle_side_effect=throttle_mock)
        self.assertEqual(svc.count_done, 1)
        self.assertEqual(svc.count_fail, 1)
        throttle_mock.assert_not_called()
        self.assertEqual(self._paused_calls(mock_bg), [])

    def test_pause_cap_aborts_without_phantom_count(self):
        # 单次等待超上限（上限 patch 成 0.02s、等待恒 61s）：立即中止本轮，
        # 被中止的书不虚计 done/fail，任务照常 complete 收尾。
        svc, mock_bg = self._run(
            [1, 2, 3],
            search_side_effect=[None],
            throttle_side_effect=[61] * 10,
            extra_patches=[mock.patch.object(autofill_module, "PAUSE_MAX_SECONDS", 0.02)],
        )
        self.assertEqual(svc.count_done, 0)
        self.assertEqual(svc.count_fail, 0)
        mock_bg.return_value.complete_task.assert_called_once()

    def test_qpm_from_conf(self):
        # qpm 未显式给定时读 CONF auto_fill_qpm：600 → 每本恰 0.1s 间隔
        # （delta 收紧：把 0.1 算成 0.2 的实现跑不过）。
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
            mock.patch.object(autofill_module.BookSearch, "throttle_wait_seconds", return_value=None),
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
        self.assertAlmostEqual(max(sleeps), 0.1, delta=0.001)


if __name__ == "__main__":
    unittest.main()
