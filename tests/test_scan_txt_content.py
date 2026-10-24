#!/usr/bin/env python3
# -*- coding: UTF-8 -*-

import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from webserver.plugins.parser.txt import TxtParser
from webserver.services.extract import ExtractService


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

    def test_timeout_does_not_fall_back_in_process(self):
        """超时说明整本扫描跑不完；回退进程内只会更慢且独占 GIL，应当直接失败"""
        with mock.patch("webserver.services.extract.subprocess.run",
                        side_effect=subprocess.TimeoutExpired(cmd="parser", timeout=600)):
            with mock.patch.object(TxtParser, "parse") as parse:
                with self.assertRaises(subprocess.TimeoutExpired):
                    self.service.parse_txt_toc("/tmp/book.txt")

        parse.assert_not_called()

    def test_timeout_scales_with_file_size(self):
        """超时按体积放宽（下限 10 分钟 / 60s per MB / 上限 2 小时）：
        解析耗时随体积线性增长，固定超时会把慢机器上大文件的正常解析误判成失败"""
        fd, path = tempfile.mkstemp(suffix=".txt")
        os.close(fd)
        try:
            for size, expected in ((1024, 600), (20 * 1024 ** 2, 1200), (1000 * 1024 ** 2, 7200)):
                os.truncate(path, size)  # 稀疏文件，只关心大小
                self.assertEqual(self.service.txt_parse_timeout(path), expected, "size=%d" % size)
        finally:
            os.remove(path)

    def test_subprocess_call_uses_scaled_timeout(self):
        fd, path = tempfile.mkstemp(suffix=".txt")
        os.close(fd)
        try:
            os.truncate(path, 20 * 1024 ** 2)
            proc = mock.Mock(returncode=0, stdout=b'{"encoding": "utf-8", "toc": []}', stderr=b"")
            with mock.patch("webserver.services.extract.subprocess.run", return_value=proc) as run:
                self.service.parse_txt_toc(path)
            self.assertEqual(run.call_args[1]["timeout"], 1200)
        finally:
            os.remove(path)


if __name__ == "__main__":
    unittest.main()
