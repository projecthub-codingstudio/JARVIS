"""Contract tests for enums and state types."""

from __future__ import annotations

import pytest

from jarvis.contracts.states import (
    AccessStatus,
    CitationState,
    GovernorMode,
    IndexingStatus,
    TaskStatus,
    ToolName,
)


class TestCitationState:
    def test_exactly_five_states(self) -> None:
        assert len(CitationState) == 5

    def test_expected_values(self) -> None:
        expected = {"VALID", "STALE", "REINDEXING", "MISSING", "ACCESS_LOST"}
        assert {s.value for s in CitationState} == expected

    def test_needs_warning(self) -> None:
        assert not CitationState.VALID.needs_warning
        assert CitationState.STALE.needs_warning
        assert not CitationState.REINDEXING.needs_warning
        assert CitationState.MISSING.needs_warning
        assert CitationState.ACCESS_LOST.needs_warning

    def test_string_serialization(self) -> None:
        assert str(CitationState.VALID) == "CitationState.VALID"
        assert CitationState.VALID.value == "VALID"
        assert CitationState("STALE") == CitationState.STALE


class TestTaskStatus:
    def test_all_statuses(self) -> None:
        expected = {"PENDING", "RUNNING", "COMPLETED", "FAILED", "SKIPPED"}
        assert {s.value for s in TaskStatus} == expected


class TestGovernorMode:
    def test_all_modes(self) -> None:
        expected = {"NORMAL", "DEGRADED", "RESTRICTED", "SHUTDOWN"}
        assert {m.value for m in GovernorMode} == expected


class TestToolName:
    def test_only_three_tools(self) -> None:
        """Invariant #6: Phase 1 exposes only 3 tools."""
        assert len(ToolName) == 3

    def test_expected_tools(self) -> None:
        expected = {"read_file", "search_files", "draft_export"}
        assert {t.value for t in ToolName} == expected


class TestIndexingStatus:
    def test_all_statuses(self) -> None:
        expected = {"PENDING", "INDEXING", "INDEXED", "FAILED", "TOMBSTONED"}
        assert {s.value for s in IndexingStatus} == expected


class TestAccessStatus:
    def test_all_statuses(self) -> None:
        expected = {"ACCESSIBLE", "DENIED", "NOT_FOUND"}
        assert {s.value for s in AccessStatus} == expected
