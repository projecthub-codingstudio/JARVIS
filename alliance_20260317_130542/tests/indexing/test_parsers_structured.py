"""Tests for structured parser output (ParsedDocument)."""
from pathlib import Path

import pytest

from jarvis.contracts import ParsedDocument
from jarvis.indexing.parsers import DocumentParser


class TestStructuredParsers:
    def test_markdown_returns_parsed_document(self, tmp_path: Path) -> None:
        (tmp_path / "test.md").write_text("# Title\n\nParagraph text.\n\n## Section\n\nMore text.")
        parser = DocumentParser()
        doc = parser.parse_structured(tmp_path / "test.md")
        assert isinstance(doc, ParsedDocument)
        assert len(doc.elements) >= 1
        assert doc.to_text()

    def test_python_returns_code_elements(self, tmp_path: Path) -> None:
        (tmp_path / "test.py").write_text("def foo():\n    return 1\n\ndef bar():\n    return 2\n")
        parser = DocumentParser()
        doc = parser.parse_structured(tmp_path / "test.py")
        assert isinstance(doc, ParsedDocument)
        code_elements = [e for e in doc.elements if e.element_type == "code"]
        assert len(code_elements) >= 1
        assert code_elements[0].metadata["language"] == "python"

    def test_xlsx_returns_table_elements(self, tmp_path: Path) -> None:
        try:
            from openpyxl import Workbook
        except ImportError:
            pytest.skip("openpyxl not installed")
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
        assert "Hello world" in doc.to_text()

    def test_csv_returns_table_elements(self, tmp_path: Path) -> None:
        (tmp_path / "test.csv").write_text("Name,Age,City\nAlice,30,Seoul\nBob,25,Busan\n")
        parser = DocumentParser()
        doc = parser.parse_structured(tmp_path / "test.csv")
        table_elements = [e for e in doc.elements if e.element_type == "table"]
        assert len(table_elements) >= 1
        assert table_elements[0].metadata["headers"] == ("Name", "Age", "City")
        assert len(table_elements[0].metadata["rows"]) == 2

    def test_parse_still_returns_str(self, tmp_path: Path) -> None:
        """Backward compatibility: parse() returns str."""
        (tmp_path / "test.txt").write_text("Hello")
        parser = DocumentParser()
        result = parser.parse(tmp_path / "test.txt")
        assert isinstance(result, str)
        assert "Hello" in result

    def test_empty_file(self, tmp_path: Path) -> None:
        (tmp_path / "empty.txt").write_text("")
        parser = DocumentParser()
        doc = parser.parse_structured(tmp_path / "empty.txt")
        assert isinstance(doc, ParsedDocument)
        assert len(doc.elements) == 0

    def test_typescript_returns_code(self, tmp_path: Path) -> None:
        (tmp_path / "test.ts").write_text("function hello(): void {\n  console.log('hi');\n}\n")
        parser = DocumentParser()
        doc = parser.parse_structured(tmp_path / "test.ts")
        code_elements = [e for e in doc.elements if e.element_type == "code"]
        assert len(code_elements) >= 1
        assert code_elements[0].metadata["language"] == "typescript"
