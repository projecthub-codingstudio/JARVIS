"""Tests for TableChunkStrategy — row-level chunking with header mapping."""
from jarvis.contracts import DocumentElement
from jarvis.indexing.strategies.table import TableChunkStrategy


class TestTableChunkStrategy:
    def test_each_row_becomes_chunk(self) -> None:
        el = DocumentElement(
            element_type="table", text="",
            metadata={
                "headers": ("Day", "Breakfast", "Lunch"),
                "rows": (
                    ("1", "eggs", "chicken"),
                    ("2", "toast", "salad"),
                    ("3", "yogurt", "soup"),
                    ("4", "oats", "rice"),
                    ("5", "cereal", "pasta"),
                ),
                "sheet_name": "Diet",
            },
        )
        strategy = TableChunkStrategy()
        chunks = strategy.chunk(el, document_id="d1")
        # 1 summary + 5 row chunks = 6
        assert len(chunks) == 6

    def test_header_mapped_to_values(self) -> None:
        el = DocumentElement(
            element_type="table", text="",
            metadata={
                "headers": ("Day", "Breakfast"),
                "rows": (("9", "구운계란2+요거트+베리"),),
                "sheet_name": "Diet",
            },
        )
        strategy = TableChunkStrategy(min_rows_for_split=1)
        chunks = strategy.chunk(el, document_id="d1")
        row_chunks = [c for c in chunks if "Day=9" in c.text]
        assert len(row_chunks) == 1
        assert "Breakfast=구운계란2+요거트+베리" in row_chunks[0].text

    def test_summary_chunk_included(self) -> None:
        el = DocumentElement(
            element_type="table", text="",
            metadata={
                "headers": ("A", "B", "C"),
                "rows": (("1", "2", "3"), ("4", "5", "6"), ("7", "8", "9"), ("10", "11", "12")),
                "sheet_name": "Sheet1",
            },
        )
        strategy = TableChunkStrategy()
        chunks = strategy.chunk(el, document_id="d1")
        summary = [c for c in chunks if "4 rows" in c.text and "Columns:" in c.text]
        assert len(summary) == 1

    def test_small_table_single_chunk(self) -> None:
        el = DocumentElement(
            element_type="table", text="",
            metadata={
                "headers": ("Name", "Value"),
                "rows": (("a", "1"), ("b", "2")),
                "sheet_name": "Config",
            },
        )
        strategy = TableChunkStrategy()
        chunks = strategy.chunk(el, document_id="d1")
        # 1 summary + 1 full table = 2 (not individual rows, since < min_rows_for_split)
        assert len(chunks) == 2

    def test_empty_table(self) -> None:
        el = DocumentElement(
            element_type="table", text="",
            metadata={"headers": (), "rows": (), "sheet_name": "Empty"},
        )
        strategy = TableChunkStrategy()
        chunks = strategy.chunk(el, document_id="d1")
        assert len(chunks) == 0

    def test_sheet_name_prefix(self) -> None:
        el = DocumentElement(
            element_type="table", text="",
            metadata={
                "headers": ("X",),
                "rows": (("1",), ("2",), ("3",), ("4",)),
                "sheet_name": "MySheet",
            },
        )
        strategy = TableChunkStrategy()
        chunks = strategy.chunk(el, document_id="d1")
        for c in chunks:
            assert "[MySheet]" in c.text
