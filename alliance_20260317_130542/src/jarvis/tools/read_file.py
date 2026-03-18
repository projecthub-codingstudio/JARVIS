"""ReadFileTool — reads file contents within allowed scope.

One of the 3 Phase 1 tools (ToolName.READ_FILE).
Respects path scope restrictions enforced by the governor.
"""

from __future__ import annotations

from pathlib import Path

from jarvis.contracts import AccessError, ErrorCode, ToolError

_TEXT_ENCODINGS = ("utf-8", "utf-8-sig", "cp949", "euc-kr", "utf-16", "latin-1")


class ReadFileTool:
    """Reads file contents from allowed paths.

    Must only access paths within configured watched_folders.
    """

    def __init__(self, *, allowed_roots: list[Path] | None = None) -> None:
        """Initialize with allowed root directories.

        Args:
            allowed_roots: Directories the tool is permitted to read from.
        """
        self._allowed_roots = allowed_roots or []

    def execute(self, *, path: str) -> str:
        """Read and return the contents of a file.

        Args:
            path: Absolute path to the file to read.

        Returns:
            The file contents as a string.

        """
        file_path = Path(path).expanduser().resolve()
        if not self._validate_path(file_path):
            raise AccessError(ErrorCode.PATH_OUTSIDE_SCOPE, f"Path outside scope: {file_path}")
        if not file_path.exists() or not file_path.is_file():
            raise ToolError(ErrorCode.TOOL_EXECUTION_FAILED, f"File not found: {file_path}")

        raw = file_path.read_bytes()
        for encoding in _TEXT_ENCODINGS:
            try:
                return raw.decode(encoding)
            except UnicodeDecodeError:
                continue

        raise ToolError(
            ErrorCode.TOOL_EXECUTION_FAILED,
            f"Unable to decode file as text: {file_path}",
        )

    def _validate_path(self, path: Path) -> bool:
        """Check that the path is within allowed roots.

        Args:
            path: Path to validate.

        Returns:
            True if the path is within an allowed root.

        """
        try:
            resolved = path.resolve()
        except OSError:
            return False

        for root in self._allowed_roots:
            try:
                resolved.relative_to(root.expanduser().resolve())
                return True
            except ValueError:
                continue
        return False
