"""SearchFilesTool — searches for files matching a query within allowed scope.

One of the 3 Phase 1 tools (ToolName.SEARCH_FILES).
Uses the retrieval pipeline to find relevant documents.
"""

from __future__ import annotations

from pathlib import Path

from jarvis.contracts import SearchHit
from jarvis.tools.read_file import ReadFileTool


class SearchFilesTool:
    """Searches for files matching a query within allowed paths.

    Delegates to the retrieval layer for actual search logic.
    """

    def __init__(self, *, allowed_roots: list[Path] | None = None) -> None:
        """Initialize with allowed root directories.

        Args:
            allowed_roots: Directories the tool is permitted to search within.
        """
        self._allowed_roots = allowed_roots or []
        self._reader = ReadFileTool(allowed_roots=self._allowed_roots)

    def execute(self, *, query: str, top_k: int = 5) -> list[SearchHit]:
        """Search for files matching a query.

        Args:
            query: The search query string.
            top_k: Maximum number of results to return.

        Returns:
            List of SearchHit typed results.

        """
        normalized = query.strip().lower()
        if not normalized:
            return []

        terms = [term for term in normalized.split() if term]
        hits: list[SearchHit] = []

        for root in self._allowed_roots:
            for path in root.rglob("*"):
                if not path.is_file() or path.name.startswith("."):
                    continue

                score = 0.0
                snippet = str(path)
                haystack = str(path).lower()

                for term in terms:
                    if term in path.name.lower():
                        score += 5.0
                    elif term in haystack:
                        score += 2.0

                try:
                    content = self._reader.execute(path=str(path))
                except Exception:
                    content = ""

                if content:
                    lower_content = content.lower()
                    for term in terms:
                        if term in lower_content:
                            score += 1.0
                            if snippet == str(path):
                                for line in content.splitlines():
                                    if term in line.lower():
                                        snippet = line.strip()[:200]
                                        break

                if score > 0.0:
                    path_str = str(path)
                    hits.append(SearchHit(
                        chunk_id=path_str,
                        document_id=path_str,
                        score=score,
                        snippet=snippet,
                    ))

        hits.sort(key=lambda hit: hit.score, reverse=True)
        return hits[:top_k]
