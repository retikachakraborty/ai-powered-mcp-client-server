from typing import List, Optional
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.styles import Style
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.auto_suggest import AutoSuggest, Suggestion
from prompt_toolkit.document import Document
from prompt_toolkit.buffer import Buffer

from core.cli_chat import CliChat


WELCOME_TEXT = """\n╭──────────────────────────────────────────────────────────────╮
│                    MCP DOCUMENT CHAT                       │
╰──────────────────────────────────────────────────────────────╯
Local document retrieval and editing through an MCP server, with Gemini
available for natural-language questions and reusable document prompts.

Where to type:
  • Run setup commands such as `uv sync --dev` in your terminal.
  • Type slash commands and questions at this interactive `> ` prompt.

Getting started:
  1. Put TXT, Markdown, PDF, or DOCX files in documents/.
  2. Type /list to see the filenames available to the server.
  3. Ask a question, optionally mentioning a file with @filename.

Commands:
  /help                  Show commands and examples.
  /list or /documents    List available documents.
  /summarize <filename>  Ask Gemini to summarize a document.
  /format <filename>     Preview a Markdown reformatting; never edits by itself.

Example questions:
  > What are the launch risks in @project_report.md?
  > Find the deadline for the API review in @meeting_notes.txt.
  > Which validation rules are described in @technical_guide.pdf?
  > What decisions and action items are in @meeting_notes.txt?

The standalone MCP server, document extraction, offline demo, and tests work
without Gemini. This interactive AI client checks for GEMINI_API_KEY at startup
because natural-language answers and prompt-based summaries require Gemini.
Press Ctrl+C to exit.
"""

CLI_HELP_TEXT = """MCP Document Chat help

Type these commands at the interactive `> ` prompt. Run `uv ...` setup or test
commands in your operating-system terminal, not inside this prompt.

  /help
      Show this help and examples.
  /list
      List supported filenames available in documents/. Alias: /documents.
  /documents
      List supported filenames available in documents/. Alias: /list.
  /summarize <filename>
      Retrieve a reusable summarization prompt for one document. Gemini must
      then use that prompt to produce an answer.
  /format <filename>
      Retrieve a preview-only Markdown-formatting prompt. It must not edit a
      file; editing requires a separate explicit edit_document request.
  @filename
      Mention a document in a natural-language question, for example:
      What decisions were made in @meeting_notes.txt?
  Ctrl+C
      Exit the interactive session.

Examples:
  > /list
  > What are the launch risks in @project_report.md?
  > /summarize technical_guide.pdf
  > /format project_report.md

Press Tab after / or @ for autocomplete. PDF and DOCX files are readable but
not editable; TXT and Markdown edits use exact replacement safeguards.
"""


class CommandAutoSuggest(AutoSuggest):
    def __init__(self, prompts: List):
        self.prompts = prompts
        self.prompt_dict = {prompt.name: prompt for prompt in prompts}

    def get_suggestion(
        self, buffer: Buffer, document: Document
    ) -> Optional[Suggestion]:
        text = document.text

        if not text.startswith("/"):
            return None

        parts = text[1:].split()

        if len(parts) == 1:
            cmd = parts[0]

            if cmd in self.prompt_dict:
                prompt = self.prompt_dict[cmd]
                if prompt.arguments:
                    return Suggestion(f" {prompt.arguments[0].name}")

        return None


class UnifiedCompleter(Completer):
    LOCAL_COMMANDS = ("help", "documents", "list")

    def __init__(self):
        self.prompts = []
        self.prompt_dict = {}
        self.resources = []

    def update_prompts(self, prompts: List):
        self.prompts = prompts
        self.prompt_dict = {prompt.name: prompt for prompt in prompts}

    def update_resources(self, resources: List):
        self.resources = resources

    @staticmethod
    def _resource_id(resource) -> str:
        if isinstance(resource, str):
            return resource
        if isinstance(resource, dict):
            return str(resource.get("id", ""))
        return str(getattr(resource, "id", ""))

    def get_completions(self, document, complete_event):
        text = document.text
        text_before_cursor = document.text_before_cursor

        if "@" in text_before_cursor:
            last_at_pos = text_before_cursor.rfind("@")
            prefix = text_before_cursor[last_at_pos + 1 :]

            for resource_id in self.resources:
                if resource_id.lower().startswith(prefix.lower()):
                    yield Completion(
                        resource_id,
                        start_position=-len(prefix),
                        display=resource_id,
                        display_meta="Resource",
                    )
            return

        if text.startswith("/"):
            parts = text[1:].split()

            if len(parts) <= 1 and not text.endswith(" "):
                cmd_prefix = parts[0] if parts else ""

                for command in self.LOCAL_COMMANDS:
                    if command.startswith(cmd_prefix):
                        yield Completion(
                            command,
                            start_position=-len(cmd_prefix),
                            display=f"/{command}",
                            display_meta="Local command",
                        )

                for prompt in self.prompts:
                    if prompt.name.startswith(cmd_prefix):
                        yield Completion(
                            prompt.name,
                            start_position=-len(cmd_prefix),
                            display=f"/{prompt.name}",
                            display_meta=prompt.description or "",
                        )
                return

            if len(parts) == 1 and text.endswith(" "):
                cmd = parts[0]

                if cmd in self.prompt_dict:
                    for id in self.resources:
                        yield Completion(
                            id,
                            start_position=0,
                            display=id,
                        )
                return

            if len(parts) >= 2:
                doc_prefix = parts[-1]

                for resource in self.resources:
                    resource_id = self._resource_id(resource)
                    if resource_id.lower().startswith(doc_prefix.lower()):
                        yield Completion(
                            resource_id,
                            start_position=-len(doc_prefix),
                            display=resource_id,
                        )
                return


class CliApp:
    def __init__(self, agent: CliChat):
        self.agent = agent
        self.resources = []
        self.prompts = []

        self.completer = UnifiedCompleter()

        self.command_autosuggester = CommandAutoSuggest([])

        self.kb = KeyBindings()

        @self.kb.add("/")
        def _(event):
            buffer = event.app.current_buffer
            if buffer.document.is_cursor_at_the_end and not buffer.text:
                buffer.insert_text("/")
                buffer.start_completion(select_first=False)
            else:
                buffer.insert_text("/")

        @self.kb.add("@")
        def _(event):
            buffer = event.app.current_buffer
            buffer.insert_text("@")
            if buffer.document.is_cursor_at_the_end:
                buffer.start_completion(select_first=False)

        @self.kb.add(" ")
        def _(event):
            buffer = event.app.current_buffer
            text = buffer.text

            buffer.insert_text(" ")

            if text.startswith("/"):
                parts = text[1:].split()

                if len(parts) == 1:
                    buffer.start_completion(select_first=False)
                elif len(parts) == 2:
                    arg = parts[1]
                    if (
                        "doc" in arg.lower()
                        or "file" in arg.lower()
                        or "id" in arg.lower()
                    ):
                        buffer.start_completion(select_first=False)

        self.history = InMemoryHistory()
        try:
            self.session = PromptSession(
                completer=self.completer,
                history=self.history,
                key_bindings=self.kb,
                style=Style.from_dict(
                    {
                        "prompt": "#aaaaaa",
                        "completion-menu.completion": "bg:#222222 #ffffff",
                        "completion-menu.completion.current": "bg:#444444 #ffffff",
                    }
                ),
                complete_while_typing=True,
                complete_in_thread=True,
                auto_suggest=self.command_autosuggester,
            )
        except Exception:
            from prompt_toolkit.output import DummyOutput
            self.session = PromptSession(
                completer=self.completer,
                history=self.history,
                key_bindings=self.kb,
                output=DummyOutput(),
                auto_suggest=self.command_autosuggester,
            )

    async def initialize(self):
        await self.refresh_resources()
        await self.refresh_prompts()
        print(WELCOME_TEXT)

    async def handle_local_command(self, user_input: str) -> bool:
        """Handle commands that should not be sent to Gemini."""
        command = user_input.strip().casefold()
        if command in {"/help", "help"}:
            print(CLI_HELP_TEXT)
            return True
        if command in {"/documents", "/list"}:
            try:
                documents = await self.agent.list_docs_ids()
                if documents:
                    print("Available documents:")
                    for document in documents:
                        print(f"- {document}")
                else:
                    print("No supported documents were found.")
            except Exception as error:
                print(f"Could not list documents ({type(error).__name__}). Try again.")
            return True
        return False

    async def refresh_resources(self):
        try:
            self.resources = await self.agent.list_docs_ids()
            self.completer.update_resources(self.resources)
        except Exception as e:
            print(f"Error refreshing resources: {e}")

    async def refresh_prompts(self):
        try:
            self.prompts = await self.agent.list_prompts()
            self.completer.update_prompts(self.prompts)
            self.command_autosuggester = CommandAutoSuggest(self.prompts)
            self.session.auto_suggest = self.command_autosuggester
        except Exception as e:
            print(f"Error refreshing prompts: {e}")

    async def run(self):
        while True:
            try:
                user_input = await self.session.prompt_async("> ")
                if not user_input.strip():
                    continue

                if await self.handle_local_command(user_input):
                    continue

                response = await self.agent.run(user_input)
                print(f"\nResponse:\n{response}")

            except KeyboardInterrupt:
                break
            except RuntimeError as error:
                print(f"\nError: {error}")
                print("You can try another request or press Ctrl+C to exit.\n")
            except Exception as error:
                print(
                    f"\nRecoverable error ({type(error).__name__}). "
                    "Your session is still active; try again or press Ctrl+C to exit.\n"
                )
