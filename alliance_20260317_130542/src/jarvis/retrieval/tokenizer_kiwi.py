"""KiwiTokenizer — Korean morphological tokenizer wrapper.

Wraps the Kiwi tokenizer for Korean text segmentation,
producing tokens suitable for FTS5 indexing.
"""

from __future__ import annotations

from kiwipiepy import Kiwi


class KiwiTokenizer:
    """Korean morphological tokenizer using Kiwi."""

    def __init__(self) -> None:
        self._kiwi = Kiwi()

    def tokenize(self, text: str) -> list[str]:
        if not text.strip():
            return []
        result = self._kiwi.tokenize(text)
        return [token.form for token in result if token.form.strip()]

    def tokenize_for_fts(self, text: str) -> str:
        tokens = self.tokenize(text)
        return " ".join(tokens)
