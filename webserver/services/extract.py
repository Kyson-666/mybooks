#!/usr/bin/env python3
# -*- coding: UTF-8 -*-

import json
import os
import logging
import subprocess
import sys
import traceback

from webserver import loader
from webserver.services import AsyncService
from webserver.plugins.parser.txt import TxtParser

CONF = loader.get_settings()


class ExtractService(AsyncService):
    # 整本扫描是 CPU 密集的纯 Python 循环，留在服务进程里会和 Tornado 抢 GIL：
    # 实测 24MB / 30 万行的书会把接口延迟从 5ms 拉到数秒。所以默认放到独立子
    # 进程里跑，起不了子进程时（冻结解释器等）回退为进程内解析。
    TXT_PARSE_TIMEOUT = 600
    # 章节扫描脚本，子进程入口（顶层可执行，见 webserver/plugins/parser/txt.py）
    TXT_PARSER_SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                     "plugins", "parser", "txt.py")

    @AsyncService.register_service
    def parse_txt_content(self, bid, fpath):
        '''从TXT文件中提取目录并存储为json'''
        outDir = os.path.join(CONF["extract_path"], str(bid))  # 解压后的目录
        content_path = os.path.join(outDir, "content.json")
        if os.path.isfile(content_path):
            logging.info(f"书籍<{bid}>已转换, {content_path} exists")
            return False

        if not os.path.exists(outDir):
            os.mkdir(outDir)

        try:
            ret = self.parse_txt_toc(fpath)
            content = json.dumps(ret, ensure_ascii=False)
            with open(content_path, 'w', encoding="utf8") as f:
                f.write(content)
                return True
        except Exception as e:
            logging.info(f"TXT convert error: {e}")
            logging.error(traceback.format_exc())
            return False

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
                                  env=env, timeout=self.TXT_PARSE_TIMEOUT)
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
