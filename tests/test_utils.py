#!/usr/bin/env pytest
# -*- coding: UTF-8 -*-


import unittest

from webserver.utils import compare_books_by_rating_or_id, normalize_site_url


class TestUtils(unittest.TestCase):
    def test_compare_by_rating_or_id(self):
        cases = [
            [1, {"id": 2}, {"id": 1}],
            [1, {"rating": 2}, {"rating": None}],
            [1, {"rating": 2}, {"rating": 0}],
            [1, {"rating": 2}, {}],
            [1, {"rating": 2}, {"id": 2}],
            [1, {"rating": 2, "id": 2}, {"rating": 2, "id": 1}],
            [1, {"rating": 0, "id": 2}, {"rating": 0, "id": 1}],
            [1, {"rating": 0, "id": 2}, {"rating": None, "id": 1}],
            [1, {"rating": 0, "id": 2}, {"id": 1}],
        ]
        for val, a, b in cases:
            self.assertEqual(val, compare_books_by_rating_or_id(a, b), "compare %s > %s" % (a, b))
            self.assertEqual(-1 * val, compare_books_by_rating_or_id(b, a), "compare %s > %s" % (b, a))


class TestNormalizeSiteUrl(unittest.TestCase):
    """网站默认访问链接：留空/非法一律归一为空串，合法地址剥掉尾部斜杠。"""

    def test_keeps_valid_absolute_urls(self):
        cases = {
            "https://books.example.com": "https://books.example.com",
            "http://192.168.5.254:8080": "http://192.168.5.254:8080",
            "  https://books.example.com/  ": "https://books.example.com",
            "https://books.example.com///": "https://books.example.com",
            "https://books.example.com/books/": "https://books.example.com/books",
        }
        for raw, expected in cases.items():
            self.assertEqual(expected, normalize_site_url(raw), raw)

    def test_empty_means_not_configured(self):
        for raw in ("", "   ", None):
            self.assertEqual("", normalize_site_url(raw), repr(raw))

    def test_invalid_values_fall_back_to_empty(self):
        for raw in ("books.example.com", "ftp://books.example.com", "//books.example.com", "https://", "https://books.example.com/ /x", "javascript:alert(1)", "https://例 子.com"):
            self.assertEqual("", normalize_site_url(raw), raw)
