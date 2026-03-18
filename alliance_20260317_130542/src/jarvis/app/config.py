"""Application configuration for JARVIS."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class JarvisConfig:
    """Central configuration. Resolved at startup by bootstrap."""

    # Workspace
    watched_folders: list[Path] = field(default_factory=list)
    data_dir: Path = field(default_factory=lambda: Path.home() / ".jarvis")

    # SQLite
    db_path: Path | None = None

    # Models
    llm_model_id: str = "default-14b-q4"
    embedding_model_id: str = "default-embedding"

    # Retrieval
    fts_top_k: int = 10
    vector_top_k: int = 10
    hybrid_top_k: int = 10
    rrf_k: int = 60  # RRF constant

    # Governor
    memory_limit_gb: float = 16.0

    # Export
    export_dir: Path | None = None

    def __post_init__(self) -> None:
        if self.db_path is None:
            self.db_path = self.data_dir / "jarvis.db"
        if self.export_dir is None:
            self.export_dir = self.data_dir / "exports"

    def validate(self) -> list[str]:
        """Return a list of validation error messages. Empty = valid."""
        errors: list[str] = []
        if not self.watched_folders:
            errors.append("No watched folders configured")
        for folder in self.watched_folders:
            if not folder.exists():
                errors.append(f"Watched folder does not exist: {folder}")
        return errors
