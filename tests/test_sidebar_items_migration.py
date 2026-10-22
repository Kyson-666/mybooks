#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""SIDEBAR_ITEMS 的升级期归一化：旧默认列表不能把新增的三个导航项永久藏掉。

背景见 webserver/base/sidebar.py 的模块说明：v4.6.0 及更早，admin.py 在值为空时写入的
默认列表没有 authors / friends / booklists（那三项是后来才成为合法取值的）。凡是打开过
设置页的站点，那份旧列表都已持久化进 auto.py，升级后「值为空」不再成立，前端 showItem
就会把三项判成「管理员取消勾选」。这里断言归一化只发生在读取期：下发值被补齐，用户存的
配置一个字都不动，真·自定义子集原样保留。
"""

import asyncio
import datetime
import unittest
from unittest import mock

from webserver.base import sidebar as sidebar_module
from webserver.base.sidebar import (
    SIDEBAR_DEFAULT_ITEMS,
    SIDEBAR_ITEMS_MIGRATED_KEY,
    SIDEBAR_LEGACY_DEFAULTS,
    normalize_sidebar_items,
)

# v4.6.0 及此前 admin.py 空值时写入的旧默认列表（10 项）
LEGACY_ITEMS = [
    "audiobooks",
    "printbooks",
    "publishers",
    "folders",
    "tags",
    "series",
    "languages",
    "rating",
    "memo",
    "categories",
]
# 更早一代（「微调目录功能」之前）还不带 categories
LEGACY_ITEMS_WITHOUT_CATEGORIES = LEGACY_ITEMS[:-1]

NEW_KEYS = ("authors", "friends", "booklists")


class TestNormalizeSidebarItems(unittest.TestCase):
    def test_legacy_default_is_served_as_new_default(self):
        """旧默认列表 → 补齐 authors/friends/booklists，等于当前默认列表。"""
        served = normalize_sidebar_items(LEGACY_ITEMS)
        self.assertEqual(list(SIDEBAR_DEFAULT_ITEMS), served)
        for key in NEW_KEYS:
            self.assertIn(key, served)

    def test_legacy_default_in_shuffled_order_is_still_migrated(self):
        """集合相同即认定陈旧（保存顺序可能因历史版本而异）。"""
        shuffled = list(reversed(LEGACY_ITEMS))
        self.assertEqual(list(SIDEBAR_DEFAULT_ITEMS), normalize_sidebar_items(shuffled))

    def test_all_legacy_shapes_are_migrated(self):
        """历史上写过的每一代旧默认都要认，不能只认最新那一代。"""
        self.assertEqual(2, len(SIDEBAR_LEGACY_DEFAULTS))
        for legacy in SIDEBAR_LEGACY_DEFAULTS:
            served = normalize_sidebar_items(list(legacy))
            self.assertEqual(list(SIDEBAR_DEFAULT_ITEMS), served, legacy)
            self.assertIn("categories", served, legacy)

    def test_custom_subset_is_returned_unchanged(self):
        """集合不等的列表是真·用户意图，必须原样返回（含顺序）。"""
        cases = (["tags", "series"], ["rating"], LEGACY_ITEMS[:5], ["series", "tags"], ["folders", "memo", "tags", "series", "languages", "rating", "memo", "categories"])
        for stored in cases:
            self.assertEqual(stored, normalize_sidebar_items(stored), stored)

    def test_custom_subset_with_a_new_key_is_untouched(self):
        """用户已经手动加过一项新键（集合与旧默认不等）→ 不改写。"""
        stored = ["tags", "series", "authors"]
        self.assertEqual(stored, normalize_sidebar_items(stored))

    def test_empty_list_means_show_all_and_is_unchanged(self):
        self.assertEqual([], normalize_sidebar_items([]))

    def test_none_sentinel_is_unchanged(self):
        """「全部隐藏」哨兵必须原样下发；旧默认列表非空，永不与之冲突。"""
        self.assertEqual(["none"], normalize_sidebar_items(["none"]))

    def test_current_default_is_idempotent(self):
        served = normalize_sidebar_items(list(SIDEBAR_DEFAULT_ITEMS))
        self.assertEqual(list(SIDEBAR_DEFAULT_ITEMS), served)

    def test_non_list_falls_back_to_show_all(self):
        """auto.py 被手改成字符串/dict/None 时沿用「空表示全部显示」，不抛异常。"""
        for raw in ("oops", {"a": 1}, None, 42):
            self.assertEqual([], normalize_sidebar_items(raw))

    def test_normalization_never_mutates_the_stored_list(self):
        """只读：归一化后用户存的列表内容与顺序都不变。"""
        stored = list(LEGACY_ITEMS)
        normalize_sidebar_items(stored)
        self.assertEqual(LEGACY_ITEMS, stored)
        served = normalize_sidebar_items(stored)
        served.append("hacked")
        self.assertEqual(LEGACY_ITEMS, stored)

    def test_get_sidebar_items_reads_settings_without_writing(self):
        settings = {"SIDEBAR_ITEMS": list(LEGACY_ITEMS)}
        served = sidebar_module.get_sidebar_items(settings)
        self.assertEqual(list(SIDEBAR_DEFAULT_ITEMS), served)
        self.assertEqual(LEGACY_ITEMS, settings["SIDEBAR_ITEMS"])

    def test_get_sidebar_items_falls_back_to_loader_settings(self):
        with mock.patch("webserver.loader.get_settings", return_value={"SIDEBAR_ITEMS": ["none"]}):
            self.assertEqual(["none"], sidebar_module.get_sidebar_items())

    def test_marker_absent_defaults_to_unmigrated_and_repairs(self):
        """settings 没有标记键时按未迁移处理：仍补齐陈旧默认。"""
        served = sidebar_module.get_sidebar_items({"SIDEBAR_ITEMS": list(LEGACY_ITEMS)})
        self.assertEqual(list(SIDEBAR_DEFAULT_ITEMS), served)


class TestSidebarMigrationMarkerUnit(unittest.TestCase):
    """标记 SIDEBAR_ITEMS_MIGRATED 的读取语义：为真后 stored 列表即权威，不再补齐。

    今天坏掉的正是「标记为真 + stored 恰等于旧默认集合」这一格——管理员有意关掉
    作者/友情链接/阅读书单全部三项，存的正好是那 10 项旧默认集合，若继续补齐会被
    还原成 13 项、三项永久无法隐藏。
    """

    def serve(self, stored, migrated):
        settings = {
            "SIDEBAR_ITEMS": list(stored),
            SIDEBAR_ITEMS_MIGRATED_KEY: migrated,
        }
        return sidebar_module.get_sidebar_items(settings)

    def test_marker_false_repairs_legacy_default(self):
        served = self.serve(LEGACY_ITEMS, False)
        self.assertEqual(list(SIDEBAR_DEFAULT_ITEMS), served)
        for key in NEW_KEYS:
            self.assertIn(key, served)

    def test_marker_true_returns_legacy_stored_unchanged(self):
        """标记为真 + stored 恰为旧默认集合 → 原样返回，三项保持隐藏。"""
        served = self.serve(LEGACY_ITEMS, True)
        self.assertEqual(list(LEGACY_ITEMS), served)
        for key in NEW_KEYS:
            self.assertNotIn(key, served)

    def test_marker_true_never_mutates_stored(self):
        """标记为真的分支同样只读，返回的是副本，用户存的列表一个字都不动。"""
        stored = list(LEGACY_ITEMS)
        served = self.serve(stored, True)
        served.append("hacked")
        self.assertEqual(list(LEGACY_ITEMS), stored)

    def test_marker_true_keeps_empty_sentinel_and_custom(self):
        self.assertEqual([], self.serve([], True))
        self.assertEqual(["none"], self.serve(["none"], True))
        self.assertEqual(["tags", "series"], self.serve(["tags", "series"], True))

    def test_normalize_sidebar_items_stays_pure(self):
        """门控只发生在 get_sidebar_items；normalize 本身不认标记，仍按旧默认补齐。"""
        self.assertEqual(list(SIDEBAR_DEFAULT_ITEMS), normalize_sidebar_items(list(LEGACY_ITEMS)))


class TestSidebarItemsServedToInfo(unittest.TestCase):
    """下发路径断言：/user/info 的 sys.sidebar_items 与设置页读到的必须是同一份归一化。"""

    def setUp(self):
        from webserver.handlers.base import BaseHandler

        BaseHandler._stats_cache.clear()
        handler = object.__new__(BaseHandler)
        handler.library_version = mock.Mock(return_value=(1, 0))
        handler.calibre_db = mock.Mock()
        handler.calibre_db.count.return_value = 5
        handler.calibre_db.all_tags.return_value = ["a", "b"]
        handler.calibre_db.all_authors.return_value = ["x"]
        handler.calibre_db.all_publishers.return_value = []
        handler.calibre_db.all_series.return_value = []
        handler.calibre_db.last_modified.return_value = datetime.datetime(2026, 1, 2)
        handler.get_audio_books_count = mock.Mock(return_value=1)
        handler.get_custom_category_count = mock.Mock(return_value=2)
        handler.get_folder_count = mock.Mock(return_value=3)
        handler.get_physical_books_count = mock.Mock(return_value=4)
        handler._build_friends_with_favicon = mock.Mock(return_value=[])
        handler.need_invited = mock.Mock(return_value=False)
        handler.sqlite_session = mock.Mock()
        handler.sqlite_session.query.return_value.scalar.return_value = 7
        handler.sqlite_session.query.return_value.filter.return_value.scalar.return_value = 3

        async def run_calibre_read(func, *a, **kw):
            return func(*a, **kw)

        handler.run_calibre_read_async = run_calibre_read
        handler.run_calibre_async = run_calibre_read
        self.handler = handler

    def served(self, stored):
        from webserver.handlers import base as base_module

        with mock.patch.dict(base_module.CONF, {"SIDEBAR_ITEMS": stored}):
            sync_info = self.handler.get_sys_info()
            async_info = asyncio.run(self.handler.get_sys_info_async())
        self.assertEqual(sync_info["sidebar_items"], async_info["sidebar_items"])
        return sync_info["sidebar_items"]

    def test_sync_and_async_both_serve_the_migrated_list(self):
        served = self.served(list(LEGACY_ITEMS))
        self.assertEqual(list(SIDEBAR_DEFAULT_ITEMS), served)
        for key in NEW_KEYS:
            self.assertIn(key, served)

    def test_sync_and_async_keep_custom_subset_untouched(self):
        self.assertEqual(["tags", "series"], self.served(["tags", "series"]))

    def test_sync_and_async_keep_sentinel_and_empty(self):
        self.assertEqual(["none"], self.served(["none"]))
        self.assertEqual([], self.served([]))

    def test_sync_and_async_with_marker_hide_all_three(self):
        """标记为真：/user/info 下发以 stored 为权威，旧默认集合原样返回、三项仍隐藏。"""
        from webserver.handlers import base as base_module

        with mock.patch.dict(base_module.CONF, {
            "SIDEBAR_ITEMS": list(LEGACY_ITEMS),
            SIDEBAR_ITEMS_MIGRATED_KEY: True,
        }):
            sync_info = self.handler.get_sys_info()
            async_info = asyncio.run(self.handler.get_sys_info_async())
        self.assertEqual(sync_info["sidebar_items"], async_info["sidebar_items"])
        self.assertEqual(list(LEGACY_ITEMS), sync_info["sidebar_items"])
        for key in NEW_KEYS:
            self.assertNotIn(key, sync_info["sidebar_items"])


class TestAdminSettingsPageRead(unittest.TestCase):
    """设置页 GET 必须看到补齐后的列表，否则管理员保存任意设置就把陈旧缺项固化下来。"""

    def load(self, stored, migrated=False):
        """打开设置页，返回（页面看到的列表, 读完后 CONF 里仍存的列表）。"""
        from webserver.handlers import admin as admin_module
        from webserver.handlers.admin import AdminSettings

        class FakeHandler:
            def __init__(self):
                self.current_user = object()
                self.admin_user = True
                self.site_url = ""
                self.request = mock.Mock()
                self.request.headers = {}
                self.written = None

            def set_header(self, *args, **kwargs):
                pass

            def write(self, rsp):
                self.written = rsp

            def finish(self):
                pass

        handler = FakeHandler()
        saved = dict(admin_module.CONF)
        admin_module.CONF["SIDEBAR_ITEMS"] = stored
        admin_module.CONF[SIDEBAR_ITEMS_MIGRATED_KEY] = migrated
        try:
            with mock.patch.object(admin_module.BookSearch, "all_sources", return_value=[]):
                asyncio.run(AdminSettings.get(handler))
            return handler.written["settings"]["SIDEBAR_ITEMS"], admin_module.CONF["SIDEBAR_ITEMS"]
        finally:
            admin_module.CONF.clear()
            admin_module.CONF.update(saved)

    def test_legacy_default_is_shown_migrated(self):
        shown, stored = self.load(list(LEGACY_ITEMS))
        self.assertEqual(list(SIDEBAR_DEFAULT_ITEMS), shown)
        # 读取期归一化不得改写用户存的配置（更不写盘）
        self.assertEqual(LEGACY_ITEMS, stored)

    def test_custom_subset_is_shown_unchanged(self):
        shown, stored = self.load(["tags", "series"])
        self.assertEqual(["tags", "series"], shown)
        self.assertEqual(["tags", "series"], stored)

    def test_empty_value_still_gets_the_default_written(self):
        """空值走 admin.py 原有的「空即写默认」分支，本 PR 不改它的语义。"""
        shown, stored = self.load([])
        self.assertEqual(list(SIDEBAR_DEFAULT_ITEMS), shown)
        self.assertEqual(list(SIDEBAR_DEFAULT_ITEMS), stored)

    def test_sentinel_is_shown_unchanged(self):
        shown, stored = self.load(["none"])
        self.assertEqual(["none"], shown)
        self.assertEqual(["none"], stored)

    def test_marker_true_shows_stored_authoritatively(self):
        """标记为真：设置页必须显示 stored 原样，否则管理员再次保存会把三项藏掉的意图洗掉。"""
        shown, stored = self.load(list(LEGACY_ITEMS), migrated=True)
        self.assertEqual(list(LEGACY_ITEMS), shown)
        self.assertEqual(list(LEGACY_ITEMS), stored)
        for key in NEW_KEYS:
            self.assertNotIn(key, shown)


class TestAdminSaveSetsAndPersistsMarker(unittest.TestCase):
    """保存设置页 = 无条件置迁移标记并落盘；之后 stored 列表以权威返回，三项能真正藏住。"""

    class PostHandler:
        """只提供 AdminSettings.post 与 @js/@auth 需要的属性/方法。"""

        def __init__(self, payload):
            import json
            self.current_user = object()
            self.admin_user = True
            self.request = mock.Mock()
            self.request.body = json.dumps(payload).encode("utf-8")
            self.request.headers = {}
            self.written = None

        def set_header(self, *args, **kwargs):
            pass

        def write(self, rsp):
            self.written = rsp

        def finish(self):
            pass

    def post(self, payload):
        from webserver.handlers import admin as admin_module
        from webserver.handlers.admin import AdminSettings

        captured = {}

        def fake_save(self, args):
            # args 即 SettingsSaver.save_extra_settings 内 dumpfile() 落盘的对象，
            # 捕获它 == 断言会写进 auto.py 的最终内容。
            captured.update(args)
            return {"err": "ok", "rsp": dict(args)}

        handler = self.PostHandler(payload)
        with mock.patch.object(admin_module.SettingsSaver, "save_extra_settings", fake_save):
            asyncio.run(AdminSettings.post(handler))
        return handler.written, captured

    def test_first_save_marks_and_persists_marker(self):
        _, captured = self.post({"SIDEBAR_ITEMS": list(LEGACY_ITEMS)})
        self.assertIs(True, captured[SIDEBAR_ITEMS_MIGRATED_KEY])
        self.assertEqual(list(LEGACY_ITEMS), captured["SIDEBAR_ITEMS"])

    def test_hiding_all_three_survives_save_then_read(self):
        """完整 save→read：取消勾选全部三项并保存后，下发值仍是这 10 项、三项保持隐藏。"""
        _, captured = self.post({"SIDEBAR_ITEMS": list(LEGACY_ITEMS)})
        served = sidebar_module.get_sidebar_items({
            "SIDEBAR_ITEMS": captured["SIDEBAR_ITEMS"],
            SIDEBAR_ITEMS_MIGRATED_KEY: captured[SIDEBAR_ITEMS_MIGRATED_KEY],
        })
        self.assertEqual(list(LEGACY_ITEMS), served)
        for key in NEW_KEYS:
            self.assertNotIn(key, served)

    def test_marker_true_survives_second_unrelated_save(self):
        """第二次保存只动别的字段：服务端仍重申标记为真，SIDEBAR_ITEMS 不被重新补齐。"""
        _, captured = self.post({
            "site_title": "新标题",
            "SIDEBAR_ITEMS": list(LEGACY_ITEMS),
            # 前端 payload 不可能带这个键（无 UI 控件），这里即便误传真意之外的假值，
            # 服务端也必须覆盖回真——证明它不会被一次普通保存意外抹回假。
            SIDEBAR_ITEMS_MIGRATED_KEY: False,
        })
        self.assertIs(True, captured[SIDEBAR_ITEMS_MIGRATED_KEY])
        self.assertEqual("新标题", captured["site_title"])
        self.assertEqual(list(LEGACY_ITEMS), captured["SIDEBAR_ITEMS"])
        served = sidebar_module.get_sidebar_items({
            "SIDEBAR_ITEMS": captured["SIDEBAR_ITEMS"],
            SIDEBAR_ITEMS_MIGRATED_KEY: captured[SIDEBAR_ITEMS_MIGRATED_KEY],
        })
        self.assertEqual(list(LEGACY_ITEMS), served)
        for key in NEW_KEYS:
            self.assertNotIn(key, served)

    def test_marker_survives_save_partial(self):
        """别的工具用 save_partial 保存无关字段时，标记已在 PERSISTABLE_KEYS，会被带下去。"""
        from webserver.base import setting_saver
        from webserver.base.setting_saver import SettingsSaver

        captured = {}

        def fake_save(self, args):
            captured.update(args)
            return {"err": "ok"}

        conf = {SIDEBAR_ITEMS_MIGRATED_KEY: True, "SIDEBAR_ITEMS": list(LEGACY_ITEMS)}
        with mock.patch.dict(setting_saver.CONF, conf, clear=False), mock.patch.object(
            SettingsSaver, "save_extra_settings", fake_save
        ):
            SettingsSaver().save_partial({"BOOKBARN_TOKEN": "t"})
        self.assertIs(True, captured[SIDEBAR_ITEMS_MIGRATED_KEY])


if __name__ == "__main__":
    unittest.main()
