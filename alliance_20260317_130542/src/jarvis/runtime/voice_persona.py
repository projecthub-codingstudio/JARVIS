"""Voice Persona — defines JARVIS's speaking style and voice parameters.

Inspired by the Iron Man JARVIS AI butler (Paul Bettany):
  - Calm, measured British English tone
  - Polite but efficient, occasionally dry wit
  - Professional butler demeanor
  - Clear enunciation, moderate pace
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VoicePersona:
    """Configuration for a TTS voice persona."""

    name: str
    description: str
    # macOS `say` voice name for Korean
    macos_voice_ko: str
    # macOS `say` voice name for English
    macos_voice_en: str
    # Speaking rate for macOS `say` (words per minute, default ~175)
    macos_rate: int
    # System prompt addition for persona-aware LLM responses
    response_style_prompt: str
    # Qwen3-TTS speaker description for custom voice generation
    speaker_description: str


# The Iron Man JARVIS persona
JARVIS_PERSONA = VoicePersona(
    name="JARVIS",
    description="Refined futuristic AI assistant — calm, intelligent, lightly playful",
    macos_voice_ko="Jian (Premium)",  # Korean male premium voice
    macos_voice_en="Daniel",           # British English male voice
    macos_rate=165,
    response_style_prompt=(
        "당신의 말투는 세련된 미래형 AI 어시스턴트입니다. "
        "차분하고 지적이며, 약간의 유머와 위트가 있는 우아한 톤으로 대답하세요. "
        "깔끔하고 정확한 표현을 사용하되, 가볍고 매끄러운 대화체를 유지하세요. "
        "자신감 있지만 과장되지 않고, 세련되지만 친근하게. "
        "약간의 장난기와 부드러운 매력이 있는 스타일입니다. "
        "절대 무겁거나, 어둡거나, 기계적이거나, 과장된 톤은 쓰지 마세요."
    ),
    speaker_description=(
        "Refined futuristic AI assistant, male, calm, intelligent, "
        "lightly playful, elegant, British-leaning neutral accent, "
        "medium pitch, clean and precise diction, smooth pacing, "
        "subtle wit, dry humor, warm composure, polished but not heavy, "
        "sophisticated but approachable, confident without sounding dramatic, "
        "premium high-tech assistant tone. Slightly cheeky at moments, "
        "with gentle conversational charm. Never too deep, never overly "
        "serious, never gloomy, never metallic, never cartoonish, "
        "never exaggerated."
    ),
)

# Default persona — can be switched later
DEFAULT_PERSONA = JARVIS_PERSONA
