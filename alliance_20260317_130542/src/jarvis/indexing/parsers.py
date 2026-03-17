"""Document parsers — extract text content from various file formats.

Supports plain text, Markdown, and code files for Phase 1.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from jarvis.contracts import AccessStatus, DocumentRecord, IndexingStatus


_EXTENSION_TYPE_MAP: dict[str, str] = {
    ".md": "markdown",
    ".markdown": "markdown",
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".json": "json",
    ".txt": "text",
    ".rst": "text",
    ".cfg": "text",
    ".toml": "text",
    ".ini": "text",
}


class DocumentParser:
    """Parses files into raw text for downstream chunking and indexing."""

    def detect_type(self, path: Path) -> str:
        """Detect the document type from file extension.

        Args:
            path: Path to the file.

        Returns:
            A string identifier for the document type (e.g. 'markdown', 'python', 'text').
            Returns 'text' for unknown extensions.
        """
        suffix = Path(path).suffix.lower()
        return _EXTENSION_TYPE_MAP.get(suffix, "text")

    def parse(self, path: Path) -> str:
        """Extract text content from a file.

        Args:
            path: Path to the file to parse.

        Returns:
            Extracted text content as a UTF-8 string.

        Raises:
            FileNotFoundError: If the file does not exist.
        """
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"File not found: {path}")
        return p.read_text(encoding="utf-8")

    def create_record(self, path: Path) -> DocumentRecord:
        """Create a DocumentRecord for a file.

        Args:
            path: Path to the file.

        Returns:
            A DocumentRecord with metadata populated.

        Raises:
            FileNotFoundError: If the file does not exist.
        """
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"File not found: {path}")

        raw_bytes = p.read_bytes()
        content_hash = hashlib.sha256(raw_bytes).hexdigest()
        size_bytes = p.stat().st_size

        return DocumentRecord(
            path=str(p),
            content_hash=content_hash,
            size_bytes=size_bytes,
            indexing_status=IndexingStatus.PENDING,
            access_status=AccessStatus.ACCESSIBLE,
        )
