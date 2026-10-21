# -*- coding: utf-8 -*-
"""KOReader 插件 API 第一步（只读接口）单元测试。"""

import os
import sys
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
sys.path.insert(0, ROOT)

from webserver.handlers import koreader  # noqa: E402
from webserver.services import koreader_service  # noqa: E402


class FakeUser:
    id = 7
    username = "alice"
    name = "Alice"
    avatar = ""

    def can_read(self):
        return True

    def can_save(self):
        return False


class FakeHandler:
    site_url = "https://books.example.com"

    def __init__(self):
        self.current_user = FakeUser()


class TestParseBookIds(unittest.TestCase):
    def test_dedup_and_invalid(self):
        self.assertEqual(koreader_service.parse_book_ids("1,2,2,x,-3,0,4"), [1, 2, 4])

    def test_empty(self):
        self.assertEqual(koreader_service.parse_book_ids(None), [])
        self.assertEqual(koreader_service.parse_book_ids(" , "), [])

    def test_limit(self):
        raw = ",".join(str(i) for i in range(1, koreader_service.MAX_STATE_IDS + 50))
        self.assertEqual(len(koreader_service.parse_book_ids(raw)), koreader_service.MAX_STATE_IDS)


class TestSessionPayload(unittest.TestCase):
    def test_shape_and_capabilities(self):
        data = koreader_service.session_payload(FakeHandler())
        self.assertEqual(data["err"], "ok")
        self.assertEqual(data["api"], 1)
        self.assertEqual(data["user"]["userId"], 7)
        self.assertEqual(data["user"]["nickname"], "Alice")
        self.assertTrue(data["capabilities"]["annotations"])
        self.assertTrue(data["allowed"]["read"])
        self.assertFalse(data["allowed"]["download"])
        self.assertTrue(data["server"]["site_url"])
        self.assertTrue(data["timezone"])
        self.assertTrue(data["today"])

    def test_avatar_url(self):
        class AvatarUser(FakeUser):
            avatar = "2020/avatar.png"

        user = AvatarUser()
        self.assertEqual(
            koreader_service.avatar_url(FakeHandler(), user),
            "https://books.example.com/avatar/2020/avatar.png",
        )


class TestRoutes(unittest.TestCase):
    def test_route_paths(self):
        paths = [item[0] for item in koreader.routes()]
        self.assertEqual(
            paths,
            [
                "/api/koreader/session",
                "/api/koreader/home",
                "/api/koreader/states",
                "/api/koreader/search",
                r"/api/koreader/progress/(\d+)",
                "/api/koreader/progress",
                "/api/koreader/reading-seconds",
                "/api/koreader/state",
                "/api/koreader/match",
                "/api/koreader/annotations",
            ],
        )


class SearchHandlerStub:
    def get_argument_start(self):
        return 0

    def get_argument(self, name, default=""):
        return default


class TestTrimSearchResponse(unittest.IsolatedAsyncioTestCase):
    async def test_fields_and_next(self):
        rsp = {
            "err": "ok",
            "title": "搜索",
            "total": 100,
            "books": [
                {
                    "id": 42,
                    "title": "三体",
                    "author": "刘慈欣",
                    "thumb": "https://x/thumb.jpg",
                    "comments": "长简介",
                    "files": [{"format": "EPUB"}, {"format": "pdf"}],
                }
            ],
        }
        states = {
            "42": {
                "read_state": 1,
                "favorite": False,
                "progress_percent": 37.5,
                "total_seconds": 5400,
            }
        }
        with mock.patch.object(koreader_service, "batch_states", new=mock.AsyncMock(return_value=states)):
            data = await koreader_service.trim_search_response(SearchHandlerStub(), rsp)
        self.assertEqual(data["err"], "ok")
        self.assertEqual(data["total"], 100)
        self.assertEqual(data["next"], 60)
        book = data["books"][0]
        self.assertEqual(book["formats"], ["epub", "pdf"])
        self.assertEqual(book["progress_percent"], 37.5)
        self.assertEqual(book["total_seconds"], 5400)
        self.assertNotIn("comments", book)
        self.assertNotIn("files", book)


if __name__ == "__main__":
    unittest.main()
