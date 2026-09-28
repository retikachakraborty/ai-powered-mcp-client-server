from types import SimpleNamespace

from prompt_toolkit.auto_suggest import Suggestion
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.document import Document

from core.cli import CLI_HELP_TEXT, CommandAutoSuggest, UnifiedCompleter


def _completion_texts(completer, text: str) -> list[str]:
    document = Document(text=text)
    return [item.text for item in completer.get_completions(document, None)]


def test_document_completion_supports_filename_resources() -> None:
    completer = UnifiedCompleter()
    completer.update_resources(["notes.md", "report.pdf"])

    assert _completion_texts(completer, "/summarize n") == ["notes.md"]
    assert _completion_texts(completer, "Ask about @rep") == ["report.pdf"]


def test_command_completion_and_autosuggestion_are_preserved() -> None:
    prompt = SimpleNamespace(
        name="summarize",
        description="Summarize a document",
        arguments=[SimpleNamespace(name="doc_id")],
    )
    completer = UnifiedCompleter()
    completer.update_prompts([prompt])
    autosuggest = CommandAutoSuggest([prompt])

    assert _completion_texts(completer, "/sum") == ["summarize"]
    suggestion = autosuggest.get_suggestion(
        Buffer(document=Document(text="/summarize")), Document(text="/summarize")
    )
    assert isinstance(suggestion, Suggestion)
    assert suggestion.text == " doc_id"


def test_local_list_command_is_documented_and_autocompletes() -> None:
    completer = UnifiedCompleter()

    assert _completion_texts(completer, "/li") == ["list"]
    assert "/list" in CLI_HELP_TEXT
