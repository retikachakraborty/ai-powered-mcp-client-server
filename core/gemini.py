import os
from typing import Any, Optional
from google import genai
from google.genai import errors as genai_errors
from google.genai import types


class GeminiResponseWrapper:
    def __init__(self, raw_response: Any):
        self.raw_response = raw_response
        self.stop_reason = "end_turn"
        self.function_calls = []
        self.text = ""

        if raw_response and getattr(raw_response, "function_calls", None):
            self.stop_reason = "tool_use"
            self.function_calls = raw_response.function_calls

        try:
            if getattr(raw_response, "candidates", None):
                candidate = raw_response.candidates[0]
                if getattr(candidate, "content", None) and getattr(candidate.content, "parts", None):
                    text_parts = [
                        p.text
                        for p in candidate.content.parts
                        if getattr(p, "text", None)
                    ]
                    if text_parts:
                        self.text = "".join(text_parts)
        except Exception:
            pass
        if not self.text and getattr(raw_response, "text", None):
            self.text = raw_response.text

        # Content representation for compatibility
        self.content = []
        if self.function_calls:
            for call in self.function_calls:
                # Add mock objects matching expected block interface if accessed
                self.content.append(type("ToolUseBlock", (), {
                    "type": "tool_use",
                    "id": getattr(call, "name", "tool"),
                    "name": getattr(call, "name", "tool"),
                    "input": getattr(call, "args", None) or {}
                })())
        if self.text:
            self.content.append(type("TextBlock", (), {
                "type": "text",
                "text": self.text
            })())


class Gemini:
    def __init__(self, model: str):
        self.api_key = os.getenv("GEMINI_API_KEY", "")
        if not self.api_key:
            raise ValueError(
                "Error: GEMINI_API_KEY environment variable is not set.\n"
                "To fix this:\n"
                "1. Get a Gemini API key from Google AI Studio: https://aistudio.google.com/\n"
                "2. Add GEMINI_API_KEY=your_key to your .env file."
            )
        self.model = model
        self.client = genai.Client(api_key=self.api_key)

    def add_user_message(self, messages: list, message: Any):
        if isinstance(message, dict):
            messages.append(message)
        elif isinstance(message, list):
            messages.append({"role": "user", "parts": message})
        else:
            messages.append({"role": "user", "parts": [str(message)]})

    def add_assistant_message(self, messages: list, message: Any):
        if isinstance(message, GeminiResponseWrapper):
            if message.raw_response and getattr(message.raw_response, "candidates", None) and message.raw_response.candidates[0].content:
                messages.append(message.raw_response.candidates[0].content)
                return
            parts = []
            if message.text:
                parts.append({"text": message.text})
            if message.function_calls:
                for call in message.function_calls:
                    parts.append({
                        "function_call": {
                            "name": call.name,
                            "args": call.args or {}
                        }
                    })
            messages.append({"role": "model", "parts": parts})
        elif isinstance(message, dict):
            messages.append(message)
        else:
            messages.append({"role": "model", "parts": [str(message)]})

    def text_from_message(self, message: Any) -> str:
        if isinstance(message, GeminiResponseWrapper):
            return message.text
        if hasattr(message, "text"):
            return message.text or ""
        return str(message)

    def _convert_tools(self, tools: Optional[list]) -> Optional[list]:
        if not tools:
            return None
        declarations = []
        for tool in tools:
            decl = {
                "name": tool.get("name"),
                "description": tool.get("description", ""),
                "parameters": tool.get("input_schema")
            }
            declarations.append(decl)
        return [types.Tool(function_declarations=declarations)]

    def _convert_messages(self, messages: list) -> list:
        formatted_contents = []
        for msg in messages:
            if isinstance(msg, types.Content):
                formatted_contents.append(msg)
                continue
            role = msg.get("role", "user")
            if role == "assistant":
                role = "model"
            content = msg.get("content")
            parts = msg.get("parts")

            content_parts = []
            if parts is not None:
                for p in parts:
                    if isinstance(p, dict):
                        if "function_response" in p:
                            content_parts.append(types.Part.from_function_response(
                                name=p["function_response"]["name"],
                                response=p["function_response"]["response"]
                            ))
                        elif "function_call" in p:
                            content_parts.append(types.Part.from_function_call(
                                name=p["function_call"]["name"],
                                args=p["function_call"]["args"]
                            ))
                        elif "text" in p:
                            content_parts.append(types.Part.from_text(text=p["text"]))
                        elif "tool_use_id" in p:
                            content_parts.append(types.Part.from_function_response(
                                name=p.get("name", "tool"),
                                response={"result": p.get("content")}
                            ))
                    elif isinstance(p, str):
                        content_parts.append(types.Part.from_text(text=p))
                    else:
                        content_parts.append(p)
            elif isinstance(content, str):
                content_parts.append(types.Part.from_text(text=content))
            elif isinstance(content, list):
                for item in content:
                    if isinstance(item, dict):
                        if item.get("type") == "text":
                            content_parts.append(types.Part.from_text(text=item.get("text", "")))
                        elif "tool_use_id" in item or "type" in item and item["type"] == "tool_result":
                            content_parts.append(types.Part.from_function_response(
                                name=item.get("name", "tool"),
                                response={"result": item.get("content")}
                            ))
                    elif isinstance(item, str):
                        content_parts.append(types.Part.from_text(text=item))

            if not content_parts:
                content_parts.append(types.Part.from_text(text=""))

            formatted_contents.append(types.Content(role=role, parts=content_parts))
        return formatted_contents

    def chat(
        self,
        messages: list,
        system=None,
        temperature=0.7,
        stop_sequences=None,
        tools=None,
        thinking=False,
        thinking_budget=1024,
    ) -> GeminiResponseWrapper:
        formatted_contents = self._convert_messages(messages)
        gemini_tools = self._convert_tools(tools)

        config_args = {
            "temperature": temperature,
        }
        if system:
            config_args["system_instruction"] = system
        if gemini_tools:
            config_args["tools"] = gemini_tools
        if stop_sequences:
            config_args["stop_sequences"] = stop_sequences

        config = types.GenerateContentConfig(**config_args)

        try:
            raw_response = self.client.models.generate_content(
                model=self.model,
                contents=formatted_contents,
                config=config,
            )
            return GeminiResponseWrapper(raw_response)

        except Exception as error:
            raise RuntimeError(self._safe_error_message(error)) from None

    @staticmethod
    def _safe_error_message(error: Exception) -> str:
        """Map SDK errors to safe messages without exposing exception text."""
        if isinstance(error, genai_errors.APIError):
            code = getattr(error, "code", None)
            status = str(getattr(error, "status", "") or "").upper()

            if code == 429 or status in {"RESOURCE_EXHAUSTED", "TOO_MANY_REQUESTS"}:
                return (
                    "Gemini API quota or rate limit reached. "
                    "Please check your usage and try again later."
                )
            if code in {401, 403} or status in {
                "UNAUTHENTICATED",
                "PERMISSION_DENIED",
                "API_KEY_INVALID",
            }:
                return "Gemini authentication or permission failed. Check your API configuration."
            if code == 404 or status in {"NOT_FOUND", "MODEL_NOT_FOUND"}:
                return "The configured Gemini model was not found. Check GEMINI_MODEL."
            if isinstance(error, genai_errors.ServerError) or (
                isinstance(code, int) and code >= 500
            ):
                return "Gemini service is temporarily unavailable. Please try again later."
            return "Gemini rejected the request. Check the model and request configuration."

        return "Gemini request failed. Check your network and service configuration."
