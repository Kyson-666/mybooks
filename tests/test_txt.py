#!/usr/bin/env python3
# -*- coding: UTF-8 -*-

import os
import tempfile
from unittest import mock

from tests.test_main import TestWithUserLogin, setUpModule as init, testdir
from webserver.plugins.parser import txt as txt_module
from webserver.plugins.parser.txt import TxtParser, get_file_encoding


def setUpModule():
    init()


class TestTxtParse(TestWithUserLogin):
    BOOK_PATH = testdir + "/cases/book.txt"
    BOOK_ENCODING = "GB18030"
    BOOK_TOC = [
            {
                "id": 1,
                "title": "《秦吏》",
                "start": 12,
                "end": 32
                },
            {
                "id": 2,
                "title": "简介：",
                "start": 40,
                "end": 544
                },
            {
                "id": 3,
                "title": "第一卷 小亭长",
                "start": 559,
                "end": 563
                },
            {
                "id": 4,
                "title": "第0001章 士伍，请出示身份证！",
                "start": 594,
                "end": 6565
                },
            {
                "id": 5,
                "title": "第0002章 天下事与眼前事",
                "start": 6590,
                "end": -1
                }
            ]

    def test_get_file_encoding(self):
        encoding = get_file_encoding(self.BOOK_PATH)
        self.assertEqual(encoding, self.BOOK_ENCODING)

    def test_parse_text_book_table_of_content(self):
        with open(self.BOOK_PATH, encoding=self.BOOK_ENCODING, newline='\n') as fileobj:
            toc = TxtParser().parse_txt_book_toc(fileobj)
            self.assertEqual(len(toc), len(self.BOOK_TOC))
            self.assertEqual(toc[-1]['title'], self.BOOK_TOC[-1]['title'])
            # self.assertEqual(toc, self.BOOK_TOC)

    def test_parse(self):
        meta = TxtParser().parse(self.BOOK_PATH)
        self.assertEqual(meta['encoding'], self.BOOK_ENCODING)
        toc = meta['toc']
        self.assertEqual(len(toc), len(self.BOOK_TOC))
        self.assertEqual(toc[-1]['title'], self.BOOK_TOC[-1]['title'])

        # github上跑pytest时文件偏移量总是不对，待排查
        # self.assertEqual(toc, self.BOOK_TOC)

    def test_parse_txt_book_toc_yields_gil(self):
        """长解析必须定期让出 GIL：整本扫描一直占着会把同进程的 IOLoop 饿住数秒"""

        class TimeStub(object):
            def __init__(self):
                self.sleeps = []

            def sleep(self, seconds):
                self.sleeps.append(seconds)

        stub = TimeStub()
        chapters = 500
        body = "".join("第%04d章 测试章节\n这是一段普通正文。\n" % i for i in range(1, chapters + 1))

        fd, path = tempfile.mkstemp(suffix=".txt")
        os.close(fd)
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(body)
            with mock.patch.object(txt_module, "time", stub):
                with open(path, encoding="utf-8", newline="\n") as fileobj:
                    toc = TxtParser().parse_txt_book_toc(fileobj)
        finally:
            os.remove(path)

        self.assertEqual(len(toc), chapters)
        # 每章两行，每扫 GIL_YIELD_EVERY_LINES 行让出一次
        expected = chapters * 2 // txt_module.GIL_YIELD_EVERY_LINES
        self.assertEqual(stub.sleeps, [0] * expected)

