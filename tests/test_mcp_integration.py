import asyncio
from types import SimpleNamespace

from mcp.types import TextContent

import mcp_server
from core.tools import ToolManager


def test_server_functions_preserve_document_api(monkeypatch, tmp_path) -> None:
    (tmp_path / "readme.md").write_text("searchable text", encoding="utf-8")
    monkeypatch.setattr(mcp_server, "DOCUMENTS_DIR", tmp_path)

    assert mcp_server.list_documents() == ["readme.md"]
    assert mcp_server.read_document("readme.md") == "searchable text"
    assert mcp_server.search_docs("SEARCH")[0]["document"] == "readme.md"
    assert "searchable" in mcp_server.fetch_doc("readme.md")


class _FakeClient:
    def __init__(self, tools, result=None, error=None, list_error=None):
        self.tools = tools
        self.result = result
        self.error = error
        self.list_error = list_error

    async def list_tools(self):
        if self.list_error:
            raise self.list_error
        return self.tools

    async def call_tool(self, _name, _input):
        if self.error:
            raise self.error
        return self.result


def test_tool_manager_skips_unavailable_servers() -> None:
    available = _FakeClient([SimpleNamespace(name="search", description="find", inputSchema={})])
    unavailable = _FakeClient([], list_error=ConnectionError("private path should not escape"))

    tools = asyncio.run(ToolManager.get_all_tools({"available": available, "down": unavailable}))

    assert [tool["name"] for tool in tools] == ["search"]


def test_tool_discovery_diagnostic_is_named_and_sanitized(capsys) -> None:
    unavailable = _FakeClient(
        [], list_error=ConnectionError("private path and credential must not leak")
    )

    assert asyncio.run(ToolManager.get_all_tools({"auxiliary": unavailable})) == []
    diagnostic = capsys.readouterr().err

    assert "auxiliary" in diagnostic
    assert "ConnectionError" in diagnostic
    assert "private path" not in diagnostic
    assert "credential" not in diagnostic


def test_tool_manager_returns_sanitized_tool_error() -> None:
    client = _FakeClient(
        [SimpleNamespace(name="search", description="find", inputSchema={})],
        error=RuntimeError("secret path and API key should not be returned"),
    )
    response = SimpleNamespace(
        function_calls=[SimpleNamespace(name="search", args={})]
    )

    result = asyncio.run(ToolManager.execute_tool_requests({"docs": client}, response))
    payload = result[0]["function_response"]["response"]

    assert payload["status"] == "error"
    assert "RuntimeError" in payload["result"]
    assert "secret path" not in payload["result"]
    assert "API key" not in payload["result"]


def test_tool_manager_serializes_text_results() -> None:
    client = _FakeClient(
        [SimpleNamespace(name="search", description="find", inputSchema={})],
        result=SimpleNamespace(
            content=[TextContent(type="text", text="result")], isError=False
        ),
    )
    response = SimpleNamespace(
        function_calls=[SimpleNamespace(name="search", args={})]
    )

    result = asyncio.run(ToolManager.execute_tool_requests({"docs": client}, response))
    payload = result[0]["function_response"]["response"]

    assert payload["status"] == "success"
    assert '"result"' in payload["result"]
