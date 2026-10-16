#!/usr/bin/env python3
# -*- coding: UTF-8 -*-

import json
import os
import sys
import tempfile
import unittest
from unittest import mock

from webserver.plugins.parser.txt import TxtParser
from webserver.services.extract import ExtractService
from webserver.services.scan_service import ScanService


class TestPrepareTxtContents(unittest.TestCase):
    """导入后应把带 TXT 的书排入目录索引(content.json)预解析队列，让内建阅读器秒开。"""

    def setUp(self):
        self.service = object.__new__(ScanService)
        self.service.db = mock.Mock()

    @mock.patch("webserver.services.scan_service.ExtractService")
    def test_enqueues_parse_for_txt_books_only(self, extract_cls):
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as fileobj:
            path = fileobj.name
        try:
            self.service.db.format_abspath.side_effect = lambda bid, fmt, index_is_id: path if bid == 1 else None
            self.service._prepare_txt_contents([1, 2])
            extract_cls.return_value.parse_txt_content.assert_called_once_with(1, path)
        finally:
            os.remove(path)

    @mock.patch("webserver.services.scan_service.ExtractService")
    def test_no_txt_format_skips(self, extract_cls):
        self.service.db.format_abspath.return_value = None
        self.service._prepare_txt_contents([1])
        extract_cls.return_value.parse_txt_content.assert_not_called()

    @mock.patch("webserver.services.scan_service.ExtractService")
    def test_lookup_error_is_swallowed(self, extract_cls):
        self.service.db.format_abspath.side_effect = RuntimeError("book not found")
        self.service._prepare_txt_contents([1])
        extract_cls.return_value.parse_txt_content.assert_not_called()


class TestParseTxtTocProcess(unittest.TestCase):
    """整本扫描是 CPU 密集的纯 Python 循环，必须放到独立子进程里跑，
    否则会和 Tornado 抢 GIL，把接口延迟从毫秒级拉到秒级。"""

    def setUp(self):
        self.service = object.__new__(ExtractService)

    def test_uses_subprocess_and_parses_stdout(self):
        payload = {"encoding": "GB18030", "toc": [{"id": 1, "title": "第一章", "start": 0, "end": -1}]}
        proc = mock.Mock(returncode=0, stdout=json.dumps(payload).encode("utf-8"), stderr=b"")
        with mock.patch("webserver.services.extract.subprocess.run", return_value=proc) as run:
            with mock.patch.object(TxtParser, "parse") as parse:
                toc = self.service.parse_txt_toc("/tmp/book.txt")

        self.assertEqual(toc, payload)
        parse.assert_not_called()
        args = run.call_args[0][0]
        self.assertEqual(args[0], sys.executable)
        self.assertEqual(args[-1], "/tmp/book.txt")
        self.assertTrue(args[1].endswith(os.path.join("plugins", "parser", "txt.py")))
        self.assertEqual(run.call_args[1]["env"]["PYTHONIOENCODING"], "utf-8")

    def test_spawn_failure_falls_back_in_process(self):
        expected = {"encoding": "utf-8", "toc": []}
        with mock.patch("webserver.services.extract.subprocess.run", side_effect=OSError("no fork")):
            with mock.patch.object(TxtParser, "parse", return_value=expected) as parse:
                toc = self.service.parse_txt_toc("/tmp/book.txt")

        self.assertEqual(toc, expected)
        parse.assert_called_once_with("/tmp/book.txt")

    def test_nonzero_exit_falls_back_in_process(self):
        expected = {"encoding": "utf-8", "toc": []}
        proc = mock.Mock(returncode=1, stdout=b"", stderr=b"parser blew up")
        with mock.patch("webserver.services.extract.subprocess.run", return_value=proc):
            with mock.patch.object(TxtParser, "parse", return_value=expected) as parse:
                toc = self.service.parse_txt_toc("/tmp/book.txt")

        self.assertEqual(toc, expected)
        parse.assert_called_once_with("/tmp/book.txt")


if __name__ == "__main__":
    unittest.main()
