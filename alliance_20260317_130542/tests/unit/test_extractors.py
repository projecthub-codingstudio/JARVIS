"""Tests for type-specific evidence extractors."""
from jarvis.contracts import ExtractedFact, EvidenceItem, CitationRecord, CitationState
from jarvis.retrieval.extractors.table import TableExtractor
from jarvis.retrieval.extractors.text import TextExtractor
from jarvis.retrieval.extractors.code import CodeExtractor


def _item(text: str, heading: str = "", chunk_id: str = "c1", doc_id: str = "d1") -> EvidenceItem:
    return EvidenceItem(
        chunk_id=chunk_id, document_id=doc_id, text=text,
        citation=CitationRecord(label="[1]", state=CitationState.VALID),
        relevance_score=0.5, heading_path=heading,
    )


class TestTableExtractor:
    def test_composite_keys_include_row_identifier(self):
        """Facts must have composite keys to disambiguate rows."""
        item = _item(
            "[Diet] Day=5 | Breakfast=계란후라이2+피망 | Lunch=닭가슴살",
            heading="table-row-Diet-4",
        )
        facts = TableExtractor().extract(item)
        keys = {f.key for f in facts}
        # First column (Day=5) is the row identifier, used in composite keys
        assert any("Day=5" in k and "Breakfast" in k for k in keys)
        bf = next(f for f in facts if "Breakfast" in f.key)
        assert bf.value == "계란후라이2+피망"
        assert bf.confidence == 1.0
        assert bf.source_chunk_id == "c1"
        assert bf.source_document_id == "d1"

    def test_two_rows_produce_distinct_keys(self):
        """Day=5 and Day=8 must NOT produce conflicting Breakfast keys."""
        item5 = _item("[D] Day=5 | Breakfast=피망", heading="table-row-D-4", chunk_id="c5")
        item8 = _item("[D] Day=8 | Breakfast=오이", heading="table-row-D-7", chunk_id="c8")
        ext = TableExtractor()
        facts5 = ext.extract(item5)
        facts8 = ext.extract(item8)
        keys5 = {f.key for f in facts5}
        keys8 = {f.key for f in facts8}
        assert keys5.isdisjoint(keys8), "Different rows must produce distinct keys"

    def test_non_table_returns_empty(self):
        item = _item("일반 텍스트", heading="paragraph-0")
        assert TableExtractor().extract(item) == []

    def test_empty_value_skipped(self):
        item = _item("[S] A= | B=val", heading="table-row-S-0")
        facts = TableExtractor().extract(item)
        assert all(f.value for f in facts)

    def test_no_sheet_prefix_returns_empty(self):
        """Without [Sheet] prefix, should return empty (per TableChunkStrategy format)."""
        item = _item("Day=1 | Name=Test", heading="table-row-0")
        facts = TableExtractor().extract(item)
        assert facts == []

    def test_non_spreadsheet_table_source_returns_empty(self):
        item = _item(
            "[tbl_day_chart] Day=9 | Lunch=wrong-answer",
            heading="table-row-sql-0",
            doc_id="sql-doc",
        )
        item = EvidenceItem(
            chunk_id=item.chunk_id,
            document_id=item.document_id,
            text=item.text,
            citation=item.citation,
            relevance_score=item.relevance_score,
            source_path="/tmp/tbl_day_chart.sql",
            heading_path=item.heading_path,
        )
        assert TableExtractor().extract(item) == []

    def test_first_column_is_row_id(self):
        """First column becomes the row identifier in composite keys."""
        item = _item("[Sheet] Name=홍길동 | Age=30 | City=서울", heading="table-row-Sheet-0")
        facts = TableExtractor().extract(item)
        # Name=홍길동 is the row id, so Age key should be "Name=홍길동 > Age"
        age = next(f for f in facts if "Age" in f.key)
        assert "Name=홍길동" in age.key
        assert age.value == "30"


class TestTextExtractor:
    def test_returns_text(self):
        item = _item("JARVIS는 로컬 AI입니다.")
        assert TextExtractor().extract(item) == "JARVIS는 로컬 AI입니다."

    def test_strips_whitespace(self):
        item = _item("  공백 있는 텍스트  ")
        assert TextExtractor().extract(item) == "공백 있는 텍스트"


class TestCodeExtractor:
    def test_returns_code_with_scope(self):
        item = _item("def hello():\n    return 'world'", heading="code-python-0")
        passage = CodeExtractor().extract(item)
        assert "def hello" in passage

    def test_without_heading(self):
        item = _item("def foo(): pass", heading="")
        passage = CodeExtractor().extract(item)
        assert passage == "def foo(): pass"
