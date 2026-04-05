# Document-Type-Specific Semantic Chunking Design

**Date**: 2026-03-22
**Status**: Approved
**Scope**: Replace single Chunker with ChunkRouter + type-specific strategies + structured parser output
**Priority**: Critical — root cause of search quality issues

## Problem

The current `Chunker` splits all document types by byte size (500 tokens / 1500 chars), ignoring document structure:

| Document Type | Current Behavior | Problem |
|---------------|-----------------|---------|
| xlsx (14-day diet) | 14 rows → 2 chunks (7 rows each) | LLM confuses rows |
| PDF (씨샵.pdf) | 19,543 chunks, avg 85 chars | Fragments too small to be meaningful |
| Code (.py) | Split mid-function by byte count | Breaks semantic units |
| DOCX | Tables flattened into text stream | Table structure lost |

## Solution: Structured Parser + ChunkRouter

### Phase 1: Data Model — `DocumentElement` and `ParsedDocument`

New contracts in `jarvis/contracts/models.py`:

```python
@dataclass(frozen=True)
class DocumentElement:
    """Base element from a parsed document."""
    element_type: str    # "text", "table", "code", "list", "slide"
    text: str            # Rendered text content
    metadata: dict       # Type-specific metadata

@dataclass(frozen=True)
class TableElement(DocumentElement):
    """Structured table with headers and rows."""
    element_type: str = "table"
    headers: tuple[str, ...] = ()
    rows: tuple[tuple[str, ...], ...] = ()
    sheet_name: str = ""

@dataclass(frozen=True)
class CodeElement(DocumentElement):
    """Code with language and scope information."""
    element_type: str = "code"
    language: str = ""
    scope_chain: str = ""  # e.g., "class Foo > method bar"

@dataclass(frozen=True)
class ParsedDocument:
    """Structured parser output with typed elements."""
    elements: tuple[DocumentElement, ...]
    metadata: dict  # filename, format, page_count, etc.

    def to_text(self) -> str:
        """Backward-compatible plain text rendering."""
        return "\n\n".join(e.text for e in self.elements if e.text)
```

### Phase 2: Parser Changes

Each parser returns `ParsedDocument` instead of `str`:

#### xlsx parser
- Header row → stored as `TableElement.headers`
- Each data row → `TableElement.rows` entry
- Produces one `TableElement` per sheet

#### docx parser
- Paragraphs → `DocumentElement(type="text")`
- Tables → `TableElement` with headers and rows
- Lists → `DocumentElement(type="list")`

#### pptx parser
- Each slide → `DocumentElement(type="slide")` containing child elements
- Tables within slides → `TableElement`

#### hwp/hwpx parser
- Paragraphs → `DocumentElement(type="text")`
- Tables → `TableElement`

#### pdf parser
- Page text blocks → `DocumentElement(type="text")` with page metadata
- Minimum text length filter (skip fragments < 50 chars)
- Tables detected by PyMuPDF → `TableElement`

#### code parser (py, ts, js, swift, etc.)
- With tree-sitter: function/class → `CodeElement` with scope chain
- Without tree-sitter: fallback to `DocumentElement(type="text")`

#### text/markdown parser
- Heading sections → `DocumentElement(type="text")` with heading_level
- Code blocks → `CodeElement`

### Phase 3: ChunkRouter

Replaces `Chunker.chunk()` as the main entry point:

```python
class ChunkRouter:
    def chunk(self, doc: ParsedDocument, *, document_id: str) -> list[ChunkRecord]:
        chunks = []
        for element in doc.elements:
            strategy = self._select_strategy(element)
            chunks.extend(strategy.chunk(element, document_id=document_id))
        return chunks

    def _select_strategy(self, element: DocumentElement) -> ChunkStrategy:
        return {
            "table": TableChunkStrategy(),
            "code": CodeChunkStrategy(),
            "slide": SlideChunkStrategy(),
        }.get(element.element_type, ParagraphChunkStrategy())
```

### Phase 4: Chunk Strategies

#### TableChunkStrategy
- Each row → independent chunk with header mapping
- Format: `[sheet] Col1=val1 | Col2=val2 | Col3=val3`
- Table summary chunk added (column names, row count, sheet name)
- Very small tables (< 5 rows): single chunk with full table

#### CodeChunkStrategy
- With tree-sitter: split at function/class boundaries
- Each chunk includes: scope chain, imports relevant to function
- Max chunk size respected; large functions split at statement boundaries
- Without tree-sitter: ParagraphChunkStrategy fallback

#### HeadingChunkStrategy
- Split at heading boundaries (# ## ### etc.)
- Each section ≤ max_tokens → single chunk
- Oversized sections → paragraph-level sub-split
- heading_path metadata preserved (last 3 levels)

#### ParagraphChunkStrategy
- Current Chunker logic (backward compatible)
- `\n\n` paragraph boundaries + byte limit + overlap
- Minimum chunk size: 100 chars (filter tiny fragments)

#### SlideChunkStrategy
- Each slide → chunk with slide number prefix
- Tables within slides → TableChunkStrategy delegation
- Slide notes merged into slide chunk

### Phase 5: Backward Compatibility

- `Chunker.chunk(text, document_id)` still works (wraps text in ParsedDocument)
- `DocumentParser.extract_text(path)` returns `str` (calls `ParsedDocument.to_text()`)
- `DocumentParser.parse(path)` returns `ParsedDocument` (new method)
- Existing tests pass without modification
- IndexPipeline updated to use `parse()` → `ChunkRouter.chunk()`

### Phase 6: Re-indexing

After implementation, existing knowledge_base must be re-indexed:
1. Clear existing chunks and embeddings
2. Re-parse all documents with new structured parsers
3. Re-chunk with ChunkRouter
4. Re-run embedding backfill

## File Changes

| File | Change |
|------|--------|
| `contracts/models.py` | Add DocumentElement, TableElement, CodeElement, ParsedDocument |
| `indexing/parsers.py` | Each parser returns ParsedDocument |
| `indexing/chunker.py` | Keep as ParagraphChunkStrategy, add min_chars filter |
| `indexing/chunk_router.py` | NEW — routes elements to strategies |
| `indexing/strategies/table.py` | NEW — row-level chunking with header mapping |
| `indexing/strategies/code.py` | NEW — AST-aware chunking (tree-sitter optional) |
| `indexing/strategies/heading.py` | NEW — heading-level section splitting |
| `indexing/strategies/slide.py` | NEW — slide-level chunking |
| `indexing/strategies/paragraph.py` | NEW — current Chunker logic extracted |
| `indexing/index_pipeline.py` | Use parse() + ChunkRouter instead of extract_text() + Chunker |

## Expected Impact

| Document Type | Before | After |
|---------------|--------|-------|
| xlsx (14 rows) | 2 chunks (7 rows each) | 14 chunks (1 row each) + 1 summary |
| PDF (씨샵.pdf) | 19,543 chunks (avg 85 chars) | ~2,000 chunks (avg 500 chars) |
| Code (.py) | Split mid-function | Function-level chunks with scope |
| DOCX with tables | Tables lost in text stream | Tables chunked separately |

## Dependencies

- `tree-sitter` + language grammars (optional, graceful fallback)
- `openpyxl` (already installed)
- `python-docx` (already installed)
- `pymupdf` (already installed)
- No new required dependencies

## Research References

- cAST: AST-based code chunking (arxiv.org/html/2506.15655v1)
- Ragie: Row-based table chunking approach
- LangChain RecursiveCharacterTextSplitter (baseline comparison)
- Docling: Hierarchical document chunking (IBM/LF AI)
- NVIDIA chunk size benchmarks (developer.nvidia.com)
