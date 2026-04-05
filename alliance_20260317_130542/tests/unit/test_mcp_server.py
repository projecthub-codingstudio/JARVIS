"""Tests for JARVIS MCP server tool definitions and handler dispatch."""
from __future__ import annotations

import pytest

from jarvis.mcp_server import TOOLS, _create_jarvis_server


class TestMCPToolDefinitions:
    def test_three_tools_registered(self) -> None:
        assert len(TOOLS) == 3

    def test_tool_names(self) -> None:
        names = {t.name for t in TOOLS}
        assert names == {"read_file", "search_files", "draft_export"}

    def test_tools_have_input_schemas(self) -> None:
        for tool in TOOLS:
            assert tool.inputSchema is not None
            assert "properties" in tool.inputSchema

    def test_read_file_requires_path(self) -> None:
        tool = next(t for t in TOOLS if t.name == "read_file")
        assert "path" in tool.inputSchema["required"]

    def test_search_files_requires_query(self) -> None:
        tool = next(t for t in TOOLS if t.name == "search_files")
        assert "query" in tool.inputSchema["required"]

    def test_draft_export_requires_content_and_destination(self) -> None:
        tool = next(t for t in TOOLS if t.name == "draft_export")
        assert "content" in tool.inputSchema["required"]
        assert "destination" in tool.inputSchema["required"]


class TestMCPServerCreation:
    def test_server_creates_successfully(self) -> None:
        server = _create_jarvis_server()
        assert server is not None
        assert server.name == "jarvis"
