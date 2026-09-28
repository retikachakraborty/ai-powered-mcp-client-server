import json
from pathlib import Path
from typing import List, Tuple, Dict, Any
from mcp.types import Prompt, PromptMessage

from core.chat import Chat
from core.gemini import Gemini
from mcp_client import MCPClient


class CliPromptError(RuntimeError):
    """A malformed or unsupported local CLI prompt command."""


class CliChat(Chat):
    def __init__(
        self,
        doc_client: MCPClient,
        clients: dict[str, MCPClient],
        claude_service: Gemini,
        max_tool_iterations: int | None = None,
    ):
        super().__init__(
            clients=clients,
            claude_service=claude_service,
            max_tool_iterations=max_tool_iterations,
        )

        self.doc_client: MCPClient = doc_client

    async def list_prompts(self) -> list[Prompt]:
        return await self.doc_client.list_prompts()

    async def list_docs_ids(self) -> list[str]:
        res = await self.doc_client.read_resource("docs://documents")
        if isinstance(res, list):
            return res
        if isinstance(res, str):
            try:
                parsed = json.loads(res)
                if isinstance(parsed, list):
                    return parsed
            except Exception:
                pass
        return []

    async def get_doc_content(self, doc_id: str) -> str:
        res = await self.doc_client.read_resource(f"docs://documents/{doc_id}")
        return res if isinstance(res, str) else str(res)

    async def get_prompt(
        self, command: str, doc_id: str
    ) -> list[PromptMessage]:
        return await self.doc_client.get_prompt(command, {"doc_id": doc_id})

    async def _extract_resources(self, query: str) -> str:
        mentions = [word[1:] for word in query.split() if word.startswith("@")]

        doc_ids = await self.list_docs_ids()
        mentioned_docs: list[Tuple[str, str]] = []

        for doc_id in doc_ids:
            if doc_id in mentions:
                content = await self.get_doc_content(doc_id)
                mentioned_docs.append((doc_id, content))

        return "".join(
            f'\n<document id="{doc_id}">\n{content}\n</document>\n'
            for doc_id, content in mentioned_docs
        )

    async def _process_command(self, query: str) -> bool:
        if not query.startswith("/"):
            return False

        words = query.split()
        command = words[0][1:].casefold()

        if command in {"help", "list", "documents"}:
            return True
        if command not in {"summarize", "format"}:
            raise CliPromptError(
                f"Unknown command '/{command}'. Use /help to see available commands."
            )
        if len(words) != 2:
            raise CliPromptError(
                f"Usage: /{command} <filename>. A filename is required."
            )

        doc_id = words[1]
        if (
            not doc_id
            or doc_id in {".", ".."}
            or Path(doc_id).name != doc_id
            or "/" in doc_id
            or "\\" in doc_id
        ):
            raise CliPromptError("The document argument must be a filename, not a path.")

        messages = await self.doc_client.get_prompt(
            command, {"doc_id": doc_id}
        )

        self.messages += convert_prompt_messages_to_message_params(messages)
        return True

    async def _process_query(self, query: str):
        if await self._process_command(query):
            return

        added_resources = await self._extract_resources(query)

        prompt = f"""
        The user has a question:
        <query>
        {query}
        </query>

        The following context may be useful in answering their question:
        <context>
        {added_resources}
        </context>

        Note the user's query might contain references to documents like "@report.docx". The "@" is only
        included as a way of mentioning the doc. The actual name of the document would be "report.docx".
        If the document content is included in this prompt, you don't need to use an additional tool to read the document.
        Answer the user's question directly and concisely. Start with the exact information they need. 
        Don't refer to or mention the provided context in any way - just use it to inform your answer.
        """

        self.messages.append({"role": "user", "content": prompt})


def convert_prompt_message_to_message_param(
    prompt_message: "PromptMessage",
) -> Dict[str, Any]:
    role = "user" if prompt_message.role == "user" else "model"
    content = prompt_message.content

    if isinstance(content, dict) or hasattr(content, "__dict__"):
        content_type = (
            content.get("type", None)
            if isinstance(content, dict)
            else getattr(content, "type", None)
        )
        if content_type == "text":
            content_text = (
                content.get("text", "")
                if isinstance(content, dict)
                else getattr(content, "text", "")
            )
            return {"role": role, "content": content_text}

    if isinstance(content, list):
        text_blocks = []
        for item in content:
            if isinstance(item, dict) or hasattr(item, "__dict__"):
                item_type = (
                    item.get("type", None)
                    if isinstance(item, dict)
                    else getattr(item, "type", None)
                )
                if item_type == "text":
                    item_text = (
                        item.get("text", "")
                        if isinstance(item, dict)
                        else getattr(item, "text", "")
                    )
                    text_blocks.append(item_text)

        if text_blocks:
            return {"role": role, "content": "\n".join(text_blocks)}

    if isinstance(content, str):
        return {"role": role, "content": content}

    return {"role": role, "content": ""}


def convert_prompt_messages_to_message_params(
    prompt_messages: List[PromptMessage],
) -> List[Dict[str, Any]]:
    return [
        convert_prompt_message_to_message_param(msg) for msg in prompt_messages
    ]
