#!/usr/bin/env python3
# -*- coding: UTF-8 -*-

import os
import tempfile
import unittest
from unittest import mock

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


if __name__ == "__main__":
    unittest.main()
