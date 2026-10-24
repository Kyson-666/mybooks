#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""BookTxtParser（/api/book/txt/parser）的索引就绪 / 自愈契约。

"content.json 存在"是阅读接口唯一的就绪信号。旧版本的非原子写入、进程被杀、
磁盘写满都会留下半截 json —— 这条用例锁死的是「坏索引要退化成没解析过」，
否则阅读器会永久 500 且没有任何自愈出口。

这里走的是真实的 @js 装饰器路径（捕获 self.write 的 payload），不是直接调
方法体：接线错了（比如删除索引后忘了往下走）单测方法体是看不出来的。
"""

import asyncio
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from webserver.handlers.book import BookTxtParser

TOC_INDEX = {
    "encoding": "GB18030",
    "toc": [
        {"id": 1, "title": "第一章 起", "start": 0, "end": 100},
        {"id": 2, "title": "第二章 承", "start": 100, "end": -1},
    ],
}


class TestBookTxtParserIndex(unittest.TestCase):
    def setUp(self):
        self.extract_dir = tempfile.mkdtemp(prefix="txt-parser-")
        self.addCleanup(shutil.rmtree, self.extract_dir, True)
        os.makedirs(os.path.join(self.extract_dir, "7"))
        self.content_path = os.path.join(self.extract_dir, "7", "content.json")
        self.txt_path = os.path.join(self.extract_dir, "book7.txt")
        with open(self.txt_path, "wb") as f:
            f.write(b"x" * 4096)
        patcher = mock.patch.dict("webserver.handlers.book.CONF",
                                  {"extract_path": self.extract_dir})
        patcher.start()
        self.addCleanup(patcher.stop)

    def _call(self, test_arg):
        handler = BookTxtParser.__new__(BookTxtParser)
        handler.request = mock.Mock(headers={})
        handler.write = mock.Mock()
        handler.finish = mock.Mock()
        handler.set_header = mock.Mock()
        handler.get_argument = lambda name, default="": {
            "id": "7", "test": test_arg}.get(name, default)
        handler.get_book = lambda bid, raise_exception=False: {
            "id": 7, "title": "测试书", "fmt_txt": self.txt_path}
        handler.current_user = mock.Mock()

        with mock.patch("webserver.handlers.book.BookAccessService") as access:
            access.share_read_granted.return_value = True
            access.guest_read_allowed.return_value = True
            with mock.patch("webserver.handlers.book.ExtractService") as extract_cls:
                extract_cls.return_value.get_queue.return_value.qsize.return_value = 3
                asyncio.run(handler.get())
        return handler.write.call_args[0][0], extract_cls.return_value

    def _write_index(self, payload):
        with open(self.content_path, "w", encoding="utf8") as f:
            f.write(payload if isinstance(payload, str) else json.dumps(payload))

    def test_valid_index_is_served(self):
        self._write_index(TOC_INDEX)

        rsp, extract_service = self._call("1")

        self.assertEqual(rsp["err"], "ok")
        self.assertEqual(rsp["msg"], "parsed")
        self.assertEqual(rsp["data"]["content"], TOC_INDEX["toc"])
        self.assertEqual(rsp["data"]["encoding"], "GB18030")
        self.assertEqual(rsp["data"]["name"], "测试书")
        extract_service.parse_txt_content.assert_not_called()

    def test_broken_index_is_dropped_and_requeued(self):
        """半截 json 不能被当成"已就绪"：删掉重建，让读者拿到正常目录"""
        self._write_index('{"encoding": "utf-8", "toc": [')

        rsp, extract_service = self._call("0")

        self.assertFalse(os.path.exists(self.content_path))
        self.assertEqual(rsp["err"], "ok")
        self.assertNotEqual(rsp["msg"], "parsed")
        self.assertEqual(rsp["data"]["que"], 3)
        extract_service.parse_txt_content.assert_called_once_with("7", self.txt_path)

    def test_broken_index_reports_not_parsed_when_polling(self):
        """轮询（test=1）不该再入队，只回"没解析过"让前端继续等"""
        self._write_index('{"encoding"')

        rsp, extract_service = self._call("1")

        self.assertFalse(os.path.exists(self.content_path))
        self.assertEqual(rsp["msg"], "not parsed")
        extract_service.parse_txt_content.assert_not_called()

    def test_missing_index_is_enqueued_on_first_read(self):
        rsp, extract_service = self._call("0")

        self.assertEqual(rsp["err"], "ok")
        self.assertEqual(rsp["data"]["que"], 3)
        self.assertEqual(rsp["data"]["path"], self.content_path)
        extract_service.parse_txt_content.assert_called_once_with("7", self.txt_path)

    def test_missing_index_polling_does_not_enqueue(self):
        rsp, extract_service = self._call("1")

        self.assertEqual(rsp["msg"], "not parsed")
        extract_service.parse_txt_content.assert_not_called()


if __name__ == "__main__":
    unittest.main()
