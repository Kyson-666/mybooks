#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
从书籍文件中提取目录结构（EPUB > PDF > TXT）
@author: PoxenStudio, 2026
"""

import logging
import os
import subprocess
import time
import traceback

from webserver.i18n import _
from webserver.constants import CALIBRE_COLUMN_CATALOG
from webserver.services import AsyncService
from webserver.services.background_service import BackgroundService, BackgroundTask

# 目录提取的格式优先级：其他格式（mobi/azw3/docx等）暂无可靠的目录提取方案，先忽略
CATALOG_FORMAT_PRIORITY = ["EPUB", "PDF", "TXT"]
MAX_TITLE_LENGTH = 200
MAX_CATALOG_LEN = 204800


class CatalogExtractService(AsyncService):
    def __init__(self):
        AsyncService.__init__(self)
        self.task_id = None
        self.start_time = None
        self.is_running = False
        self.current_book_id = None
        self.count_total = 0
        self.count_done = 0
        self.count_fail = 0
        self.count_skip = 0
        self.count_txt_warm = 0

    def status(self):
        return {
            "is_running": self.is_running,
            "current_book_id": self.current_book_id,
            "start_time": self.start_time,
            "count_total": self.count_total,
            "count_done": self.count_done,
            "count_fail": self.count_fail,
            "count_skip": self.count_skip,
            "count_txt_warm": self.count_txt_warm,
            "task_id": self.task_id,
        }

    def _update_task_progress(self):
        if not self.task_id:
            return
        try:
            processed = self.count_done + self.count_fail + self.count_skip
            progress = int(processed * 100 / self.count_total) if self.count_total else 100
            BackgroundService().update_progress(
                task_id=self.task_id,
                progress=progress,
                progress_data={
                    "total": self.count_total,
                    "done": self.count_done,
                    "fail": self.count_fail,
                    "skip": self.count_skip,
                    "txt_warm": self.count_txt_warm,
                    "current_book_id": self.current_book_id,
                },
            )
        except Exception as e:
            logging.error("[Catalog] Failed to update task progress: %s", e)

    def _md_line(self, title, depth):
        title = (title or "").strip().replace("\n", " ")
        if not title:
            return None
        if len(title) > MAX_TITLE_LENGTH:
            title = title[:MAX_TITLE_LENGTH] + "..."
        return "%s- %s" % ("  " * max(depth, 0), title)

    def _extract_epub_toc(self, fpath):
        from ebooklib import epub

        lines = []

        try:
            book = epub.read_epub(fpath, {"ignore_ncx": True})
        except Exception as e:
            book = None
            logging.error(f"Failed to load book from {fpath}, error: {e}")

        if not book:
            return lines

        def walk(items, depth):
            for item in items or []:
                if isinstance(item, tuple) and len(item) == 2:
                    section, children = item
                    line = self._md_line(getattr(section, "title", None), depth)
                    if line:
                        lines.append(line)
                    walk(children, depth + 1)
                else:
                    line = self._md_line(getattr(item, "title", None), depth)
                    if line:
                        lines.append(line)
                    walk(getattr(item, "children", None), depth + 1)

        walk(book.toc, 0)
        return "\n".join(lines)

    def _extract_pdf_toc(self, fpath):
        import fitz

        doc = fitz.open(fpath)
        try:
            toc = doc.get_toc() or []
        finally:
            doc.close()
        lines = []
        for level, title, _page in toc:
            line = self._md_line(title, level - 1)
            if line:
                lines.append(line)
        return "\n".join(lines)

    def _extract_txt_toc(self, fpath):
        """返回 (markdown, 解析结果)。后者用于顺带写阅读器索引，避免二次全扫。

        走 ExtractService.parse_txt_toc 而不是进程内 TxtParser：整本扫描是纯
        Python 循环，extract_one 跑在 IOLoop 线程上时会把接口拖到秒级。
        """
        from webserver.services.extract import ExtractService

        result = ExtractService().parse_txt_toc(fpath)
        lines = []
        for item in result.get("toc", []):
            line = self._md_line(item.get("title"), 0)
            if line:
                lines.append(line)
        return "\n".join(lines), result

    @staticmethod
    def _store_catalog(cache, book_id, value):
        try:
            cache.set_field(CALIBRE_COLUMN_CATALOG, {book_id: value})
            return True
        except Exception:
            if cache.has_id(book_id):
                raise
            logging.info("[Catalog] book %s was deleted during extraction, skip", book_id)
            return False

    def _cache_txt_reader_index(self, book_id, parsed):
        """把本次 TXT 解析结果交给 ExtractService 落成阅读器索引。

        批量提取时 TXT 本来就要整本扫一遍（为了生成 #catalog），这里复用同一份
        解析结果，避免预热队列把同一本书再扫一遍；落盘格式与阅读器首读完全一致。
        overwrite=True：手上就是刚解析出的结果，旧索引的 start/end 偏移要一起刷新
        （强制重提取时 #catalog 会更新，索引不跟就会与正文错位）。
        """
        if not parsed:
            return False
        try:
            # 延迟导入：避免 catalog 模块加载时就拉起 parser/extract 依赖
            from webserver.services.extract import ExtractService

            return ExtractService().store_txt_content(book_id, parsed, overwrite=True)
        except Exception as e:
            # 写索引只是附带优化，失败不能影响目录提取本身
            logging.debug("[Catalog] write txt reader index skipped book=%s: %s", book_id, e)
            return False

    def _warm_txt_reader_cache(self, book_id):
        """给含 TXT 的书排队生成阅读器章节索引(content.json)。

        目录提取写的是 calibre 列 #catalog，内建 TXT 阅读器读的却是
        extract_path/<id>/content.json，两套缓存互不相干。这里把后者顺带
        预热掉，批量提取跑完后 TXT 打开即出目录。parse_txt_content 幂等
        且异步入队，不阻塞本次提取。
        """
        try:
            # 延迟导入：避免 catalog 模块加载时就拉起 parser/extract 依赖
            from webserver.services.extract import ExtractService

            extract_service = ExtractService()
            # 刚才的目录提取可能已经同步写好索引，别再排一个只会空跑的任务：
            # 队列长度会直接显示给读者（/api/book/txt/parser 的 que），虚高会误导人
            if os.path.isfile(extract_service.txt_content_path(book_id)):
                return False
            cache = self.db.new_api
            if "TXT" not in set(cache.formats(book_id, verify_formats=False) or []):
                return False
            fpath = self.db.format_abspath(book_id, "TXT", index_is_id=True)
            if not fpath or not os.path.isfile(fpath):
                return False
            extract_service.parse_txt_content(book_id, fpath)
            return True
        except Exception as e:
            # 预热只是优化，失败不能影响目录提取本身
            logging.debug("[Catalog] txt reader cache warm-up skipped book=%s: %s", book_id, e)
            return False

    def _extract_one(self, book_id, force):
        cache = self.db.new_api
        if not cache.has_id(book_id):
            return {"err": "book.not_found", "skipped": True, "msg": _("书籍不存在")}
        if not force:
            existing = (cache.field_for(CALIBRE_COLUMN_CATALOG, book_id) or "").strip()
            if existing:
                return {"err": "ok", "skipped": True, "msg": _("已有目录信息，跳过")}

        available = set(cache.formats(book_id, verify_formats=False) or [])
        last_error = _("书籍不包含可提取目录的格式（EPUB/PDF/TXT）")
        skipped = True
        for fmt in CATALOG_FORMAT_PRIORITY:
            if fmt not in available:
                continue
            fpath = self.db.format_abspath(book_id, fmt, index_is_id=True)
            if not fpath or not os.path.isfile(fpath):
                continue
            skipped = False
            txt_parsed = None
            try:
                if fmt == "EPUB":
                    markdown = self._extract_epub_toc(fpath)
                elif fmt == "PDF":
                    markdown = self._extract_pdf_toc(fpath)
                else:
                    markdown, txt_parsed = self._extract_txt_toc(fpath)
            except subprocess.TimeoutExpired:
                # 子进程超时是「这本书太大/太慢」，不是磁盘或解析器坏了：
                # 原始异常串会把绝对路径和秒数糊到前端提示里，这里换成可读文案
                logging.warning("[Catalog] txt parse timeout book=%s fmt=%s", book_id, fmt)
                last_error = _("%s格式解析超时") % fmt
                continue
            except Exception as e:
                logging.warning("[Catalog] extract failed for book=%s fmt=%s: %s", book_id, fmt, e)
                logging.debug(traceback.format_exc())
                last_error = str(e)
                continue

            if markdown and len(markdown.splitlines()) > 1:
                if len(markdown) > MAX_CATALOG_LEN:
                    markdown = markdown[:MAX_CATALOG_LEN] + "\n\n* 目录过长，已被截断*"
                if not self._store_catalog(cache, book_id, markdown):
                    return {"err": "book.not_found", "skipped": True, "msg": _("书籍不存在")}
                self._cache_txt_reader_index(book_id, txt_parsed)
                return {"err": "ok", "format": fmt, "catalog": markdown}
            elif not self._store_catalog(cache, book_id, ""):
                return {"err": "book.not_found", "skipped": True, "msg": _("书籍不存在")}
            # 只命中「目录不足两行」这一分支：#catalog 留空（不污染页面展示），
            # 但阅读索引照写 —— 单章兜底也能让阅读器直接打开，省掉首读整本扫描
            self._cache_txt_reader_index(book_id, txt_parsed)
            last_error = _("未能从%s格式中解析出目录") % fmt

        return {"err": "catalog.not_found", "skipped": skipped, "msg": last_error}

    @AsyncService.register_function
    def extract_one(self, book_id, force=True):
        """提取单本书籍的目录，默认强制重新提取"""
        ret = self._extract_one(book_id, force)
        if ret.get("err") != "book.not_found":
            self._warm_txt_reader_cache(book_id)
        return ret

    @AsyncService.register_service
    def extract_one_async(self, book_id, force=True):
        ret = self._extract_one(book_id, force)
        if ret.get("err") != "book.not_found":
            self._warm_txt_reader_cache(book_id)

    @AsyncService.register_service
    def extract_batch(self, uid, book_ids, force=False):
        """批量提取，force=False 时跳过已有目录信息的书籍"""
        self.is_running = True
        self.start_time = time.time()
        self.count_done = 0
        self.count_fail = 0
        self.count_skip = 0
        self.count_txt_warm = 0
        self.count_total = len(book_ids)

        if not book_ids:
            logging.info("[Catalog] No books to extract, exiting")
            self.is_running = False
            return

        logging.info("[Catalog] Starting batch extract for %d books, force=%s", self.count_total, force)

        try:
            task = BackgroundService().update_task(
                service_type=BackgroundTask.SERVICE_TYPE_CATALOG_EXTRACT,
                service_item="提取图书目录",
                progress=0,
                progress_data={
                    "total": self.count_total,
                    "done": 0,
                    "fail": 0,
                    "skip": 0,
                },
            )
            self.task_id = task.id
        except Exception as e:
            logging.error("[Catalog] Failed to create background task: %s", e)
            self.task_id = None

        try:
            for index, book_id in enumerate(book_ids):
                self.current_book_id = book_id
                try:
                    ret = self._extract_one(book_id, force)
                except Exception as e:
                    logging.error("[Catalog] batch extract error book=%s: %s", book_id, e)
                    ret = {"err": "internal"}
                if ret.get("skipped"):
                    self.count_skip += 1
                elif ret.get("err") != "ok":
                    self.count_fail += 1
                    logging.info("[Catalog] Failed to extract book=%s: %s", book_id, ret.get("msg", "Unknown error"))
                else:
                    self.count_done += 1

                # 已跳过（目录已存在）的书同样要预热阅读索引，否则老书依旧要等首读
                if ret.get("err") != "book.not_found" and self._warm_txt_reader_cache(book_id):
                    self.count_txt_warm += 1

                if (index + 1) % 100 == 0:
                    self._update_task_progress()
        finally:
            self._update_task_progress()

            if self.task_id:
                try:
                    BackgroundService().complete_task(task_id=self.task_id)
                except Exception as e:
                    logging.error("[Catalog] Failed to complete task: %s", e)

            logging.info(
                "[Catalog] Completed: total=%d, done=%d, skip=%d, fail=%d, txt_warm=%d, elapsed=%.1fs",
                self.count_total, self.count_done, self.count_skip, self.count_fail,
                self.count_txt_warm, time.time() - self.start_time,
            )

            self.add_msg(
                user_id=uid,
                status="success",
                msg=_("目录提取完成：共%d本，成功%d，跳过%d，失败%d") % (
                    self.count_total, self.count_done, self.count_skip, self.count_fail),
            )

            self.is_running = False
            self.current_book_id = None
            self.task_id = None
