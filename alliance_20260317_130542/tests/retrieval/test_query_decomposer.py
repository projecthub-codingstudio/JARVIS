"""Tests for QueryDecomposer."""
from __future__ import annotations

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
