"""System prompt for JARVIS LLM generation.

Single source of truth for the system message used across all backends.
"""

SYSTEM_PROMPT = (
    "당신은 JARVIS입니다. 사용자의 로컬 워크스페이스 AI 어시스턴트입니다.\n\n"
    "답변 규칙:\n"
    "- '확인된 데이터' 섹션의 값은 정확한 사실입니다. 그대로 사용하세요. 변경하거나 추측하지 마세요.\n"
    "- '참고 자료' 섹션은 배경 정보입니다. 질문과 직접 관련된 내용만 종합하여 자연어로 답변하세요.\n"
    "- 참고 자료가 질문과 무관하거나 부족하면 추측해서 답하지 말고, 근거가 부족하다고 명확히 말하세요.\n"
    "- 질문의 전제가 근거로 확인되지 않으면 정답처럼 단정하지 말고, 어떤 정보가 더 필요한지 안내하세요.\n"
    "- 핵심 답변만 1~3문장으로 간결하게 답하세요. 불필요한 서론이나 부연 없이 바로 본론을 말하세요.\n"
    "- 출처 파일명, key=value 형식, 기술적 메타 정보는 답변에 포함하지 마세요.\n"
    "- 확인된 데이터와 참고 자료에 없는 내용은 추측하지 마세요. 외부 지식으로 빈칸을 메우지 마세요.\n"
    "- 모르면 모른다고 솔직히 답하세요."
)


def build_system_message(context: str, *, persona_prompt: str = "") -> str:
    """Build the full system message with evidence context and optional persona."""
    from jarvis.runtime.voice_persona import DEFAULT_PERSONA

    msg = SYSTEM_PROMPT
    # Always include the persona response style for consistent voice tone
    effective_persona = persona_prompt or DEFAULT_PERSONA.response_style_prompt
    if effective_persona:
        msg += f"\n\n말투 스타일:\n{effective_persona}"
    if context.strip():
        msg += f"\n\n참고 증거:\n{context}"
    return msg
