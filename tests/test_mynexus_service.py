import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from webserver.models import MyNexusBookAnalysis, MyNexusChatSession
from webserver.services import mynexus_service
from webserver.services.mynexus_service import MyNexusClient, MyNexusError
from webserver.handlers import mynexus as mynexus_handler
from webserver.handlers.mynexus import routes, _analysis_dict, _failed_task_id


@pytest.mark.parametrize("language", ["en", "zh-TW"])
def test_response_messages_have_translations(language):
    catalog_path = Path(__file__).resolve().parents[1] / "webserver" / "i18n" / f"{language}.json"
    with catalog_path.open(encoding="utf-8") as catalog_file:
        catalog = json.load(catalog_file)

    messages = (
        "AI 助手暂不可用",
        "AI解析结果已不存在",
        "AI解析尚未完成",
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


def test_client_retries_remote_task(monkeypatch):
    client = MyNexusClient("http://localhost:3000", "api-token")
    calls = {}

    def fake_request(method, url, **kwargs):
        calls.update(method=method, url=url, kwargs=kwargs)
        return FakeResponse(status_code=202, body={"id": "task-1", "status": "pending"})

    monkeypatch.setattr(mynexus_service.requests, "request", fake_request)
    assert client.retry_task("task-1")["status"] == "pending"
    assert calls["method"] == "POST"
    assert calls["url"] == "http://localhost:3000/api/v1/tasks/task-1/retry"


def test_failed_analysis_is_always_retryable():
    analysis = MyNexusBookAnalysis(42, status="failed")
    analysis.remote_book_id = "remote-book"
    analysis.error_msg = "ingest failed"

    payload = _analysis_dict(analysis)

    assert payload["status"] == "failed"
    assert payload["can_retry"] is True


def test_failed_task_id_prefers_the_failed_stage():
    assert _failed_task_id({
        "ingest_task": {"id": "ingest-1", "status": "failed"},
        "summarize_task": {"id": "summarize-1", "status": "completed"},
    }) == "ingest-1"
    assert _failed_task_id({
        "ingest_task": {"id": "ingest-1", "status": "completed"},
        "summarize_task": {"id": "summarize-1", "status": "canceled"},
    }) == "summarize-1"
    assert _failed_task_id({
        "ingest_task": {"id": "ingest-1", "status": "completed"},
        "summarize_task": None,
    }) is None


def test_retry_remote_analysis_retries_the_failed_task(monkeypatch):
    analysis = MyNexusBookAnalysis(42, status="failed")
    analysis.remote_book_id = "remote-book"
    analysis.error_msg = "ingest failed"
    retried = []
    polls = []

    class FakeClient:
        def analysis_status(self, book_id):
            return {
                "analysis_status": "failed",
                "book_id": "remote-book",
                "ingest_task": {"id": "ingest-1", "status": "failed"},
            }

        def retry_task(self, task_id):
            retried.append(task_id)

    class FakeSession:
        def commit(self):
            pass

    async def fake_run_in_threadpool(func, *args, **kwargs):
        return func(*args, **kwargs)

    handler = SimpleNamespace(
        sqlite_session=FakeSession(),
        settings={"ScopedSession": object()},
    )
    monkeypatch.setattr(mynexus_handler.utils, "run_in_threadpool", fake_run_in_threadpool)
    monkeypatch.setattr(
        mynexus_handler, "_ensure_status_poll",
        lambda book_id, session: polls.append(book_id),
    )

    handled = asyncio.run(
        mynexus_handler.MyNexusBookHandler._retry_remote_analysis(
            handler, FakeClient(), 42, analysis
        )
    )

    assert handled is True
    assert retried == ["ingest-1"]
    assert polls == [42]
    assert analysis.status == "pending"
    assert analysis.error_msg == ""


def _fake_threadpool(monkeypatch):
    async def fake_run_in_threadpool(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(mynexus_handler.utils, "run_in_threadpool", fake_run_in_threadpool)


class _CommitSession:
    def __init__(self):
        self.commits = 0

    def commit(self):
        self.commits += 1


def test_refresh_remote_analysis_detects_book_deleted_from_mynexus(monkeypatch):
    analysis = MyNexusBookAnalysis(42, status="completed")
    analysis.remote_book_id = "remote-book"
    session = _CommitSession()

    class FakeClient:
        def analysis_status(self, book_id):
            raise MyNexusError(404, "book not found")

    monkeypatch.setattr(mynexus_handler, "MyNexusClient", lambda *args, **kwargs: FakeClient())
    _fake_threadpool(monkeypatch)

    state, error = asyncio.run(
        mynexus_handler._refresh_remote_analysis(session, analysis, 42)
    )

    assert (state, error) == ("missing", None)
    assert analysis.status == "failed"
    assert analysis.remote_book_id == ""


def test_refresh_remote_analysis_reports_not_ready(monkeypatch):
    analysis = MyNexusBookAnalysis(42, status="completed")
    analysis.remote_book_id = "remote-book"
    session = _CommitSession()

    class FakeClient:
        def analysis_status(self, book_id):
            return {
                "analysis_status": "processing",
                "book_id": "remote-book",
                "ingest_task": {"status": "processing", "progress": 30},
            }

    monkeypatch.setattr(mynexus_handler, "MyNexusClient", lambda *args, **kwargs: FakeClient())
    _fake_threadpool(monkeypatch)

    state, error = asyncio.run(
        mynexus_handler._refresh_remote_analysis(session, analysis, 42)
    )

    assert (state, error) == ("not_ready", None)
    assert analysis.status == "processing"
    assert analysis.progress == 30


def test_refresh_remote_analysis_surfaces_transport_errors(monkeypatch):
    analysis = MyNexusBookAnalysis(42, status="completed")
    analysis.remote_book_id = "remote-book"
    session = _CommitSession()

    class FakeClient:
        def analysis_status(self, book_id):
            raise MyNexusError(502, "MyNexus request failed")

    monkeypatch.setattr(mynexus_handler, "MyNexusClient", lambda *args, **kwargs: FakeClient())
    _fake_threadpool(monkeypatch)

    state, error = asyncio.run(
        mynexus_handler._refresh_remote_analysis(session, analysis, 42)
    )

    assert state is None
    assert isinstance(error, MyNexusError)
    # A transport failure must not mark the local analysis as failed.
    assert analysis.status == "completed"
