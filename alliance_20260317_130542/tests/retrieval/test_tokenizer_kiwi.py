"""Tests for KiwiTokenizer."""
from __future__ import annotations

from jarvis.retrieval.tokenizer_kiwi import KiwiTokenizer


class TestKiwiTokenizer:
    def test_tokenize_korean(self) -> None:
        t = KiwiTokenizer()
        tokens = t.tokenize("프로젝트 아키텍처를 설명해줘")
        assert len(tokens) > 0
        assert all(isinstance(tok, str) for tok in tokens)

    def test_tokenize_english_passthrough(self) -> None:
        t = KiwiTokenizer()
        tokens = t.tokenize("architecture design")
        assert len(tokens) > 0

    def test_tokenize_empty(self) -> None:
        t = KiwiTokenizer()
        assert t.tokenize("") == []

    def test_tokenize_for_fts(self) -> None:
        t = KiwiTokenizer()
        result = t.tokenize_for_fts("음성 인식 시스템")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_tokenize_mixed(self) -> None:
        t = KiwiTokenizer()
        tokens = t.tokenize("JARVIS 프로젝트의 아키텍처")
        assert len(tokens) > 0
