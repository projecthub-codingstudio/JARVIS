"""Tests for ChunkRouter — dispatches elements to strategies."""
from jarvis.contracts import DocumentElement, ParsedDocument
from jarvis.indexing.chunk_router import ChunkRouter


class TestChunkRouter:
    def test_routes_text_to_paragraph_strategy(self) -> None:
        doc = ParsedDocument(
            elements=(DocumentElement(element_type="text", text="Hello world, this is a sufficiently long paragraph for chunking tests."),),
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
        assert any("Day=1" in c.text for c in chunks)
        assert any("Meal=eggs" in c.text for c in chunks)

    def test_routes_code_to_code_strategy(self) -> None:
        doc = ParsedDocument(
            elements=(DocumentElement(
                element_type="code",
                text="def foo():\n    return 1\n",
                metadata={"language": "python"},
            ),),
            metadata={},
        )
        router = ChunkRouter()
        chunks = router.chunk(doc, document_id="d1")
        assert len(chunks) >= 1
        assert "def foo" in chunks[0].text

    def test_mixed_document(self) -> None:
        doc = ParsedDocument(
            elements=(
                DocumentElement(element_type="text", text="Introduction paragraph with enough text to pass minimum chunk filter requirements."),
                DocumentElement(
                    element_type="table", text="",
                    metadata={"headers": ("A", "B"), "rows": (("1", "2"),), "sheet_name": "S1"},
                ),
                DocumentElement(element_type="code", text="def example():\n    x = 1\n    return x\n", metadata={"language": "python"}),
            ),
            metadata={},
        )
        router = ChunkRouter()
        chunks = router.chunk(doc, document_id="d1")
        assert len(chunks) >= 3

    def test_empty_document(self) -> None:
        doc = ParsedDocument(elements=(), metadata={})
        router = ChunkRouter()
        chunks = router.chunk(doc, document_id="d1")
        assert chunks == []

    def test_unknown_element_type_uses_paragraph(self) -> None:
        doc = ParsedDocument(
            elements=(DocumentElement(element_type="slide", text="Slide content here with some extra detail for the minimum chunk size"),),
            metadata={},
        )
        router = ChunkRouter()
        chunks = router.chunk(doc, document_id="d1")
        assert len(chunks) >= 1
        assert "Slide content" in chunks[0].text
