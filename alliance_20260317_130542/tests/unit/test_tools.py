"""Tests for tool implementations and approval flow."""
from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.cli.approval import CLIApprovalGateway
from jarvis.contracts import (
    AccessError,
    AnswerDraft,
    DraftExportRequest,
    ToolError,
    VerifiedEvidenceSet,
)
from jarvis.tools.draft_export import DraftExportTool
from jarvis.tools.read_file import ReadFileTool
from jarvis.tools.search_files import SearchFilesTool


class TestReadFileTool:
    def test_reads_file_within_allowed_root(self, tmp_path: Path) -> None:
        file_path = tmp_path / "notes.txt"
        file_path.write_text("hello tool", encoding="utf-8")

        tool = ReadFileTool(allowed_roots=[tmp_path])
        assert tool.execute(path=str(file_path)) == "hello tool"

    def test_rejects_path_outside_scope(self, tmp_path: Path) -> None:
        outside = tmp_path.parent / "outside.txt"
        outside.write_text("blocked", encoding="utf-8")

        tool = ReadFileTool(allowed_roots=[tmp_path])
        with pytest.raises(AccessError):
            tool.execute(path=str(outside))

    def test_raises_for_missing_file(self, tmp_path: Path) -> None:
        tool = ReadFileTool(allowed_roots=[tmp_path])
        with pytest.raises(ToolError):
            tool.execute(path=str(tmp_path / "missing.txt"))


class TestSearchFilesTool:
    def test_finds_by_filename_and_content(self, tmp_path: Path) -> None:
        (tmp_path / "architecture.md").write_text("hybrid search and vector index", encoding="utf-8")
        (tmp_path / "notes.txt").write_text("unrelated", encoding="utf-8")

        tool = SearchFilesTool(allowed_roots=[tmp_path])
        hits = tool.execute(query="architecture vector", top_k=5)

        assert hits
        assert hits[0].document_id.endswith("architecture.md")

    def test_empty_query_returns_empty(self, tmp_path: Path) -> None:
        tool = SearchFilesTool(allowed_roots=[tmp_path])
        assert tool.execute(query="   ") == []


class TestDraftExportFlow:
    def test_gateway_writes_export_after_approval(self, tmp_path: Path) -> None:
        gateway = CLIApprovalGateway(auto_approve=True)
        draft = AnswerDraft(content="# Exported", evidence=VerifiedEvidenceSet(items=(), query_fragments=()))
        request = DraftExportRequest(draft=draft, destination=tmp_path / "draft.md")

        assert gateway.request_approval(request) is True
        result = gateway.execute_export(request)

        assert result.success is True
        assert request.destination.read_text(encoding="utf-8") == "# Exported"

    def test_draft_export_tool_denies_without_approval(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        gateway = CLIApprovalGateway(auto_approve=False)
        monkeypatch.setattr("builtins.input", lambda _prompt: "n")
        tool = DraftExportTool(approval_gateway=gateway)
        draft = AnswerDraft(content="body", evidence=VerifiedEvidenceSet(items=(), query_fragments=()))
        request = DraftExportRequest(draft=draft, destination=tmp_path / "denied.md")

        result = tool.execute(request=request)

        assert result.success is False
        assert result.approved is False
        assert not request.destination.exists()

    def test_draft_export_tool_exports_with_approval(self, tmp_path: Path) -> None:
        gateway = CLIApprovalGateway(auto_approve=True)
        tool = DraftExportTool(approval_gateway=gateway)
        draft = AnswerDraft(content="approved body", evidence=VerifiedEvidenceSet(items=(), query_fragments=()))
        request = DraftExportRequest(draft=draft, destination=tmp_path / "approved.md")

        result = tool.execute(request=request)

        assert result.success is True
        assert result.approved is True
        assert request.destination.read_text(encoding="utf-8") == "approved body"
