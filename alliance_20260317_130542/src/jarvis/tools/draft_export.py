"""DraftExportTool — exports a draft artifact with user approval.

One of the 3 Phase 1 tools (ToolName.DRAFT_EXPORT).
Requires explicit user approval before writing (invariant #3).
"""

from __future__ import annotations

from pathlib import Path

from jarvis.contracts import (
    ApprovalGatewayProtocol,
    DraftExportRequest,
    DraftExportResult,
)


class DraftExportTool:
    """Exports draft artifacts to disk after user approval.

    Requires ApprovalGatewayProtocol for invariant #3 compliance.
    """

    def __init__(
        self,
        *,
        approval_gateway: ApprovalGatewayProtocol,
        export_dir: Path | None = None,
    ) -> None:
        """Initialize with approval gateway and export directory.

        Args:
            approval_gateway: Gateway for requesting user approval.
            export_dir: Default directory for exports.
        """
        self._approval_gateway = approval_gateway
        self._export_dir = export_dir

    def execute(self, *, request: DraftExportRequest) -> DraftExportResult:
        """Export a draft after obtaining user approval.

        Args:
            request: The export request with draft and destination.

        Returns:
            DraftExportResult indicating success/failure.
        """
        approved = self._approval_gateway.request_approval(request)
        if not approved:
            return DraftExportResult(
                success=False,
                destination=request.destination,
                approved=False,
                error_message="Approval denied",
            )
        return self._approval_gateway.execute_export(request)
