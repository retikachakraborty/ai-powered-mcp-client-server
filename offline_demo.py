"""Demonstrate document operations without Gemini, network, or user files."""

from __future__ import annotations

import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TextIO

from core.documents import (
    list_documents,
    read_document_content,
    replace_document_text,
    search_documents,
)


def run_demo(output: TextIO = sys.stdout) -> None:
    """Run a safe document workflow entirely in a temporary directory."""
    with TemporaryDirectory(prefix="mcp-document-demo-") as directory:
        documents_dir = Path(directory)
        document = documents_dir / "demo.md"
        document.write_text(
            "# Offline demo\n\nMCP documents stay local.\n",
            encoding="utf-8",
        )

        print("1. List documents", file=output)
        print(list_documents(documents_dir), file=output)

        print("2. Search for 'MCP'", file=output)
        print(search_documents(documents_dir, "MCP"), file=output)

        print("3. Read demo.md", file=output)
        print(read_document_content(documents_dir, "demo.md"), file=output)

        print("4. Edit demo.md", file=output)
        replacements = replace_document_text(
            documents_dir, "demo.md", "stay local", "remain local"
        )
        print(f"Replacements: {replacements}", file=output)
        print(read_document_content(documents_dir, "demo.md"), file=output)


if __name__ == "__main__":
    run_demo()
