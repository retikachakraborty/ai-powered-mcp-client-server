import os

from core.gemini import Gemini
from mcp_client import MCPClient
from core.tools import ToolManager


DEFAULT_MAX_TOOL_ITERATIONS = 8


class ToolIterationLimitError(RuntimeError):
    """Raised when a model exceeds the configured tool-call round limit."""


class Chat:
    def __init__(
        self,
        claude_service: Gemini,
        clients: dict[str, MCPClient],
        max_tool_iterations: int | None = None,
    ):
        self.claude_service: Gemini = claude_service
        self.clients: dict[str, MCPClient] = clients
        self.messages: list = []
        if max_tool_iterations is None:
            configured_limit = os.getenv(
                "MCP_MAX_TOOL_ITERATIONS", str(DEFAULT_MAX_TOOL_ITERATIONS)
            )
            try:
                max_tool_iterations = int(configured_limit)
            except ValueError as exc:
                raise ValueError(
                    "MCP_MAX_TOOL_ITERATIONS must be a positive integer."
                ) from exc
        if max_tool_iterations < 1:
            raise ValueError("max_tool_iterations must be a positive integer.")
        self.max_tool_iterations = max_tool_iterations

    async def _process_query(self, query: str):
        self.messages.append({"role": "user", "content": query})

    async def run(
        self,
        query: str,
    ) -> str:
        final_text_response = ""
        history_length = len(self.messages)
        tool_iterations = 0

        try:
            await self._process_query(query)

            while True:
                response = self.claude_service.chat(
                    messages=self.messages,
                    tools=await ToolManager.get_all_tools(self.clients),
                )

                self.claude_service.add_assistant_message(self.messages, response)

                if response.stop_reason == "tool_use":
                    tool_iterations += 1
                    if tool_iterations > self.max_tool_iterations:
                        raise ToolIterationLimitError(
                            "Maximum tool-calling iterations reached "
                            f"({self.max_tool_iterations}). Try a narrower request."
                        )
                    text = self.claude_service.text_from_message(response)
                    if text:
                        print(text)
                    tool_result_parts = await ToolManager.execute_tool_requests(
                        self.clients, response
                    )

                    for result_part in tool_result_parts:
                        function_response = result_part.get("function_response", {})
                        tool_name = function_response.get("name", "unknown")
                        status = function_response.get("response", {}).get("status")
                        if status == "success":
                            print(f"[tool] {tool_name}: completed")
                        else:
                            print(
                                f"[tool] {tool_name}: failed; continuing with the session"
                            )

                    self.claude_service.add_user_message(
                        self.messages, tool_result_parts
                    )
                else:
                    final_text_response = self.claude_service.text_from_message(
                        response
                    )
                    break
        except Exception:
            # Keep all previously completed turns, but remove every message
            # produced while processing this failed turn.
            del self.messages[history_length:]
            raise

        return final_text_response
