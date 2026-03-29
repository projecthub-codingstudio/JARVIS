# Semantic Chunking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace single byte-size Chunker with document-type-specific semantic chunking that produces precise, meaningful chunks for each file format.

**Architecture:** Parser returns structured `ParsedDocument` with typed `DocumentElement` list. `ChunkRouter` dispatches each element to the appropriate `ChunkStrategy` (Table, Code, Heading, Paragraph). Backward compatible — old `Chunker.chunk(text)` still works.

**Tech Stack:** Python 3.12, tree-sitter (optional), openpyxl, python-docx, pymupdf, existing test fixtures.

**Spec:** `docs/superpowers/specs/2026-03-22-semantic-chunking-design.md`

---

## File Structure

| File | Responsibility |
|------|---------------|
| `src/jarvis/contracts/models.py` | Add `DocumentElement`, `ParsedDocument` dataclasses |
| `src/jarvis/indexing/chunk_router.py` | NEW — routes elements to strategies, main entry point |
| `src/jarvis/indexing/strategies/__init__.py` | NEW — strategy package |
| `src/jarvis/indexing/strategies/table.py` | NEW — row-level chunking with header mapping |
| `src/jarvis/indexing/strategies/code.py` | NEW — AST-aware chunking (tree-sitter optional) |
| `src/jarvis/indexing/strategies/heading.py` | NEW — heading-level section splitting |
| `src/jarvis/indexing/strategies/paragraph.py` | NEW — extract current Chunker logic |
| `src/jarvis/indexing/parsers.py` | Each parser returns `ParsedDocument` + backward compat |
| `src/jarvis/indexing/chunker.py` | Delegate to ChunkRouter, keep old API |
| `src/jarvis/indexing/index_pipeline.py` | Use `parse()` → `ChunkRouter.chunk()` |
| `tests/indexing/test_document_elements.py` | NEW — test data models |
| `tests/indexing/test_chunk_router.py` | NEW — test routing logic |
| `tests/indexing/test_table_strategy.py` | NEW — test table chunking |
| `tests/indexing/test_code_strategy.py` | NEW — test code chunking |
| `tests/indexing/test_heading_strategy.py` | NEW — test heading chunking |
| `tests/indexing/test_parsers_structured.py` | NEW — test structured parser output |

---

### Task 1: Data Models — DocumentElement and ParsedDocument

**Files:**
- Modify: `src/jarvis/contracts/models.py`
- Create: `tests/indexing/test_document_elements.py`

- [ ] **Step 1: Write failing tests for data models**

```python
# tests/indexing/test_document_elements.py
"""Tests for DocumentElement and ParsedDocument data models."""
from jarvis.contracts import DocumentElement, ParsedDocument


class TestDocumentElement:
    def test_create_text_element(self) -> None:
        el = DocumentElement(element_type="text", text="Hello world")
        assert el.element_type == "text"
        assert el.text == "Hello world"
        assert el.metadata == {}

    def test_create_table_element(self) -> None:
        el = DocumentElement(
            element_type="table",
            text="Day | Breakfast",
            metadata={
                "headers": ("Day", "Breakfast"),
                "rows": (("1", "eggs"),),
                "sheet_name": "Sheet1",
            },
        )
        assert el.element_type == "table"
        assert el.metadata["headers"] == ("Day", "Breakfast")

    def test_create_code_element(self) -> None:
        el = DocumentElement(
            element_type="code",
            text="def foo(): pass",
            metadata={"language": "python", "scope_chain": "module > foo"},
        )
        assert el.element_type == "code"
        assert el.metadata["language"] == "python"


class TestParsedDocument:
    def test_to_text(self) -> None:
        doc = ParsedDocument(
            elements=(
                DocumentElement(element_type="text", text="Hello"),
                DocumentElement(element_type="text", text="World"),
            ),
            metadata={"filename": "test.md"},
        )
        assert doc.to_text() == "Hello\n\nWorld"

    def test_empty_document(self) -> None:
        doc = ParsedDocument(elements=(), metadata={})
        assert doc.to_text() == ""
        assert len(doc.elements) == 0
```

- [ ] **Step 2: Run tests — expect FAIL (ImportError)**

Run: `python -m pytest tests/indexing/test_document_elements.py -v`

- [ ] **Step 3: Implement data models**

Add to `src/jarvis/contracts/models.py` (after ChunkRecord):

```python
@dataclass(frozen=True)
class DocumentElement:
    """A typed element extracted from a parsed document.

    element_type: "text", "table", "code", "list", "slide"
    metadata: type-specific data (headers, rows, language, scope_chain, etc.)
    """
    element_type: str
    text: str
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ParsedDocument:
    """Structured parser output with typed elements."""
    elements: tuple[DocumentElement, ...]
    metadata: dict = field(default_factory=dict)

    def to_text(self) -> str:
        """Backward-compatible plain text rendering."""
        return "\n\n".join(e.text for e in self.elements if e.text)
```

Add to `src/jarvis/contracts/__init__.py`:
```python
from jarvis.contracts.models import DocumentElement, ParsedDocument
```

- [ ] **Step 4: Run tests — expect PASS**

Run: `python -m pytest tests/indexing/test_document_elements.py -v`

- [ ] **Step 5: Commit**

```bash
git add src/jarvis/contracts/models.py src/jarvis/contracts/__init__.py tests/indexing/test_document_elements.py
git commit -m "feat: add DocumentElement and ParsedDocument data models"
```

---

### Task 2: ChunkStrategy Protocol and ParagraphChunkStrategy

**Files:**
- Create: `src/jarvis/indexing/strategies/__init__.py`
- Create: `src/jarvis/indexing/strategies/paragraph.py`
- Create: `tests/indexing/test_heading_strategy.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/indexing/test_heading_strategy.py
"""Tests for ParagraphChunkStrategy (default strategy)."""
from jarvis.contracts import DocumentElement
from jarvis.indexing.strategies.paragraph import ParagraphChunkStrategy


class TestParagraphChunkStrategy:
    def test_single_paragraph(self) -> None:
        el = DocumentElement(element_type="text", text="Short paragraph.")
        strategy = ParagraphChunkStrategy()
        chunks = strategy.chunk(el, document_id="d1")
        assert len(chunks) >= 1
        assert "Short paragraph" in chunks[0].text

    def test_long_text_splits(self) -> None:
        el = DocumentElement(element_type="text", text="Word " * 500)
        strategy = ParagraphChunkStrategy(max_tokens=100)
        chunks = strategy.chunk(el, document_id="d1")
        assert len(chunks) > 1

    def test_respects_paragraph_boundaries(self) -> None:
        text = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
        el = DocumentElement(element_type="text", text=text)
        strategy = ParagraphChunkStrategy(max_tokens=20)
        chunks = strategy.chunk(el, document_id="d1")
        # Should not split mid-paragraph
        for c in chunks:
            assert "First" in c.text or "Second" in c.text or "Third" in c.text

    def test_heading_path_preserved(self) -> None:
        text = "# Architecture\n\nThe system uses monolith design."
        el = DocumentElement(element_type="text", text=text, metadata={"heading_path": "Architecture"})
        strategy = ParagraphChunkStrategy()
        chunks = strategy.chunk(el, document_id="d1")
        assert chunks[0].heading_path  # heading metadata preserved
```

- [ ] **Step 2: Run tests — expect FAIL**

- [ ] **Step 3: Implement**

```python
# src/jarvis/indexing/strategies/__init__.py
"""Chunk strategies for document-type-specific splitting."""

# src/jarvis/indexing/strategies/paragraph.py
"""ParagraphChunkStrategy — default text chunking by paragraph boundaries.

Extracted from the original Chunker logic. Splits on double-newline,
respects heading hierarchy, applies overlap.
"""
from __future__ import annotations
from jarvis.contracts import ChunkRecord, DocumentElement
from jarvis.indexing.chunker import Chunker


class ParagraphChunkStrategy:
    """Default chunk strategy using paragraph boundaries."""

    def __init__(self, *, max_tokens: int = 500, overlap_tokens: int = 80) -> None:
        self._chunker = Chunker(max_tokens=max_tokens, overlap_tokens=overlap_tokens)

    def chunk(self, element: DocumentElement, *, document_id: str) -> list[ChunkRecord]:
        chunks = self._chunker.chunk(element.text, document_id=document_id)
        # Apply heading_path from element metadata if available
        heading = element.metadata.get("heading_path", "")
        if heading:
            from dataclasses import replace
            chunks = [replace(c, heading_path=heading) if not c.heading_path else c for c in chunks]
        return chunks
```

- [ ] **Step 4: Run tests — expect PASS**
- [ ] **Step 5: Commit**

---

### Task 3: TableChunkStrategy

**Files:**
- Create: `src/jarvis/indexing/strategies/table.py`
- Create: `tests/indexing/test_table_strategy.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/indexing/test_table_strategy.py
"""Tests for TableChunkStrategy — row-level chunking with header mapping."""
from jarvis.contracts import DocumentElement
from jarvis.indexing.strategies.table import TableChunkStrategy


class TestTableChunkStrategy:
    def test_each_row_becomes_chunk(self) -> None:
        el = DocumentElement(
            element_type="table",
            text="",
            metadata={
                "headers": ("Day", "Breakfast", "Lunch"),
                "rows": (
                    ("1", "eggs", "chicken"),
                    ("2", "toast", "salad"),
                    ("3", "yogurt", "soup"),
                ),
                "sheet_name": "Diet",
            },
        )
        strategy = TableChunkStrategy()
        chunks = strategy.chunk(el, document_id="d1")
        # 3 row chunks + 1 summary = 4
        assert len(chunks) >= 3

    def test_header_mapped_to_values(self) -> None:
        el = DocumentElement(
            element_type="table",
            text="",
            metadata={
                "headers": ("Day", "Breakfast"),
                "rows": (("9", "구운계란2+요거트+베리"),),
                "sheet_name": "Diet",
            },
        )
        strategy = TableChunkStrategy()
        chunks = strategy.chunk(el, document_id="d1")
        row_chunk = [c for c in chunks if "Day=9" in c.text][0]
        assert "Breakfast=구운계란2+요거트+베리" in row_chunk.text

    def test_summary_chunk_included(self) -> None:
        el = DocumentElement(
            element_type="table",
            text="",
            metadata={
                "headers": ("A", "B", "C"),
                "rows": (("1", "2", "3"), ("4", "5", "6")),
                "sheet_name": "Sheet1",
            },
        )
        strategy = TableChunkStrategy()
        chunks = strategy.chunk(el, document_id="d1")
        summary = [c for c in chunks if "columns:" in c.text.lower() or "rows:" in c.text.lower()]
        assert len(summary) >= 1

    def test_small_table_single_chunk(self) -> None:
        el = DocumentElement(
            element_type="table",
            text="",
            metadata={
                "headers": ("Name", "Value"),
                "rows": (("a", "1"), ("b", "2")),
                "sheet_name": "Config",
            },
        )
        strategy = TableChunkStrategy()
        chunks = strategy.chunk(el, document_id="d1")
        # Very small table: may produce single combined chunk + summary
        assert len(chunks) >= 1

    def test_empty_table(self) -> None:
        el = DocumentElement(
            element_type="table", text="",
            metadata={"headers": (), "rows": (), "sheet_name": "Empty"},
        )
        strategy = TableChunkStrategy()
        chunks = strategy.chunk(el, document_id="d1")
        assert len(chunks) == 0
```

- [ ] **Step 2: Run tests — expect FAIL**

- [ ] **Step 3: Implement**

```python
# src/jarvis/indexing/strategies/table.py
"""TableChunkStrategy — row-level chunking with header mapping for structured data."""
from __future__ import annotations
import hashlib
from jarvis.contracts import ChunkRecord, DocumentElement


class TableChunkStrategy:
    """Chunks table data with each row as an independent chunk.

    Each row chunk includes header-mapped key=value pairs so the LLM
    can identify which column each value belongs to without needing
    the full table context.
    """

    def __init__(self, *, min_rows_for_split: int = 4) -> None:
        self._min_rows_for_split = min_rows_for_split

    def chunk(self, element: DocumentElement, *, document_id: str) -> list[ChunkRecord]:
        headers = element.metadata.get("headers", ())
        rows = element.metadata.get("rows", ())
        sheet_name = element.metadata.get("sheet_name", "")

        if not rows:
            return []

        chunks: list[ChunkRecord] = []

        # Summary chunk (table overview)
        summary = self._build_summary(sheet_name, headers, len(rows))
        chunks.append(self._make_chunk(summary, document_id, f"table-summary-{sheet_name}"))

        # Small tables: single chunk with all rows
        if len(rows) < self._min_rows_for_split:
            full_text = self._render_full_table(sheet_name, headers, rows)
            chunks.append(self._make_chunk(full_text, document_id, f"table-full-{sheet_name}"))
            return chunks

        # Each row as independent chunk with header mapping
        for row_idx, row in enumerate(rows):
            row_text = self._render_row(sheet_name, headers, row, row_idx)
            chunks.append(self._make_chunk(row_text, document_id, f"table-row-{sheet_name}-{row_idx}"))

        return chunks

    def _render_row(self, sheet_name: str, headers: tuple, row: tuple, row_idx: int) -> str:
        pairs = []
        for i, val in enumerate(row):
            header = headers[i] if i < len(headers) else f"col{i}"
            pairs.append(f"{header}={val}")
        prefix = f"[{sheet_name}] " if sheet_name else ""
        return f"{prefix}{' | '.join(pairs)}"

    def _render_full_table(self, sheet_name: str, headers: tuple, rows: tuple) -> str:
        prefix = f"[{sheet_name}] " if sheet_name else ""
        lines = [f"{prefix}{' | '.join(headers)}"]
        for row in rows:
            lines.append(f"{prefix}{' | '.join(row)}")
        return "\n".join(lines)

    def _build_summary(self, sheet_name: str, headers: tuple, row_count: int) -> str:
        cols = ", ".join(headers) if headers else "unknown"
        return f"[{sheet_name}] Table with {row_count} rows. Columns: {cols}"

    def _make_chunk(self, text: str, document_id: str, label: str) -> ChunkRecord:
        chunk_bytes = text.encode("utf-8")
        return ChunkRecord(
            document_id=document_id,
            text=text,
            chunk_hash=hashlib.sha256(chunk_bytes).hexdigest(),
            heading_path=label,
        )
```

- [ ] **Step 4: Run tests — expect PASS**
- [ ] **Step 5: Commit**

---

### Task 4: CodeChunkStrategy

**Files:**
- Create: `src/jarvis/indexing/strategies/code.py`
- Create: `tests/indexing/test_code_strategy.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/indexing/test_code_strategy.py
"""Tests for CodeChunkStrategy — function/class boundary splitting."""
from jarvis.contracts import DocumentElement
from jarvis.indexing.strategies.code import CodeChunkStrategy


class TestCodeChunkStrategy:
    def test_splits_at_function_boundaries(self) -> None:
        code = '''def foo():
    return 1

def bar():
    return 2

def baz():
    return 3
'''
        el = DocumentElement(element_type="code", text=code, metadata={"language": "python"})
        strategy = CodeChunkStrategy()
        chunks = strategy.chunk(el, document_id="d1")
        # Should produce separate chunks for each function
        assert len(chunks) >= 2
        texts = [c.text for c in chunks]
        assert any("def foo" in t for t in texts)
        assert any("def bar" in t for t in texts)

    def test_class_with_methods(self) -> None:
        code = '''class MyClass:
    def method_a(self):
        pass

    def method_b(self):
        pass
'''
        el = DocumentElement(element_type="code", text=code, metadata={"language": "python"})
        strategy = CodeChunkStrategy()
        chunks = strategy.chunk(el, document_id="d1")
        assert len(chunks) >= 1

    def test_fallback_without_tree_sitter(self) -> None:
        """Should work even if tree-sitter is not installed."""
        code = "def hello():\n    print('hello')\n"
        el = DocumentElement(element_type="code", text=code, metadata={"language": "unknown_lang"})
        strategy = CodeChunkStrategy()
        chunks = strategy.chunk(el, document_id="d1")
        assert len(chunks) >= 1
        assert "hello" in chunks[0].text

    def test_short_code_single_chunk(self) -> None:
        code = "x = 1\n"
        el = DocumentElement(element_type="code", text=code, metadata={"language": "python"})
        strategy = CodeChunkStrategy()
        chunks = strategy.chunk(el, document_id="d1")
        assert len(chunks) == 1
```

- [ ] **Step 2: Run tests — expect FAIL**

- [ ] **Step 3: Implement**

```python
# src/jarvis/indexing/strategies/code.py
"""CodeChunkStrategy — splits code at function/class boundaries.

Uses regex-based heuristic for Python (def/class detection).
Tree-sitter integration deferred — can be added without API change.
"""
from __future__ import annotations
import hashlib
import re
from jarvis.contracts import ChunkRecord, DocumentElement

# Regex patterns for top-level definitions
_PY_DEF_RE = re.compile(r"^(class |def |async def )", re.MULTILINE)
_CHARS_PER_TOKEN = 3
_MAX_CHUNK_CHARS = 500 * _CHARS_PER_TOKEN


class CodeChunkStrategy:
    """Splits code at function/class definition boundaries."""

    def __init__(self, *, max_tokens: int = 500) -> None:
        self._max_chars = max_tokens * _CHARS_PER_TOKEN

    def chunk(self, element: DocumentElement, *, document_id: str) -> list[ChunkRecord]:
        text = element.text
        if not text.strip():
            return []

        language = element.metadata.get("language", "")

        # Try splitting at definition boundaries
        blocks = self._split_by_definitions(text, language)

        if len(blocks) <= 1:
            # Single block or no definitions found — use as-is or split by size
            return self._size_split(text, document_id, language)

        # Merge small adjacent blocks, respect max size
        chunks: list[ChunkRecord] = []
        current_parts: list[str] = []
        current_len = 0

        for block in blocks:
            if current_len + len(block) > self._max_chars and current_parts:
                chunk_text = "\n".join(current_parts)
                chunks.append(self._make_chunk(chunk_text, document_id, language))
                current_parts = []
                current_len = 0
            current_parts.append(block)
            current_len += len(block)

        if current_parts:
            chunks.append(self._make_chunk("\n".join(current_parts), document_id, language))

        return chunks

    def _split_by_definitions(self, text: str, language: str) -> list[str]:
        """Split code text at top-level function/class definitions."""
        lines = text.split("\n")
        blocks: list[str] = []
        current: list[str] = []

        for line in lines:
            # Detect top-level definition (no leading whitespace)
            if _PY_DEF_RE.match(line) and current:
                blocks.append("\n".join(current))
                current = []
            current.append(line)

        if current:
            blocks.append("\n".join(current))

        return blocks

    def _size_split(self, text: str, document_id: str, language: str) -> list[ChunkRecord]:
        """Fallback: split by character size."""
        if len(text) <= self._max_chars:
            return [self._make_chunk(text, document_id, language)]

        chunks: list[ChunkRecord] = []
        lines = text.split("\n")
        current: list[str] = []
        current_len = 0
        for line in lines:
            if current_len + len(line) > self._max_chars and current:
                chunks.append(self._make_chunk("\n".join(current), document_id, language))
                current = []
                current_len = 0
            current.append(line)
            current_len += len(line)
        if current:
            chunks.append(self._make_chunk("\n".join(current), document_id, language))
        return chunks

    def _make_chunk(self, text: str, document_id: str, language: str) -> ChunkRecord:
        chunk_bytes = text.encode("utf-8")
        return ChunkRecord(
            document_id=document_id,
            text=text,
            chunk_hash=hashlib.sha256(chunk_bytes).hexdigest(),
            heading_path=f"code:{language}" if language else "code",
        )
```

- [ ] **Step 4: Run tests — expect PASS**
- [ ] **Step 5: Commit**

---

### Task 5: ChunkRouter

**Files:**
- Create: `src/jarvis/indexing/chunk_router.py`
- Create: `tests/indexing/test_chunk_router.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/indexing/test_chunk_router.py
"""Tests for ChunkRouter — dispatches elements to strategies."""
from jarvis.contracts import DocumentElement, ParsedDocument
from jarvis.indexing.chunk_router import ChunkRouter


class TestChunkRouter:
    def test_routes_text_to_paragraph_strategy(self) -> None:
        doc = ParsedDocument(
            elements=(DocumentElement(element_type="text", text="Hello world"),),
            metadata={},
        )
        router = ChunkRouter()
        chunks = router.chunk(doc, document_id="d1")
        assert len(chunks) >= 1
        assert "Hello world" in chunks[0].text

    def test_routes_table_to_table_strategy(self) -> None:
        doc = ParsedDocument(
            elements=(DocumentElement(
                element_type="table", text="",
                metadata={
                    "headers": ("Day", "Meal"),
                    "rows": (("1", "eggs"), ("2", "toast"), ("3", "yogurt"),
                             ("4", "oats"), ("5", "cereal")),
                    "sheet_name": "Diet",
                },
            ),),
            metadata={},
        )
        router = ChunkRouter()
        chunks = router.chunk(doc, document_id="d1")
        # Should have row-level chunks with header mapping
        assert any("Day=1" in c.text for c in chunks)
        assert any("Meal=eggs" in c.text for c in chunks)

    def test_routes_code_to_code_strategy(self) -> None:
        doc = ParsedDocument(
            elements=(DocumentElement(
                element_type="code",
                text="def foo():\n    return 1\n\ndef bar():\n    return 2\n",
                metadata={"language": "python"},
            ),),
            metadata={},
        )
        router = ChunkRouter()
        chunks = router.chunk(doc, document_id="d1")
        assert len(chunks) >= 1

    def test_mixed_document(self) -> None:
        doc = ParsedDocument(
            elements=(
                DocumentElement(element_type="text", text="# Introduction\n\nThis is a doc."),
                DocumentElement(
                    element_type="table", text="",
                    metadata={"headers": ("A", "B"), "rows": (("1", "2"),), "sheet_name": "S1"},
                ),
                DocumentElement(element_type="code", text="x = 1", metadata={"language": "python"}),
            ),
            metadata={},
        )
        router = ChunkRouter()
        chunks = router.chunk(doc, document_id="d1")
        assert len(chunks) >= 3  # At least one from each element

    def test_empty_document(self) -> None:
        doc = ParsedDocument(elements=(), metadata={})
        router = ChunkRouter()
        chunks = router.chunk(doc, document_id="d1")
        assert chunks == []
```

- [ ] **Step 2: Run tests — expect FAIL**

- [ ] **Step 3: Implement**

```python
# src/jarvis/indexing/chunk_router.py
"""ChunkRouter — dispatches document elements to type-specific chunk strategies."""
from __future__ import annotations
from jarvis.contracts import ChunkRecord, ParsedDocument, DocumentElement
from jarvis.indexing.strategies.paragraph import ParagraphChunkStrategy
from jarvis.indexing.strategies.table import TableChunkStrategy
from jarvis.indexing.strategies.code import CodeChunkStrategy


class ChunkRouter:
    """Routes each DocumentElement to the appropriate ChunkStrategy."""

    def __init__(self) -> None:
        self._paragraph = ParagraphChunkStrategy()
        self._table = TableChunkStrategy()
        self._code = CodeChunkStrategy()

    def chunk(self, doc: ParsedDocument, *, document_id: str) -> list[ChunkRecord]:
        chunks: list[ChunkRecord] = []
        for element in doc.elements:
            strategy = self._select_strategy(element)
            chunks.extend(strategy.chunk(element, document_id=document_id))
        return chunks

    def _select_strategy(self, element: DocumentElement):
        if element.element_type == "table":
            return self._table
        if element.element_type == "code":
            return self._code
        # "text", "list", "slide", and anything else → paragraph
        return self._paragraph
```

- [ ] **Step 4: Run tests — expect PASS**
- [ ] **Step 5: Commit**

---

### Task 6: Update Parsers to Return ParsedDocument

**Files:**
- Modify: `src/jarvis/indexing/parsers.py`
- Create: `tests/indexing/test_parsers_structured.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/indexing/test_parsers_structured.py
"""Tests for structured parser output (ParsedDocument)."""
from pathlib import Path
from jarvis.contracts import ParsedDocument
from jarvis.indexing.parsers import DocumentParser


class TestStructuredParsers:
    def test_markdown_returns_parsed_document(self, tmp_path: Path) -> None:
        (tmp_path / "test.md").write_text("# Title\n\nParagraph text.\n\n## Section\n\nMore text.")
        parser = DocumentParser()
        doc = parser.parse_structured(tmp_path / "test.md")
        assert isinstance(doc, ParsedDocument)
        assert len(doc.elements) >= 1
        assert doc.to_text()  # backward compat

    def test_python_returns_code_elements(self, tmp_path: Path) -> None:
        (tmp_path / "test.py").write_text("def foo():\n    return 1\n\ndef bar():\n    return 2\n")
        parser = DocumentParser()
        doc = parser.parse_structured(tmp_path / "test.py")
        assert isinstance(doc, ParsedDocument)
        code_elements = [e for e in doc.elements if e.element_type == "code"]
        assert len(code_elements) >= 1

    def test_xlsx_returns_table_elements(self, tmp_path: Path) -> None:
        try:
            from openpyxl import Workbook
        except ImportError:
            import pytest; pytest.skip("openpyxl not installed")
        wb = Workbook()
        ws = wb.active
        ws.title = "Diet"
        ws.append(["Day", "Breakfast", "Lunch"])
        ws.append([1, "eggs", "chicken"])
        ws.append([2, "toast", "salad"])
        xlsx_path = tmp_path / "test.xlsx"
        wb.save(str(xlsx_path))
        wb.close()

        parser = DocumentParser()
        doc = parser.parse_structured(xlsx_path)
        table_elements = [e for e in doc.elements if e.element_type == "table"]
        assert len(table_elements) >= 1
        assert table_elements[0].metadata["headers"] == ("Day", "Breakfast", "Lunch")
        assert len(table_elements[0].metadata["rows"]) == 2

    def test_txt_returns_text_elements(self, tmp_path: Path) -> None:
        (tmp_path / "test.txt").write_text("Hello world.\n\nSecond paragraph.")
        parser = DocumentParser()
        doc = parser.parse_structured(tmp_path / "test.txt")
        assert isinstance(doc, ParsedDocument)
        assert len(doc.elements) >= 1

    def test_parse_still_returns_str(self, tmp_path: Path) -> None:
        """Backward compatibility: parse() returns str."""
        (tmp_path / "test.txt").write_text("Hello")
        parser = DocumentParser()
        result = parser.parse(tmp_path / "test.txt")
        assert isinstance(result, str)
        assert "Hello" in result
```

- [ ] **Step 2: Run tests — expect FAIL**

- [ ] **Step 3: Implement `parse_structured()` on DocumentParser**

Add `parse_structured(path) -> ParsedDocument` method that returns structured elements. Keep existing `parse(path) -> str` as backward compat wrapper calling `parse_structured().to_text()`.

Key changes per format:
- **xlsx**: Return `TableElement` with headers/rows instead of pipe-separated text
- **code files** (.py, .ts, etc.): Return `DocumentElement(type="code")`
- **text/markdown**: Return `DocumentElement(type="text")`
- **docx**: Return text elements + table elements separately
- **pdf**: Return text elements with minimum length filter

- [ ] **Step 4: Run tests — expect PASS**
- [ ] **Step 5: Run existing parser tests for backward compat**

Run: `python -m pytest tests/indexing/test_parsers.py -v`

- [ ] **Step 6: Commit**

---

### Task 7: Update IndexPipeline to Use ChunkRouter

**Files:**
- Modify: `src/jarvis/indexing/index_pipeline.py`
- Modify: `src/jarvis/indexing/chunker.py` (add delegation)

- [ ] **Step 1: Update IndexPipeline**

Change `index_file()` and `reindex_file()` to use:
```python
parsed_doc = self._parser.parse_structured(path)
chunks = self._chunk_router.chunk(parsed_doc, document_id=record.document_id)
```

Add `chunk_router` parameter to `__init__` with backward-compat default.

- [ ] **Step 2: Update Chunker for backward compat**

Add `ChunkRouter` delegation method to `Chunker`:
```python
def chunk(self, text_or_doc, *, document_id=""):
    if isinstance(text_or_doc, ParsedDocument):
        from jarvis.indexing.chunk_router import ChunkRouter
        return ChunkRouter().chunk(text_or_doc, document_id=document_id)
    # Original logic for plain text
    ...
```

- [ ] **Step 3: Run ALL existing tests**

Run: `python -m pytest tests/indexing/ -v`
Expected: All existing tests still pass.

- [ ] **Step 4: Commit**

---

### Task 8: Re-index Knowledge Base and Verify

**Files:**
- No code changes — operational task

- [ ] **Step 1: Clear existing chunks and embeddings**

```python
db.execute("DELETE FROM chunks")
db.execute("UPDATE documents SET indexing_status = 'PENDING'")
db.commit()
# Clear LanceDB vectors
```

- [ ] **Step 2: Re-index all documents**

```python
for doc in documents:
    pipeline.index_file(doc.path)
```

- [ ] **Step 3: Re-run embedding backfill**

- [ ] **Step 4: Verify chunk quality**

Check xlsx: each row should be a separate chunk with header mapping.
Check PDF: chunks should be avg 300-500 chars, not 85 chars.
Check code: functions should be separate chunks.

- [ ] **Step 5: Test with problem queries**

```
"다이어트 식단 메뉴에서 9일 차 아침 메뉴 알려줘"
"14day diet supplements final 에서 13일차 음료"
"14day diet supplements final 에서 1일차 아침"
```

All should return correct, specific answers.

- [ ] **Step 6: Commit any fixes**
