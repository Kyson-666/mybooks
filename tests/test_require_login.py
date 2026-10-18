#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""REQUIRE_LOGIN（必须登录才能访问）门禁测试。

覆盖三层：
1. 放行名单判定（纯函数 login_gate_allowed）；
2. BaseHandler.should_be_logged_in 的分支（JSON 拦截 / 页面跳转 / WAP 跳转 / 放行）；
3. 与访问码模式（INVITE_MODE）的覆盖关系，以及 sys.allow 的上报值。
"""

import unittest
from types import SimpleNamespace

from tornado import web

from webserver.handlers.base import CONF, BaseHandler, login_gate_allowed


def _bare_handler(path="/api/index", uri=None):
    """跳过 RequestHandler.__init__（需要 application/ioloop），只装配门禁用得到的东西。"""
    handler = BaseHandler.__new__(BaseHandler)
    handler.request = SimpleNamespace(path=path, uri=uri or path)
    handler.current_user = None
    handler.written = []
    handler.status = None
    handler.redirects = []
    handler.write = lambda data: handler.written.append(data)
    handler.set_status = lambda code: setattr(handler, "status", code)
    handler.redirect = lambda url, **kw: handler.redirects.append(url)
    return handler


class TestLoginGateAllowList(unittest.TestCase):
    def test_blocked_by_default(self):
        for path in (
            "/",
            "/index",
            "/search",
            "/api/index",
            "/api/search",
            "/api/book/1",
            "/api/booklists/public",
            "/api/library/stats/size",
            "/get/1/cover",
            "/get/extract/1/foo",
            "/read/1",
            "/api/audiobooks",
        ):
            self.assertFalse(login_gate_allowed(path), path)

    def test_login_and_install_surfaces_allowed(self):
        for path in (
            "/login",
            "/logout",
            "/signup",
            "/welcome",
            "/install",
            "/starting",
            "/api/user/info",
            "/api/user/sign_in",
            "/api/user/sign_up",
            "/api/user/reset",
            "/api/user/active/abc/def",
            "/api/access",
            "/api/admin/install",
            "/api/favicon/1",
            "/wap/login",
            "/wap/welcome",
        ):
            self.assertTrue(login_gate_allowed(path), path)

    def test_credential_bearing_surfaces_allowed(self):
        # 这些入口各自带 token / Basic 认证，设备端无法走网页登录
        for path in (
            "/s/abc123",
            "/api/share/abc123",
            "/api/share/abc123/verify",
            "/opds",
            "/opds/nav/new",
            "/podcast/all",
            "/podcast/book/1",
            "/books/dav/",
            "/api/mcp/health",
            "/api/mcp/stream",
        ):
            self.assertTrue(login_gate_allowed(path), path)

    def test_static_assets_allowed_but_not_book_files(self):
        self.assertTrue(login_gate_allowed("/_nuxt/abc.js"))
        self.assertTrue(login_gate_allowed("/logo/favicon.ico"))
        self.assertTrue(login_gate_allowed("/favicon.ico"))
        # /get/* 是封面/正文/解包，只认白名单，绝不因为带扩展名就放行
        self.assertFalse(login_gate_allowed("/get/cover/1.jpg"))
        self.assertFalse(login_gate_allowed("/get/1/book.epub"))
        # /api/* 同理
        self.assertFalse(login_gate_allowed("/api/book/1/export.json"))

    def test_empty_path_is_blocked(self):
        self.assertFalse(login_gate_allowed(""))


class TestShouldBeLoggedIn(unittest.TestCase):
    def setUp(self):
        self._saved = CONF.get("REQUIRE_LOGIN", False)

    def tearDown(self):
        CONF["REQUIRE_LOGIN"] = self._saved

    def test_off_never_blocks(self):
        CONF["REQUIRE_LOGIN"] = False
        handler = _bare_handler("/api/index")
        self.assertFalse(handler.should_be_logged_in())
        self.assertEqual(handler.written, [])
        self.assertEqual(handler.redirects, [])

    def test_logged_in_user_passes(self):
        CONF["REQUIRE_LOGIN"] = True
        handler = _bare_handler("/api/index")
        handler.current_user = SimpleNamespace(id=1)
        self.assertFalse(handler.should_be_logged_in())
        self.assertEqual(handler.written, [])

    def test_anonymous_api_gets_need_login(self):
        CONF["REQUIRE_LOGIN"] = True
        handler = _bare_handler("/api/index")
        with self.assertRaises(web.Finish):
            handler.should_be_logged_in()
        self.assertEqual(len(handler.written), 1)
        self.assertEqual(handler.written[0]["err"], "user.need_login")
        self.assertIn("msg", handler.written[0])

    def test_anonymous_page_redirects_to_login_with_next(self):
        CONF["REQUIRE_LOGIN"] = True
        handler = _bare_handler("/book/12", uri="/book/12?tab=meta")
        with self.assertRaises(web.Finish):
            handler.should_be_logged_in()
        self.assertEqual(handler.written, [])
        self.assertEqual(len(handler.redirects), 1)
        self.assertTrue(handler.redirects[0].startswith("/login?next="))
        self.assertIn("%2Fbook%2F12%3Ftab%3Dmeta", handler.redirects[0])

    def test_anonymous_wap_redirects_to_wap_login(self):
        CONF["REQUIRE_LOGIN"] = True
        handler = _bare_handler("/wap/categories")
        with self.assertRaises(web.Finish):
            handler.should_be_logged_in()
        self.assertEqual(len(handler.redirects), 1)
        self.assertTrue(handler.redirects[0].startswith("/wap/login?next="))

    def test_allowlisted_api_passes(self):
        CONF["REQUIRE_LOGIN"] = True
        handler = _bare_handler("/api/user/info")
        self.assertFalse(handler.should_be_logged_in())
        self.assertEqual(handler.written, [])


class TestInviteModeInteraction(unittest.TestCase):
    def setUp(self):
        self._saved = {k: CONF.get(k) for k in ("REQUIRE_LOGIN", "INVITE_MODE", "INVITE_CODE")}

    def tearDown(self):
        for k, v in self._saved.items():
            CONF[k] = v

    def test_require_login_overrides_invite_mode(self):
        CONF["REQUIRE_LOGIN"] = True
        CONF["INVITE_MODE"] = True
        CONF["INVITE_CODE"] = "mybooks"
        handler = _bare_handler("/")
        self.assertFalse(handler.need_invited())

    def test_invite_mode_still_works_when_require_login_off(self):
        CONF["REQUIRE_LOGIN"] = False
        CONF["INVITE_MODE"] = True
        CONF["INVITE_CODE"] = "mybooks"
        handler = _bare_handler("/")
        self.assertTrue(handler.need_invited())

    def test_invite_mode_without_code_is_inert(self):
        CONF["REQUIRE_LOGIN"] = False
        CONF["INVITE_MODE"] = True
        CONF["INVITE_CODE"] = ""
        handler = _bare_handler("/")
        self.assertFalse(handler.need_invited())


class TestAllowFlags(unittest.TestCase):
    def setUp(self):
        self._saved = {k: CONF.get(k) for k in ("REQUIRE_LOGIN", "ALLOW_GUEST_READ", "ALLOW_GUEST_DOWNLOAD", "ALLOW_GUEST_PUSH", "ALLOW_GUEST_UPLOAD")}

    def tearDown(self):
        for k, v in self._saved.items():
            CONF[k] = v

    def test_guest_permissions_pass_through_when_off(self):
        CONF["REQUIRE_LOGIN"] = False
        CONF["ALLOW_GUEST_READ"] = True
        CONF["ALLOW_GUEST_DOWNLOAD"] = True
        CONF["ALLOW_GUEST_PUSH"] = True
        CONF["ALLOW_GUEST_UPLOAD"] = False
        flags = _bare_handler("/").allow_flags()
        self.assertFalse(flags["require_login"])
        self.assertTrue(flags["read"])
        self.assertTrue(flags["download"])
        self.assertTrue(flags["push"])
        self.assertFalse(flags["upload"])

    def test_guest_permissions_forced_false_when_on(self):
        CONF["REQUIRE_LOGIN"] = True
        CONF["ALLOW_GUEST_READ"] = True
        CONF["ALLOW_GUEST_DOWNLOAD"] = True
        CONF["ALLOW_GUEST_PUSH"] = True
        CONF["ALLOW_GUEST_UPLOAD"] = True
        flags = _bare_handler("/").allow_flags()
        self.assertTrue(flags["require_login"])
        for key in ("read", "download", "push", "upload"):
            self.assertFalse(flags[key], key)


if __name__ == "__main__":
    unittest.main()
