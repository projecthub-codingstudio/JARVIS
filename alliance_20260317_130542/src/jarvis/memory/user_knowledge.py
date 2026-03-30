"""UserKnowledgeStore — Tier 3 memory for extracted user preferences and knowledge.

Stores user-specific information extracted from conversations:
  - Role/expertise (e.g., "Python developer", "data scientist")
  - Preferences (e.g., "prefers Korean responses", "uses MLX")
  - Project context (e.g., "working on JARVIS", "uses M1 Max")
  - Named entities (e.g., people, tools, frameworks)

Knowledge is extracted via pattern matching after each turn and
injected into the LLM system prompt for personalized responses.
"""
from __future__ import annotations

import logging
import re
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class UserKnowledge:
    """A piece of extracted user knowledge."""

    knowledge_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    category: str = "general"
    key: str = ""
    value: str = ""
    confidence: float = 0.5
    source_turn: str = ""
    created_at: datetime = field(default_factory=datetime.now)


class UserKnowledgeStore:
    """Persistent storage for user knowledge (Tier 3 memory)."""

    def __init__(self, *, db: sqlite3.Connection | None = None) -> None:
        self._db = db
        self._cache: dict[str, UserKnowledge] = {}  # category:key → knowledge
        if db is not None:
            self._load_cache()

    def _load_cache(self) -> None:
        if self._db is None:
            return
        try:
            rows = self._db.execute(
                "SELECT knowledge_id, category, key, value, confidence, source_turn"
                " FROM user_knowledge ORDER BY updated_at DESC"
            ).fetchall()
            for row in rows:
                k = UserKnowledge(
                    knowledge_id=row[0], category=row[1], key=row[2],
                    value=row[3], confidence=row[4], source_turn=row[5] or "",
                )
                self._cache[f"{k.category}:{k.key}"] = k
        except sqlite3.OperationalError:
            pass  # Table may not exist yet

    def upsert(self, knowledge: UserKnowledge) -> None:
        """Insert or update a knowledge entry (upsert by category+key)."""
        cache_key = f"{knowledge.category}:{knowledge.key}"
        self._cache[cache_key] = knowledge
        if self._db is not None:
            try:
                self._db.execute(
                    "INSERT INTO user_knowledge"
                    " (knowledge_id, category, key, value, confidence, source_turn, updated_at)"
                    " VALUES (?, ?, ?, ?, ?, ?, datetime('now'))"
                    " ON CONFLICT(category, key) DO UPDATE SET"
                    " value=excluded.value, confidence=excluded.confidence,"
                    " source_turn=excluded.source_turn, updated_at=datetime('now')",
                    (knowledge.knowledge_id, knowledge.category, knowledge.key,
                     knowledge.value, knowledge.confidence, knowledge.source_turn),
                )
                self._db.commit()
            except sqlite3.OperationalError as exc:
                logger.debug("user_knowledge upsert failed: %s", exc)

    def get_all(self) -> list[UserKnowledge]:
        """Get all knowledge entries, sorted by confidence descending."""
        return sorted(self._cache.values(), key=lambda k: -k.confidence)

    def get_by_category(self, category: str) -> list[UserKnowledge]:
        return [k for k in self._cache.values() if k.category == category]

    def format_for_prompt(self, *, max_entries: int = 10) -> str:
        """Format user knowledge as a context block for the LLM prompt."""
        entries = self.get_all()[:max_entries]
        if not entries:
            return ""
        lines = ["[사용자 정보]"]
        for entry in entries:
            lines.append(f"- {entry.key}: {entry.value}")
        return "\n".join(lines)


# --- Knowledge Extraction ---

# Patterns for extracting user knowledge from conversation turns.
# Each pattern: (regex, category, key_template, value_group)

_ROLE_PATTERNS = [
    (re.compile(r"(?:나는|저는)\s+(.+?)\s*(?:입니다|이에요|이야|야)", re.IGNORECASE), "role", "직업/역할"),
    (re.compile(r"I(?:'m| am) (?:a |an )?(.+?)(?:\.|,|$)", re.IGNORECASE), "role", "role"),
]

_PREFERENCE_PATTERNS = [
    (re.compile(r"(?:한국어|영어|Korean|English)(?:로|로만|로\s+)?(?:답변|응답|대답)", re.IGNORECASE), "preference", "언어"),
    (re.compile(r"(?:항상|매번|늘)\s+(.+?)(?:해\s*줘|하세요|해주세요)", re.IGNORECASE), "preference", "습관"),
]

_CONTEXT_PATTERNS = [
    (re.compile(r"(?:MacBook|맥북|iMac|아이맥)\s*(Pro|Air|Max|M\d)?\s*(M\d\s*(?:Pro|Max|Ultra)?)?", re.IGNORECASE), "system", "하드웨어"),
    (re.compile(r"(?:사용|쓰고\s*있|using)\s+(.+?)(?:\s+(?:모델|프레임워크|라이브러리))", re.IGNORECASE), "tool", "도구"),
]


def extract_knowledge(user_input: str, assistant_output: str, *, turn_id: str = "") -> list[UserKnowledge]:
    """Extract user knowledge from a conversation turn using pattern matching.

    Returns a list of UserKnowledge entries found in the user's input.
    Only extracts from user_input (not assistant_output) to avoid
    attributing LLM-generated content as user knowledge.
    """
    results: list[UserKnowledge] = []

    for pattern, category, key_template in _ROLE_PATTERNS:
        match = pattern.search(user_input)
        if match:
            value = match.group(1).strip()
            if len(value) > 2:
                results.append(UserKnowledge(
                    category=category, key=key_template, value=value,
                    confidence=0.8, source_turn=turn_id,
                ))

    for pattern, category, key_template in _PREFERENCE_PATTERNS:
        match = pattern.search(user_input)
        if match:
            value = match.group(0).strip() if match.lastindex is None else match.group(1).strip()
            if len(value) > 2:
                results.append(UserKnowledge(
                    category=category, key=key_template, value=value,
                    confidence=0.6, source_turn=turn_id,
                ))

    for pattern, category, key_template in _CONTEXT_PATTERNS:
        match = pattern.search(user_input)
        if match:
            value = match.group(0).strip()
            if len(value) > 2:
                results.append(UserKnowledge(
                    category=category, key=key_template, value=value,
                    confidence=0.7, source_turn=turn_id,
                ))

    return results
