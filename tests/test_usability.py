import asyncio
import io
from types import SimpleNamespace

import pytest

from core.chat import Chat
from core.cli import CLI_HELP_TEXT, CliApp
from core.cli_chat import CliChat, CliPromptError
from core.chat import ToolIterationLimitError
from offline_demo import run_demo


def test_offline_demo_lists_searches_reads_and_edits() -> None:
    output = io.StringIO()

    run_demo(output)
    text = output.getvalue()

    assert "1. List documents" in text
    assert "2. Search for 'MCP'" in text
    assert "3. Read demo.md" in text
    assert "4. Edit demo.md" in text
    assert "Replacements: 1" in text
    assert "remain local" in text


def test_help_is_local_and_documents_are_recoverable(capsys) -> None:
    agent = SimpleNamespace(list_docs_ids=lambda: asyncio.sleep(0, result=["notes.md"]))
    app = object.__new__(CliApp)
    app.agent = agent

    assert asyncio.run(app.handle_local_command("/help")) is True
    assert CLI_HELP_TEXT in capsys.readouterr().out

    assert asyncio.run(app.handle_local_command("/documents")) is True
    assert "notes.md" in capsys.readouterr().out

    assert asyncio.run(app.handle_local_command("/list")) is True
    assert "notes.md" in capsys.readouterr().out


def test_unknown_local_command_is_left_for_mcp() -> None:
    app = object.__new__(CliApp)
    app.agent = SimpleNamespace()

    assert asyncio.run(app.handle_local_command("/summarize notes.md")) is False


class _PromptSequence:
    def __init__(self) -> None:
        self.calls = 0

    async def prompt_async(self, _prompt: str) -> str:
        self.calls += 1
        if self.calls == 1:
            return "first question"
        if self.calls == 2:
            return "second question"
        raise KeyboardInterrupt


class _RecoveringAgent:
    def __init__(self) -> None:
        self.calls = 0

    async def run(self, _query: str) -> str:
        self.calls += 1
        if self.calls == 1:
            raise ValueError("recoverable test failure")
        return "recovered response"


def test_cli_keeps_running_after_unexpected_agent_error(capsys) -> None:
    app = object.__new__(CliApp)
    app.agent = _RecoveringAgent()
    app.session = _PromptSequence()

    asyncio.run(app.run())
    output = capsys.readouterr().out

    assert "Recoverable error (ValueError)" in output
    assert "recovered response" in output
    assert app.agent.calls == 2


class _ChatService:
    def __init__(self) -> None:
        self.calls = 0

    def chat(self, **_kwargs):
        self.calls += 1
        if self.calls == 1:
            return SimpleNamespace(
                stop_reason="tool_use",
                function_calls=[SimpleNamespace(name="demo", args={})],
            )
        return SimpleNamespace(stop_reason="end_turn", text="done")

    def add_assistant_message(self, _messages, _response):
        return None

    def add_user_message(self, _messages, _message):
        return None

    def text_from_message(self, response):
        return getattr(response, "text", "")


class _ToolClient:
    async def list_tools(self):
        return [SimpleNamespace(name="demo", description="demo", inputSchema={})]

    async def call_tool(self, _name, _input):
        return SimpleNamespace(content=[], isError=False)


def test_chat_reports_successful_tool_execution(capsys) -> None:
    service = _ChatService()
    chat = Chat(service, {"demo": _ToolClient()})

    assert asyncio.run(chat.run("run demo")) == "done"
    assert "[tool] demo: completed" in capsys.readouterr().out


class _FailingAfterFirstTurnService:
    def __init__(self) -> None:
        self.calls = 0

    def chat(self, **_kwargs):
        self.calls += 1
        if self.calls == 1:
            return SimpleNamespace(stop_reason="end_turn", text="first answer")
        raise RuntimeError("Gemini request failed with private details")

    def add_assistant_message(self, _messages, _response):
        return None

    def text_from_message(self, response):
        return getattr(response, "text", "")


def test_failed_gemini_turn_rolls_back_only_current_messages() -> None:
    service = _FailingAfterFirstTurnService()
    chat = Chat(service, {})

    assert asyncio.run(chat.run("first")) == "first answer"
    completed_history = list(chat.messages)

    with pytest.raises(RuntimeError):
        asyncio.run(chat.run("second"))

    assert chat.messages == completed_history


class _EndlessToolService:
    def __init__(self) -> None:
        self.calls = 0

    def chat(self, **_kwargs):
        self.calls += 1
        return SimpleNamespace(
            stop_reason="tool_use",
            function_calls=[SimpleNamespace(name="demo", args={})],
        )

    def add_assistant_message(self, _messages, _response):
        return None

    def add_user_message(self, _messages, _message):
        return None

    def text_from_message(self, _response):
        return ""


def test_tool_iteration_limit_rolls_back_incomplete_turn() -> None:
    service = _EndlessToolService()
    chat = Chat(service, {"demo": _ToolClient()}, max_tool_iterations=2)

    with pytest.raises(ToolIterationLimitError, match="Maximum tool-calling"):
        asyncio.run(chat.run("loop"))

    assert service.calls == 3
    assert chat.messages == []


class _PromptClient:
    def __init__(self) -> None:
        self.calls = []

    async def get_prompt(self, command, args):
        self.calls.append((command, args))
        return []


def test_cli_prompt_validation_happens_before_server_contact() -> None:
    client = _PromptClient()
    chat = CliChat(client, {}, object())

    for query in ("/unknown notes.md", "/summarize", "/format a.md extra", "/format ../a.md"):
        with pytest.raises(CliPromptError):
            asyncio.run(chat._process_command(query))

    assert client.calls == []


def test_cli_prompt_validation_preserves_valid_prompts_and_local_commands() -> None:
    client = _PromptClient()
    chat = CliChat(client, {}, object())

    assert asyncio.run(chat._process_command("/summarize notes.md")) is True
    assert asyncio.run(chat._process_command("/format notes.md")) is True
    assert asyncio.run(chat._process_command("/list")) is True
    assert client.calls == [
        ("summarize", {"doc_id": "notes.md"}),
        ("format", {"doc_id": "notes.md"}),
    ]
