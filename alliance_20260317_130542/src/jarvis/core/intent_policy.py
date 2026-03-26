"""Intent policy dispatcher for frontend-facing execution overrides.

This module centralizes non-retrieval intent handling so frontend bridges do
not accumulate scattered string-based overrides. Query classification still
comes from Planner; this layer only maps classified intents to execution
policies.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from jarvis.core.planner import Planner, QueryAnalysis


@dataclass(frozen=True)
class IntentPolicy:
    intent: str
    mode: str
    response_text: str
    skill: str
    suggested_replies: tuple[str, ...]
    interaction_mode: str = "general_query"
    response_type: str = "plain_answer"
    primary_source_type: str = "none"
    source_profile: str = "none"


@dataclass(frozen=True)
class IntentPolicyResolution:
    analysis: QueryAnalysis
    policy: IntentPolicy | None


_MENU_INTENT_POLICIES: dict[str, IntentPolicy] = {
    "smalltalk": IntentPolicy(
        intent="smalltalk",
        mode="smalltalk",
        response_text="안녕하세요. 무엇을 도와드릴까요?",
        skill="conversation_support",
        suggested_replies=("오늘 일정", "문서 찾아줘", "무엇을 할 수 있어?"),
    ),
    "weather": IntentPolicy(
        intent="weather",
        mode="capability_gap",
        response_text=(
            "현재 메뉴바 로컬 서비스는 실시간 날씨 데이터에 연결되어 있지 않습니다. "
            "날씨 조회 기능을 붙이면 바로 알려드릴 수 있습니다."
        ),
        skill="capability_notice",
        suggested_replies=("날씨 기능 연결", "다른 질문 하기"),
    ),
}


def resolve_menu_intent_policy(
    query: str,
    *,
    knowledge_base_path: Path | None = None,
) -> IntentPolicyResolution:
    planner = Planner(knowledge_base_path=knowledge_base_path)
    analysis = planner.analyze(query)
    return IntentPolicyResolution(
        analysis=analysis,
        policy=_MENU_INTENT_POLICIES.get(analysis.intent),
    )
