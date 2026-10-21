#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""MyBooks KOReader plugin API: /api/koreader/*."""

from webserver.handlers.base import BaseHandler, auth, js
from webserver.handlers.book import SearchBook
from webserver.i18n import _
from webserver.services import koreader_service


class KoreaderSession(BaseHandler):
    @js
    @auth
    def get(self):
        if not koreader_service.is_enabled():
            return koreader_service.disabled_error()
        return koreader_service.session_payload(self)


class KoreaderHome(BaseHandler):
    @js
    @auth
    async def get(self):
        if not koreader_service.is_enabled():
            return koreader_service.disabled_error()
        return await koreader_service.home_payload(self)


class KoreaderStates(BaseHandler):
    @js
    @auth
    async def get(self):
        if not koreader_service.is_enabled():
            return koreader_service.disabled_error()
        ids = koreader_service.parse_book_ids(self.get_argument("ids", ""))
        return {"err": "ok", "states": await koreader_service.batch_states(self, ids)}


class KoreaderSearch(SearchBook):
    async def get(self):
        if not self.current_user:
            self.write({"err": "user.need_login", "msg": _("请先登录")})
            return
        if not koreader_service.is_enabled():
            self.write(koreader_service.disabled_error())
            return
        q = self.get_argument("q", "").strip()
        if q and not self.get_argument("name", "").strip():
            self.request.query_arguments.setdefault("name", [q.encode("utf-8")])
        sort = self.get_argument("sort", "").strip()
        if sort and not self.get_argument("order", "").strip():
            self.request.query_arguments.setdefault("order", [sort.encode("utf-8")])
        rsp = await super().get()
        if isinstance(rsp, dict) and not self._write_buffer:
            self.set_header("Content-Type", "application/json; charset=UTF-8")
            self.write(rsp)
        return rsp

    async def get_book_list(self, all_books, ids=None, title=None, sort_fields=None, include_comments=True):
        rsp = await super().get_book_list(all_books, ids, title, sort_fields, include_comments)
        return await koreader_service.trim_search_response(self, rsp)


def routes():
    return [
        (r"/api/koreader/session", KoreaderSession),
        (r"/api/koreader/home", KoreaderHome),
        (r"/api/koreader/states", KoreaderStates),
        (r"/api/koreader/search", KoreaderSearch),
    ]
