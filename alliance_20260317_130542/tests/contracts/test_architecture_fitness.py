"""Architecture fitness tests — detect layer boundary violations.

Invariant #8:
- tools/ must not call runtime/ directly
- runtime/ must not depend on cli/
- retrieval/ must not depend on draft_export
"""

from __future__ import annotations

import ast
import os
from pathlib import Path

import pytest

SRC_ROOT = Path(__file__).parent.parent.parent / "src" / "jarvis"


def _get_imports_from_file(filepath: Path) -> set[str]:
    """Extract all import module names from a Python file."""
    try:
        source = filepath.read_text()
        tree = ast.parse(source, filename=str(filepath))
    except (SyntaxError, UnicodeDecodeError):
        return set()

    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.add(node.module)
    return imports


def _get_all_imports_in_package(package_dir: Path) -> set[str]:
    """Collect all imports across all .py files in a package directory."""
    all_imports: set[str] = set()
    if not package_dir.exists():
        return all_imports
    for py_file in package_dir.rglob("*.py"):
        all_imports.update(_get_imports_from_file(py_file))
    return all_imports


class TestLayerBoundaries:
    """Invariant #8: Layer boundary violations are forbidden."""

    def test_tools_does_not_import_runtime(self) -> None:
        """tools/ must not call runtime/ directly."""
        tools_imports = _get_all_imports_in_package(SRC_ROOT / "tools")
        runtime_modules = {
            "jarvis.runtime",
            "jarvis.runtime.mlx_runtime",
            "jarvis.runtime.model_router",
            "jarvis.runtime.embedding_runtime",
        }
        violations = tools_imports & runtime_modules
        assert not violations, f"tools/ imports runtime/ modules: {violations}"

    def test_runtime_does_not_import_cli(self) -> None:
        """runtime/ must not depend on cli/."""
        runtime_imports = _get_all_imports_in_package(SRC_ROOT / "runtime")
        cli_modules = {
            "jarvis.cli",
            "jarvis.cli.repl",
            "jarvis.cli.approval",
        }
        violations = runtime_imports & cli_modules
        assert not violations, f"runtime/ imports cli/ modules: {violations}"

    def test_retrieval_does_not_import_draft_export(self) -> None:
        """retrieval/ must not depend on draft_export."""
        retrieval_imports = _get_all_imports_in_package(SRC_ROOT / "retrieval")
        draft_modules = {
            "jarvis.tools.draft_export",
            "jarvis.tools",
        }
        violations = retrieval_imports & draft_modules
        assert not violations, f"retrieval/ imports draft_export: {violations}"
