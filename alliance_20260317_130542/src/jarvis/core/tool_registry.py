"""ToolRegistry — working stub implementing ToolRegistryProtocol.

Registers exactly the 3 tools from ToolName enum (invariant #6).
Execute dispatches to tool handlers but raises NotImplementedError
for actual execution in Phase 0.
"""

from __future__ import annotations

from typing import Callable

from jarvis.contracts import (
    ErrorCode,
    ToolError,
    ToolName,
    ToolRegistryProtocol,
)
from jarvis.core.error_monitor import ErrorMonitor


class ToolRegistry:
    """Working stub tool registry. Only allows Phase 1 tools.

    Implements ToolRegistryProtocol (invariant #6: only 3 tools in Phase 1).
    The three allowed tools are: READ_FILE, SEARCH_FILES, DRAFT_EXPORT.
    """

    _ALLOWED_TOOLS: frozenset[ToolName] = frozenset(ToolName)

    def __init__(self, *, error_monitor: ErrorMonitor | None = None) -> None:
        """Initialize with empty handler map for Phase 0."""
        self._handlers: dict[ToolName, Callable[..., object]] = {}
        self._error_monitor = error_monitor

    def get_allowed_tools(self) -> list[ToolName]:
        """Return the list of allowed tool names (all 3 ToolName values)."""
        return list(self._ALLOWED_TOOLS)

    def register_handler(self, tool_name: ToolName, handler: Callable[..., object]) -> None:
        """Register a handler for a tool. Must be an allowed tool name.

        Args:
            tool_name: Must be one of the 3 ToolName enum values.
            handler: Callable that implements the tool logic.

        Raises:
            ToolError: If tool_name is not in the allowed set.
        """
        if tool_name not in self._ALLOWED_TOOLS:
            raise ToolError(
                ErrorCode.TOOL_NOT_REGISTERED,
                f"Tool '{tool_name}' is not in the allowed tool set",
            )
        self._handlers[tool_name] = handler

    def execute(self, tool_name: ToolName, **kwargs: object) -> object:
        """Execute a registered tool by name.

        Args:
            tool_name: The tool to execute.
            **kwargs: Arguments to pass to the tool handler.

        Returns:
            The tool handler's return value.

        Raises:
            ToolError: If the tool is not registered or not allowed.
        """
        if self._error_monitor is not None and self._error_monitor.should_block_tools():
            raise ToolError(
                ErrorCode.TOOL_EXECUTION_FAILED,
                "Tool execution blocked due to repeated recent failures",
            )
        if (
            self._error_monitor is not None
            and self._error_monitor.write_blocked
            and tool_name == ToolName.DRAFT_EXPORT
        ):
            raise ToolError(
                ErrorCode.TOOL_EXECUTION_FAILED,
                "Write operations are temporarily blocked due to repeated SQLite lock failures",
            )
        if tool_name not in self._ALLOWED_TOOLS:
            raise ToolError(
                ErrorCode.TOOL_NOT_REGISTERED,
                f"Tool '{tool_name}' is not in the allowed tool set",
            )
        handler = self._handlers.get(tool_name)
        if handler is None:
            raise ToolError(
                ErrorCode.TOOL_NOT_REGISTERED,
                f"No handler registered for tool '{tool_name}'",
            )
        return handler(**kwargs)


# Runtime-checkable verification
assert isinstance(ToolRegistry(), ToolRegistryProtocol)
