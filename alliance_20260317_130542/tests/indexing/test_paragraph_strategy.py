"""Tests for ParagraphChunkStrategy (default strategy)."""
from jarvis.contracts import DocumentElement
from jarvis.indexing.strategies.paragraph import ParagraphChunkStrategy


class TestParagraphChunkStrategy:
    def test_single_paragraph(self) -> None:
        el = DocumentElement(element_type="text", text="A paragraph that is long enough to pass the minimum chunk filter threshold for testing.")
        strategy = ParagraphChunkStrategy()
        chunks = strategy.chunk(el, document_id="d1")
        assert len(chunks) >= 1
        assert "paragraph" in chunks[0].text

    def test_long_text_splits(self) -> None:
        el = DocumentElement(element_type="text", text="Word " * 600)
        strategy = ParagraphChunkStrategy(max_tokens=100)
        chunks = strategy.chunk(el, document_id="d1")
        assert len(chunks) > 1

    def test_respects_paragraph_boundaries(self) -> None:
        text = "First paragraph here.\n\nSecond paragraph here.\n\nThird paragraph here."
        el = DocumentElement(element_type="text", text=text)
        strategy = ParagraphChunkStrategy(max_tokens=20)
        chunks = strategy.chunk(el, document_id="d1")
        assert len(chunks) >= 2

    def test_heading_path_from_metadata(self) -> None:
        el = DocumentElement(
            element_type="text",
            text="The system uses monolith design.",
            metadata={"heading_path": "Architecture"},
        )
        strategy = ParagraphChunkStrategy()
        chunks = strategy.chunk(el, document_id="d1")
        assert chunks[0].heading_path == "Architecture"

    def test_page_metadata_falls_back_to_page_heading(self) -> None:
        el = DocumentElement(
            element_type="text",
            text="PDF body text that is long enough to pass the paragraph chunk threshold.",
            metadata={"page": 3},
        )
        strategy = ParagraphChunkStrategy()
        chunks = strategy.chunk(el, document_id="d1")
        assert chunks[0].heading_path == "Page 3"

    def test_empty_text_returns_empty(self) -> None:
        el = DocumentElement(element_type="text", text="")
        strategy = ParagraphChunkStrategy()
        chunks = strategy.chunk(el, document_id="d1")
        assert chunks == []

    def test_whitespace_only_returns_empty(self) -> None:
        el = DocumentElement(element_type="text", text="   \n\n  ")
        strategy = ParagraphChunkStrategy()
        chunks = strategy.chunk(el, document_id="d1")
        assert chunks == []
