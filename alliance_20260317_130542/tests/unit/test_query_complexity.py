"""Tests for query complexity classification."""
from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.core.planner import Planner, QueryAnalysis, _classify_query_complexity


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


class TestPlannerAnalysis:
    def test_planner_uses_heuristic_baseline(self) -> None:
        planner = Planner(lightweight_backend=None)
        analysis = planner.analyze("Reranker 구조 알려줘")
        assert isinstance(analysis, QueryAnalysis)
        assert analysis.source == "heuristic"
        assert "reranker" in analysis.search_terms

    def test_planner_enriches_bilingual_terms(self) -> None:
        planner = Planner()
        analysis = planner.analyze("검색 파이프라인 구조 알려줘")
        assert "검색" in analysis.search_terms
        assert "search" in analysis.search_terms
        assert analysis.source == "lightweight"

    def test_planner_preserves_filename_target(self) -> None:
        planner = Planner()
        analysis = planner.analyze("runtime_context.py 구조 설명해줘")
        assert analysis.target_file == "runtime_context.py"
        assert "runtime" in analysis.search_terms

    def test_planner_expands_brochure_queries_for_document_lookup(self) -> None:
        planner = Planner()
        analysis = planner.analyze("ProjectHub 브로셔에서 ProjectHub를 어떻게 소개하나요?")
        assert "projecthub" in analysis.search_terms
        assert "brochure" in analysis.search_terms
        assert analysis.source == "lightweight"

    def test_planner_falls_back_when_lightweight_fails(self) -> None:
        class FailingBackend:
            def analyze(self, raw_text: str, baseline: QueryAnalysis) -> QueryAnalysis | None:
                raise RuntimeError("boom")

        planner = Planner(lightweight_backend=FailingBackend())
        analysis = planner.analyze("검색 구조 설명")
        assert analysis.source == "heuristic"

    def test_planner_restores_spoken_code_query_from_lexicon(self, tmp_path: Path) -> None:
        kb = tmp_path / "knowledge_base"
        kb.mkdir()
        (kb / "pipeline.py").write_text(
            "class Pipeline:\n    provider_result = 'ok'\n",
            encoding="utf-8",
        )
        planner = Planner(knowledge_base_path=kb)
        analysis = planner.analyze("파이프라인점 파이에 있는 프로바이더 리절트 설명해줘")
        assert analysis.target_file == "pipeline.py"
        assert "provider_result" in analysis.search_terms

    def test_planner_restores_spoken_python_class_query_from_lexicon(self, tmp_path: Path) -> None:
        kb = tmp_path / "knowledge_base"
        kb.mkdir()
        (kb / "pipeline.py").write_text(
            "class Pipeline:\n    def run(self) -> None:\n        pass\n",
            encoding="utf-8",
        )
        planner = Planner(knowledge_base_path=kb)
        analysis = planner.analyze("다시 파이선 소스인 파이프라인에서 클래스 파이프라인에 대해 설명해 줘")
        assert analysis.target_file == "pipeline.py"
        assert "pipeline" in analysis.search_terms

    def test_planner_does_not_pollute_document_query_with_code_identifiers(self, tmp_path: Path) -> None:
        kb = tmp_path / "knowledge_base"
        kb.mkdir()
        (kb / "pipeline.py").write_text(
            "class StageDesign:\n"
            "    project_path = 'demo'\n"
            "    def _parse_research_section(self) -> None:\n"
            "        pass\n",
            encoding="utf-8",
        )
        planner = Planner(knowledge_base_path=kb)

        analysis = planner.analyze("ProjectHub 브로셔에서 ProjectHub를 어떻게 소개하나요?")

        assert analysis.retrieval_task == "document_qa"
        assert "projecthub" in analysis.search_terms
        assert "project_path" not in analysis.search_terms
        assert "_parse_research_section" not in analysis.search_terms
