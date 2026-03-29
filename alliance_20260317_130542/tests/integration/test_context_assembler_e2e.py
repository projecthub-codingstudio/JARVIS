"""Integration: ContextAssembler pipeline produces unambiguous facts from evidence."""
from jarvis.contracts import (
    CitationRecord, CitationState, EvidenceItem,
    TypedQueryFragment, VerifiedEvidenceSet,
)
from jarvis.retrieval.context_assembler import ContextAssembler


def test_diet_multi_row_disambiguation():
    """The exact scenario that previously confused the LLM:
    Day=5 Breakfast=계란후라이2+피망 vs Day=8 Breakfast=계란후라이2+오이.
    ContextAssembler must produce distinct composite keys."""
    evidence = VerifiedEvidenceSet(
        items=(
            EvidenceItem(
                chunk_id="day5", document_id="diet",
                text="[Diet] Day=5 | Breakfast=계란후라이2+피망 | Lunch=닭가슴살+현미밥",
                citation=CitationRecord(label="[1]", state=CitationState.VALID),
                relevance_score=1.0, heading_path="table-row-Diet-4",
            ),
            EvidenceItem(
                chunk_id="day8", document_id="diet",
                text="[Diet] Day=8 | Breakfast=계란후라이2+오이 | Lunch=닭가슴살+샐러드",
                citation=CitationRecord(label="[2]", state=CitationState.VALID),
                relevance_score=0.9, heading_path="table-row-Diet-7",
            ),
        ),
        query_fragments=(TypedQueryFragment(text="5일차 아침 8일차 점심", query_type="semantic", language="ko"),),
    )

    ctx = ContextAssembler().assemble(evidence, query="5일차 아침 8일차 점심")

    # Day 5 Breakfast must be 피망, NOT 오이
    day5_bf = next((f for f in ctx.facts if "Day=5" in f.key and "Breakfast" in f.key), None)
    assert day5_bf is not None
    assert day5_bf.value == "계란후라이2+피망"

    # Day 8 Breakfast must be 오이
    day8_bf = next((f for f in ctx.facts if "Day=8" in f.key and "Breakfast" in f.key), None)
    assert day8_bf is not None
    assert day8_bf.value == "계란후라이2+오이"

    # Rendered context must be unambiguous
    rendered = ctx.render_for_llm()
    assert "Day=5 > Breakfast: 계란후라이2+피망" in rendered
    assert "Day=8 > Breakfast: 계란후라이2+오이" in rendered


def test_mixed_table_and_text_separation():
    """Table evidence → facts, text evidence → passages."""
    evidence = VerifiedEvidenceSet(
        items=(
            EvidenceItem(
                chunk_id="r1", document_id="d1",
                text="[Data] Name=JARVIS | Version=1.0",
                citation=CitationRecord(label="[1]", state=CitationState.VALID),
                relevance_score=0.8, heading_path="table-row-Data-0",
            ),
            EvidenceItem(
                chunk_id="t1", document_id="d2",
                text="JARVIS는 로컬 AI 비서 프로젝트입니다.",
                citation=CitationRecord(label="[2]", state=CitationState.VALID),
                relevance_score=0.7, heading_path="paragraph-intro",
            ),
        ),
        query_fragments=(TypedQueryFragment(text="JARVIS", query_type="semantic", language="ko"),),
    )

    ctx = ContextAssembler().assemble(evidence, query="JARVIS가 뭐야?")
    assert any("Name" in f.key and f.value == "JARVIS" for f in ctx.facts)
    assert any("로컬 AI" in p for p in ctx.text_passages)


def test_three_day_query_all_distinct():
    """3-day query: all days produce facts with distinct keys."""
    evidence = VerifiedEvidenceSet(
        items=tuple(
            EvidenceItem(
                chunk_id=f"day{d}", document_id="diet",
                text=f"[Diet] Day={d} | Breakfast=B{d} | Lunch=L{d} | Dinner=D{d}",
                citation=CitationRecord(label=f"[{i}]", state=CitationState.VALID),
                relevance_score=1.0 - i * 0.1,
                heading_path=f"table-row-Diet-{d-1}",
            )
            for i, d in enumerate([5, 8, 12])
        ),
        query_fragments=(TypedQueryFragment(text="5일차 8일차 12일차", query_type="semantic", language="ko"),),
    )

    ctx = ContextAssembler().assemble(evidence, query="5일차 아침 8일차 점심 12일차 저녁")

    # Each day has distinct facts
    assert any("Day=5" in f.key and "Breakfast" in f.key and f.value == "B5" for f in ctx.facts)
    assert any("Day=8" in f.key and "Lunch" in f.key and f.value == "L8" for f in ctx.facts)
    assert any("Day=12" in f.key and "Dinner" in f.key and f.value == "D12" for f in ctx.facts)

    # All keys are unique
    all_keys = [f.key for f in ctx.facts]
    assert len(all_keys) == len(set(all_keys)), "All fact keys must be unique"


def test_rendered_context_format():
    """Verify the LLM sees '확인된 데이터' and '참고 자료' sections."""
    evidence = VerifiedEvidenceSet(
        items=(
            EvidenceItem(
                chunk_id="r1", document_id="d1",
                text="[S] Key=Value",
                citation=CitationRecord(label="[1]", state=CitationState.VALID),
                relevance_score=0.8, heading_path="table-row-S-0",
            ),
            EvidenceItem(
                chunk_id="t1", document_id="d2",
                text="텍스트 참고 자료입니다.",
                citation=CitationRecord(label="[2]", state=CitationState.VALID),
                relevance_score=0.7, heading_path="paragraph-0",
            ),
        ),
        query_fragments=(TypedQueryFragment(text="test", query_type="semantic", language="ko"),),
    )

    ctx = ContextAssembler().assemble(evidence, query="test")
    rendered = ctx.render_for_llm()

    # Must have both sections
    assert "확인된 데이터:" in rendered
    assert "참고 자료:" in rendered
    # Facts section comes first
    facts_pos = rendered.index("확인된 데이터:")
    ref_pos = rendered.index("참고 자료:")
    assert facts_pos < ref_pos
