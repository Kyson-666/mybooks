#!/usr/bin/env python3
# -*- coding: UTF-8 -*-

import json
import os
import logging
import subprocess
import sys
import threading
import time
import traceback

from webserver import loader
from webserver.services import AsyncService
from webserver.plugins.parser.txt import TxtParser

CONF = loader.get_settings()


def load_txt_content_index(content_path):
    """读取 TXT 阅读索引；文件写坏时删掉并返回 None，让调用方重新解析。

    "content.json 存在"是阅读器唯一的就绪信号，一旦里面是半截 json（旧版本
    非原子写入、进程被杀、磁盘写满），阅读接口就会永久 500 且没有任何自愈
    路径。这里把"读不动"退化成"没解析过"，代价只是重扫一次。
    """
    if not os.path.isfile(content_path):
        return None
    try:
        with open(content_path, 'r', encoding='utf8') as f:
            meta = json.loads(f.read())
        return {"content": meta['toc'], "encoding": meta['encoding']}
    except (OSError, ValueError, KeyError) as e:
        logging.warning("Broken txt content index, rebuilding: %s (%s)", content_path, e)
        try:
            os.remove(content_path)
        except OSError:
            pass
        return None


class ExtractService(AsyncService):
    # 整本扫描是 CPU 密集的纯 Python 循环，留在服务进程里会和 Tornado 抢 GIL：
    # 实测 24MB / 30 万行的书会把接口延迟从 5ms 拉到数秒。所以默认放到独立子
    # 进程里跑，起不了子进程时（冻结解释器等）回退为进程内解析。
    #
    # 超时只是「卡死兜底」而非性能预算，按体积线性放宽：1MB 给 60s（实测约
    # 0.6s/MB，留两个数量级余量），下限 10 分钟、上限 2 小时。
    TXT_PARSE_TIMEOUT_MIN = 600
    TXT_PARSE_TIMEOUT_MAX = 7200
    TXT_PARSE_TIMEOUT_PER_MB = 60
    # 章节扫描脚本，子进程入口（顶层可执行，见 webserver/plugins/parser/txt.py）
    TXT_PARSER_SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                     "plugins", "parser", "txt.py")

    @staticmethod
    def txt_content_path(bid):
        """TXT 阅读器章节索引的落盘路径"""
        return os.path.join(CONF["extract_path"], str(bid), "content.json")

    def store_txt_content(self, bid, parsed, overwrite=False):
        """把已解析出的目录写成阅读器索引。

        单独抽出来是给目录提取复用：那边为了生成 #catalog 已经把整本扫过一遍，
        拿到的 `{encoding, toc}` 与这里完全同构，直接落盘就不用再排一次解析。
        overwrite=True 用于强制重新提取目录的场景 —— 此时手上就是刚解析出的
        最新结果，旧的 start/end 偏移必须一起刷新，否则目录与正文会错位。
        """
        if not parsed or "toc" not in parsed:
            return False
        content_path = self.txt_content_path(bid)
        if not overwrite and os.path.isfile(content_path):
            logging.debug(f"书籍<{bid}>已有目录索引, {content_path} exists")
            return False
        # 每条写入用独立临时名：两个写入方（目录提取 / 阅读器首读）可能同时写同一本
        tmp = "%s.%d.tmp" % (content_path, threading.get_ident())
        try:
            os.makedirs(os.path.dirname(content_path), exist_ok=True)
            with open(tmp, "w", encoding="utf8") as f:
                json.dump(parsed, f, ensure_ascii=False)
            # 原子替换：读方要么看到旧文件，要么看到完整的新文件。
            # Windows 上读方正打开 content.json 时 replace 会 PermissionError
            # （CPython 的 open 不共享 DELETE），短暂重试即可，别把刷新吞掉
            for attempt in range(3):
                try:
                    os.replace(tmp, content_path)
                    break
                except OSError:
                    if attempt == 2:
                        raise
                    time.sleep(0.05)
            return True
        except Exception as e:
            logging.warning(f"Failed to store txt content for book {bid}: {e}")
            return False
        finally:
            if os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass

    @AsyncService.register_service
    def parse_txt_content(self, bid, fpath):
        '''从TXT文件中提取目录并存储为json'''
        content_path = self.txt_content_path(bid)
        if os.path.isfile(content_path):
            logging.debug(f"书籍<{bid}>已转换, {content_path} exists")
            return False

        try:
            ret = self.parse_txt_toc(fpath)
        except Exception as e:
            logging.info(f"TXT convert error: {e}")
            logging.error(traceback.format_exc())
            return False
        return self.store_txt_content(bid, ret)

    def txt_parse_timeout(self, fpath):
        """按文件体积放宽的子进程超时；解析耗时随体积线性增长，慢机器上大文件
        远超固定值，固定超时会把正常解析误判成失败。"""
        try:
            size_mb = os.path.getsize(fpath) / (1024 * 1024)
        except OSError:
            return self.TXT_PARSE_TIMEOUT_MIN
        return min(self.TXT_PARSE_TIMEOUT_MAX,
                   max(self.TXT_PARSE_TIMEOUT_MIN, size_mb * self.TXT_PARSE_TIMEOUT_PER_MB))

    def parse_txt_toc(self, fpath):
        """优先在独立子进程里解析目录；子进程不可用时回退为进程内解析"""
        if not sys.executable or getattr(sys, "frozen", False):
            return TxtParser().parse(fpath)
        if not os.path.isfile(self.TXT_PARSER_SCRIPT):
            logging.warning("TXT parser script not found: %s", self.TXT_PARSER_SCRIPT)
            return TxtParser().parse(fpath)

        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        try:
            proc = subprocess.run([sys.executable, self.TXT_PARSER_SCRIPT, fpath],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  env=env, timeout=self.txt_parse_timeout(fpath))
        except subprocess.TimeoutExpired:
            # 超时意味着整本扫描跑不完，进程内回退只会更慢、还会独占 GIL，直接失败
            raise
        except Exception as e:
            logging.warning("TXT parser subprocess failed, fallback in-process: %s", e)
            return TxtParser().parse(fpath)

        if proc.returncode != 0:
            logging.warning("TXT parser subprocess exit=%s, fallback in-process: %s",
                            proc.returncode, proc.stderr.decode("utf-8", "replace")[-500:])
            return TxtParser().parse(fpath)

        try:
            return json.loads(proc.stdout.decode("utf-8"))
        except Exception as e:
            logging.warning("TXT parser subprocess output invalid, fallback in-process: %s", e)
            return TxtParser().parse(fpath)
