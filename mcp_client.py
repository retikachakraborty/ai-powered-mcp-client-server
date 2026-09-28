import sys
import json
import asyncio
from typing import Optional, Any
from contextlib import AsyncExitStack
from pydantic import AnyUrl
from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client


class MCPClient:
    def __init__(
        self,
        command: str,
        args: list[str],
        env: Optional[dict] = None,
    ):
        self._command = command
        self._args = args
        self._env = env
        self._session: Optional[ClientSession] = None
        self._exit_stack: AsyncExitStack = AsyncExitStack()

    async def connect(self):
        if self._session is not None:
            return
        server_params = StdioServerParameters(
            command=self._command,
            args=self._args,
            env=self._env,
        )
        stdio_transport = await self._exit_stack.enter_async_context(
            stdio_client(server_params)
        )
        _stdio, _write = stdio_transport
        self._session = await self._exit_stack.enter_async_context(
            ClientSession(_stdio, _write)
        )
        await self._session.initialize()

    def session(self) -> ClientSession:
        if self._session is None:
            raise ConnectionError(
                "Client session not initialized or cache not populated. Call connect_to_server first."
            )
        return self._session

    async def list_tools(self) -> list[types.Tool]:
        res = await self.session().list_tools()
        return res.tools

    async def call_tool(
        self, tool_name: str, tool_input: dict
    ) -> types.CallToolResult | None:
        return await self.session().call_tool(name=tool_name, arguments=tool_input)

    async def list_prompts(self) -> list[types.Prompt]:
        res = await self.session().list_prompts()
        return res.prompts

    async def get_prompt(self, prompt_name: str, args: dict[str, str]):
        res = await self.session().get_prompt(name=prompt_name, arguments=args)
        return res.messages


    async def read_resource(self, uri: str) -> Any:
        res = await self.session().read_resource(AnyUrl(uri))
        if not res.contents:
            raise RuntimeError(f"MCP resource '{uri}' returned no content.")
        resource = res.contents[0]

        if isinstance(resource, types.TextResourceContents):
            if resource.mimeType == "application/json":
                try:
                    return json.loads(resource.text)
                except json.JSONDecodeError as exc:
                    raise RuntimeError(
                        f"MCP resource '{uri}' returned invalid JSON."
                    ) from exc
            return resource.text

        return getattr(resource, "text", str(resource))



    async def cleanup(self):
        await self._exit_stack.aclose()
        self._session = None

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.cleanup()


# For testing
async def main():
    async with MCPClient(
        command=sys.executable,
        args=["mcp_server.py"],
    ) as _client:
        res = await _client.list_tools()
        print("Tools:", res)

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(main())
