"""SearchFilesTool — searches indexed files within the allowed scope.

One of the 3 Phase 1 tools (ToolName.SEARCH_FILES).
Prefers the indexed document/chunk store when available and falls back to
lightweight path-name matching when the retrieval DB is unavailable.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from jarvis.contracts import SearchHit


class SearchFilesTool:
    """Searches for files matching a query within allowed paths."""

    def __init__(
        self,
        *,
        db: sqlite3.Connection | None = None,
        allowed_roots: list[Path] | None = None,
    ) -> None:
        """Initialize with allowed root directories.

        Args:
            db: Indexed retrieval database. When available, search uses it.
            allowed_roots: Directories the tool is permitted to search within.
        """
        self._db = db
        self._allowed_roots = allowed_roots or []

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
        if not terms:
            return []

        if self._db is not None:
            return self._search_indexed_files(terms=terms, top_k=top_k)
        return self._search_paths_only(terms=terms, top_k=top_k)

    def _search_indexed_files(self, *, terms: list[str], top_k: int) -> list[SearchHit]:
        if self._db is None:
            return []

        rows = self._db.execute(
            "SELECT d.path, c.chunk_id, c.text"
            " FROM documents d"
            " LEFT JOIN chunks c ON d.document_id = c.document_id"
            " WHERE d.indexing_status = 'INDEXED'"
            " ORDER BY d.path ASC"
        ).fetchall()

        hits_by_path: dict[str, SearchHit] = {}
        for path_str, chunk_id, text in rows:
            if not self._is_allowed_path(path_str):
                continue

            score = 0.0
            snippet = path_str
            path_lower = path_str.lower()
            name_lower = Path(path_str).name.lower()
            text_lower = text.lower() if text else ""

            for term in terms:
                if term in name_lower:
                    score += 5.0
                elif term in path_lower:
                    score += 2.0
                if term in text_lower:
                    score += 1.0
                    if snippet == path_str:
                        snippet = self._snippet_from_text(text, term) or path_str

            if score <= 0.0:
                continue

            existing = hits_by_path.get(path_str)
            hit = SearchHit(
                chunk_id=chunk_id or path_str,
                document_id=path_str,
                score=score,
                snippet=snippet,
            )
            if existing is None or hit.score > existing.score:
                hits_by_path[path_str] = hit

        hits = sorted(hits_by_path.values(), key=lambda hit: hit.score, reverse=True)
        return hits[:top_k]

    def _search_paths_only(self, *, terms: list[str], top_k: int) -> list[SearchHit]:
        hits: list[SearchHit] = []
        for root in self._allowed_roots:
            for path in root.rglob("*"):
                if not path.is_file() or path.name.startswith("."):
                    continue

                score = 0.0
                haystack = str(path).lower()
                name_lower = path.name.lower()
                for term in terms:
                    if term in name_lower:
                        score += 5.0
                    elif term in haystack:
                        score += 2.0

                if score > 0.0:
                    path_str = str(path)
                    hits.append(SearchHit(
                        chunk_id=path_str,
                        document_id=path_str,
                        score=score,
                        snippet=path_str,
                    ))

        hits.sort(key=lambda hit: hit.score, reverse=True)
        return hits[:top_k]

    def _is_allowed_path(self, path_str: str) -> bool:
        if not self._allowed_roots:
            return True
        path = Path(path_str).resolve()
        for root in self._allowed_roots:
            resolved_root = root.resolve()
            if path == resolved_root or resolved_root in path.parents:
                return True
        return False

    def _snippet_from_text(self, text: str, term: str) -> str:
        for line in text.splitlines():
            if term in line.lower():
                return line.strip()[:200]
        return text.strip()[:200]
