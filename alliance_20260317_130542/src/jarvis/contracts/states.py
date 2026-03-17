"""Enumerations and state types for the JARVIS system.

Defines the required enums and Literal types per Implementation Spec Section 3.1.
"""

from __future__ import annotations

from enum import Enum, unique
from typing import Literal

# --- Literal types (Spec Section 3.1) ---

RuntimeTier = Literal["fast", "balanced", "deep", "unloaded"]
ThermalState = Literal["nominal", "fair", "serious", "critical"]


@unique
class CitationState(str, Enum):
    """Five allowed citation freshness states (invariant #5)."""

    VALID = "VALID"
    STALE = "STALE"
    REINDEXING = "REINDEXING"
    MISSING = "MISSING"
    ACCESS_LOST = "ACCESS_LOST"

    @property
    def needs_warning(self) -> bool:
        return self in (CitationState.STALE, CitationState.MISSING, CitationState.ACCESS_LOST)


@unique
class TaskStatus(str, Enum):
    """Status lifecycle for a task log entry."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


@unique
class GovernorMode(str, Enum):
    """Governor operational modes."""

    NORMAL = "NORMAL"
    DEGRADED = "DEGRADED"
    RESTRICTED = "RESTRICTED"
    SHUTDOWN = "SHUTDOWN"


@unique
class ToolName(str, Enum):
    """Phase 1 allowed tools (invariant #6)."""

    READ_FILE = "read_file"
    SEARCH_FILES = "search_files"
    DRAFT_EXPORT = "draft_export"


@unique
class IndexingStatus(str, Enum):
    """Document indexing pipeline status."""

    PENDING = "PENDING"
    INDEXING = "INDEXING"
    INDEXED = "INDEXED"
    FAILED = "FAILED"
    TOMBSTONED = "TOMBSTONED"


@unique
class AccessStatus(str, Enum):
    """Document access permission status."""

    ACCESSIBLE = "ACCESSIBLE"
    DENIED = "DENIED"
    NOT_FOUND = "NOT_FOUND"
