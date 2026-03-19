"""Tests for MLXRuntime generation behavior."""

from __future__ import annotations

from jarvis.contracts import CitationRecord, EvidenceItem, VerifiedEvidenceSet
from jarvis.runtime.mlx_runtime import MLXRuntime


class _Backend:
    model_id = "stub-backend"

    def generate(self, prompt: str, context: str, intent: str) -> str:
        return (
            "JARVIS uses SQLite FTS5 and LanceDB hybrid retrieval. "
            "It also controls every macOS application automatically."
        )


def _evidence_set() -> VerifiedEvidenceSet:
    item = EvidenceItem(
        chunk_id="c1",
        document_id="d1",
        text="JARVIS uses SQLite FTS5 and LanceDB hybrid retrieval for grounded answers.",
        citation=CitationRecord(document_id="d1", chunk_id="c1", label="[1]"),
        source_path="/tmp/architecture.md",
        relevance_score=1.0,
    )
    return VerifiedEvidenceSet(items=(item,), query_fragments=())


class TestMLXRuntime:
    def test_exposes_backend_model_id_for_health_checks(self) -> None:
        runtime = MLXRuntime(backend=_Backend(), model_id="stub")

        assert runtime.model_id == "stub-backend"

    def test_generate_records_verification_warnings(self) -> None:
        runtime = MLXRuntime(backend=_Backend())

        answer = runtime.generate("설명해줘", _evidence_set())

        assert len(answer.verification_warnings) == 1
        assert "근거 정렬 미확인 문장" in answer.verification_warnings[0]
