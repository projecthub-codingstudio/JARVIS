"""Tests for QueryDecomposer."""
from __future__ import annotations

from pathlib import Path

from jarvis.contracts import QueryDecomposerProtocol, TypedQueryFragment
from jarvis.retrieval.query_decomposer import QueryDecomposer


class TestQueryDecomposer:
    def test_korean_query(self) -> None:
        fragments = QueryDecomposer().decompose("프로젝트 아키텍처를 설명해줘")
        assert len(fragments) >= 1
        assert all(isinstance(f, TypedQueryFragment) for f in fragments)
        assert any(f.language == "ko" for f in fragments)

    def test_english_query(self) -> None:
        fragments = QueryDecomposer().decompose("explain the architecture")
        assert len(fragments) >= 1
        assert any(f.language == "en" for f in fragments)

    def test_code_query(self) -> None:
        fragments = QueryDecomposer().decompose("def search_files(query)")
        assert len(fragments) >= 1
        assert any(f.language == "code" for f in fragments)

    def test_mixed_query(self) -> None:
        fragments = QueryDecomposer().decompose("JARVIS 프로젝트의 architecture를 보여줘")
        assert len(fragments) >= 1
        types = {f.query_type for f in fragments}
        assert "keyword" in types

    def test_empty_query(self) -> None:
        assert QueryDecomposer().decompose("") == []

    def test_fragments_have_weight(self) -> None:
        fragments = QueryDecomposer().decompose("검색 시스템 구조")
        for f in fragments:
            assert f.weight > 0.0

    def test_protocol_conformance(self) -> None:
        assert isinstance(QueryDecomposer(), QueryDecomposerProtocol)

    def test_restores_spoken_korean_code_terms_from_lexicon(self, tmp_path: Path) -> None:
        kb = tmp_path / "knowledge_base"
        kb.mkdir()
        (kb / "pipeline.py").write_text(
            "class Pipeline:\n    provider_result = 'ok'\n",
            encoding="utf-8",
        )
        fragments = QueryDecomposer(knowledge_base_path=kb).decompose(
            "파이프라인점 파이에 있는 소스야 프로바이더 리절트에 대해서 다시 설명해줘"
        )
        keyword_texts = [f.text for f in fragments if f.query_type == "keyword"]
        semantic_texts = [f.text for f in fragments if f.query_type == "semantic"]

        assert any("pipeline.py" in text for text in keyword_texts + semantic_texts)
        assert any("provider_result" in text for text in keyword_texts + semantic_texts)

    def test_restores_spoken_python_class_query_from_lexicon(self, tmp_path: Path) -> None:
        kb = tmp_path / "knowledge_base"
        kb.mkdir()
        (kb / "pipeline.py").write_text(
            "class Pipeline:\n    def run(self) -> None:\n        pass\n",
            encoding="utf-8",
        )
        fragments = QueryDecomposer(knowledge_base_path=kb).decompose(
            "다시 파이선 소스인 파이프라인에서 클래스 파이프라인에 대해 설명해 줘"
        )
        texts = [f.text for f in fragments]

        assert any("pipeline.py" in text for text in texts)
        assert any("Pipeline" in text for text in texts)
