#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""目录提取顺带预热 TXT 阅读索引。

目录提取写的是 calibre 列 #catalog，内建 TXT 阅读器读的是
extract_path/<id>/content.json。两套缓存互不相干，所以批量提取跑完后
TXT 仍然要等首读才生成章节索引；这里验证提取链路把它一并解决。
"""

import json
import os
import subprocess
import tempfile
import threading
import unittest
from unittest import mock

from webserver.constants import CALIBRE_COLUMN_CATALOG
from webserver.services import AsyncService
from webserver.services.catalog import CatalogExtractService
from webserver.services.extract import ExtractService, load_txt_content_index

TXT_TOC = {
    "encoding": "GB18030",
    "toc": [
        {"id": 1, "title": "第一章 起", "start": 0, "end": 100},
        {"id": 2, "title": "第二章 承", "start": 100, "end": -1},
    ],
}
SINGLE_CHAPTER_TOC = {
    "encoding": "GB18030",
    "toc": [{"id": 1, "title": "正文", "start": 26, "end": -1}],
}


class TempDirMixin:
    def make_temp_dir(self):
        path = tempfile.mkdtemp(prefix="catalog-extract-")
        self.addCleanup(self._remove_tree, path)
        return path

    @staticmethod
    def _remove_tree(path):
        for root, dirs, files in os.walk(path, topdown=False):
            for name in files:
                os.remove(os.path.join(root, name))
            for name in dirs:
                os.rmdir(os.path.join(root, name))
        os.rmdir(path)

    def make_temp_file(self, suffix=".txt", content=b""):
        fd, path = tempfile.mkstemp(suffix=suffix)
        os.close(fd)
        if content:
            with open(path, "wb") as f:
                f.write(content)
        self.addCleanup(lambda: os.path.exists(path) and os.remove(path))
        return path


class TestWarmTxtReaderCache(TempDirMixin, unittest.TestCase):
    def setUp(self):
        self.service = object.__new__(CatalogExtractService)
        self.cache = mock.Mock()
        self.service.db = mock.Mock(new_api=self.cache)
        self.extract_dir = self.make_temp_dir()
        patcher = mock.patch.dict("webserver.services.extract.CONF",
                                  {"extract_path": self.extract_dir})
        patcher.start()
        self.addCleanup(patcher.stop)
        extract_patcher = mock.patch("webserver.services.extract.ExtractService")
        self.extract_cls = extract_patcher.start()
        self.addCleanup(extract_patcher.stop)
        # 让短路检查拿到的是一条真实的（默认不存在的）路径，而不是 Mock
        self.extract_cls.return_value.txt_content_path.side_effect = \
            lambda bid: os.path.join(self.extract_dir, str(bid), "content.json")
        # 复刻真实实现：判的是「可用」而非「存在」，坏文件会被删掉
        self.extract_cls.return_value.has_txt_content_index.side_effect = \
            lambda bid: load_txt_content_index(
                os.path.join(self.extract_dir, str(bid), "content.json")) is not None

    def test_enqueues_on_preheat_channel(self):
        """预热必须走预热专用队列：读者可见的 que 只统计 parse_txt_content"""
        path = self.make_temp_file()
        self.service.db.format_abspath.return_value = path

        self.assertTrue(self.service._warm_txt_reader_cache(1))
        self.extract_cls.return_value.preheat_txt_content.assert_called_once_with(1, path)
        self.extract_cls.return_value.parse_txt_content.assert_not_called()

    def test_existing_index_is_not_enqueued_again(self):
        """目录提取刚同步写好的索引不该再排一个只会空跑的任务"""
        os.makedirs(os.path.join(self.extract_dir, "1"), exist_ok=True)
        with open(os.path.join(self.extract_dir, "1", "content.json"), "w", encoding="utf8") as f:
            json.dump(TXT_TOC, f)

        self.assertFalse(self.service._warm_txt_reader_cache(1))
        self.extract_cls.return_value.preheat_txt_content.assert_not_called()

    def test_broken_index_is_rebuilt(self):
        """半截 json 不能被当成"已有索引"：force=False 全库批量会一直跳过它，
        索引就只能等读者真打开才自愈 —— 这里要求预热顺手重建"""
        os.makedirs(os.path.join(self.extract_dir, "1"), exist_ok=True)
        broken = os.path.join(self.extract_dir, "1", "content.json")
        with open(broken, "w", encoding="utf8") as f:
            f.write('{"encoding": "utf-8", "toc": [')
        path = self.make_temp_file()
        self.service.db.format_abspath.return_value = path

        self.assertTrue(self.service._warm_txt_reader_cache(1))
        self.extract_cls.return_value.preheat_txt_content.assert_called_once_with(1, path)
        self.assertFalse(os.path.exists(broken))

    def test_skips_books_without_txt_format(self):
        """没有 TXT 格式时 format_abspath 抛异常（NoSuchFormat），当跳过处理"""
        self.service.db.format_abspath.side_effect = RuntimeError("No TXT format")

        self.assertFalse(self.service._warm_txt_reader_cache(1))
        self.extract_cls.return_value.preheat_txt_content.assert_not_called()

    def test_skips_missing_file(self):
        self.service.db.format_abspath.return_value = "/no/such/book.txt"

        self.assertFalse(self.service._warm_txt_reader_cache(1))
        self.extract_cls.return_value.preheat_txt_content.assert_not_called()

    def test_lookup_error_is_swallowed(self):
        """预热只是优化，查库异常不能冒泡打断目录提取"""
        self.service.db.format_abspath.side_effect = RuntimeError("db closed")

        self.assertFalse(self.service._warm_txt_reader_cache(1))
        self.extract_cls.return_value.preheat_txt_content.assert_not_called()


class TestCacheTxtReaderIndex(unittest.TestCase):
    def setUp(self):
        self.service = object.__new__(CatalogExtractService)
        self.service.db = mock.Mock(new_api=mock.Mock())

    @mock.patch("webserver.services.extract.ExtractService")
    def test_delegates_with_overwrite(self, extract_cls):
        """强制重提取时索引也要跟着刷新，否则章的 start/end 会和正文错位"""
        extract_cls.return_value.store_txt_content.return_value = True

        self.assertTrue(self.service._cache_txt_reader_index(7, TXT_TOC))
        extract_cls.return_value.store_txt_content.assert_called_once_with(7, TXT_TOC, overwrite=True)

    @mock.patch("webserver.services.extract.ExtractService")
    def test_noop_for_non_txt_formats(self, extract_cls):
        """EPUB/PDF 分支拿不到解析结果，不应落下空索引"""
        self.assertFalse(self.service._cache_txt_reader_index(7, None))
        extract_cls.return_value.store_txt_content.assert_not_called()

    @mock.patch("webserver.services.extract.ExtractService")
    def test_write_error_is_swallowed(self, extract_cls):
        extract_cls.return_value.store_txt_content.side_effect = OSError("disk full")
        self.assertFalse(self.service._cache_txt_reader_index(7, TXT_TOC))


class TestPreheatChannel(unittest.TestCase):
    """预热必须走自己的服务队列。

    parse_txt_content 的队列长度是读者可见的（/api/book/txt/parser 的 que），
    批量预热的几千个任务绝不能挤进去；两个函数不同 → _service_key 不同 →
    两条队列两条线程，读者请求不会排在预热后面。
    """

    def _enqueue(self, method_name, *args):
        queue = mock.Mock()
        with mock.patch.object(AsyncService, "setup", return_value=False):
            with mock.patch.object(AsyncService, "async_mode", return_value=True):
                with mock.patch.object(AsyncService, "start_service", return_value=queue) as start:
                    getattr(ExtractService(), method_name)(*args)
        return start.call_args[0][0], queue

    def test_preheat_uses_its_own_service(self):
        preheat_func, preheat_queue = self._enqueue("preheat_txt_content", 3, "/lib/3/f.txt")
        parse_func, _ = self._enqueue("parse_txt_content", 3, "/lib/3/f.txt")

        self.assertEqual(preheat_func.__name__, "preheat_txt_content")
        self.assertEqual(parse_func.__name__, "parse_txt_content")
        self.assertIsNot(preheat_func, parse_func)
        preheat_queue.put.assert_called_once_with(((3, "/lib/3/f.txt"), {}))


class TestPreheatTxtContent(TempDirMixin, unittest.TestCase):
    """预热本体：幂等、失败不留痕（读者首读时还会再试一次）"""

    def setUp(self):
        self.service = object.__new__(ExtractService)
        self.extract_dir = self.make_temp_dir()
        self.path = os.path.join(self.extract_dir, "7", "content.json")
        patcher = mock.patch.dict("webserver.services.extract.CONF",
                                  {"extract_path": self.extract_dir})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.txt_path = self.make_temp_file()

    def _preheat(self, fpath=None):
        # async_mode=False 让 register_service 同步执行服务本体，不用起线程
        with mock.patch.object(AsyncService, "setup", return_value=False):
            with mock.patch.object(AsyncService, "async_mode", return_value=False):
                return self.service.preheat_txt_content(7, self.txt_path if fpath is None else fpath)

    def test_writes_index(self):
        with mock.patch.object(ExtractService, "parse_txt_toc", return_value=TXT_TOC):
            self.assertTrue(self._preheat())
        with open(self.path, encoding="utf8") as f:
            self.assertEqual(json.load(f), TXT_TOC)

    def test_existing_index_is_reused(self):
        with mock.patch.object(ExtractService, "parse_txt_toc", return_value=TXT_TOC):
            self._preheat()
        with mock.patch.object(ExtractService, "parse_txt_toc") as parse:
            self.assertFalse(self._preheat())
        parse.assert_not_called()

    def test_broken_index_is_rebuilt(self):
        """坏索引要当成「没有索引」重扫，而不是被 isfile 挡在门外"""
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w", encoding="utf8") as f:
            f.write('{"encoding": "utf-8", "toc": [')

        with mock.patch.object(ExtractService, "parse_txt_toc", return_value=TXT_TOC):
            self.assertTrue(self._preheat())

        with open(self.path, encoding="utf8") as f:
            self.assertEqual(json.load(f), TXT_TOC)

    def test_missing_source_is_skipped(self):
        with mock.patch.object(ExtractService, "parse_txt_toc") as parse:
            self.assertFalse(self._preheat(fpath="/no/such/book.txt"))
        parse.assert_not_called()
        self.assertFalse(os.path.exists(self.path))

    def test_parse_failure_writes_nothing(self):
        with mock.patch.object(ExtractService, "parse_txt_toc", side_effect=RuntimeError("boom")):
            self.assertFalse(self._preheat())
        self.assertFalse(os.path.exists(self.path))


class TestLoadTxtContentIndex(TempDirMixin, unittest.TestCase):
    """阅读接口只认「文件存在」，坏索引必须能自愈，否则永久 500"""

    def setUp(self):
        self.path = os.path.join(self.make_temp_dir(), "content.json")

    def test_returns_content_for_valid_index(self):
        with open(self.path, "w", encoding="utf8") as f:
            json.dump(TXT_TOC, f)

        self.assertEqual(load_txt_content_index(self.path),
                         {"content": TXT_TOC["toc"], "encoding": TXT_TOC["encoding"]})

    def test_truncated_json_is_dropped(self):
        with open(self.path, "w", encoding="utf8") as f:
            f.write('{"encoding": "utf-8", "toc": [')

        self.assertIsNone(load_txt_content_index(self.path))
        self.assertFalse(os.path.exists(self.path))

    def test_missing_key_is_dropped(self):
        with open(self.path, "w", encoding="utf8") as f:
            json.dump({"encoding": "utf-8"}, f)

        self.assertIsNone(load_txt_content_index(self.path))
        self.assertFalse(os.path.exists(self.path))

    def test_absent_file_returns_none(self):
        self.assertIsNone(load_txt_content_index(self.path))


class TestStoreTxtContent(TempDirMixin, unittest.TestCase):
    """落盘逻辑与阅读器首读共用，必须写出同构 json 且幂等"""

    def setUp(self):
        self.service = object.__new__(ExtractService)
        self.extract_dir = self.make_temp_dir()
        self.path = os.path.join(self.extract_dir, "7", "content.json")
        # patch 只在单线程的 setUp 里做：mock.patch.dict 退出时是「快照回写」，
        # 多线程各自进出会互相覆盖，把 CONF 永久留在临时目录上
        patcher = mock.patch.dict("webserver.services.extract.CONF",
                                  {"extract_path": self.extract_dir})
        patcher.start()
        self.addCleanup(patcher.stop)

    def _store(self, parsed=TXT_TOC, overwrite=False):
        return self.service.store_txt_content(7, parsed, overwrite=overwrite)

    def test_writes_content_json(self):
        self.assertTrue(self._store())
        with open(self.path, encoding="utf8") as f:
            self.assertEqual(json.load(f), TXT_TOC)

    def test_second_write_is_noop_and_keeps_content(self):
        self.assertTrue(self._store())
        self.assertFalse(self._store(parsed=SINGLE_CHAPTER_TOC))
        with open(self.path, encoding="utf8") as f:
            self.assertEqual(json.load(f), TXT_TOC)

    def test_overwrite_refreshes_stale_index(self):
        self.assertTrue(self._store())
        self.assertTrue(self._store(parsed=SINGLE_CHAPTER_TOC, overwrite=True))
        with open(self.path, encoding="utf8") as f:
            self.assertEqual(json.load(f), SINGLE_CHAPTER_TOC)

    def test_rejects_payload_without_toc(self):
        """阅读器裸取 meta['toc']，结构不对宁可写不进去"""
        self.assertFalse(self._store(parsed={"encoding": "utf-8"}))
        self.assertFalse(os.path.exists(self.path))

    def test_rejects_non_list_toc(self):
        """toc 不是非空 list 会写出一条 content=null 的"就绪"索引，阅读器永久打不开"""
        for toc in (None, "", {}, []):
            with self.subTest(toc=toc):
                self.assertFalse(self._store(parsed={"encoding": "utf-8", "toc": toc}))
                self.assertFalse(os.path.exists(self.path))

    def test_write_failure_returns_false_and_cleans_tmp(self):
        with mock.patch("os.replace", side_effect=OSError("disk full")):
            self.assertFalse(self._store())
        self.assertFalse(os.path.exists(self.path))
        leftovers = [n for n in os.listdir(os.path.dirname(self.path)) if n.endswith(".tmp")]
        self.assertEqual(leftovers, [])

    def test_concurrent_writes_leave_readable_json(self):
        """两条写入路径（目录提取 / 阅读器首读）可能同时写同一本，读方绝不能拿到半截文件"""
        errors = []

        def worker(payload):
            try:
                self._store(parsed=payload, overwrite=True)
            except Exception as e:  # pragma: no cover - 失败时由 errors 暴露
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(payload,))
                   for payload in (TXT_TOC, SINGLE_CHAPTER_TOC) * 8]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [])
        with open(self.path, encoding="utf8") as f:
            self.assertIn(json.load(f), (TXT_TOC, SINGLE_CHAPTER_TOC))


class TestExtractOneWritesReaderIndex(TempDirMixin, unittest.TestCase):
    """TXT 书提取目录时，同一次整本扫描的结果应同时产出 #catalog 与 content.json"""

    def setUp(self):
        self.service = object.__new__(CatalogExtractService)
        self.cache = mock.Mock()
        self.cache.has_id.return_value = True
        self.service.db = mock.Mock(new_api=self.cache)
        self.extract_dir = self.make_temp_dir()
        patcher = mock.patch.dict("webserver.services.extract.CONF",
                                  {"extract_path": self.extract_dir})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.txt_path = self.make_temp_file()

    def _extract(self, formats, parsed=None, side_effect=None):
        self.cache.formats.return_value = formats
        self.service.db.format_abspath.return_value = self.txt_path
        with mock.patch.object(ExtractService, "parse_txt_toc",
                               return_value=parsed, side_effect=side_effect) as parse:
            ret = self.service._extract_one(7, True)
        return ret, parse

    def _read_index(self):
        with open(os.path.join(self.extract_dir, "7", "content.json"), encoding="utf8") as f:
            return json.load(f)

    def test_txt_extraction_writes_both_caches(self):
        ret, _ = self._extract(["TXT"], parsed=TXT_TOC)

        self.assertEqual(ret["err"], "ok")
        self.assertIn("第一章 起", ret["catalog"])
        self.cache.set_field.assert_called_once()
        self.assertEqual(self._read_index(), TXT_TOC)

    def test_single_chapter_still_writes_reader_index(self):
        """目录不足两行时 #catalog 留空，但阅读索引照写（单章兜底可读，省一次首读扫描）"""
        ret, _ = self._extract(["TXT"], parsed=SINGLE_CHAPTER_TOC)

        self.assertEqual(ret["err"], "catalog.not_found")
        self.cache.set_field.assert_called_once_with(CALIBRE_COLUMN_CATALOG, {7: ""})
        self.assertEqual(self._read_index(), SINGLE_CHAPTER_TOC)

    def test_parse_error_writes_nothing(self):
        ret, _ = self._extract(["TXT"], side_effect=RuntimeError("bad encoding"))

        self.assertEqual(ret["err"], "catalog.not_found")
        self.assertFalse(os.path.exists(os.path.join(self.extract_dir, "7", "content.json")))

    def test_parse_timeout_reports_friendly_message(self):
        """超时算 fail，但别把带绝对路径的原始异常串甩到前端"""
        ret, _ = self._extract(["TXT"], side_effect=subprocess.TimeoutExpired(cmd="parser", timeout=600))

        self.assertEqual(ret["err"], "catalog.not_found")
        self.assertIn("超时", ret["msg"])
        self.assertNotIn("timed out", ret["msg"])

    def test_epub_extraction_leaves_txt_index_alone(self):
        """EPUB 优先命中时不该写 TXT 索引（内容来自 EPUB，没有 TXT 解析结果）"""
        epub_path = self.make_temp_file(suffix=".epub")
        self.cache.formats.return_value = ["EPUB", "TXT"]
        self.service.db.format_abspath.return_value = epub_path
        self.service._extract_epub_toc = mock.Mock(return_value="- 第一章\n- 第二章")

        ret = self.service._extract_one(7, True)

        self.assertEqual(ret["err"], "ok")
        self.assertFalse(os.path.exists(os.path.join(self.extract_dir, "7", "content.json")))


class TestExtractOneEntryWarms(unittest.TestCase):
    """单本提取入口（同步 / 异步）也要预热，书不存在时不要白跑"""

    def setUp(self):
        self.service = object.__new__(CatalogExtractService)
        self.service.db = mock.Mock(new_api=mock.Mock())

    def _call(self, method_name, ret):
        self.service._extract_one = mock.Mock(return_value=ret)
        self.service._warm_txt_reader_cache = mock.Mock(return_value=True)
        with mock.patch.object(AsyncService, "setup", return_value=False):
            with mock.patch.object(AsyncService, "async_mode", return_value=False):
                return getattr(self.service, method_name)(7)

    def test_extract_one_warms_and_returns_result(self):
        ret = {"err": "ok", "format": "TXT", "catalog": "- 第一章"}
        self.assertEqual(self._call("extract_one", ret), ret)
        self.service._warm_txt_reader_cache.assert_called_once_with(7)

    def test_extract_one_async_warms(self):
        self._call("extract_one_async", {"err": "ok"})
        self.service._warm_txt_reader_cache.assert_called_once_with(7)

    def test_missing_book_is_not_warmed(self):
        for method_name in ("extract_one", "extract_one_async"):
            with self.subTest(method=method_name):
                self._call(method_name, {"err": "book.not_found"})
                self.service._warm_txt_reader_cache.assert_not_called()

    def test_failed_extraction_is_not_warmed(self):
        """刚解析失败的书不能重排预热：超时那本会把单线程解析队列占住最长 2 小时"""
        for method_name in ("extract_one", "extract_one_async"):
            for ret in ({"err": "catalog.not_found", "msg": "TXT格式解析超时"},
                        {"err": "internal"}):
                with self.subTest(method=method_name, err=ret["err"]):
                    self._call(method_name, ret)
                    self.service._warm_txt_reader_cache.assert_not_called()


class TestBatchWarmsSkippedBooks(unittest.TestCase):
    """全库模式会跳过已有目录的书，但这些书的阅读索引同样要预热"""

    def setUp(self):
        self.service = object.__new__(CatalogExtractService)
        self.cache = mock.Mock()
        self.service.db = mock.Mock(new_api=self.cache)
        self.service.task_id = None
        self.service.start_time = 0
        self.service.add_msg = mock.Mock()
        self.service._update_task_progress = mock.Mock()

    def _run_batch(self, book_ids):
        # extract_batch 是 @register_service：默认会入队到后台线程。
        # 这里把 async_mode 关掉让它同步执行（该方法注释即 "for unittest"）。
        with mock.patch.object(AsyncService, "setup", return_value=False):
            with mock.patch.object(AsyncService, "async_mode", return_value=False):
                with mock.patch("webserver.services.catalog.BackgroundService"):
                    self.service.extract_batch(1, book_ids, force=False)

    def test_warm_covers_skipped_books(self):
        self.service._extract_one = mock.Mock(return_value={
            "err": "ok", "skipped": True, "msg": "已有目录信息，跳过"})
        self.service._warm_txt_reader_cache = mock.Mock(return_value=True)

        self._run_batch([11, 12])

        self.assertEqual(self.service.count_skip, 2)
        self.assertEqual(self.service.count_txt_warm, 2)
        self.assertEqual(self.service._warm_txt_reader_cache.call_count, 2)

    def test_missing_book_not_warmed(self):
        self.service._extract_one = mock.Mock(return_value={
            "err": "book.not_found", "skipped": True, "msg": "书籍不存在"})
        self.service._warm_txt_reader_cache = mock.Mock(return_value=True)

        self._run_batch([11])

        self.service._warm_txt_reader_cache.assert_not_called()
        self.assertEqual(self.service.count_txt_warm, 0)

    def test_failed_book_not_warmed(self):
        """解析失败的书不排预热（同一份输入只会再失败一次，还占住队列）"""
        self.service._extract_one = mock.Mock(return_value={
            "err": "catalog.not_found", "skipped": False, "msg": "TXT格式解析超时"})
        self.service._warm_txt_reader_cache = mock.Mock(return_value=True)

        self._run_batch([11])

        self.service._warm_txt_reader_cache.assert_not_called()
        self.assertEqual(self.service.count_fail, 1)
        self.assertEqual(self.service.count_txt_warm, 0)


if __name__ == "__main__":
    unittest.main()
