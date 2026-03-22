"""Tests for query complexity classification."""
from __future__ import annotations

import pytest

from jarvis.core.planner import Planner, _classify_query_complexity


class TestClassifyQueryComplexity:
    """Heuristic complexity classifier should route queries to appropriate tiers."""

    # --- Simple queries (data lookups, short questions) ---

    @pytest.mark.parametrize("query", [
        "오늘 날씨",
        "파일 어디 있어?",
        "몇 시야?",
        "씨샵.pdf",
        "JARVIS 버전",
        "what is BGE-M3",
        "show me the config",
        "list files",
    ])
    def test_simple_queries(self, query: str) -> None:
        assert _classify_query_complexity(query) == "simple"

    # --- Complex queries (analysis, comparison, multi-step reasoning) ---

    @pytest.mark.parametrize("query", [
        "EXAONE-3.5와 EXAONE-4.0의 성능 차이점을 분석해주세요",
        "현재 검색 파이프라인의 문제점을 설명해주고 개선 방안을 제시해줘",
        "MLX와 Ollama 백엔드의 장단점을 비교 분석해줘",
        "compare the trade-offs between monolith and microservice architecture for this project",
        "explain how the semantic chunking pipeline works and why it improves search quality",
        "왜 PDF 청킹이 19,543개나 생성되는지 원인을 분석하고 해결 방법을 설계해줘",
    ])
    def test_complex_queries(self, query: str) -> None:
        assert _classify_query_complexity(query) == "complex"

    # --- Moderate queries (standard Q&A, no complex keywords) ---

    @pytest.mark.parametrize("query", [
        "Reranker가 어떤 모델을 사용하는지 찾아줘",
        "JARVIS 프로젝트의 현재 진행 상태를 알려줘",
        "BGE-M3 임베딩 모델이 무엇인지 알려줘",
    ])
    def test_moderate_queries(self, query: str) -> None:
        result = _classify_query_complexity(query)
        assert result in ("moderate", "simple")  # acceptable range

    def test_planner_has_classify_method(self) -> None:
        planner = Planner()
        assert hasattr(planner, "classify_complexity")
        result = planner.classify_complexity("테스트 쿼리입니다")
        assert result in ("simple", "moderate", "complex")
