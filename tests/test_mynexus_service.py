import json
from pathlib import Path

import pytest

from webserver.models import MyNexusBookAnalysis, MyNexusChatSession
from webserver.services import mynexus_service
from webserver.services.mynexus_service import MyNexusClient, MyNexusError
from webserver.handlers.mynexus import routes


@pytest.mark.parametrize("language", ["en", "zh-TW"])
def test_response_messages_have_translations(language):
    catalog_path = Path(__file__).resolve().parents[1] / "webserver" / "i18n" / f"{language}.json"
    with catalog_path.open(encoding="utf-8") as catalog_file:
        catalog = json.load(catalog_file)

    messages = (
        "AI 助手暂不可用",
        "JSON 请求格式无效",
        "MyNexus 会话失败",
        "MyNexus 未返回会话 ID",
        "MyNexus 请求失败，请稍后重试",
        "无法连接到 MyNexus 服务，请检查服务状态或网络设置",
        "请求内容无效",
        "消息必须包含用户或助手角色及文本内容",
        "未找到该图书或无权访问",
        "所选图书文件不可用",
        "至少需要一条消息",
        "需要 EPUB 或 TXT 格式",
        "最后一条消息必须来自用户",
    )
    for message in messages:
        assert catalog.get(message, "").strip(), f"{language}.json is missing {message}"


class FakeResponse:
    def __init__(self, status_code=200, body=None):
        self.status_code = status_code
        self.ok = 200 <= status_code < 300
        self.reason = "response reason"
        self.text = "response body"
        self.body = body or {"ok": True}

    def json(self):
        return self.body


def test_client_builds_mynexus_api_url_and_external_user_header(monkeypatch):
    client = MyNexusClient("http://localhost:3000/", "api-token")
    calls = {}

    assert client.url("/chat/sessions") == "http://localhost:3000/api/v1/chat/sessions"
    assert client.headers(17) == {
        "Authorization": "Bearer api-token",
        "X-MyBooks-User-ID": "17",
    }

    def fake_request(method, url, **kwargs):
        calls.update(method=method, url=url, kwargs=kwargs)
        return FakeResponse(body={"analysis_status": "completed"})

    monkeypatch.setattr(mynexus_service.requests, "request", fake_request)
    assert client.analysis_status(17) == {"analysis_status": "completed"}
    assert calls["url"] == "http://localhost:3000/api/v1/books/by-mybooks-id/17"
    assert calls["kwargs"]["headers"]["Authorization"] == "Bearer api-token"


def test_client_rejects_invalid_configuration():
    with pytest.raises(MyNexusError, match="URL"):
        MyNexusClient("file:///tmp/mynexus", "api-token")
    with pytest.raises(MyNexusError, match="token"):
        MyNexusClient("http://localhost:3000", "")


def test_analysis_and_session_mapping_use_expected_keys():
    assert list(MyNexusBookAnalysis.__table__.primary_key.columns.keys()) == ["book_id"]
    assert list(MyNexusChatSession.__table__.primary_key.columns.keys()) == ["reader_id", "book_id"]
    assert {route[0] for route in routes()} == {
        r"/api/admin/mynexus/test",
        r"/api/book/([0-9]+)/mynexus/analysis",
        r"/api/book/([0-9]+)/mynexus/availability",
        r"/api/book/([0-9]+)/mynexus/session",
        r"/api/book/([0-9]+)/mynexus/chat",
    }


def test_client_reports_remote_auth_failure(monkeypatch):
    client = MyNexusClient("http://localhost:3000", "bad-token")
    monkeypatch.setattr(mynexus_service.requests, "request", lambda *args, **kwargs: FakeResponse(401))

    with pytest.raises(MyNexusError) as exc_info:
        client.test_connection()

    assert exc_info.value.status_code == 401
    assert exc_info.value.message == "response body"
