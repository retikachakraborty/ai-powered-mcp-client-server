# MCP Chat

MCP Chat is a local command-line document assistant built around a FastMCP
stdio server, an MCP client, and Google Gemini tool calling. It keeps document
storage local and supports TXT, Markdown, PDF, and DOCX extraction.

## Requirements

- Ubuntu, macOS, or Windows
- Python 3.10 or newer
- [uv](https://docs.astral.sh/uv/)
- A Gemini API key only when running the interactive AI chat

The document server and the offline test suite do not require a Gemini API
request.

## Setup

From the project root:

```bash
uv sync --dev
```

Create the local document directory if it does not exist, then place supported
files inside it:

```bash
mkdir -p documents
```

For interactive chat, set `GEMINI_API_KEY` in your local `.env` file. The file
is intentionally ignored by Git. You may also set `GEMINI_MODEL`; otherwise the
application uses its configured default.

Gemini is required only for the natural-language AI chat. The MCP document
server, offline demo, and test suite work without Gemini requests.
The current interactive client checks for the key at startup because it is the
AI chat entrypoint; the standalone MCP server and offline workflows do not.

## Quick start

To verify document functionality without an API key:

```bash
uv sync --dev
mkdir -p documents
printf '# Quick start\n\nThis is a local MCP document.\n' > documents/quickstart.md
uv run python offline_demo.py
uv run pytest -q
```

For AI chat, configure `GEMINI_API_KEY` locally and then run:

```bash
uv run python main.py
```

Inside the client, try `/list`, then ask about the sample with
`Tell me about @quickstart.md`.

Run the client and document server together:

```bash
uv run python main.py
```

The client starts the document server over stdio. Do not run the server in a
terminal by itself unless you are connecting another MCP client to its stdio
transport.

Inside the interactive client, use `/help` for the command summary and
`/documents` or `/list` to list the files currently visible to the document
server. Tool completion and recoverable failures are reported in the terminal;
a failed request does not end the session.

## Document features

Place documents in `documents/`. Supported extensions are `.txt`, `.md`,
`.pdf`, and `.docx`.

- `@filename.ext` includes a document in a chat question.
- `/summarize filename.ext` creates a summarization prompt.
- `/format filename.ext` creates a preview-only Markdown-formatting prompt.
- The `search_documents` MCP tool performs case-insensitive search and returns
  ranked filenames with bounded snippets.
- Exact replacement editing is limited to TXT and Markdown files.

Formatting previews never edit files. Editing remains available only through
an explicit `edit_document` request.

Run a safe end-to-end document demonstration without Gemini or network access:

```bash
uv run python offline_demo.py
```

The demo creates a temporary Markdown file, lists it, searches it, reads it,
and performs an exact replacement. It never changes files in `documents/`.

Document IDs are filenames, not paths. Path traversal, unsupported formats,
and symbolic-link documents are rejected. Text edits use an atomic replacement
so an interrupted write does not leave a partially written document.

The document layer limits readable/editable files to 10 MiB by default. Set
`MCP_MAX_DOCUMENT_BYTES` to use a different positive byte limit, and
`MCP_MAX_EDIT_REPLACEMENTS` to change the default 100-replacement safety cap.
The public `edit_document(doc_id, old_str, new_str)` MCP contract is unchanged;
lower-level callers can additionally provide an expected replacement count.

## Understanding MCP: Tools, Resources, and Prompts

MCP (Model Context Protocol) is the connection between an MCP client and a
server. In this project, `mcp_server.py` is the server and the interactive
Gemini client is one client. MCP Inspector is a separate developer/testing
client. They are related, but they are not interchangeable:

- **Tools** are callable operations that perform a task or return a result.
- **Resources** expose information through MCP URIs such as
  `docs://documents`.
- **Prompts** are reusable instruction templates. Retrieving a prompt does not
  call Gemini or complete the requested AI task; an AI client must send the
  resulting instructions to a model.

The four tools, two resources, and two prompts registered by this project are
listed below. Reading and searching do not modify files. `edit_document` is the
only registered operation that intentionally modifies a document.

### Tools

#### `list_documents`

- **What it does:** Lists supported files in `documents/`.
- **Inputs:** None.
- **Output:** A sorted list of filenames, for example
  `["project_report.md", "meeting_notes.txt"]`.
- **Use it when:** You want to discover document IDs before reading or
  searching.
- **Inspector:** Open Tools, select `list_documents`, provide `{}`, and run it.
- **File effect:** Read-only.

#### `search_documents`

- **What it does:** Searches extracted document text case-insensitively.
- **Inputs:** Required `query` string; optional `limit` integer from 1 to 100,
  defaulting to 20.
- **Output:** Matching filename, occurrence count, and a bounded snippet, for
  example `{"document":"project_report.md","matches":2,"snippet":"...pilot..."}`.
- **Use it when:** You remember a term such as `rollback` but not which file
  contains it.
- **Inspector:** Open Tools, select `search_documents`, and run
  `{"query":"rollback","limit":5}`.
- **File effect:** Read-only. Files that cannot be extracted are skipped and
  reported with privacy-safe diagnostics.

#### `read_doc_contents`

- **What it does:** Extracts text from one document.
- **Inputs:** Required `doc_id` filename, such as `technical_guide.pdf`.
- **Output:** Extracted text from TXT, Markdown, PDF, or DOCX.
- **Use it when:** You need the full source text or want to inspect a document
  before asking an AI assistant to summarize or format it.
- **Inspector:** Open Tools, select `read_doc_contents`, and run
  `{"doc_id":"meeting_notes.txt"}`.
- **File effect:** Read-only. Scanned PDFs without an extractable text layer
  require OCR, which this project does not implement.

#### `edit_document`

- **What it does:** Replaces exact text in an existing TXT or Markdown file.
- **Inputs:** `doc_id`, exact `old_str`, and `new_str`.
- **Output:** A success message containing the replacement count.
- **Use it when:** You have reviewed the exact change and intentionally want
  to modify a disposable or approved TXT/Markdown file.
- **Inspector:** Open Tools, select `edit_document`, and run it only against a
  disposable copy, for example
  `{"doc_id":"disposable.md","old_str":"Draft","new_str":"Approved"}`.
- **File effect:** Modifies the actual file atomically. It rejects path
  traversal, symlinks, PDF/DOCX files, missing text, and empty replacements.
  The default safety cap is 100 replacements and can be changed with
  `MCP_MAX_EDIT_REPLACEMENTS`. The MCP tool itself can perform the edit when
  invoked; it does not promise an interactive approval dialog.

### Resources

#### `list_docs` — `docs://documents`

- **What it does:** The registered resource handler exposes available document
  filenames through the `docs://documents` URI.
- **Inputs:** The URI has no parameters.
- **Output:** A JSON-like list of filenames.
- **Use it when:** An MCP client needs document inventory as context rather
  than as a callable tool result.
- **Inspector:** Open Resources, enter or select `docs://documents`, and read
  it.
- **File effect:** Read-only.

This is similar to `list_documents`, but the access mechanism differs:
`list_documents` is a tool call, while `list_docs` is a resource read.

#### `fetch_doc` — `docs://documents/{doc_id}`

- **What it does:** The registered resource-template handler retrieves one
  document's extracted text through its URI.
- **Inputs:** A filename substituted into the URI, for example
  `docs://documents/meeting_notes.txt`.
- **Output:** Plain extracted text.
- **Use it when:** An MCP client wants document content as a resource.
- **Inspector:** Open Resources and read
  `docs://documents/meeting_notes.txt`.
- **File effect:** Read-only.

This is similar to `read_doc_contents`, but `read_doc_contents` is a tool call
with a `doc_id` argument while `fetch_doc` is a resource-template read.

### Prompts

#### `summarize`

- **What it does:** Generates a reusable summarization instruction containing
  the selected document's extracted text.
- **Inputs:** Required `doc_id`, such as `project_report.md`.
- **Output:** Prompt content asking an AI assistant to summarize the document.
- **Use it when:** You want a consistent summarization request for an AI
  client.
- **Inspector:** Open Prompts, select `summarize`, provide
  `{"doc_id":"project_report.md"}`, and retrieve it.
- **File effect:** Reads the document; it does not modify it or itself generate
  a summary. An AI client must use the prompt with a model.

#### `format`

- **What it does:** Generates instructions for an AI assistant to propose a
  clearer Markdown structure with headings, lists, and organization.
- **Inputs:** Required `doc_id`, such as `project_report.md`.
- **Output:** Preview-only formatting instructions.
- **Use it when:** You want a proposed presentation change while preserving the
  document's meaning.
- **Inspector:** Open Prompts, select `format`, provide
  `{"doc_id":"project_report.md"}`, and retrieve it.
- **File effect:** Preview/read guidance only. It must not automatically call
  `edit_document`; a separate explicit request is required to edit TXT or
  Markdown. PDF and DOCX files must not be edited through this prompt.

`summarize` condenses and explains key information. `format` proposes clearer
structure and presentation while aiming to preserve the meaning. Both are
instruction templates, not independently executing AI features.

### MCP Inspector walkthrough

Inspector is a developer/testing interface for connecting to an MCP server. It
is not the ordinary Gemini chat UI and it does not automatically call Gemini
when you retrieve a prompt.

1. Install or otherwise make `npx` available, then run this in the **terminal**
   from the project directory:

   ```bash
   npx @modelcontextprotocol/inspector
   ```

2. In Inspector, choose a **STDIO** connection.
3. Set the command to `uv` and arguments to:
   `run python /absolute/path/to/mcp-project/mcp_server.py`.
   Alternatively, set the command to the project interpreter and pass the
   absolute path to `mcp_server.py`.
4. Connect. The server does not need `GEMINI_API_KEY` for tool, resource, or
   prompt discovery.
5. Use the **Tools** panel for the four tool examples above, **Resources** for
   `docs://documents` and `docs://documents/{doc_id}`, and **Prompts** for
   `summarize` and `format`.
6. Use a disposable TXT/Markdown copy before testing `edit_document`; it
   changes the actual file and does not provide an Inspector approval dialog.

The Inspector connection tests the MCP server directly. The interactive CLI
adds prompt-toolkit autocomplete and Gemini-backed conversation on top of MCP;
testing one does not verify the other.

## Development

Run the offline checks with:

```bash
uv run pytest
uv run python -m compileall -q main.py mcp_server.py mcp_client.py core
```

Tests create temporary PDF, DOCX, and text fixtures. They do not initialize
Gemini or make network requests.

The fictional sample documents can be copied without overwriting existing user
files. Run this from the project root; it reports every skipped filename:

```bash
mkdir -p documents
for file in examples/sample_documents/*; do
  name="$(basename "$file")"
  target="documents/$name"
  if [ -e "$target" ]; then
    echo "Skipping existing $target"
  else
    cp "$file" "$target"
    echo "Copied $target"
  fi
done
```

The examples are fictional and contain no credentials or real confidential
information. Review any file before copying it into a directory containing
private documents.

Limitations: Gemini is required for natural-language chat, scanned PDFs do not
provide OCR, and editing is exact text replacement rather than a general
document editor. PDF and DOCX files are readable but not editable. The live
Gemini tool-calling workflow is not covered by the offline test suite.

## Troubleshooting and security

- **Missing API key:** The MCP server and offline tests work without Gemini;
  configure `GEMINI_API_KEY` locally only before starting `main.py` for AI chat.
- **Quota or rate-limit errors:** Wait or check the Gemini account quota; the
  application reports a safe error without printing API-key values.
- **Scanned PDF:** OCR is not implemented. Provide a PDF with a text layer or
  extract the text separately before using this project.
- **Private files:** Keep confidential files in `documents/` only on trusted
  machines. Do not commit `.env`, credentials, private documents, `.venv`, or
  generated files.
- **Edits:** Use a disposable copy for Inspector demonstrations and review
  exact replacement text before invoking `edit_document`.

Future deployment could place the MCP server behind an appropriately secured
MCP host or provide a separate authenticated service. This repository currently
implements local stdio operation only; it does not provide a hosted deployment.

The main modules are organized as follows:

```text
mcp_server.py       FastMCP tools, resources, and prompts
mcp_client.py       stdio MCP client wrapper
core/documents.py   safe paths, extraction, search, and atomic edits
core/tools.py       Gemini-to-MCP tool dispatch
core/gemini.py      Gemini adapter and response normalization
core/cli*.py        prompt-toolkit CLI and autocomplete
tests/              offline regression tests
examples/sample_documents/ fictional PDF, DOCX, Markdown, and TXT examples
documents/          user-managed document storage
```

Do not add `.env`, API keys, `.venv`, caches, or generated package metadata to
Git. Existing Git history contains sensitive material; this project must not
reuse that history for a public repository. Do not commit, push, or publish
without explicit approval.
