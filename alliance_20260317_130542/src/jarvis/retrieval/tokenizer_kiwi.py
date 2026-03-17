"""KiwiTokenizer — Korean morphological tokenizer wrapper.

Wraps the Kiwi tokenizer for Korean text segmentation,
producing tokens suitable for FTS5 indexing.
"""

from __future__ import annotations

import os
import warnings


class KiwiTokenizer:
    """Korean morphological tokenizer using Kiwi."""

    def __init__(self) -> None:
        # Suppress Kiwi's "Quantization is not supported" stderr warning
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            _stderr = os.dup(2)
            _devnull = os.open(os.devnull, os.O_WRONLY)
            os.dup2(_devnull, 2)
            try:
                from kiwipiepy import Kiwi
                self._kiwi = Kiwi()
            finally:
                os.dup2(_stderr, 2)
                os.close(_stderr)
                os.close(_devnull)

    # POS tags for content words (nouns, verbs, adjectives, adverbs)
    # NNG=일반명사, NNP=고유명사, NNB=의존명사, NR=수사, SN=숫자
    # VV=동사, VA=형용사, MAG=일반부사
    # SL=외국어, SH=한자, SW=기호
    _CONTENT_POS = frozenset({
        "NNG", "NNP", "NNB", "NR", "SN",
        "VV", "VA", "MAG",
        "SL", "SH",
    })

    def tokenize(self, text: str) -> list[str]:
        """Tokenize text, returning all morphemes."""
        if not text.strip():
            return []
        result = self._kiwi.tokenize(text)
        return [token.form for token in result if token.form.strip()]

    def tokenize_nouns(self, text: str) -> list[str]:
        """Tokenize text, returning only content words (nouns, verbs, etc.).

        Filters out particles, endings, and punctuation for better
        FTS query precision.
        """
        if not text.strip():
            return []
        result = self._kiwi.tokenize(text)
        return [
            token.form for token in result
            if token.tag in self._CONTENT_POS and token.form.strip()
        ]

    def tokenize_for_fts(self, text: str) -> str:
        """Tokenize for FTS indexing (all morphemes for recall)."""
        tokens = self.tokenize(text)
        return " ".join(tokens)
