"""Tests for planner intent classification."""

from __future__ import annotations

from jarvis.core.planner import LLMIntentJSONBackend, Planner, QueryAnalysis
from jarvis.identifier_restoration import IdentifierCandidate, IdentifierRewrite


def test_planner_classifies_greeting_as_smalltalk() -> None:
    planner = Planner(lightweight_backend=None)

    analysis = planner.analyze("안녕하세요")

    assert analysis.intent == "smalltalk"
    assert analysis.retrieval_task == "smalltalk"
    assert analysis.to_payload()["intent"] == "smalltalk"


def test_planner_classifies_pleasantry_as_smalltalk() -> None:
    planner = Planner(lightweight_backend=None)

    analysis = planner.analyze("만나서 반갑습니다")

    assert analysis.intent == "smalltalk"
    assert analysis.retrieval_task == "smalltalk"


def test_planner_keeps_document_query_as_qa() -> None:
    planner = Planner(lightweight_backend=None)

    analysis = planner.analyze("안녕하세요 문서를 찾아줘")

    assert analysis.intent == "qa"
    assert analysis.retrieval_task == "document_qa"


def test_planner_classifies_weather_as_weather() -> None:
    planner = Planner(lightweight_backend=None)

    analysis = planner.analyze("오늘 날씨좀 알려주세요")

    assert analysis.intent == "weather"
    assert analysis.retrieval_task == "live_data_request"
    assert analysis.entities["capability"] == "weather"


def test_planner_does_not_route_negated_weather_over_table_lookup() -> None:
    planner = Planner(lightweight_backend=None)

    analysis = planner.analyze("날씨 말고 식단표에서 12일차 저녁 메뉴 알려줘")

    assert analysis.intent == "qa"
    assert analysis.retrieval_task == "table_lookup"
    assert analysis.entities["row_ids"] == ["12"]
    assert analysis.entities["fields"] == ["Dinner"]


def test_planner_classifies_table_lookup_with_row_and_field_entities() -> None:
    planner = Planner(lightweight_backend=None)

    analysis = planner.analyze("다이어트 식단표에서 9일차 저녁 메뉴 알려주세요")

    assert analysis.retrieval_task == "table_lookup"
    assert analysis.entities["row_ids"] == ["9"]
    assert analysis.entities["fields"] == ["Dinner"]


def test_planner_expands_table_overview_terms_for_retrieval() -> None:
    planner = Planner()

    analysis = planner.analyze("다이어트 식단표 보여줘")

    assert analysis.retrieval_task == "table_lookup"
    assert "diet" in analysis.search_terms
    assert "menu" in analysis.search_terms


def test_planner_classifies_code_lookup_from_filename() -> None:
    planner = Planner(lightweight_backend=None)

    analysis = planner.analyze("pipeline.py 파일에서 Pipeline 클래스 설명해 줘")

    assert analysis.retrieval_task == "code_lookup"
    assert analysis.entities["target_file"] == "pipeline.py"


def test_planner_extracts_document_topic_and_negative_terms() -> None:
    planner = Planner(lightweight_backend=None)

    analysis = planner.analyze("한글문서 파일형식에서 하이퍼 텍스트 정보가 아니라 기본 구조를 설명해 주세요")

    assert analysis.retrieval_task == "document_qa"
    assert "기본 구조" in analysis.entities["topic_terms"]
    assert "하이퍼 텍스트 정보" in analysis.entities["negative_terms"]


def test_planner_does_not_promote_filename_rewrite_for_plain_document_query(monkeypatch) -> None:
    def fake_rewrite(query: str, *, knowledge_base_path=None, max_candidates: int = 4) -> IdentifierRewrite:
        return IdentifierRewrite(
            original_query=query,
            rewritten_query=f"{query} tbl_day_chart.sql",
            candidates=(
                IdentifierCandidate(
                    canonical="tbl_day_chart.sql",
                    kind="filename",
                    score=0.95,
                ),
            ),
            appended_terms=("tbl_day_chart.sql",),
        )

    monkeypatch.setattr("jarvis.core.planner.rewrite_query_with_identifiers", fake_rewrite)

    planner = Planner()
    analysis = planner.analyze("한글 문서 8 형식에서 그리기 개체 자료에서 기본 구조에 대해 설명해줘")

    assert analysis.retrieval_task == "document_qa"
    assert analysis.target_file == ""
    assert "tbl_day_chart.sql" not in analysis.search_terms


def test_planner_payload_supports_llm_intent_json_shape() -> None:
    fallback = QueryAnalysis(retrieval_task="table_lookup", intent="qa", search_terms=["다이어트", "식단표"])
    payload = {
        "retrieval_task": "table_lookup",
        "intent": "diet_plan_lookup",
        "sub_intents": ["smalltalk"],
        "entities": {
            "day_numbers": [9],
            "meal_slots": ["dinner"],
        },
        "search_terms": ["다이어트", "식단표", "9일차", "저녁"],
        "language": "ko",
        "confidence": 0.94,
        "source": "llm_json",
    }

    analysis = QueryAnalysis.from_payload(payload, fallback=fallback)

    assert analysis.retrieval_task == "table_lookup"
    assert analysis.intent == "diet_plan_lookup"
    assert analysis.sub_intents == ["smalltalk"]
    assert analysis.entities["day_numbers"] == [9]
    assert analysis.source == "llm_json"


def test_planner_accepts_llm_intent_json_backend() -> None:
    class FakeBackend:
        def generate(self, prompt: str, context: str, intent: str) -> str:
            assert intent == "planner_intent_json"
            return """
            {
              "retrieval_task": "table_lookup",
              "intent": "diet_plan_lookup",
              "sub_intents": ["smalltalk"],
              "entities": {"day_numbers": [9], "meal_slots": ["dinner"]},
              "search_terms": ["다이어트", "식단표", "9일차", "저녁"],
              "target_file": "",
              "language": "ko",
              "confidence": 0.96,
              "source": "llm_json"
            }
            """

    planner = Planner(lightweight_backend=LLMIntentJSONBackend(llm_backend=FakeBackend()))

    analysis = planner.analyze("안녕하세요. 만나서 반갑습니다. 다이어트 식단표에서 9일차 저녁 메뉴 알려주세요.")

    assert analysis.retrieval_task == "table_lookup"
    assert analysis.intent == "diet_plan_lookup"
    assert analysis.sub_intents == ["smalltalk"]
    assert analysis.entities["day_numbers"] == [9]
    assert analysis.entities["meal_slots"] == ["dinner"]
    assert analysis.source == "llm_json"


def test_planner_merges_keyword_expansion_into_llm_analysis() -> None:
    class FakeBackend:
        def generate(self, prompt: str, context: str, intent: str) -> str:
            assert intent == "planner_intent_json"
            return """
            {
              "retrieval_task": "document_qa",
              "intent": "qa",
              "sub_intents": [],
              "entities": {},
              "search_terms": ["projecthub", "브로셔"],
              "target_file": "",
              "language": "ko",
              "confidence": 0.91,
              "source": "llm_json"
            }
            """

    planner = Planner(lightweight_backend=LLMIntentJSONBackend(llm_backend=FakeBackend()))

    analysis = planner.analyze("ProjectHub 브로셔에서 ProjectHub를 어떻게 소개하나요?")

    assert "brochure" in analysis.search_terms
    assert analysis.source == "llm_json"


def test_planner_falls_back_to_keyword_expansion_when_llm_intent_json_is_invalid() -> None:
    class FakeBackend:
        def generate(self, prompt: str, context: str, intent: str) -> str:
            assert intent == "planner_intent_json"
            return "not-json"

    planner = Planner(lightweight_backend=LLMIntentJSONBackend(llm_backend=FakeBackend()))

    analysis = planner.analyze("ProjectHub 브로셔에서 ProjectHub를 어떻게 소개하나요?")

    assert "brochure" in analysis.search_terms
    assert analysis.source == "lightweight"
