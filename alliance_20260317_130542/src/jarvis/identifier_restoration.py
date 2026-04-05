"""Data-driven identifier restoration for spoken developer queries.

Builds a local lexicon from the knowledge base, scores ASR output against that
lexicon, and rewrites retrieval queries by appending high-confidence anchors.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher
from functools import lru_cache
import json
import re
from pathlib import Path

_CODE_EXTENSIONS = {".py", ".ts", ".tsx", ".js", ".jsx", ".sql"}
_IDENTIFIER_RE = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]{2,}\b")
_CLASS_DEF_RE = re.compile(r"^\s*class\s+([A-Za-z_][A-Za-z0-9_]*)", re.MULTILINE)
_FUNC_DEF_RE = re.compile(r"^\s*def\s+([A-Za-z_][A-Za-z0-9_]*)", re.MULTILINE)
_CAMEL_SPLIT_RE = re.compile(r"(?<!^)(?=[A-Z])")
_QUERY_TOKEN_RE = re.compile(r"[0-9A-Za-z가-힣_.-]+")
_ASCII_IDENTIFIER_HINT_RE = re.compile(r"\b[A-Za-z_][A-Za-z0-9_.-]{2,}\b")
_MAX_FILES = 80
_MAX_FILE_BYTES = 256_000
_MAX_REWRITE_CANDIDATES = 4
_MAX_SYMBOL_ENTRIES = 80

_CHOSEONG = ["g", "kk", "n", "d", "tt", "r", "m", "b", "pp", "s", "ss", "", "j", "jj", "ch", "k", "t", "p", "h"]
_JUNGSEONG = [
    "a", "ae", "ya", "yae", "eo", "e", "yeo", "ye", "o", "wa", "wae", "oe",
    "yo", "u", "wo", "we", "wi", "yu", "eu", "ui", "i",
]
_JONGSEONG = ["", "k", "k", "ks", "n", "nj", "nh", "t", "l", "lk", "lm", "lb", "ls", "lt", "lp", "lh", "m", "p", "ps", "t", "t", "ng", "t", "t", "k", "t", "p", "h"]
_VOWELS = set("aeiouy")
_TYPE_HINTS: dict[str, tuple[str, ...]] = {
    "filename": ("파일", "소스", "문서", "파이썬", "파이선", "python", "source", "file"),
    "class": ("클래스", "타입", "객체", "class", "model"),
    "function": ("함수", "메서드", "메소드", "호출", "function", "method"),
    "symbol": ("변수", "필드", "속성", "값", "identifier", "symbol"),
}


@dataclass(frozen=True)
class IdentifierEntry:
    canonical: str
    kind: str
    path: str = ""
    aliases: tuple[str, ...] = ()
    tokens: tuple[str, ...] = ()


@dataclass(frozen=True)
class IdentifierCandidate:
    canonical: str
    kind: str
    score: float
    evidence: tuple[str, ...] = ()


@dataclass(frozen=True)
class VoiceQuerySample:
    query: str
    expected_identifiers: tuple[str, ...] = ()


@dataclass(frozen=True)
class IdentifierRewrite:
    original_query: str
    rewritten_query: str
    candidates: tuple[IdentifierCandidate, ...] = ()
    appended_terms: tuple[str, ...] = ()


def rewrite_query_with_identifiers(
    query: str,
    *,
    knowledge_base_path: Path | None = None,
    max_candidates: int = _MAX_REWRITE_CANDIDATES,
) -> IdentifierRewrite:
    """Append high-confidence identifier anchors while preserving the original text."""
    lexicon = build_identifier_lexicon(knowledge_base_path)
    if not query.strip() or not lexicon:
        return IdentifierRewrite(original_query=query, rewritten_query=query)

    candidates = score_identifier_candidates(query, lexicon, limit=max_candidates)
    if not candidates:
        return IdentifierRewrite(original_query=query, rewritten_query=query)

    lowered_query = query.lower()
    appended_terms: list[str] = []
    for candidate in candidates:
        for term in _candidate_terms(candidate):
            if term in query:
                continue
            if term.lower() == term and term.lower() in lowered_query:
                continue
            if term in appended_terms:
                continue
            appended_terms.append(term)
            lowered_query += f" {term.lower()}"

    rewritten = query if not appended_terms else f"{query} {' '.join(appended_terms)}"
    return IdentifierRewrite(
        original_query=query,
        rewritten_query=rewritten,
        candidates=tuple(candidates),
        appended_terms=tuple(appended_terms),
    )


def score_identifier_candidates(
    query: str,
    lexicon: tuple[IdentifierEntry, ...],
    *,
    limit: int = _MAX_REWRITE_CANDIDATES,
) -> tuple[IdentifierCandidate, ...]:
    """Generate and rank identifier candidates against ASR output."""
    if not query.strip() or not lexicon:
        return ()

    query_tokens = _tokenize_query(query)
    query_forms = _build_query_forms(query_tokens)
    category_hints = _detect_category_hints(query)
    hinted_kinds = {
        kind for kind, boost in category_hints.items()
        if boost > 0.0
    }
    restrict_symbol_matching = "class" in hinted_kinds or "function" in hinted_kinds
    candidates: list[IdentifierCandidate] = []

    for entry in lexicon:
        if hinted_kinds and entry.kind not in hinted_kinds and entry.kind != "filename":
            if entry.kind != "symbol" or restrict_symbol_matching:
                continue
        if restrict_symbol_matching and entry.kind == "symbol":
            continue
        phrase_score = _best_phrase_score(query_forms, entry.aliases or (entry.canonical,))
        token_score = _token_match_score(query_forms, entry.tokens or _split_identifier(entry.canonical))
        score = max(phrase_score, token_score)
        if score <= 0.0:
            continue
        score += category_hints.get(entry.kind, 0.0)
        if entry.kind == "filename" and "." in query:
            score += 0.05
        if entry.kind == "filename" and phrase_score >= 0.58:
            score += 0.10
        if entry.kind == "filename" and ("점" in query or "닷" in query):
            score += 0.06
        if token_score >= 0.55 and len(entry.tokens) > 1:
            score += 0.08
        if score < 0.68:
            continue
        candidates.append(IdentifierCandidate(
            canonical=entry.canonical,
            kind=entry.kind,
            score=min(score, 1.0),
            evidence=tuple(entry.tokens[:3] or (entry.canonical,)),
        ))

    has_code_anchor = _query_has_code_anchor(query, category_hints=category_hints)
    if not has_code_anchor:
        has_strong_code_context = any(
            candidate.kind in {"filename", "class", "function"} and candidate.score >= 0.82
            for candidate in candidates
        )
        filtered: list[IdentifierCandidate] = []
        for candidate in candidates:
            if candidate.kind == "symbol" and not has_strong_code_context:
                continue
            if (
                candidate.kind in {"filename", "class", "function"}
                and candidate.score < 0.82
            ):
                continue
            filtered.append(candidate)
        candidates = filtered

    ranked = sorted(candidates, key=lambda item: (item.score, len(item.canonical)), reverse=True)
    deduped: list[IdentifierCandidate] = []
    seen: set[tuple[str, str]] = set()
    for candidate in ranked:
        key = (candidate.canonical.lower(), candidate.kind)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
        if len(deduped) >= limit:
            break
    return tuple(deduped)


def build_identifier_lexicon(knowledge_base_path: Path | None) -> tuple[IdentifierEntry, ...]:
    """Build a reusable identifier lexicon from local code files."""
    if knowledge_base_path is None:
        return ()
    root = knowledge_base_path.expanduser().resolve()
    if not root.exists():
        return ()
    return _build_identifier_lexicon_cached(str(root))


def load_voice_query_samples(path: Path) -> tuple[VoiceQuerySample, ...]:
    """Load a small evaluation set for spoken-code retrieval regressions."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    return tuple(
        VoiceQuerySample(
            query=str(item["query"]),
            expected_identifiers=tuple(str(value) for value in item.get("expected_identifiers", [])),
        )
        for item in raw
    )


@lru_cache(maxsize=8)
def _build_identifier_lexicon_cached(root_value: str) -> tuple[IdentifierEntry, ...]:
    root = Path(root_value)
    entries: list[IdentifierEntry] = []
    seen: set[tuple[str, str]] = set()
    symbol_count = 0

    for path in sorted(root.rglob("*")):
        if len(entries) >= 400:
            break
        if not path.is_file() or path.suffix.lower() not in _CODE_EXTENSIONS:
            continue
        try:
            if path.stat().st_size > _MAX_FILE_BYTES:
                continue
        except OSError:
            continue

        relative_path = path.relative_to(root).as_posix()
        _add_entry(entries, seen, path.name, "filename", relative_path)
        _add_entry(entries, seen, path.stem, "filename", relative_path)

        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue

        for match in _CLASS_DEF_RE.findall(text):
            _add_entry(entries, seen, match, "class", relative_path)
        for match in _FUNC_DEF_RE.findall(text):
            _add_entry(entries, seen, match, "function", relative_path)
        for match in _IDENTIFIER_RE.findall(text):
            if symbol_count >= _MAX_SYMBOL_ENTRIES:
                break
            if not _is_interesting_symbol(match):
                continue
            before = len(entries)
            _add_entry(entries, seen, match, "symbol", relative_path)
            if len(entries) > before:
                symbol_count += 1

        if len(entries) >= 400 or len(seen) >= _MAX_FILES * 20:
            break

    return tuple(entries)


def _add_entry(
    entries: list[IdentifierEntry],
    seen: set[tuple[str, str]],
    canonical: str,
    kind: str,
    path: str,
) -> None:
    cleaned = canonical.strip()
    if len(cleaned) < 3:
        return
    key = (cleaned.lower(), kind)
    if key in seen:
        return
    seen.add(key)
    tokens = tuple(token for token in _split_identifier(cleaned) if len(token) >= 2)
    aliases = _build_aliases(cleaned, tokens)
    entries.append(IdentifierEntry(
        canonical=cleaned,
        kind=kind,
        path=path,
        aliases=aliases,
        tokens=tokens,
    ))


def _build_aliases(canonical: str, tokens: tuple[str, ...]) -> tuple[str, ...]:
    aliases: list[str] = [canonical]
    if tokens:
        aliases.append(" ".join(tokens))
        aliases.append("".join(tokens))
    if "." in canonical:
        aliases.append(canonical.rsplit(".", 1)[0])
    return tuple(dict.fromkeys(alias for alias in aliases if alias))


def _candidate_terms(candidate: IdentifierCandidate) -> tuple[str, ...]:
    terms = [candidate.canonical]
    if candidate.kind == "filename" and "." in candidate.canonical:
        terms.append(candidate.canonical.rsplit(".", 1)[0])
    return tuple(dict.fromkeys(terms))


def _detect_category_hints(query: str) -> dict[str, float]:
    lowered = query.lower()
    hints = {kind: 0.0 for kind in _TYPE_HINTS}
    for kind, words in _TYPE_HINTS.items():
        if any(word.lower() in lowered for word in words):
            hints[kind] += 0.16
    return hints


def _query_has_code_anchor(query: str, *, category_hints: dict[str, float] | None = None) -> bool:
    if _ASCII_IDENTIFIER_HINT_RE.search(query):
        return True
    hints = category_hints if category_hints is not None else _detect_category_hints(query)
    return any(boost > 0.0 for boost in hints.values())


def _best_phrase_score(query_forms: tuple[str, ...], aliases: tuple[str, ...]) -> float:
    best = 0.0
    for alias in aliases:
        alias_forms = _forms_for_text(alias)
        for query_form in query_forms:
            for alias_form in alias_forms:
                best = max(best, _similarity(query_form, alias_form))
    return best


def _token_match_score(query_forms: tuple[str, ...], tokens: tuple[str, ...]) -> float:
    if not tokens:
        return 0.0
    token_scores: list[float] = []
    for token in tokens[:4]:
        token_forms = _forms_for_text(token)
        best = 0.0
        for query_form in query_forms:
            for token_form in token_forms:
                best = max(best, _similarity(query_form, token_form))
        token_scores.append(best)
    if not token_scores:
        return 0.0
    average = sum(token_scores) / len(token_scores)
    if len(tokens) > 1 and min(token_scores) >= 0.46:
        average += 0.08
    return average


def _tokenize_query(query: str) -> list[str]:
    tokens: list[str] = []
    for token in _QUERY_TOKEN_RE.findall(query):
        stripped = _strip_korean_suffixes(token.strip())
        if stripped:
            tokens.append(stripped)
    return tokens


def _build_query_forms(tokens: list[str]) -> tuple[str, ...]:
    forms: list[str] = []
    seen: set[str] = set()
    for size in range(1, min(4, len(tokens)) + 1):
        for index in range(0, len(tokens) - size + 1):
            span = " ".join(tokens[index:index + size])
            for form in _forms_for_text(span):
                if form and form not in seen:
                    seen.add(form)
                    forms.append(form)
    return tuple(forms)


def _forms_for_text(text: str) -> tuple[str, ...]:
    cleaned = re.sub(r"[^0-9A-Za-z가-힣]+", "", text).lower()
    if not cleaned:
        return ()
    forms: list[str] = [cleaned]
    if _contains_hangul(cleaned):
        romanized = _romanize_hangul_text(cleaned)
        if romanized:
            forms.append(romanized)
            forms.append(_consonant_skeleton(romanized))
    else:
        forms.append(_consonant_skeleton(cleaned))
    return tuple(dict.fromkeys(form for form in forms if form))


def _split_identifier(value: str) -> tuple[str, ...]:
    base = value.rsplit(".", 1)[0]
    spaced = base.replace("_", " ").replace("-", " ")
    parts: list[str] = []
    for chunk in spaced.split():
        parts.extend(_CAMEL_SPLIT_RE.sub(" ", chunk).split())
    normalized = [part.lower() for part in parts if len(part) >= 2]
    return tuple(dict.fromkeys(normalized))


def _is_interesting_symbol(value: str) -> bool:
    if len(value) < 3 or len(value) > 48:
        return False
    if value.startswith("_") and not value.startswith("__"):
        return False
    if "_" in value:
        return True
    return any(char.isupper() for char in value[1:])


def _strip_korean_suffixes(token: str) -> str:
    stripped = token.strip(".,?!;:()[]{}\"'")
    suffixes = (
        "이라는", "라는", "에서", "으로", "중에", "중", "파일", "소스", "클래스",
        "함수", "메서드", "메소드", "가", "이", "은", "는", "을", "를", "의",
    )
    for suffix in suffixes:
        if stripped.endswith(suffix) and len(stripped) > len(suffix) + 1:
            stripped = stripped[: -len(suffix)]
            break
    return stripped


def _similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    if len(left) >= 4 and len(right) >= 4 and (left in right or right in left):
        return 0.92
    direct = SequenceMatcher(None, left, right).ratio()
    skeleton = SequenceMatcher(None, _consonant_skeleton(left), _consonant_skeleton(right)).ratio()
    return max(direct, skeleton * 0.94)


def _contains_hangul(value: str) -> bool:
    return any("가" <= char <= "힣" for char in value)


def _consonant_skeleton(value: str) -> str:
    letters = [char for char in value if char.isalnum()]
    skeleton = "".join(char for char in letters if char.lower() not in _VOWELS)
    return skeleton or "".join(letters[:4])


def _romanize_hangul_text(text: str) -> str:
    parts: list[str] = []
    for char in text:
        if "가" <= char <= "힣":
            parts.append(_romanize_hangul_syllable(char))
        elif char.isalnum():
            parts.append(char.lower())
    return "".join(parts)


def _romanize_hangul_syllable(char: str) -> str:
    code = ord(char) - 0xAC00
    if code < 0 or code > 11171:
        return char.lower()
    choseong = code // 588
    jungseong = (code % 588) // 28
    jongseong = code % 28
    return _CHOSEONG[choseong] + _JUNGSEONG[jungseong] + _JONGSEONG[jongseong]
