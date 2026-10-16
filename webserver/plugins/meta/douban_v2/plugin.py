#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
# @author: PoxenStudio, 2026-06

import logging
import traceback

from webserver import loader
from webserver.i18n import _
from webserver.base.request_counter import RequestCounter
from webserver.constants import META_SOURCE_DOUBAN_V2
from webserver.plugins.meta.base import MetaSourcePlugin

from . import api
from .api import KEY

CONF = loader.get_settings()


def _max_count():
    return max(1, min(int(CONF.get("douban_max_count", 2)), 5))


class DoubanV2MetaPlugin(MetaSourcePlugin):
    """豆瓣(V2)信息源插件 —— 仅使用 subject_search 接口，不发二次详情请求。"""

    SOURCE_KEYS: tuple = (META_SOURCE_DOUBAN_V2, )
    PROVIDER_KEY = KEY

    MAX_REQUESTS_PER_HOUR = max(1, int(CONF.get("douban_v2_max_per_hour", 180) or 180))
    # 插件每次调用都会新建实例，计数器必须挂在类上才能跨实例共享
    _counter = RequestCounter(MAX_REQUESTS_PER_HOUR)

    @classmethod
    def throttle_wait_seconds(cls):
        """预算耗尽时返回距预算真正可用的秒数，否则 None。

        用 seconds_until_budget_available 而非 seconds_until_window_end：
        突发额度耗尽后下一窗口整体拒绝，只等到本窗尾会展示过早的恢复时间。
        供批量抓取方（autofill）主动让路：与其让本插件静默跳过（书拿不到
        元数据且无感知），不如暂停等预算恢复后继续。
        """
        if not cls._counter.is_exceeded():
            return None
        return cls._counter.seconds_until_budget_available()

    @classmethod
    def _acquire(cls):
        """未超限则计入一次请求并返回 True；超限返回 False"""
        counter = cls._counter
        if counter.is_exceeded():
            logging.warning("[DoubanV2]请求频率已达上限（每小时 %d 次，每 %d 秒最多 %d 次），本次请求被跳过", cls.MAX_REQUESTS_PER_HOUR, counter.window_seconds, counter.limit)
            return False
        counter.record()
        return True

    def search(self, title=None, isbn=None, publisher=None):
        query = isbn or title
        if not query or not self._acquire():
            return []
        items, search_url = api.search(query, max_count=_max_count())
        return api.build_metadata_batch(items, search_url, isbn=isbn, copy_image=False, get_detail=True)

    def search_best(self, mi):
        query = mi.isbn or mi.title
        if not query:
            logging.warning("[DoubanV2]search_best 跳过：isbn 和 title 均为空")
            return None
        if not self._acquire():
            logging.warning("[DoubanV2]search_best 跳过 %s：本地请求频率限制", query)
            return None
        result = api.search(query, max_count=_max_count(), skip_error=True)
        if not result:
            logging.warning("[DoubanV2]%s 查询返回错误响应，已跳过", query)
            return None
        items, search_url = result
        if not items:
            logging.warning("[DoubanV2]search_best %s 无结果", query)
            return None
        if items[0].get("title", "") == "BLOCKED":
            logging.warning("[DoubanV2]search_best %s 被豆瓣限制访问：%s", query, items[0].get("summary", ""))
            return None
        # 优先取标题完全匹配的，否则取首个结果
        best = next((i for i in items if i.get("title") == mi.title), items[0])
        try:
            return api.build_metadata(best, search_url, isbn=getattr(mi, "isbn", None), copy_image=True, get_detail=True)
        except Exception:
            logging.error(_("[DoubanV2]查询 %s 失败"), query, exc_info=True)
            return None

    def get_metadata_by_provider(self, provider_value, item=None):
        # 按标题重新搜索，找到 provider_value 匹配的条目后下载封面
        if not item or not self._acquire():
            return None
        try:
            return api.build_metadata(
                item, "https://book.douban.com",
                isbn=None,
                copy_image=True,
                get_detail=True
            )
        except Exception as e:
            logging.error("[DoubanV2]获取详情失败，provider_value=%s", provider_value)
            logging.error(f"[DoubanV2] Exception {e}")
            logging.error(f"[DoubanV2] {traceback.format_exc()}")

        return None

    def get_cover(self, cover_url):
        return api.get_cover(cover_url)

    def search_physical_by_isbn(self, isbn):
        """按 ISBN 精确查询实体书信息（用于 BookSearch.find_physical_book_by_isbn 兜底链）"""
        if not isbn or not self._acquire():
            return None
        items, search_url = api.search(isbn, max_count=1)
        if not items:
            return None
        try:
            return api.build_metadata(items[0], search_url, isbn=isbn, copy_image=True)
        except Exception:
            logging.error("[DoubanV2] ISBN查询 %s 失败", isbn)
            return None
