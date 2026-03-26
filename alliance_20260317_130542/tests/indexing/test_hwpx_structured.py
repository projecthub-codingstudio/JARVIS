"""Tests for HWPX structured parsing (text + table extraction)."""
from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from jarvis.indexing.parsers import _parse_hwpx_structured, _extract_hwpx_tables, DocumentParser


_HP_NS = "http://www.hancom.co.kr/hwpml/2011/paragraph"
_HS_NS = "http://www.hancom.co.kr/hwpml/2011/section"


def _create_hwpx_with_table(
    path: Path,
    *,
    text: str = "",
    caption: str = "",
    table_rows: list[list[str]] | None = None,
) -> None:
    """Create a minimal HWPX file with optional text and table."""
    parts = []
    if text:
        parts.append(f'<hp:p><hp:run><hp:t>{text}</hp:t></hp:run></hp:p>')
    if table_rows:
        if caption:
            parts.append(f'<hp:p><hp:run><hp:t>{caption}</hp:t></hp:run></hp:p>')
        rows_xml = []
        for row in table_rows:
            cells_xml = "".join(
                f'<hp:tc><hp:p><hp:run><hp:t>{cell}</hp:t></hp:run></hp:p></hp:tc>'
                for cell in row
            )
            rows_xml.append(f"<hp:tr>{cells_xml}</hp:tr>")
        parts.append(f'<hp:tbl>{"".join(rows_xml)}</hp:tbl>')

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<hs:sec xmlns:hs="{_HS_NS}" xmlns:hp="{_HP_NS}">
  {"".join(parts)}
</hs:sec>"""

    with zipfile.ZipFile(str(path), "w") as zf:
        zf.writestr("Contents/section0.xml", xml)
        zf.writestr("mimetype", "application/hwp+zip")


class TestExtractHwpxTables:
    def test_extracts_table_from_hwpx(self, tmp_path: Path) -> None:
        hwpx = tmp_path / "table.hwpx"
        _create_hwpx_with_table(hwpx, table_rows=[
            ["Name", "Score"],
            ["Alice", "95"],
            ["Bob", "87"],
        ])
        tables = _extract_hwpx_tables(hwpx)
        assert len(tables) == 1
        assert tables[0].element_type == "table"
        assert tables[0].metadata["headers"] == ("Name", "Score")
        assert ("Alice", "95") in tables[0].metadata["rows"]
        assert ("Bob", "87") in tables[0].metadata["rows"]

    def test_uses_nearby_caption_as_sheet_name(self, tmp_path: Path) -> None:
        hwpx = tmp_path / "caption.hwpx"
        _create_hwpx_with_table(
            hwpx,
            caption="표 76 그리기 개체 공통 속성",
            table_rows=[
                ["항목", "값"],
                ["크기", "348 바이트"],
            ],
        )
        tables = _extract_hwpx_tables(hwpx)
        assert len(tables) == 1
        assert tables[0].metadata["sheet_name"] == "표 76 그리기 개체 공통 속성"

    def test_skips_single_row_tables(self, tmp_path: Path) -> None:
        hwpx = tmp_path / "small.hwpx"
        _create_hwpx_with_table(hwpx, table_rows=[["Header1", "Header2"]])
        tables = _extract_hwpx_tables(hwpx)
        assert len(tables) == 0  # Need at least 2 rows (header + data)

    def test_no_tables_returns_empty(self, tmp_path: Path) -> None:
        hwpx = tmp_path / "nodata.hwpx"
        _create_hwpx_with_table(hwpx, text="Just text, no tables")
        tables = _extract_hwpx_tables(hwpx)
        assert tables == []


class TestParseHwpxStructured:
    def test_extracts_text_and_tables(self, tmp_path: Path) -> None:
        hwpx = tmp_path / "mixed.hwpx"
        _create_hwpx_with_table(
            hwpx,
            text="Document with text and tables for structured parsing test.",
            table_rows=[
                ["항목", "값"],
                ["메모리", "64GB"],
                ["CPU", "M1 Max"],
            ],
        )
        elements = _parse_hwpx_structured(hwpx)

        text_elems = [e for e in elements if e.element_type == "text"]
        table_elems = [e for e in elements if e.element_type == "table"]

        assert len(text_elems) >= 1
        assert len(table_elems) == 1
        assert table_elems[0].metadata["headers"] == ("항목", "값")
        assert ("메모리", "64GB") in table_elems[0].metadata["rows"]

    def test_parse_structured_routes_hwpx(self, tmp_path: Path) -> None:
        hwpx = tmp_path / "test.hwpx"
        _create_hwpx_with_table(
            hwpx,
            text="Structured HWPX document content for parser routing test.",
            table_rows=[
                ["Col1", "Col2"],
                ["A", "1"],
                ["B", "2"],
            ],
        )
        parser = DocumentParser()
        doc = parser.parse_structured(hwpx)
        assert len(doc.elements) >= 2  # text + table
        types = {e.element_type for e in doc.elements}
        assert "table" in types
