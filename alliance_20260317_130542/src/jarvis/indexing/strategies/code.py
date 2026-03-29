"""CodeChunkStrategy — splits code at function/class boundaries.

Uses tree-sitter for AST-based splitting when available, falling back
to regex heuristics. Tree-sitter provides accurate function/class
boundary detection including nested definitions and async functions.
"""
from __future__ import annotations
import hashlib
import logging
import re
from jarvis.contracts import ChunkRecord, DocumentElement

logger = logging.getLogger(__name__)

_PY_DEF_RE = re.compile(r"^(class |def |async def )", re.MULTILINE)
_CHARS_PER_TOKEN = 3

# tree-sitter language support (lazy-loaded)
_TS_LANGUAGES: dict[str, object] | None = None
_TS_AVAILABLE: bool | None = None

# Top-level node types that represent semantic code units per language
_DEFINITION_NODE_TYPES: dict[str, set[str]] = {
    "python": {"function_definition", "class_definition", "decorated_definition"},
    "javascript": {"function_declaration", "class_declaration", "export_statement",
                   "lexical_declaration"},
    "typescript": {"function_declaration", "class_declaration", "export_statement",
                   "lexical_declaration", "interface_declaration", "type_alias_declaration"},
}


def _get_ts_language(lang: str):
    """Get a tree-sitter Language for the given language name, or None."""
    global _TS_AVAILABLE, _TS_LANGUAGES

    if _TS_AVAILABLE is False:
        return None

    if _TS_LANGUAGES is None:
        _TS_LANGUAGES = {}
        try:
            from tree_sitter import Language
            _TS_AVAILABLE = True
        except ImportError:
            _TS_AVAILABLE = False
            return None

    if lang in _TS_LANGUAGES:
        return _TS_LANGUAGES[lang]

    from tree_sitter import Language

    lang_modules = {
        "python": "tree_sitter_python",
        "javascript": "tree_sitter_javascript",
        "typescript": "tree_sitter_typescript",
    }

    module_name = lang_modules.get(lang)
    if not module_name:
        return None

    try:
        import importlib
        mod = importlib.import_module(module_name)
        language_fn = getattr(mod, "language", None)
        if language_fn is None:
            return None
        ts_lang = Language(language_fn())
        _TS_LANGUAGES[lang] = ts_lang
        return ts_lang
    except Exception:
        return None


def _split_by_tree_sitter(text: str, language: str) -> list[str] | None:
    """Split code into semantic blocks using tree-sitter AST.

    Returns a list of code blocks split at top-level definition boundaries,
    or None if tree-sitter is unavailable for this language.
    """
    ts_lang = _get_ts_language(language)
    if ts_lang is None:
        return None

    try:
        from tree_sitter import Parser

        parser = Parser(ts_lang)
        tree = parser.parse(text.encode("utf-8"))
        root = tree.root_node

        definition_types = _DEFINITION_NODE_TYPES.get(language, set())
        if not definition_types:
            return None

        # Collect top-level definition boundaries
        boundaries: list[int] = []
        for child in root.children:
            if child.type in definition_types:
                boundaries.append(child.start_byte)

        if not boundaries:
            return None

        # Split text at definition boundaries
        text_bytes = text.encode("utf-8")
        blocks: list[str] = []
        prev = 0
        for boundary in boundaries:
            if boundary > prev:
                block = text_bytes[prev:boundary].decode("utf-8").rstrip()
                if block.strip():
                    blocks.append(block)
            prev = boundary

        # Last block
        if prev < len(text_bytes):
            block = text_bytes[prev:].decode("utf-8").rstrip()
            if block.strip():
                blocks.append(block)

        return blocks if len(blocks) > 1 else None

    except Exception as exc:
        logger.debug("tree-sitter parse failed for %s: %s", language, exc)
        return None


class CodeChunkStrategy:
    """Splits code at function/class definition boundaries.

    Uses tree-sitter AST parsing when available for accurate boundary
    detection, falling back to regex-based heuristics.
    """

    def __init__(self, *, max_tokens: int = 500) -> None:
        self._max_chars = max_tokens * _CHARS_PER_TOKEN

    def chunk(self, element: DocumentElement, *, document_id: str) -> list[ChunkRecord]:
        text = element.text
        if not text.strip():
            return []

        language = element.metadata.get("language", "")

        # Try tree-sitter first, then regex fallback
        blocks = _split_by_tree_sitter(text, language)
        if blocks is None:
            blocks = self._split_by_definitions(text)

        if len(blocks) <= 1:
            return self._size_split(text, document_id, language)

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

    def _split_by_definitions(self, text: str) -> list[str]:
        """Regex-based fallback for languages without tree-sitter."""
        lines = text.split("\n")
        blocks: list[str] = []
        current: list[str] = []

        for line in lines:
            if _PY_DEF_RE.match(line) and current:
                blocks.append("\n".join(current))
                current = []
            current.append(line)

        if current:
            blocks.append("\n".join(current))

        return blocks

    def _size_split(self, text: str, document_id: str, language: str) -> list[ChunkRecord]:
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
