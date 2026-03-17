"""Document parsers — extract text content from various file formats.

Parser Tiers per PHASE1_ARCHITECTURE_CORE_DESIGN.md Section 12:
  Tier 1 (committed): Markdown, plain text, source code, PDF, DOCX, XLSX
  Tier 2 (conditional): HWPX (formatting-loss caveats accepted)

Parser routing per Implementation Spec Task 1.1.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from jarvis.contracts import AccessStatus, DocumentRecord, IndexingStatus

logger = logging.getLogger(__name__)

# --- Extension → type mapping ---

_EXTENSION_TYPE_MAP: dict[str, str] = {
    # Text / Markdown
    ".md": "markdown",
    ".markdown": "markdown",
    ".txt": "text",
    ".rst": "text",
    ".cfg": "text",
    ".toml": "text",
    ".ini": "text",
    # Code
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".json": "json",
    # Tier 1: binary document formats
    ".pdf": "pdf",
    ".docx": "docx",
    ".xlsx": "xlsx",
    # Tier 2: Korean document formats
    ".hwpx": "hwpx",
    # Tier 3: legacy binary HWP (experimental)
    ".hwp": "hwp",
}

# Types that require specialized parsers (not plain read_text)
_BINARY_TYPES: frozenset[str] = frozenset({"pdf", "docx", "xlsx", "hwpx", "hwp"})


# --- Individual format parsers ---


def _parse_pdf(path: Path) -> str:
    """Extract text from PDF using PyMuPDF.

    Limits to first 500KB of text to avoid excessive chunking
    on very large PDFs (e.g. 16MB C# reference = 2.8M chars).
    """
    import pymupdf

    _MAX_TEXT_CHARS = 500_000  # ~250K tokens, more than enough for RAG

    pages: list[str] = []
    total_chars = 0
    with pymupdf.open(str(path)) as doc:
        for page in doc:
            text = page.get_text()
            if text.strip():
                pages.append(text)
                total_chars += len(text)
                if total_chars > _MAX_TEXT_CHARS:
                    logger.info("PDF truncated at %d chars: %s", total_chars, path.name)
                    break
    return "\n\n".join(pages)


def _parse_docx(path: Path) -> str:
    """Extract text from DOCX using python-docx."""
    from docx import Document

    doc = Document(str(path))
    parts: list[str] = []

    # Paragraphs
    for para in doc.paragraphs:
        if para.text.strip():
            parts.append(para.text)

    # Tables
    for table in doc.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
            if cells:
                parts.append(" | ".join(cells))

    return "\n\n".join(parts)


def _parse_xlsx(path: Path) -> str:
    """Extract text from XLSX using openpyxl.

    Each row becomes a separate paragraph (\\n\\n separated)
    so the Chunker can split at row boundaries.
    Header row is prepended to each data row for context.
    """
    from openpyxl import load_workbook

    wb = load_workbook(str(path), read_only=True, data_only=True)
    parts: list[str] = []

    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        header: str = ""
        row_idx = 0

        for row in ws.iter_rows(values_only=True):
            cells = [str(c) for c in row if c is not None]
            if not cells:
                continue

            row_text = " | ".join(cells)

            if row_idx == 0:
                # First row is header
                header = row_text
                parts.append(f"[{sheet_name}] {header}")
            else:
                # Data rows: include header mapping for context
                parts.append(f"[{sheet_name}] {row_text}")

            row_idx += 1

    wb.close()
    return "\n\n".join(parts)


def _parse_hwpx(path: Path) -> str:
    """Extract text from HWPX (Korean word processor, XML-based ZIP).

    HWPX is a ZIP archive containing OWPML XML (KS X 6101).
    Formatting loss is accepted per spec.
    """
    try:
        from hwpx import HWPXFile

        hwpx_file = HWPXFile(str(path))
        return hwpx_file.get_text()
    except Exception:
        # Fallback: manual ZIP+XML extraction
        return _parse_hwpx_fallback(path)


def _parse_hwpx_fallback(path: Path) -> str:
    """Fallback HWPX parser using direct ZIP+XML extraction."""
    import zipfile
    from xml.etree import ElementTree

    parts: list[str] = []

    with zipfile.ZipFile(str(path), "r") as zf:
        for name in zf.namelist():
            if name.startswith("Contents/") and name.endswith(".xml"):
                try:
                    xml_bytes = zf.read(name)
                    root = ElementTree.fromstring(xml_bytes)
                    # Extract all text content from XML
                    for elem in root.iter():
                        if elem.text and elem.text.strip():
                            parts.append(elem.text.strip())
                        if elem.tail and elem.tail.strip():
                            parts.append(elem.tail.strip())
                except ElementTree.ParseError:
                    continue

    return "\n".join(parts)


def _parse_hwp(path: Path) -> str:
    """Extract text from legacy binary HWP using pyhwp (hwp5txt).

    Tier 3 experimental — formatting loss is expected.
    """
    import subprocess

    result = subprocess.run(
        ["hwp5txt", str(path)],
        capture_output=True,
        text=True,
        timeout=60,
    )

    if result.returncode != 0:
        raise RuntimeError(f"hwp5txt failed: {result.stderr[:200]}")

    # Clean up: remove <그림> placeholders and excessive blank lines
    import re

    text = result.stdout
    text = re.sub(r"<그림>", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# --- Parser dispatch ---

_PARSER_DISPATCH: dict[str, object] = {
    "pdf": _parse_pdf,
    "docx": _parse_docx,
    "xlsx": _parse_xlsx,
    "hwpx": _parse_hwpx,
    "hwp": _parse_hwp,
}


class DocumentParser:
    """Parses files into raw text for downstream chunking and indexing.

    Routes to specialized parsers for binary formats (PDF, DOCX, XLSX, HWPX, HWP).
    Falls back to UTF-8 read_text for text-based formats.
    """

    def detect_type(self, path: Path) -> str:
        """Detect the document type from file extension."""
        suffix = Path(path).suffix.lower()
        return _EXTENSION_TYPE_MAP.get(suffix, "text")

    def parse(self, path: Path) -> str:
        """Extract text content from a file.

        Routes to specialized parsers for binary formats.
        Falls back to UTF-8 text read for all other formats.

        Raises:
            FileNotFoundError: If the file does not exist.
        """
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"File not found: {path}")

        doc_type = self.detect_type(p)

        if doc_type in _BINARY_TYPES:
            parser_fn = _PARSER_DISPATCH[doc_type]
            try:
                return parser_fn(p)  # type: ignore[operator]
            except Exception as e:
                logger.warning("Parser failed for %s (%s): %s", p, doc_type, e)
                raise

        return p.read_text(encoding="utf-8")

    def create_record(self, path: Path) -> DocumentRecord:
        """Create a DocumentRecord for a file.

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
