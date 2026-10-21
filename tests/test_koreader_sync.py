# -*- coding: utf-8 -*-
"""KOReader 插件第二步（进度/时长/状态/关联）单元测试。"""

import datetime
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
sys.path.insert(0, ROOT)

from webserver.services import koreader_service  # noqa: E402


class TestProgressHelpers(unittest.TestCase):
    def test_normalize_progress_pair(self):
        self.assertEqual(koreader_service._normalize_progress({"progress": [120, 1000]}), (120, 1000))

    def test_normalize_progress_pair_invalid(self):
        self.assertEqual(koreader_service._normalize_progress({"progress": [1, 0], "percent": 12.5}), (1250, 10000))

    def test_normalize_progress_percent_only(self):
        self.assertEqual(koreader_service._normalize_progress({"percent": 37.5}), (3750, 10000))

    def test_normalize_progress_missing(self):
        self.assertIsNone(koreader_service._normalize_progress({}))

    def test_progress_percent(self):
        self.assertEqual(koreader_service._progress_percent((1, 4)), 25.0)
        self.assertEqual(koreader_service._progress_percent(None, 12.5), 12.5)

    def test_normalize_format(self):
        self.assertEqual(koreader_service.normalize_format(" EPUB "), "epub")
        self.assertEqual(koreader_service.normalize_format(""), None)
        self.assertEqual(koreader_service.normalize_format("../etc"), None)
        self.assertEqual(len(koreader_service.normalize_format("x" * 40)), 16)

    def test_book_id(self):
        self.assertEqual(koreader_service._book_id("42"), 42)
        self.assertIsNone(koreader_service._book_id("0"))
        self.assertIsNone(koreader_service._book_id("abc"))


class TestSecondsDedup(unittest.TestCase):
    def setUp(self):
        koreader_service._SECONDS_DEDUP.clear()

    def test_same_entry_only_once(self):
        key = koreader_service._seconds_fingerprint(7, 42, "epub", "2026-10-21", 60, 1760900000)
        self.assertFalse(koreader_service._dedup_hit(key))
        self.assertTrue(koreader_service._dedup_hit(key))
        other = koreader_service._seconds_fingerprint(7, 42, "epub", "2026-10-21", 61, 1760900000)
        self.assertFalse(koreader_service._dedup_hit(other))

    def test_expired_entry_is_dropped(self):
        key = koreader_service._seconds_fingerprint(7, 42, "epub", "2026-10-20", 60, 1)
        koreader_service._SECONDS_DEDUP[key] = 0
        self.assertFalse(koreader_service._dedup_hit(key))


class TestAckConversion(unittest.TestCase):
    def test_iso_to_ms(self):
        self.assertEqual(koreader_service._iso_to_ms("1970-01-01T00:00:01Z"), 1000)
        self.assertEqual(koreader_service._iso_to_ms(None), 0)
        self.assertEqual(koreader_service._iso_to_ms("bad"), 0)

    def test_round_trip(self):
        raw = koreader_service._iso_now()
        moment = datetime.datetime.fromisoformat(raw.replace("Z", "+00:00"))
        self.assertGreater(moment.timestamp(), 0)

    def test_client_ms_normalizes_units(self):
        self.assertEqual(koreader_service._client_ms(1760900000), 1760900000000)
        self.assertEqual(koreader_service._client_ms(1760900000000), 1760900000000)
        self.assertIsNone(koreader_service._client_ms(None))


if __name__ == "__main__":
    unittest.main()
