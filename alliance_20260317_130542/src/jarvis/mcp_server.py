"""JARVIS MCP Server — exposes tools via Model Context Protocol.

Wraps the existing ToolRegistry tools (READ_FILE, SEARCH_FILES, DRAFT_EXPORT)
as MCP-compliant tool endpoints. Communicates via stdio transport.

Usage:
    python -m jarvis.mcp_server

This allows any MCP-compatible client (Claude Desktop, etc.) to use
JARVIS's local knowledge base tools.
"""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    TextContent,
    Tool,
)

logger = logging.getLogger(__name__)

# Tool definitions matching the existing ToolRegistry tools
TOOLS = [
    Tool(
        name="read_file",
        description="Read the contents of a file from the local knowledge base. "
        "Supports text, code, markdown, and other text-based formats.",
        inputSchema={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute or relative path to the file to read",
                },
            },
            "required": ["path"],
        },
    ),
    Tool(
        name="search_files",
        description="Search the indexed knowledge base using full-text search. "
        "Returns ranked results from documents indexed by JARVIS.",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query (supports Korean and English)",
                },
                "top_k": {
                    "type": "integer",
                    "description": "Maximum number of results to return",
                    "default": 5,
                },
            },
            "required": ["query"],
        },
    ),
    Tool(
        name="draft_export",
        description="Export a draft document to the file system. "
        "Requires explicit approval before writing.",
        inputSchema={
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "The content to export",
                },
                "destination": {
                    "type": "string",
                    "description": "File path for the exported document",
                },
                "approved": {
                    "type": "boolean",
                    "description": "Whether the export has been approved by the user",
                    "default": False,
                },
            },
            "required": ["content", "destination"],
        },
    ),
]


def _create_jarvis_server() -> Server:
    """Create and configure the JARVIS MCP server."""
    server = Server("jarvis")

    # Lazy-loaded runtime context
    _context = {}

    def _get_context():
        if "runtime" not in _context:
            from jarvis.app.runtime_context import build_runtime_context

            ctx = build_runtime_context(
                start_watcher_enabled=False,
                start_background_backfill=False,
                allow_mlx=False,  # MCP server doesn't need LLM
            )
            _context["runtime"] = ctx
        return _context["runtime"]

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return TOOLS

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        try:
            if name == "read_file":
                path = arguments.get("path", "")
                from jarvis.tools.read_file import ReadFileTool

                ctx = _get_context()
                tool = ReadFileTool(
                    allowed_roots=[ctx.knowledge_base_path or Path.cwd()],
                )
                result = tool.execute(path=path)
                return [TextContent(type="text", text=result)]

            elif name == "search_files":
                query = arguments.get("query", "")
                top_k = int(arguments.get("top_k", 5))
                from jarvis.tools.search_files import SearchFilesTool

                ctx = _get_context()
                tool = SearchFilesTool(
                    db=ctx.bootstrap_result.db,
                    allowed_roots=[ctx.knowledge_base_path or Path.cwd()],
                )
                hits = tool.execute(query=query, top_k=top_k)
                results = [
                    {"path": h.document_id, "score": h.score, "snippet": h.snippet[:200]}
                    for h in hits
                ]
                return [TextContent(type="text", text=json.dumps(results, ensure_ascii=False, indent=2))]

            elif name == "draft_export":
                content = arguments.get("content", "")
                destination = arguments.get("destination", "")
                approved = bool(arguments.get("approved", False))
                from jarvis.contracts import DraftExportRequest
                from jarvis.tools.draft_export import DraftExportTool

                tool = DraftExportTool()
                request = DraftExportRequest(
                    draft=None,  # type: ignore
                    destination=Path(destination),
                )
                if not approved:
                    return [TextContent(type="text", text=json.dumps({
                        "status": "pending_approval",
                        "message": "Export requires user approval. Set approved=true to proceed.",
                        "destination": destination,
                    }))]
                # Write directly when approved
                Path(destination).parent.mkdir(parents=True, exist_ok=True)
                Path(destination).write_text(content, encoding="utf-8")
                return [TextContent(type="text", text=json.dumps({
                    "status": "exported",
                    "destination": destination,
                    "bytes": len(content.encode("utf-8")),
                }))]

            else:
                return [TextContent(type="text", text=f"Unknown tool: {name}")]

        except Exception as exc:
            return [TextContent(type="text", text=f"Error: {exc}")]

    return server


async def main():
    """Run the JARVIS MCP server with stdio transport."""
    server = _create_jarvis_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
