"""PatternExtractor — classify reformulation type and extract LearnedPattern."""
from __future__ import annotations

from jarvis.learning.session_event import ReformulationPair
from jarvis.learning.learned_pattern import LearnedPattern, ReformulationType


def _entity_count(entities: dict[str, object]) -> int:
    total = 0
    for value in entities.values():
        if isinstance(value, list):
            total += len(value)
        elif value:
            total += 1
    return total


def _entities_structurally_equal(a: dict[str, object], b: dict[str, object]) -> bool:
    if set(a.keys()) != set(b.keys()):
        return False
    for key in a:
        if a[key] != b[key]:
            return False
    return True


class PatternExtractor:
    def __init__(self, *, error_correction_similarity: float = 0.85) -> None:
        self._err_corr_sim = error_correction_similarity

    def classify(self, pair: ReformulationPair) -> ReformulationType:
        f_count = _entity_count(pair.failure.entities)
        s_count = _entity_count(pair.success.entities)

        if _entities_structurally_equal(pair.failure.entities, pair.success.entities):
            if pair.similarity >= self._err_corr_sim:
                return ReformulationType.ERROR_CORRECTION
            return ReformulationType.PARALLEL_MOVE

        if s_count > f_count:
            return ReformulationType.SPECIALIZATION
        if s_count < f_count:
            return ReformulationType.GENERALIZATION
        return ReformulationType.PARALLEL_MOVE

    def extract(
        self,
        pair: ReformulationPair,
        *,
        pattern_id: str,
        now: int,
    ) -> LearnedPattern | None:
        ptype = self.classify(pair)
        if ptype is ReformulationType.GENERALIZATION:
            return None

        return LearnedPattern(
            pattern_id=pattern_id,
            canonical_query=pair.success.query_text,
            failed_variants=[pair.failure.query_text],
            retrieval_task=pair.success.retrieval_task,
            entity_hints=dict(pair.success.entities),
            reformulation_type=ptype,
            success_count=1,
            citation_paths=list(pair.success.citation_paths),
            created_at=now,
            last_used_at=now,
        )
