import asyncio
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from contextlib import AsyncExitStack

from mcp_client import MCPClient
from core.gemini import Gemini

from core.cli_chat import CliChat
from core.cli import CliApp

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent


def document_server_path() -> Path:
    """Return the bundled MCP server path independent of the caller's cwd."""
    return PROJECT_ROOT / "mcp_server.py"


def document_server_command(use_uv: bool) -> tuple[str, list[str]]:
    server_path = document_server_path()
    if use_uv:
        return "uv", ["run", str(server_path)]
    return sys.executable, [str(server_path)]


async def main() -> int:
    if not os.getenv("GEMINI_API_KEY", ""):
        print(
            "[startup] GEMINI_API_KEY is not configured; AI chat cannot start.",
            file=sys.stderr,
        )
        return 1

    server_path = document_server_path()
    if not server_path.is_file():
        print("[startup] Bundled document server is unavailable.", file=sys.stderr)
        return 1

    try:
        gemini_service = Gemini(model=os.getenv("GEMINI_MODEL", "gemini-3.6-flash"))
        server_scripts = sys.argv[1:]
        clients = {}

        use_uv = os.getenv("USE_UV", "0") == "1"
        command, args = document_server_command(use_uv)

        async with AsyncExitStack() as stack:
            doc_client = await stack.enter_async_context(
                MCPClient(command=command, args=args)
            )
            clients["doc_client"] = doc_client

            for i, server_script in enumerate(server_scripts):
                client_id = f"client_{i}_{server_script}"
                script_cmd, script_args = (
                    ("uv", ["run", server_script])
                    if use_uv
                    else (sys.executable, [server_script])
                )
                client = await stack.enter_async_context(
                    MCPClient(command=script_cmd, args=script_args)
                )
                clients[client_id] = client

            chat = CliChat(
                doc_client=doc_client,
                clients=clients,
                claude_service=gemini_service,
            )

            cli = CliApp(chat)
            await cli.initialize()
            await cli.run()
    except Exception as error:
        print(
            f"[startup] MCP chat could not start ({type(error).__name__}).",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    raise SystemExit(asyncio.run(main()))
