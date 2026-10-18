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
    handler.headers = {}
    handler.redirects = []
    handler.write = lambda data: handler.written.append(data)
    handler.set_status = lambda code: setattr(handler, "status", code)
    handler.set_header = lambda k, v: handler.headers.__setitem__(k, v)

    def _redirect(url, **kw):
        # tornado 的 redirect() 自带 302，这里复刻一下，测试才能断言状态码
        handler.redirects.append(url)
        handler.status = kw.get("status", 302)

    handler.redirect = _redirect
    handler.get_argument = lambda name, default=None: default
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

    def test_shares_and_opds_are_not_open_doors(self):
        # 私人图书馆下"任何账号都能读全库"，分享没有意义；放行它们等于留后门（见方案文档 §2.2）
        for path in ("/s/abc123", "/api/share/abc123", "/api/share/abc123/verify", "/opds", "/opds/nav/new"):
            self.assertFalse(login_gate_allowed(path), path)

    def test_login_and_install_surfaces_allowed(self):
        for path in (
            "/login",
            "/login/",          # 尾斜杠：StaticFileHandler 会把 /login 301 到 /login/
            "/signup",
            "/signup/",
            "/logout",
            "/welcome",
            "/install",
            "/starting",
            "/api/user/info",
            "/api/user/sign_in",
            "/api/user/sign_up",
            "/api/user/reset",
            "/api/user/sign_out",
            "/api/done",                  # 社交登录 OAuth 回调
            "/api/active/alice/3f2b1c",   # 邮件里的真实激活链接
            "/api/access",
            "/api/admin/install",
            "/api/favicon/1",
            "/wap/login",
            "/wap/welcome",
        ):
            self.assertTrue(login_gate_allowed(path), path)
        # 激活接口的真实路由是 /api/active/...，不是 /api/user/active/...
        self.assertFalse(login_gate_allowed("/api/user/active/alice/3f2b1c"))

    def test_credential_bearing_surfaces_allowed(self):
        # 这些入口各自带 token / Basic 认证，设备端无法走网页登录
        for path in (
            "/podcast/abc123token",              # 用户自己的 feed（路径即 token）
            "/podcast/abc123token/",
            "/podcast/abc123token/book/12",
            "/podcast/audio/12/abc123token/ep1.mp3",
            "/books/dav/",
            "/api/mcp/health",
            "/api/mcp/stream",
        ):
            self.assertTrue(login_gate_allowed(path), path)

    def test_podcast_public_catalog_is_blocked(self):
        # 公开目录会把有声书书名/作者/简介匿名暴露，必须按普通页面拦掉
        for path in (
            "/podcast",
            "/podcast/",
            "/podcast/all",
            "/podcast/book/1",
            "/podcast/book/1/opml",
            "/podcast/category/novel",
            "/podcast/tag/x",
            "/podcast/author/alice",
        ):
            self.assertFalse(login_gate_allowed(path), path)

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
        self.assertEqual(handler.status, 200)

    def test_anonymous_page_redirects_to_login_with_next(self):
        CONF["REQUIRE_LOGIN"] = True
        handler = _bare_handler("/book/12", uri="/book/12?tab=meta")
        with self.assertRaises(web.Finish):
            handler.should_be_logged_in()
        self.assertEqual(handler.written, [])
        self.assertEqual(len(handler.redirects), 1)
        self.assertTrue(handler.redirects[0].startswith("/login/?next="), handler.redirects[0])
        self.assertEqual(handler.status, 302)
        self.assertIn("%2Fbook%2F12%3Ftab%3Dmeta", handler.redirects[0])

    def test_anonymous_wap_redirects_to_wap_login(self):
        CONF["REQUIRE_LOGIN"] = True
        # 尾斜杠归一化会把 /wap/ 变成 /wap：入口的两种写法都必须进 WAP 登录页，
        # 否则 WAP 首页会掉到 /login/（Nuxt SPA 登录页，老设备跑不动）。
        for path in ("/wap", "/wap/", "/wap/categories"):
            handler = _bare_handler(path)
            with self.assertRaises(web.Finish, msg=path):
                handler.should_be_logged_in()
            self.assertEqual(len(handler.redirects), 1, path)
            self.assertTrue(handler.redirects[0].startswith("/wap/login?next="), path)
            self.assertEqual(handler.status, 302, path)

    def test_allowlisted_api_passes(self):
        CONF["REQUIRE_LOGIN"] = True
        handler = _bare_handler("/api/user/info")
        self.assertFalse(handler.should_be_logged_in())
        self.assertEqual(handler.written, [])

    def test_book_file_returns_401_not_json(self):
        # /get/* 的消费者是 <img>/下载器，200 JSON 会被当成资源解析
        CONF["REQUIRE_LOGIN"] = True
        handler = _bare_handler("/get/cover/1.jpg")
        with self.assertRaises(web.Finish):
            handler.should_be_logged_in()
        self.assertEqual(handler.written, [])
        self.assertEqual(handler.status, 401)

    def test_opds_returns_401_with_basic_challenge(self):
        # OPDS 客户端靠 WWW-Authenticate 弹认证；配了账号即可通过（Basic → current_user）
        CONF["REQUIRE_LOGIN"] = True
        handler = _bare_handler("/opds/nav/new")
        with self.assertRaises(web.Finish):
            handler.should_be_logged_in()
        self.assertEqual(handler.status, 401)
        self.assertTrue(handler.headers.get("WWW-Authenticate", "").startswith("Basic "))

    def test_valid_download_sign_passes(self):
        # formatter 给登录用户生成的 ?dl= 直链（10 秒、绑定用户+书+格式）：下载器没 cookie 也能用
        CONF["REQUIRE_LOGIN"] = True
        handler = _bare_handler("/api/book/12.epub")
        handler.get_argument = lambda name, default=None: "1.1792300490.deadbeef" if name == "dl" else default
        handler.parse_download_sign = lambda sign, bid, fmt: 3 if (bid, fmt) == ("12", "epub") else None
        self.assertFalse(handler.should_be_logged_in())
        self.assertEqual(handler.written, [])

    def test_invalid_or_expired_download_sign_is_blocked(self):
        CONF["REQUIRE_LOGIN"] = True
        handler = _bare_handler("/api/book/12.epub")
        handler.get_argument = lambda name, default=None: "bad" if name == "dl" else default
        handler.parse_download_sign = lambda sign, bid, fmt: None
        with self.assertRaises(web.Finish):
            handler.should_be_logged_in()
        self.assertEqual(handler.written[0]["err"], "user.need_login")

    def test_podcast_token_is_not_a_web_session(self):
        # ?token=<podcast_token> 会出现在 RSS URL/日志/Referer 里，不能当整站通行证
        CONF["REQUIRE_LOGIN"] = True
        handler = _bare_handler("/api/index")
        handler.current_user = SimpleNamespace(id=2)
        handler._login_via_token = True
        with self.assertRaises(web.Finish):
            handler.should_be_logged_in()
        self.assertEqual(handler.written[0]["err"], "user.need_login")

    def test_cookie_session_still_passes(self):
        CONF["REQUIRE_LOGIN"] = True
        handler = _bare_handler("/api/index")
        handler.current_user = SimpleNamespace(id=2)
        handler._login_via_token = False
        self.assertFalse(handler.should_be_logged_in())

    def test_podcast_token_endpoint_still_works(self):
        # token 自身的播客路径在白名单里，不受"token≠会话"影响
        CONF["REQUIRE_LOGIN"] = True
        handler = _bare_handler("/podcast/abc123token/book/12")
        handler.current_user = SimpleNamespace(id=2)
        handler._login_via_token = True
        self.assertFalse(handler.should_be_logged_in())

    def test_podcast_catalog_allowed_for_token_identity(self):
        # 订阅页的目录（?token=）要能把"我的收藏/待读"渲染出来，但绝不能放行 /api/*
        CONF["REQUIRE_LOGIN"] = True
        handler = _bare_handler("/podcast/all")
        handler.current_user = SimpleNamespace(id=2)
        handler._login_via_token = True
        self.assertFalse(handler.should_be_logged_in())
        handler = _bare_handler("/api/index")
        handler.current_user = SimpleNamespace(id=2)
        handler._login_via_token = True
        with self.assertRaises(web.Finish):
            handler.should_be_logged_in()

    def test_token_login_never_sets_cookie(self):
        # 长期 token 只是"本次请求的凭据"，响应里不能种 user_id/lt（否则一次 curl 换 7 天会话）
        handler = BaseHandler.__new__(BaseHandler)
        handler.saved_cookies = []
        handler.set_secure_cookie = lambda k, v: handler.saved_cookies.append(k)
        handler.sqlite_session = SimpleNamespace()
        handler.request = SimpleNamespace(remote_ip="127.0.0.1")
        handler.login_user(SimpleNamespace(id=3, username="u"), persist=False, set_cookie=False)
        self.assertEqual(handler.saved_cookies, [])

    def test_password_login_still_sets_cookie(self):
        handler = BaseHandler.__new__(BaseHandler)
        handler.saved_cookies = []
        handler.set_secure_cookie = lambda k, v: handler.saved_cookies.append(k)
        handler.login_user(SimpleNamespace(id=3, username="u"), persist=False)
        self.assertEqual(handler.saved_cookies, ["user_id", "lt"])


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


class TestWapSafeNext(unittest.TestCase):
    """WAP 登录/访问码页的 next 校验（此前只判 //，反斜杠写法可绕过）。"""

    def test_rejects_offsite_targets(self):
        from webserver.handlers.wap import safe_next_path

        for bad in ("//evil.com", "/" + chr(92) + "evil.com", "%2F%5Cevil.com", "http://evil.com", "https://x/y", "", None):
            self.assertEqual(safe_next_path(bad), "/wap", repr(bad))

    def test_keeps_site_paths(self):
        from webserver.handlers.wap import safe_next_path

        self.assertEqual(safe_next_path("/wap/search"), "/wap/search")
        self.assertEqual(safe_next_path("%2Fwap%2Ffavorites"), "/wap/favorites")
        self.assertEqual(safe_next_path("/wap/book/1?x=1"), "/wap/book/1?x=1")
