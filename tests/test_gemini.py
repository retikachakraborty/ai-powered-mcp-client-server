import inspect
from types import SimpleNamespace

import pytest
from google.genai import errors as genai_errors
from google.genai import types

from core.gemini import Gemini, GeminiResponseWrapper


def _uninitialized_gemini(error=None):
    gemini = object.__new__(Gemini)
    gemini.model = "test-model"

    def generate_content(**_kwargs):
        if error is not None:
            raise error
        return SimpleNamespace(candidates=[])

    gemini.client = SimpleNamespace(
        models=SimpleNamespace(generate_content=generate_content)
    )
    return gemini


def test_mixed_text_and_function_call_response_is_converted() -> None:
    function_call = SimpleNamespace(
        name="search_documents", args={"query": "MCP"}
    )
    model_content = types.Content(
        role="model",
        parts=[
            types.Part.from_text(text="I will search."),
            types.Part.from_function_call(
                name=function_call.name, args=function_call.args
            ),
        ],
    )
    raw_response = SimpleNamespace(
        candidates=[SimpleNamespace(content=model_content)],
        function_calls=[function_call],
    )

    wrapper = GeminiResponseWrapper(raw_response)
    gemini = object.__new__(Gemini)
    messages = []
    gemini.add_assistant_message(messages, wrapper)
    converted = gemini._convert_messages(
        messages
        + [
            {
                "role": "user",
                "parts": [
                    {
                        "function_response": {
                            "name": "search_documents",
                            "response": {"result": "found"},
                        }
                    }
                ],
            }
        ]
    )

    assert wrapper.stop_reason == "tool_use"
    assert wrapper.text == "I will search."
    assert wrapper.function_calls == [function_call]
    assert converted[0] is model_content
    assert converted[1].parts[0].function_response.name == "search_documents"


def test_function_call_message_conversion_creates_sdk_parts() -> None:
    gemini = object.__new__(Gemini)

    converted = gemini._convert_messages(
        [
            {
                "role": "assistant",
                "parts": [
                    {"function_call": {"name": "read_doc_contents", "args": {"doc_id": "a.md"}}}
                ],
            }
        ]
    )

    assert converted[0].role == "model"
    assert converted[0].parts[0].function_call.name == "read_doc_contents"
    assert converted[0].parts[0].function_call.args == {"doc_id": "a.md"}


def test_stop_sequences_default_is_immutable_none() -> None:
    assert inspect.signature(Gemini.chat).parameters["stop_sequences"].default is None


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (
            genai_errors.ClientError(
                401,
                {"error": {"status": "UNAUTHENTICATED", "message": "SECRET_KEY"}},
            ),
            "authentication or permission",
        ),
        (
            genai_errors.ClientError(
                429,
                {"error": {"status": "RESOURCE_EXHAUSTED", "message": "SECRET_KEY"}},
            ),
            "quota or rate limit",
        ),
        (
            genai_errors.ServerError(
                503,
                {"error": {"status": "UNAVAILABLE", "message": "SECRET_KEY"}},
            ),
            "temporarily unavailable",
        ),
    ],
)
def test_structured_google_errors_have_safe_messages(error, expected) -> None:
    gemini = _uninitialized_gemini(error)

    with pytest.raises(RuntimeError) as raised:
        gemini.chat([])

    message = str(raised.value)
    assert expected in message
    assert "SECRET_KEY" not in message


def test_unknown_errors_use_safe_fallback_without_exception_text() -> None:
    gemini = _uninitialized_gemini(RuntimeError("credential=SECRET_KEY"))

    with pytest.raises(RuntimeError, match="Gemini request failed") as raised:
        gemini.chat([])

    assert "SECRET_KEY" not in str(raised.value)
