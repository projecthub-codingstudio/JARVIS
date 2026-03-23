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
