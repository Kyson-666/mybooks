#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""MyBooks KOReader plugin API: /api/koreader/*."""

import logging

import tornado.escape

from webserver.handlers.base import BaseHandler, auth, js, throttle
from webserver.handlers.book import SearchBook
from webserver.i18n import _
from webserver.services import koreader_service


def _body(handler):
    if not handler.request.body:
        return {}
    try:
        data = tornado.escape.json_decode(handler.request.body)
    except Exception:
        return None
    return data if isinstance(data, dict) else None


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


class KoreaderWrite(BaseHandler):
    @js
    @auth
    async def post(self):
        if not koreader_service.is_enabled():
            return koreader_service.disabled_error()
        data = _body(self)
        if data is None:
            return {"err": "params.invalid", "msg": _("请求内容不是合法的 JSON")}
        try:
            return await self.handler_action(data)
        except Exception:
            logging.error("[koreader] %s failed", self.request.path, exc_info=True)
            return {"err": "failed", "msg": _("服务器处理失败")}

    async def handler_action(self, data):
        raise NotImplementedError


class KoreaderProgress(KoreaderWrite):
    @throttle(write=True)
    async def post(self):
        return await super().post()

    async def handler_action(self, data):
        return await koreader_service.update_progress(self, data)


class KoreaderReadingSeconds(KoreaderWrite):
    async def handler_action(self, data):
        return await koreader_service.update_reading_seconds(self, data)


class KoreaderState(KoreaderWrite):
    async def handler_action(self, data):
        return await koreader_service.update_state(self, data)


class KoreaderProgressGet(BaseHandler):
    @js
    @auth
    async def get(self, book_id):
        if not koreader_service.is_enabled():
            return koreader_service.disabled_error()
        return await koreader_service.get_progress(self, int(book_id), self.get_argument("format", "epub"))


class KoreaderMatch(KoreaderWrite):
    async def handler_action(self, data):
        return await koreader_service.match_books(self, data)


class KoreaderAnnotations(KoreaderWrite):
    async def handler_action(self, data):
        return await koreader_service.exchange_annotations(self, data)


def routes():
    return [
        (r"/api/koreader/session", KoreaderSession),
        (r"/api/koreader/home", KoreaderHome),
        (r"/api/koreader/states", KoreaderStates),
        (r"/api/koreader/search", KoreaderSearch),
        (r"/api/koreader/progress/(\d+)", KoreaderProgressGet),
        (r"/api/koreader/progress", KoreaderProgress),
        (r"/api/koreader/reading-seconds", KoreaderReadingSeconds),
        (r"/api/koreader/state", KoreaderState),
        (r"/api/koreader/match", KoreaderMatch),
        (r"/api/koreader/annotations", KoreaderAnnotations),
    ]
