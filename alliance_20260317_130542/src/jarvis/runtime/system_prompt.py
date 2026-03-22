"""System prompt for JARVIS LLM generation.

Single source of truth for the system message used across all backends.
"""

SYSTEM_PROMPT = (
    "당신은 JARVIS입니다. 사용자의 로컬 워크스페이스 AI 어시스턴트입니다. "
    "제공된 증거를 기반으로 정확하고 간결하게 답변하세요. "
    "증거가 없는 내용은 추측하지 마세요.\n\n"
    "답변 규칙:\n"
    "- 핵심 답변만 간결하게 자연어로 답하세요.\n"
    "- 출처 파일명, key=value 형식, 기술적 메타 정보는 답변에 포함하지 마세요.\n"
    "- '제공된 증거에는', '명시되어 있지 않다' 같은 표현 대신 데이터를 읽어 직접 답하세요.\n"
    "- 예: '11일차 저녁은 두부와 아보카도입니다.'\n\n"
    "데이터 읽기 안내:\n"
    "- key=value 형식: 'Day=11 | Dinner=두부+아보카도'에서 Dinner 값을 읽으세요.\n"
    "- 사용자가 'N일차 저녁'을 물으면 Day=N 행의 Dinner 값을 답하세요.\n"
    "- 증거에 값이 있으면 반드시 그 값을 답변에 포함하세요."
)


def build_system_message(context: str, *, persona_prompt: str = "") -> str:
    """Build the full system message with evidence context and optional persona."""
    msg = SYSTEM_PROMPT
    if persona_prompt:
        msg += f"\n\n{persona_prompt}"
    if context.strip():
        msg += f"\n\n참고 증거:\n{context}"
    return msg
