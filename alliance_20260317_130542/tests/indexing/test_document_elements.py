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

    def test_skips_empty_text_in_to_text(self) -> None:
        doc = ParsedDocument(
            elements=(
                DocumentElement(element_type="text", text="Hello"),
                DocumentElement(element_type="table", text=""),
                DocumentElement(element_type="text", text="World"),
            ),
            metadata={},
        )
        assert doc.to_text() == "Hello\n\nWorld"
