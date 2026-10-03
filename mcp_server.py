from pathlib import Path

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.prompts import base
from mcp.types import ToolAnnotations
from pydantic import Field

from core.documents import (
    EDITABLE_EXTENSIONS,
    SUPPORTED_EXTENSIONS,
    list_documents as _list_documents,
    read_document_content as _read_document_content,
    replace_document_text,
    resolve_document_path,
    search_documents,
)


mcp = FastMCP("DocumentMCP", log_level="ERROR")

DOCUMENTS_DIR = (Path(__file__).resolve().parent / "documents").resolve()


def get_document_path(doc_id: str) -> Path:
    """Resolve a document ID safely within the documents directory."""
    return resolve_document_path(DOCUMENTS_DIR, doc_id)


def read_document_content(doc_id: str) -> str:
    """Extract text from a supported document."""
    return _read_document_content(DOCUMENTS_DIR, doc_id)


@mcp.tool(
    name="list_documents",
    description="List all available documents in the MCP server.",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def list_documents() -> list[str]:
    """Return supported document filenames."""
    return _list_documents(DOCUMENTS_DIR)


@mcp.tool(
    name="search_documents",
    description="Search all supported documents and return matching filenames and snippets.",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def search_docs(
    query: str = Field(description="Case-insensitive text to search for"),
    limit: int = 20,
) -> list[dict[str, str | int]]:
    return search_documents(DOCUMENTS_DIR, query, limit=limit)


@mcp.tool(
    name="read_doc_contents",
    description="Read the text contents of a document.",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def read_document(
    doc_id: str = Field(description="Filename of the document to read")
) -> str:
    return read_document_content(doc_id)


@mcp.tool(
    name="edit_document",
    description="Replace exact text in a TXT or Markdown document.",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=True,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def edit_document(
    doc_id: str = Field(description="Filename of the document to edit"),
    old_str: str = Field(description="Exact text to replace"),
    new_str: str = Field(description="Replacement text")
) -> str:
    replacements = replace_document_text(DOCUMENTS_DIR, doc_id, old_str, new_str)

    return f"Successfully updated '{doc_id}' ({replacements} replacement(s))."


@mcp.resource(
    "docs://documents",
    mime_type="application/json"
)
def list_docs() -> list[str]:
    return list_documents()


@mcp.resource(
    "docs://documents/{doc_id}",
    mime_type="text/plain"
)
def fetch_doc(doc_id: str) -> str:
    return read_document_content(doc_id)


@mcp.prompt(
    name="format",
    description="Preview a Markdown reformatting without editing the document."
)
def format_document(
    doc_id: str = Field(description="Filename of the document to format")
) -> list[base.Message]:
    prompt = f"""
    Prepare a preview of how the document '{doc_id}' could be formatted using
    Markdown syntax.

    Read the document using the read_doc_contents tool.
    Add appropriate headings, bullet points, and structure.

    This is preview-only: do not call edit_document and do not modify any file
    during this request, including TXT or Markdown files. Return the proposed
    Markdown content and a concise explanation of the changes. Editing requires
    a separate user request that explicitly approves the proposed changes and
    uses edit_document. Never edit PDF or DOCX files.
    """
    return [base.UserMessage(prompt)]


@mcp.prompt("summarize")
def summarize_doc_prompt(doc_id: str) -> str:
    """Summarize a document."""
    content = read_document_content(doc_id)
    return f"Please summarize the following document ({doc_id}):\n\n{content}"


if __name__ == "__main__":
    mcp.run(transport="stdio")
