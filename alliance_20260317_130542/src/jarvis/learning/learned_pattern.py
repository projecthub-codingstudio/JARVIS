"""LearnedPattern — extracted refinement pattern stored for future injection."""
from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum


class ReformulationType(str, Enum):
    SPECIALIZATION = "specialization"
    GENERALIZATION = "generalization"
    ERROR_CORRECTION = "error_correction"
    PARALLEL_MOVE = "parallel_move"


@dataclass(frozen=True)
class LearnedPattern:
    pattern_id: str
    canonical_query: str
    failed_variants: list[str]
    retrieval_task: str
    entity_hints: dict[str, object]
    reformulation_type: ReformulationType
    success_count: int
    citation_paths: list[str]
    created_at: int
    last_used_at: int

    def to_row(self) -> dict[str, object]:
        return {
            "pattern_id": self.pattern_id,
            "canonical_query": self.canonical_query,
            "failed_variants": json.dumps(self.failed_variants, ensure_ascii=False),
            "retrieval_task": self.retrieval_task,
            "entity_hints_json": json.dumps(self.entity_hints, ensure_ascii=False),
            "reformulation_type": self.reformulation_type.value,
            "success_count": self.success_count,
            "citation_paths": json.dumps(self.citation_paths, ensure_ascii=False),
            "created_at": self.created_at,
            "last_used_at": self.last_used_at,
        }

    @classmethod
    def from_row(cls, row: dict[str, object]) -> "LearnedPattern":
        return cls(
            pattern_id=str(row["pattern_id"]),
            canonical_query=str(row["canonical_query"]),
            failed_variants=json.loads(str(row.get("failed_variants") or "[]")),
            retrieval_task=str(row["retrieval_task"]),
            entity_hints=json.loads(str(row.get("entity_hints_json") or "{}")),
            reformulation_type=ReformulationType(str(row["reformulation_type"])),
            success_count=int(row.get("success_count") or 1),
            citation_paths=json.loads(str(row.get("citation_paths") or "[]")),
            created_at=int(row["created_at"]),
            last_used_at=int(row["last_used_at"]),
        )
