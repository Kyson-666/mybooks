"""
书栈推书接收开关工具

展示书栈(BookBarn)服务状态与Token，并允许开关"接收推书"功能
(ENABLE_RECEIVING_BOOKS)、申请新的 BOOKBARN_TOKEN。

@author: PoxenStudio, 2026
"""
from webserver import loader
from webserver.base.setting_saver import SettingsSaver
from webserver.services.book_barn import BookBarnClient
from webserver.toolbox.base_tool import BaseTool

CONF = loader.get_settings()


class BookBarnAcceptorTool(BaseTool):
    """管理书栈"接收推书"开关及Token。"""

    service_item_name = "书栈收书"

    @staticmethod
    def info() -> dict:
        return {
            "tool_id": "bookbarn_acceptor",
            "name": "书栈接收器",
            "description": "查看书栈(BookBarn)服务状态与Token，开关接收推书功能。",
            "revision": "0.1.0",
            "author": "Arthas",
            "publish_date": "2026-07-22",
        }

    def get_status(self) -> dict:
        return {
            "enable_bookbarn": bool(CONF.get("ENABLE_BOOKBARN", False)),
            "enable_receiving_books": bool(CONF.get("ENABLE_RECEIVING_BOOKS", False)),
            "token": CONF.get("BOOKBARN_TOKEN", ""),
            "collection_hour": int(CONF.get("BOOKBARN_COLLECTION_HOUR", 3)),
        }

    def set_receiving_books(self, enabled: bool) -> dict:
        return SettingsSaver().save_partial({"ENABLE_RECEIVING_BOOKS": bool(enabled)})

    def apply_token(self, os_name: str) -> str:
        token = BookBarnClient().apply_token(os=os_name)
        SettingsSaver().save_partial({"BOOKBARN_TOKEN": token})
        return token

    def set_collection_hour(self, hour: int) -> dict:
        if hour < 0 or hour > 23:
            raise ValueError("hour must be between 0 and 23")
        return SettingsSaver().save_partial({"BOOKBARN_COLLECTION_HOUR": hour})
