"""QueryDecomposer — decomposes user queries into typed fragments.

Extracts structured intent from natural language queries:
  - Filename references (for targeted file search)
  - Search keywords (stripped of noise words)
  - Semantic text (for vector embedding)
"""
from __future__ import annotations

import re

from jarvis.contracts import TypedQueryFragment

_KOREAN_RE = re.compile(r"[\uac00-\ud7af\u1100-\u11ff\u3130-\u318f]+")
_CODE_RE = re.compile(
    r"(?:def |class |import |from |function |const |let |var |=>|->|\(\)|\.py|\.ts|\.js)"
)

# Matches filenames with extensions
_FILENAME_EXT_RE = re.compile(
    r"([\w.-]+\.(?:py|ts|tsx|js|jsx|sql|md|txt|json|yaml|yml|csv|docx|pptx|xlsx|pdf|hwp|hwpx))"
)

# Matches underscore/hyphen-separated multi-word identifiers (likely filenames without extension)
# e.g., "14day_diet_supplements_final", "project-config-v2"
_FILENAME_STEM_RE = re.compile(r"\b([a-zA-Z0-9][\w]*(?:[_-][\w]+){2,})\b")

# Korean noise words to strip from search keywords
_KO_STOPWORDS = {
    "에서", "에", "의", "를", "을", "이", "가", "은", "는", "와", "과",
    "로", "으로", "도", "만", "까지", "부터", "에게", "한테", "에서는",
    "무엇인가요", "무엇이에요", "무엇이야", "뭐야", "뭐에요", "뭔가요",
    "알려줘", "알려주세요", "보여줘", "보여주세요", "찾아줘", "찾아주세요",
    "설명해줘", "설명해주세요", "뭐야", "뭐예요",
    "어떤", "어떻게", "무슨", "몇",
}

# English noise words
_EN_STOPWORDS = {"what", "is", "the", "a", "an", "in", "of", "for", "and", "or", "from", "to", "how"}


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


def _extract_filenames(query: str) -> list[str]:
    """Extract filename references from the query."""
    filenames: list[str] = []

    # With extension: "pipeline.py", "14day_diet.xlsx"
    for m in _FILENAME_EXT_RE.findall(query):
        filenames.append(m)

    # Without extension: "14day_diet_supplements_final"
    for m in _FILENAME_STEM_RE.findall(query):
        if m not in filenames:
            filenames.append(m)

    return filenames


def _extract_keywords(query: str, filenames: list[str]) -> str:
    """Extract clean search keywords by removing filenames and noise words."""
    text = query

    # Remove filename references from the text
    for fn in filenames:
        text = text.replace(fn, " ")

    # Also try space-separated version of underscore filenames
    for fn in filenames:
        space_version = fn.replace("_", " ").replace("-", " ")
        text = text.replace(space_version, " ")

    # Split into words and filter
    words = text.split()
    clean_words: list[str] = []
    for word in words:
        w = word.strip(",.?!;:()[]{}\"'")
        if not w or len(w) <= 1:
            continue
        if w.lower() in _KO_STOPWORDS or w.lower() in _EN_STOPWORDS:
            continue
        clean_words.append(w)

    return " ".join(clean_words)


class QueryDecomposer:
    """Decomposes a user query into typed fragments for retrieval.

    Separates filename references from search keywords and produces
    targeted fragments for more precise retrieval.
    """

    def decompose(self, query: str) -> list[TypedQueryFragment]:
        if not query.strip():
            return []

        language = _detect_language(query)
        filenames = _extract_filenames(query)
        keywords = _extract_keywords(query, filenames)

        fragments: list[TypedQueryFragment] = []

        # Keyword fragment: cleaned search terms (highest priority for FTS)
        if keywords.strip():
            kw_lang = _detect_language(keywords) if keywords.strip() else language
            fragments.append(TypedQueryFragment(
                text=keywords, language=kw_lang, query_type="keyword", weight=1.0,
            ))

        # Semantic fragment: full query for vector embedding (captures intent)
        fragments.append(TypedQueryFragment(
            text=query, language=language, query_type="semantic", weight=0.7,
        ))

        # If no keywords were extracted, add full query as keyword too
        if not keywords.strip():
            fragments.append(TypedQueryFragment(
                text=query, language=language, query_type="keyword", weight=1.0,
            ))

        return fragments
