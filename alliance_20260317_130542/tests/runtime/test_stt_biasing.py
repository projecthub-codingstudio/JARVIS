from __future__ import annotations

from pathlib import Path

from jarvis.runtime.stt_biasing import build_vocabulary_hint


def test_build_vocabulary_hint_extracts_code_terms(tmp_path: Path) -> None:
    kb = tmp_path / "knowledge_base"
    kb.mkdir()
    code = kb / "pipeline.py"
    code.write_text(
        "class Pipeline:\n"
        "    def validate_provider_result(self):\n"
        "        provider_result = []\n",
        encoding="utf-8",
    )

    hint = build_vocabulary_hint(kb)

    assert "pipeline.py" in hint
    assert "pipeline" in hint
    assert "validate_provider_result" in hint
    assert "provider_result" in hint


def test_build_vocabulary_hint_returns_empty_when_path_missing(tmp_path: Path) -> None:
    hint = build_vocabulary_hint(tmp_path / "missing")
    assert hint == ""
