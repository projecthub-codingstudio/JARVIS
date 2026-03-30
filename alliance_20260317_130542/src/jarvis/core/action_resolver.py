"""Resolve action intents to macOS open commands."""

from __future__ import annotations

import logging
import re
import subprocess
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ActionTarget:
    action_type: str   # "open_url" or "open_app"
    target: str        # URL or app name
    label: str         # display name
    confidence: str    # "high" or "low"


@dataclass(frozen=True)
class ActionResult:
    success: bool
    spoken_response: str
    display_response: str
    label: str
    action_type: str
    target: str
    error_message: str = ""


_ACTION_VERB_KO_RE = re.compile(
    r"(열어줘|열어|실행해줘|실행해|켜줘|켜|틀어줘|틀어|재생해줘|재생해|시작해줘|시작해)",
)
_ACTION_VERB_EN_RE = re.compile(
    r"\b(open|launch|start|run|play)\b",
    re.IGNORECASE,
)

_KNOWN_TARGETS: dict[str, tuple[str, str, str]] = {
    # (action_type, target, label)
    # Web services
    "유튜브": ("open_url", "https://youtube.com", "YouTube"),
    "youtube": ("open_url", "https://youtube.com", "YouTube"),
    "구글": ("open_url", "https://google.com", "Google"),
    "google": ("open_url", "https://google.com", "Google"),
    "네이버": ("open_url", "https://naver.com", "네이버"),
    "naver": ("open_url", "https://naver.com", "네이버"),
    "인스타": ("open_url", "https://instagram.com", "Instagram"),
    "인스타그램": ("open_url", "https://instagram.com", "Instagram"),
    "instagram": ("open_url", "https://instagram.com", "Instagram"),
    "깃허브": ("open_url", "https://github.com", "GitHub"),
    "github": ("open_url", "https://github.com", "GitHub"),
    "지메일": ("open_url", "https://mail.google.com", "Gmail"),
    "gmail": ("open_url", "https://mail.google.com", "Gmail"),
    "트위터": ("open_url", "https://x.com", "X"),
    "twitter": ("open_url", "https://x.com", "X"),
    "x": ("open_url", "https://x.com", "X"),
    "페이스북": ("open_url", "https://facebook.com", "Facebook"),
    "facebook": ("open_url", "https://facebook.com", "Facebook"),
    "링크드인": ("open_url", "https://linkedin.com", "LinkedIn"),
    "linkedin": ("open_url", "https://linkedin.com", "LinkedIn"),
    "챗지피티": ("open_url", "https://chat.openai.com", "ChatGPT"),
    "chatgpt": ("open_url", "https://chat.openai.com", "ChatGPT"),
    "클로드": ("open_url", "https://claude.ai", "Claude"),
    "claude": ("open_url", "https://claude.ai", "Claude"),
    "노션": ("open_url", "https://notion.so", "Notion"),
    "notion": ("open_url", "https://notion.so", "Notion"),
    # Local apps
    "카카오톡": ("open_app", "KakaoTalk", "카카오톡"),
    "카톡": ("open_app", "KakaoTalk", "카카오톡"),
    "사파리": ("open_app", "Safari", "Safari"),
    "safari": ("open_app", "Safari", "Safari"),
    "크롬": ("open_app", "Google Chrome", "Chrome"),
    "chrome": ("open_app", "Google Chrome", "Chrome"),
    "파인더": ("open_app", "Finder", "Finder"),
    "finder": ("open_app", "Finder", "Finder"),
    "터미널": ("open_app", "Terminal", "Terminal"),
    "terminal": ("open_app", "Terminal", "Terminal"),
    "메모": ("open_app", "Notes", "메모"),
    "notes": ("open_app", "Notes", "Notes"),
    "설정": ("open_app", "System Preferences", "시스템 설정"),
    "시스템설정": ("open_app", "System Preferences", "시스템 설정"),
    "캘린더": ("open_app", "Calendar", "캘린더"),
    "calendar": ("open_app", "Calendar", "Calendar"),
    "음악": ("open_app", "Music", "음악"),
    "music": ("open_app", "Music", "Music"),
    "메시지": ("open_app", "Messages", "메시지"),
    "messages": ("open_app", "Messages", "Messages"),
    "슬랙": ("open_app", "Slack", "Slack"),
    "slack": ("open_app", "Slack", "Slack"),
    "디스코드": ("open_app", "Discord", "Discord"),
    "discord": ("open_app", "Discord", "Discord"),
    "vscode": ("open_app", "Visual Studio Code", "VS Code"),
    "코드": ("open_app", "Visual Studio Code", "VS Code"),
    "xcode": ("open_app", "Xcode", "Xcode"),
}


def _extract_target_name(text: str) -> str:
    """Remove action verbs and common particles to extract the target name."""
    cleaned = _ACTION_VERB_KO_RE.sub("", text)
    cleaned = _ACTION_VERB_EN_RE.sub("", cleaned)
    # Only strip particles at the end of the cleaned text (not mid-word)
    cleaned = re.sub(r"\s+(좀|을|를|이|가|도|에서|으로|로|해줘|해|주세요|줘)$", "", cleaned)
    cleaned = re.sub(r"(좀|을|를|이|가|도|에서|으로|로|해줘|해|주세요|줘)$", "", cleaned)
    return cleaned.strip()


def parse_action_target(query: str) -> ActionTarget | None:
    """Parse query for action intent. Returns None if no action verb detected."""
    has_ko_verb = _ACTION_VERB_KO_RE.search(query)
    has_en_verb = _ACTION_VERB_EN_RE.search(query)

    if not has_ko_verb and not has_en_verb:
        return None

    target_name = _extract_target_name(query)
    if not target_name:
        return None

    normalized = target_name.lower().replace(" ", "")
    for key in sorted(_KNOWN_TARGETS, key=len, reverse=True):
        action_type, target, label = _KNOWN_TARGETS[key]
        if key == normalized or key in normalized:
            return ActionTarget(
                action_type=action_type,
                target=target,
                label=label,
                confidence="high",
            )

    return ActionTarget(
        action_type="open_app",
        target=target_name,
        label=target_name,
        confidence="low",
    )


def execute_action(target: ActionTarget) -> ActionResult:
    """Execute the action via macOS open command."""
    try:
        if target.action_type == "open_url":
            logger.debug("Executing action: %s %s", target.action_type, target.target)
            subprocess.run(["open", target.target], timeout=5, check=True)
        else:
            logger.debug("Executing action: %s %s", target.action_type, target.target)
            subprocess.run(["open", "-a", target.target], timeout=5, check=True)
    except subprocess.CalledProcessError:
        logger.warning("Action failed: %s not found", target.target)
        return ActionResult(
            success=False,
            spoken_response=f"{target.label}을 찾을 수 없습니다.",
            display_response=f"{target.label}을(를) 찾을 수 없습니다. 이름을 확인해 주세요.",
            label=target.label,
            action_type=target.action_type,
            target=target.target,
            error_message="app_not_found",
        )
    except subprocess.TimeoutExpired:
        logger.warning("Action timed out: %s", target.target)
        return ActionResult(
            success=False,
            spoken_response="실행 중 시간이 초과되었습니다.",
            display_response="실행 중 시간이 초과되었습니다.",
            label=target.label,
            action_type=target.action_type,
            target=target.target,
            error_message="timeout",
        )
    except OSError as exc:
        logger.error("OS error executing action: %s", exc)
        return ActionResult(
            success=False,
            spoken_response="명령을 실행할 수 없습니다.",
            display_response="명령을 실행할 수 없습니다.",
            label=target.label,
            action_type=target.action_type,
            target=target.target,
            error_message="os_error",
        )

    if target.action_type == "open_url":
        spoken = f"{target.label}을 열었습니다."
        display = f"{target.label}을(를) 열었습니다."
    else:
        spoken = f"{target.label}을 실행했습니다."
        display = f"{target.label}을(를) 실행했습니다."

    return ActionResult(
        success=True,
        spoken_response=spoken,
        display_response=display,
        label=target.label,
        action_type=target.action_type,
        target=target.target,
    )
