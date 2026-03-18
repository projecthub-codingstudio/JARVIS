"""ApprovalGateway — CLI-based approval gateway for draft exports.

Implements ApprovalGatewayProtocol (invariant #3: no file writes
without explicit user approval).
"""

from __future__ import annotations

from datetime import datetime

from jarvis.contracts import (
    ApprovalGatewayProtocol,
    DraftExportRequest,
    DraftExportResult,
)
from jarvis.observability.metrics import MetricName, MetricsCollector


class CLIApprovalGateway:
    """CLI-based user approval gateway for draft exports.

    Implements ApprovalGatewayProtocol.
    Phase 0 stub: auto-approves for testing, real implementation
    will prompt user via stdin.
    """

    def __init__(
        self,
        *,
        auto_approve: bool = False,
        metrics: MetricsCollector | None = None,
    ) -> None:
        self._auto_approve = auto_approve
        self._metrics = metrics
        self._approved_requests: set[str] = set()

    def _request_key(self, request: DraftExportRequest) -> str:
        return f"{request.destination}:{request.requested_at.isoformat()}"

    def request_approval(self, request: DraftExportRequest) -> bool:
        """Present the export request and return True if user approves.

        Args:
            request: The export request to present for approval.

        Returns:
            True if the user approves, False otherwise.
        """
        key = self._request_key(request)
        if self._auto_approve:
            self._approved_requests.add(key)
            if self._metrics is not None:
                self._metrics.record(
                    MetricName.DRAFT_EXPORT_APPROVAL_RATE,
                    1.0,
                    unit="ratio",
                )
            return True

        response = input(
            f"Export draft to '{request.destination}'? [y/N]: "
        ).strip().lower()
        approved = response in {"y", "yes"}
        if approved:
            self._approved_requests.add(key)
        if self._metrics is not None:
            self._metrics.record(
                MetricName.DRAFT_EXPORT_APPROVAL_RATE,
                1.0 if approved else 0.0,
                unit="ratio",
            )
        return approved

    def execute_export(self, request: DraftExportRequest) -> DraftExportResult:
        """Execute the export after approval.

        Must not be called without prior approval.

        Args:
            request: The approved export request.

        Returns:
            DraftExportResult with success/failure status.
        """
        key = self._request_key(request)
        if key not in self._approved_requests:
            return DraftExportResult(
                success=False,
                destination=request.destination,
                approved=False,
                error_message="Approval required before export",
            )

        try:
            request.destination.parent.mkdir(parents=True, exist_ok=True)
            request.destination.write_text(request.draft.content, encoding="utf-8")
            return DraftExportResult(
                success=True,
                destination=request.destination,
                approved=True,
                exported_at=datetime.now(),
            )
        except OSError as exc:
            return DraftExportResult(
                success=False,
                destination=request.destination,
                approved=True,
                error_message=str(exc),
            )
