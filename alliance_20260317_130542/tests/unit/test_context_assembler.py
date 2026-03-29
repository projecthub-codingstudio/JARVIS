"""Tests for ContextAssembler extract layer — data models."""
from jarvis.contracts import ExtractedFact, AssembledContext


class TestExtractedFact:
    def test_creation(self):
        fact = ExtractedFact(
            key="Day=5 > Breakfast",
            value="계란후라이2+피망",
            source_chunk_id="abc123",
            source_document_id="doc1",
            confidence=1.0,
        )
        assert fact.key == "Day=5 > Breakfast"
        assert fact.value == "계란후라이2+피망"
        assert fact.confidence == 1.0
        assert fact.is_deterministic is True

    def test_low_confidence(self):
        fact = ExtractedFact(
            key="요약", value="프로젝트 설명",
            source_chunk_id="c1", source_document_id="d1",
            confidence=0.7,
        )
        assert fact.is_deterministic is False


class TestAssembledContext:
    def test_creation(self):
        facts = (
            ExtractedFact(key="Day=5 > Breakfast", value="계란후라이2+피망",
                          source_chunk_id="a", source_document_id="d1"),
            ExtractedFact(key="Day=8 > Lunch", value="닭가슴살+샐러드",
                          source_chunk_id="b", source_document_id="d1"),
        )
        ctx = AssembledContext(facts=facts, text_passages=("텍스트 증거",))
        assert len(ctx.facts) == 2
        assert len(ctx.text_passages) == 1
        assert ctx.has_deterministic_facts is True

    def test_no_facts(self):
        ctx = AssembledContext(facts=(), text_passages=("텍스트만",))
        assert ctx.has_deterministic_facts is False
        assert ctx.deterministic_facts == ()

    def test_render_for_llm_facts_only(self):
        facts = (
            ExtractedFact(key="Day=5 > Breakfast", value="계란후라이2+피망",
                          source_chunk_id="a", source_document_id="d1"),
        )
        ctx = AssembledContext(facts=facts, text_passages=())
        rendered = ctx.render_for_llm()
        assert "확인된 데이터" in rendered
        assert "Day=5 > Breakfast: 계란후라이2+피망" in rendered
        assert "참고 자료" not in rendered

    def test_render_for_llm_passages_only(self):
        ctx = AssembledContext(facts=(), text_passages=("참고 텍스트",))
        rendered = ctx.render_for_llm()
        assert "확인된 데이터" not in rendered
        assert "참고 자료" in rendered

    def test_render_for_llm_mixed(self):
        facts = (
            ExtractedFact(key="Name", value="JARVIS",
                          source_chunk_id="a", source_document_id="d1"),
        )
        ctx = AssembledContext(facts=facts, text_passages=("설명 텍스트",))
        rendered = ctx.render_for_llm()
        assert "확인된 데이터" in rendered
        assert "참고 자료" in rendered


from jarvis.contracts import (
    CitationRecord, CitationState, EvidenceItem,
    TypedQueryFragment, VerifiedEvidenceSet,
)
from jarvis.retrieval.context_assembler import ContextAssembler


def _item(text: str, heading: str = "", chunk_id: str = "c1") -> EvidenceItem:
    return EvidenceItem(
        chunk_id=chunk_id, document_id="d1", text=text,
        citation=CitationRecord(label="[1]", state=CitationState.VALID),
        relevance_score=0.5, heading_path=heading,
    )


def _evidence(*items: EvidenceItem) -> VerifiedEvidenceSet:
    return VerifiedEvidenceSet(
        items=tuple(items),
        query_fragments=(TypedQueryFragment(text="test", query_type="semantic", language="ko"),),
    )


class TestContextAssembler:
    def test_table_produces_facts(self):
        ev = _evidence(_item("[D] Day=5 | Breakfast=피망", heading="table-row-D-4"))
        ctx = ContextAssembler().assemble(ev, query="5일차 아침")
        assert ctx.has_deterministic_facts
        assert any("Breakfast" in f.key and "피망" in f.value for f in ctx.facts)

    def test_text_produces_passages(self):
        ev = _evidence(_item("JARVIS는 AI입니다.", heading="paragraph-0"))
        ctx = ContextAssembler().assemble(ev, query="JARVIS?")
        assert not ctx.has_deterministic_facts
        assert len(ctx.text_passages) == 1

    def test_mixed_separates_facts_and_passages(self):
        ev = _evidence(
            _item("[S] Day=3 | Lunch=닭가슴살", heading="table-row-S-2", chunk_id="c1"),
            _item("프로젝트 설명...", heading="paragraph-0", chunk_id="c2"),
        )
        ctx = ContextAssembler().assemble(ev, query="3일차 점심")
        assert ctx.has_deterministic_facts
        assert len(ctx.text_passages) >= 1

    def test_budget_respected(self):
        items = [_item(f"텍스트 " * 100, heading=f"para-{i}", chunk_id=f"c{i}") for i in range(20)]
        ev = _evidence(*items)
        ctx = ContextAssembler(max_context_chars=500).assemble(ev, query="test")
        rendered = ctx.render_for_llm()
        assert len(rendered) <= 700

    def test_budget_stops_across_items(self):
        items = [
            _item("A " * 300, heading="para-0", chunk_id="c0"),
            _item("B " * 300, heading="para-1", chunk_id="c1"),
        ]
        ev = _evidence(*items)
        ctx = ContextAssembler(max_context_chars=400).assemble(ev, query="test")
        total_len = sum(len(p) for p in ctx.text_passages)
        assert total_len <= 500

    def test_empty_evidence(self):
        ev = _evidence()
        ctx = ContextAssembler().assemble(ev, query="test")
        assert not ctx.has_deterministic_facts
        assert len(ctx.text_passages) == 0

    def test_preserves_evidence_order(self):
        ev = _evidence(
            _item("[S] Day=5 | X=first", heading="table-row-S-4", chunk_id="c5"),
            _item("[S] Day=8 | X=second", heading="table-row-S-7", chunk_id="c8"),
        )
        ctx = ContextAssembler().assemble(ev, query="test")
        values = [f.value for f in ctx.facts if "X" in f.key]
        assert values == ["first", "second"]

    def test_code_produces_passage(self):
        ev = _evidence(_item("def foo(): pass", heading="code-python-0"))
        ctx = ContextAssembler().assemble(ev, query="foo")
        assert not ctx.has_deterministic_facts
        assert len(ctx.text_passages) == 1
        assert "def foo" in ctx.text_passages[0]
