import asyncio
from pathlib import Path

import main as app_main
import mcp_server
from core.documents import list_documents, read_document_content
from core.cli import CLI_HELP_TEXT, WELCOME_TEXT


def test_document_server_path_is_relative_to_main_module() -> None:
    expected = Path(app_main.__file__).resolve().with_name("mcp_server.py")

    assert app_main.document_server_path() == expected
    assert app_main.document_server_command(False)[1] == [str(expected)]
    assert app_main.document_server_command(True)[1] == ["run", str(expected)]


def test_missing_gemini_key_has_concise_safe_startup_error(monkeypatch, capsys) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    assert asyncio.run(app_main.main()) == 1
    error = capsys.readouterr().err

    assert error == "[startup] GEMINI_API_KEY is not configured; AI chat cannot start.\n"
    assert "SECRET" not in error


def test_format_prompt_is_preview_only() -> None:
    messages = mcp_server.format_document("notes.md")
    prompt_text = str(messages)

    assert "preview-only" in prompt_text
    assert "do not call edit_document" in prompt_text
    assert "explicitly approves" in prompt_text


def test_welcome_and_help_cover_supported_first_time_actions() -> None:
    for text in (WELCOME_TEXT, CLI_HELP_TEXT):
        assert "/help" in text
        assert "/list" in text
        assert "/documents" in text
        assert "/summarize <filename>" in text
        assert "/format <filename>" in text
        assert "@" in text
        assert "Ctrl+C" in text


def test_fictional_examples_cover_all_supported_document_formats() -> None:
    examples_dir = Path(__file__).resolve().parents[1] / "examples" / "sample_documents"

    assert set(list_documents(examples_dir)) == {
        "implementation_brief.docx",
        "meeting_notes.txt",
        "project_report.md",
        "technical_guide.pdf",
    }
    assert "Northstar" in read_document_content(examples_dir, "technical_guide.pdf")
    assert "Milestones" in read_document_content(examples_dir, "implementation_brief.docx")
