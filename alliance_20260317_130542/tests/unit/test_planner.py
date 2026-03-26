"""Tests for planner intent classification."""

from __future__ import annotations

from jarvis.core.planner import LLMIntentJSONBackend, Planner, QueryAnalysis


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
