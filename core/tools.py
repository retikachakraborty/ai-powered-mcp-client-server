import json
import sys
from typing import Any, Literal, Optional
from mcp.types import CallToolResult, TextContent
from mcp_client import MCPClient


class ToolManager:
    @staticmethod
    def _report_discovery_error(client_name: str, error: Exception) -> None:
        """Report diagnostics without leaking exception text or paths."""
        print(
            f"[mcp] Tool discovery failed for '{client_name}' "
            f"({type(error).__name__}); continuing.",
            file=sys.stderr,
        )

    @classmethod
    async def get_all_tools(cls, clients: dict[str, MCPClient]) -> list[dict]:
        """Gets all tools from the provided clients formatted as dicts."""
        tools: list[dict] = []
        for client_name, client in clients.items():
            try:
                tool_models = await client.list_tools()
            except Exception as error:
                # One unavailable auxiliary server should not hide tools from
                # the document server or make the chat loop crash.
                cls._report_discovery_error(client_name, error)
                continue
            tools += [
                {
                    "name": t.name,
                    "description": t.description,
                    "input_schema": t.inputSchema,
                }
                for t in tool_models
            ]
        return tools

    @classmethod
    async def _find_client_with_tool(
        cls, clients: dict[str, MCPClient], tool_name: str
    ) -> Optional[MCPClient]:
        """Finds the first client that has the specified tool."""
        for client_name, client in clients.items():
            try:
                tools = await client.list_tools()
            except Exception as error:
                cls._report_discovery_error(client_name, error)
                continue
            tool = next((t for t in tools if t.name == tool_name), None)
            if tool:
                return client
        return None

    @classmethod
    def _build_tool_result_part(
        cls,
        tool_name: str,
        text: str,
        status: Literal["success"] | Literal["error"],
    ) -> dict:
        """Builds a function response dictionary for Gemini."""
        return {
            "function_response": {
                "name": tool_name,
                "response": {"result": text, "status": status}
            }
        }

    @classmethod
    async def execute_tool_requests(
        cls, clients: dict[str, MCPClient], response: Any
    ) -> list[dict]:
        """Executes a list of tool requests against the provided clients."""
        tool_requests = []
        if hasattr(response, "function_calls") and response.function_calls:
            for call in response.function_calls:
                tool_requests.append((call.name, call.args or {}))
        elif hasattr(response, "content"):
            for block in response.content:
                if getattr(block, "type", None) == "tool_use":
                    tool_requests.append((getattr(block, "name"), getattr(block, "input", {})))

        tool_result_blocks: list[dict] = []
        for tool_name, tool_input in tool_requests:
            client = await cls._find_client_with_tool(
                clients, tool_name
            )

            if not client:
                tool_result_part = cls._build_tool_result_part(
                    tool_name, "Could not find that tool", "error"
                )
                tool_result_blocks.append(tool_result_part)
                continue

            try:
                tool_output: CallToolResult | None = await client.call_tool(
                    tool_name, tool_input
                )
                items = []
                if tool_output:
                    items = tool_output.content
                content_list = [
                    item.text for item in items if isinstance(item, TextContent)
                ]
                content_json = json.dumps(content_list)
                tool_result_part = cls._build_tool_result_part(
                    tool_name,
                    content_json,
                    "error"
                    if tool_output and tool_output.isError
                    else "success",
                )
            except Exception as e:
                error_message = f"Tool '{tool_name}' failed: {type(e).__name__}."
                tool_result_part = cls._build_tool_result_part(
                    tool_name,
                    json.dumps({"error": error_message}),
                    "error",
                )

            tool_result_blocks.append(tool_result_part)
        return tool_result_blocks
