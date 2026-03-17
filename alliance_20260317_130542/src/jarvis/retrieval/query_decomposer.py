"""QueryDecomposer — decomposes user queries into typed fragments."""
from __future__ import annotations

import re

from jarvis.contracts import TypedQueryFragment

_KOREAN_RE = re.compile(r"[\uac00-\ud7af\u1100-\u11ff\u3130-\u318f]+")
_CODE_RE = re.compile(
    r"(?:def |class |import |from |function |const |let |var |=>|->|\(\)|\.py|\.ts|\.js)"
)


def _detect_language(text: str) -> str:
    if _CODE_RE.search(text):
        return "code"
    korean_chars = len(_KOREAN_RE.findall(text))
    ascii_words = len(re.findall(r"[a-zA-Z]+", text))
    if korean_chars > ascii_words:
        return "ko"
    if ascii_words > 0 and korean_chars == 0:
        return "en"
    return "ko"


class QueryDecomposer:
    """Decomposes a user query into typed fragments for retrieval."""

    def decompose(self, query: str) -> list[TypedQueryFragment]:
        if not query.strip():
            return []

        language = _detect_language(query)
        return [
            TypedQueryFragment(
                text=query, language=language, query_type="keyword", weight=1.0,
            ),
            TypedQueryFragment(
                text=query, language=language, query_type="semantic", weight=0.7,
            ),
        ]
