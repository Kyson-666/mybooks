#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""POST /api/admin/settings 的入参校验，免 HTTP 栈与 calibre 依赖。

test_main.py 的 TestAdmin 走完整 HTTP 栈（需要 tests/cases 里的存量 sqlite），
那份库的 readers 表落后于 models.py，本机整类跑不起来；「网站默认访问链接」的
校验逻辑用最小 fake handler 直接打 AdminSettings.post 验证。
"""

import asyncio
import json
import unittest
from unittest import mock

from webserver.handlers import admin as admin_module
from webserver.handlers.admin import AdminSettings


class FakeHandler:
    """只提供 AdminSettings.post 与 @js/@auth 装饰器需要的那几个属性/方法。"""

    def __init__(self, payload):
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


class TestAdminSettingsPost(unittest.TestCase):

    def post(self, payload):
        captured = {}
        handler = FakeHandler(payload)

        def fake_save(self, args):
            captured.update(args)
            return {"err": "ok", "rsp": dict(args)}

        with mock.patch.object(admin_module.SettingsSaver, "save_extra_settings", fake_save):
            asyncio.run(AdminSettings.post(handler))
        return handler.written, captured

    def test_site_url_normalized(self):
        """尾部斜杠必须剥掉，否则前端会拼出 https://host//s/<token>。"""
        rsp, saved = self.post({"SITE_URL": "https://books.example.com//"})
        self.assertEqual(rsp["err"], "ok")
        self.assertEqual("https://books.example.com", saved["SITE_URL"])
        self.assertEqual("https://books.example.com", rsp["rsp"]["SITE_URL"])

    def test_site_url_invalid_rejected(self):
        for bad in ("books.example.com", "ftp://books.example.com", "https://"):
            rsp, saved = self.post({"SITE_URL": bad})
            self.assertEqual("params.site_url.invalid", rsp["err"], bad)
            self.assertNotIn("SITE_URL", saved, bad)

    def test_site_url_empty_means_not_configured(self):
        rsp, saved = self.post({"SITE_URL": "   "})
        self.assertEqual(rsp["err"], "ok")
        self.assertEqual("", saved["SITE_URL"])

    def test_site_url_absent_is_not_touched(self):
        rsp, saved = self.post({"site_title": "abc"})
        self.assertEqual(rsp["err"], "ok")
        self.assertNotIn("SITE_URL", saved)
        self.assertEqual("abc", saved["site_title"])


if __name__ == "__main__":
    unittest.main()
