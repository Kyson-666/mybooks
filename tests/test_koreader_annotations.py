# -*- coding: utf-8 -*-
"""KOReader 插件第三步（标注交换）单元测试。"""

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
sys.path.insert(0, ROOT)

from webserver.services import koreader_service  # noqa: E402


class TestNormalizeNote(unittest.TestCase):
    def test_camel_case_converted(self):
        note = {
            "id": "ko-abc",
            "type": "annotation",
            "xpointer0": "/body/DocFragment[3]/body/p[4]/text().12",
            "text": "原文",
            "createdAt": 1760900000000,
            "updatedAt": 1760900000001,
            "deletedAt": None,
        }
        clean = koreader_service._normalize_note(note, 7)
        self.assertEqual(clean["uid"], 7)
        self.assertEqual(clean["created_at"], 1760900000000)
        self.assertEqual(clean["updated_at"], 1760900000001)
        self.assertNotIn("deleted_at", clean)

    def test_missing_id_rejected(self):
        self.assertIsNone(koreader_service._normalize_note({"text": "x"}, 7))

    def test_foreign_uid_rejected(self):
        self.assertIsNone(koreader_service._normalize_note({"id": "n1", "uid": 8}, 7))

    def test_updated_at_falls_back_to_created(self):
        clean = koreader_service._normalize_note({"id": "n1", "createdAt": 123}, 7)
        self.assertEqual(clean["updated_at"], 123)

    def test_deleted_tombstone_kept(self):
        clean = koreader_service._normalize_note({"id": "n1", "deletedAt": 456, "updatedAt": 456}, 7)
        self.assertEqual(clean["deleted_at"], 456)


class TestNoteItems(unittest.TestCase):
    def test_changed_since_ack(self):
        records = {
            ("h", "a"): {"id": "a", "updated_at": 100, "xpointer0": "/x"},
            ("h", "b"): {"id": "b", "updated_at": 50, "xpointer0": "/y"},
            ("h", "c"): {"id": "c", "updated_at": 10, "deleted_at": 200},
        }
        items = koreader_service._note_items(records, 90)
        ids = [item["id"] for item in items]
        self.assertEqual(ids, ["a", "c"])

    def test_cfi_only_marked_unresolvable(self):
        records = {("h", "a"): {"id": "a", "updated_at": 100, "cfi": "epubcfi(/6/2!/4/2)"}}
        items = koreader_service._note_items(records, 0)
        self.assertTrue(items[0]["unresolvable"])
        records[("h", "a")]["xpointer0"] = "/body/DocFragment[1]"
        items = koreader_service._note_items(records, 0)
        self.assertFalse(items[0].get("unresolvable"))

    def test_sorted_by_updated_at(self):
        records = {
            ("h", "b"): {"id": "b", "updated_at": 300, "xpointer0": "/b"},
            ("h", "a"): {"id": "a", "updated_at": 100, "xpointer0": "/a"},
        }
        items = koreader_service._note_items(records, 0)
        self.assertEqual([item["id"] for item in items], ["a", "b"])

    def test_always_echoes_pushed_ids(self):
        records = {
            ("h", "a"): {"id": "a", "updated_at": 10, "xpointer0": "/x"},
            ("h", "b"): {"id": "b", "updated_at": 11, "xpointer0": "/y"},
        }
        items = koreader_service._note_items(records, 900, {"a"})
        self.assertEqual([item["id"] for item in items], ["a"])

    def test_limit(self):
        records = {
            ("h", str(i)): {"id": str(i), "updated_at": i, "xpointer0": "/x"}
            for i in range(koreader_service.NOTES_LIMIT + 20)
        }
        self.assertEqual(len(koreader_service._note_items(records, 0)), koreader_service.NOTES_LIMIT)


class TestBookHash(unittest.TestCase):
    def test_book_hash(self):
        self.assertEqual(koreader_service._book_hash(42, "epub"), "cloud-42-epub")


if __name__ == "__main__":
    unittest.main()
