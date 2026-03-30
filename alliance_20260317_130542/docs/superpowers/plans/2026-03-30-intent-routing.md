# Intent-Based Response Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix action requests like "YouTube 열어줘" by adding intent classification and action execution, so they open apps/URLs instead of returning HWP document content.

**Architecture:** Add `"action"` intent to the existing heuristic planner, create an `ActionResolver` module that executes macOS `open` commands, and wire it into `_intent_override_response` in menu_bridge.py so action intents bypass RAG entirely. Also harden the system prompt to ignore irrelevant evidence.

**Tech Stack:** Python 3.9+, subprocess, dataclasses, pytest, monkeypatch

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `src/jarvis/core/action_resolver.py` | Create | Parse action targets from queries, execute macOS `open` commands, return structured results |
| `src/jarvis/core/planner.py` | Modify (lines 581-599) | Add `"action"` to `_classify_intent` return values |
| `src/jarvis/core/intent_policy.py` | Modify (lines 36-54) | Add `"action"` entry to `_MENU_INTENT_POLICIES` |
| `src/jarvis/cli/menu_bridge.py` | Modify (lines 977-1019) | Call `ActionResolver` when intent is `"action"` |
| `src/jarvis/runtime/system_prompt.py` | Modify (lines 6-15) | Harden prompt to ignore irrelevant evidence |
| `tests/unit/test_action_resolver.py` | Create | Unit tests for action parsing and execution |
| `tests/unit/test_intent_classification.py` | Create | Unit tests for action intent detection in planner |
| `tests/unit/test_intent_routing_e2e.py` | Create | End-to-end tests through application service |

---

### Task 1: ActionResolver — Target Parsing and Execution

**Files:**
- Create: `src/jarvis/core/action_resolver.py`
- Test: `tests/unit/test_action_resolver.py`

- [ ] **Step 1: Write failing tests for action target parsing**

```python
# tests/unit/test_action_resolver.py
"""Tests for ActionResolver — target parsing and macOS open execution."""

from __future__ import annotations

from jarvis.core.action_resolver import parse_action_target, ActionTarget


def test_parse_youtube_open():
    target = parse_action_target("YouTube 열어줘")
    assert target is not None
    assert target.action_type == "open_url"
    assert target.target == "https://youtube.com"
    assert target.label == "YouTube"


def test_parse_kakaotalk_open():
    target = parse_action_target("카톡 켜줘")
    assert target is not None
    assert target.action_type == "open_app"
    assert target.target == "KakaoTalk"
    assert target.label == "카카오톡"


def test_parse_unknown_app():
    target = parse_action_target("모르는앱 열어줘")
    assert target is not None
    assert target.action_type == "open_app"
    assert target.target == "모르는앱"
    assert target.label == "모르는앱"
    assert target.confidence == "low"


def test_parse_no_action_verb():
    target = parse_action_target("서울 인구 알려줘")
    assert target is None


def test_parse_naver_open():
    target = parse_action_target("네이버 열어")
    assert target is not None
    assert target.action_type == "open_url"
    assert target.target == "https://naver.com"


def test_parse_english_open():
    target = parse_action_target("open github")
    assert target is not None
    assert target.action_type == "open_url"
    assert target.target == "https://github.com"


def test_parse_settings_open():
    target = parse_action_target("설정 열어줘")
    assert target is not None
    assert target.action_type == "open_app"
    assert target.target == "System Preferences"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_action_resolver.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'jarvis.core.action_resolver'`

- [ ] **Step 3: Implement ActionResolver — target parsing**

```python
# src/jarvis/core/action_resolver.py
"""Resolve action intents to macOS open commands."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass


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
    cleaned = re.sub(r"\s*(좀|을|를|이|가|도|에서|으로|로|해줘|해|주세요|줘)\s*", " ", cleaned)
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
    for key, (action_type, target, label) in _KNOWN_TARGETS.items():
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
            subprocess.run(["open", target.target], timeout=5, check=True)
        else:
            subprocess.run(["open", "-a", target.target], timeout=5, check=True)
    except subprocess.CalledProcessError:
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
        return ActionResult(
            success=False,
            spoken_response="실행 중 시간이 초과되었습니다.",
            display_response="실행 중 시간이 초과되었습니다.",
            label=target.label,
            action_type=target.action_type,
            target=target.target,
            error_message="timeout",
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_action_resolver.py -v`
Expected: 7 passed

- [ ] **Step 5: Write failing tests for execute_action**

Add to `tests/unit/test_action_resolver.py`:

```python
from jarvis.core.action_resolver import execute_action


def test_execute_url_success(monkeypatch):
    monkeypatch.setattr(
        "jarvis.core.action_resolver.subprocess.run",
        lambda *args, **kwargs: None,
    )
    target = ActionTarget(
        action_type="open_url",
        target="https://youtube.com",
        label="YouTube",
        confidence="high",
    )
    result = execute_action(target)
    assert result.success is True
    assert "YouTube" in result.spoken_response
    assert "열었습니다" in result.spoken_response


def test_execute_app_success(monkeypatch):
    monkeypatch.setattr(
        "jarvis.core.action_resolver.subprocess.run",
        lambda *args, **kwargs: None,
    )
    target = ActionTarget(
        action_type="open_app",
        target="KakaoTalk",
        label="카카오톡",
        confidence="high",
    )
    result = execute_action(target)
    assert result.success is True
    assert "카카오톡" in result.spoken_response
    assert "실행했습니다" in result.spoken_response


def test_execute_app_not_found(monkeypatch):
    import subprocess as sp

    def fail_run(*args, **kwargs):
        raise sp.CalledProcessError(1, "open")

    monkeypatch.setattr("jarvis.core.action_resolver.subprocess.run", fail_run)
    target = ActionTarget(
        action_type="open_app",
        target="NonExistentApp",
        label="NonExistentApp",
        confidence="low",
    )
    result = execute_action(target)
    assert result.success is False
    assert "찾을 수 없습니다" in result.spoken_response


def test_execute_timeout(monkeypatch):
    import subprocess as sp

    def timeout_run(*args, **kwargs):
        raise sp.TimeoutExpired("open", 5)

    monkeypatch.setattr("jarvis.core.action_resolver.subprocess.run", timeout_run)
    target = ActionTarget(
        action_type="open_url",
        target="https://example.com",
        label="example",
        confidence="high",
    )
    result = execute_action(target)
    assert result.success is False
    assert "시간이 초과" in result.spoken_response
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/unit/test_action_resolver.py -v`
Expected: 11 passed

- [ ] **Step 7: Commit**

```bash
git add src/jarvis/core/action_resolver.py tests/unit/test_action_resolver.py
git commit -m "feat: add ActionResolver for macOS open commands"
```

---

### Task 2: Planner — Add Action Intent Classification

**Files:**
- Modify: `src/jarvis/core/planner.py` (lines 581-599)
- Test: `tests/unit/test_intent_classification.py`

- [ ] **Step 1: Write failing tests for action intent in planner**

```python
# tests/unit/test_intent_classification.py
"""Tests for action intent classification in the planner."""

from __future__ import annotations

from jarvis.core.planner import _classify_intent


def test_classify_youtube_open_as_action():
    result = _classify_intent(
        "YouTube 열어줘",
        tokens=["youtube", "열어줘"],
        target_file="",
    )
    assert result == "action"


def test_classify_kakaotalk_as_action():
    result = _classify_intent(
        "카톡 켜줘",
        tokens=["카톡", "켜줘"],
        target_file="",
    )
    assert result == "action"


def test_classify_english_open_as_action():
    result = _classify_intent(
        "open safari",
        tokens=["open", "safari"],
        target_file="",
    )
    assert result == "action"


def test_classify_qa_unchanged():
    result = _classify_intent(
        "서울 인구 알려줘",
        tokens=["서울", "인구", "알려줘"],
        target_file="",
    )
    assert result == "qa"


def test_classify_smalltalk_unchanged():
    result = _classify_intent(
        "안녕하세요",
        tokens=["안녕하세요"],
        target_file="",
    )
    assert result == "smalltalk"


def test_classify_weather_unchanged():
    result = _classify_intent(
        "서울 날씨 어때",
        tokens=["서울", "날씨", "어때"],
        target_file="",
    )
    assert result == "weather"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_intent_classification.py -v`
Expected: FAIL — `test_classify_youtube_open_as_action` returns `"qa"` instead of `"action"`

- [ ] **Step 3: Modify `_classify_intent` in planner.py**

In `src/jarvis/core/planner.py`, add the action verb regex near the top of the file (after line 42, after `_STOPWORDS`):

```python
_ACTION_VERB_RE = re.compile(
    r"(열어줘|열어|실행해줘|실행해|켜줘|켜[^가-힣]|틀어줘|틀어|재생해줘|재생해|시작해줘|시작해)"
    r"|\b(open|launch|start|run|play)\b",
    re.IGNORECASE,
)
```

In `_classify_intent` (lines 581-599), add the action check **before** the final `return "qa"` fallthrough, but **after** smalltalk and weather checks:

```python
def _classify_intent(raw_text: str, *, tokens: list[str], target_file: str) -> str:
    # ... existing smalltalk checks ...
    # ... existing weather checks ...
    # ... existing route_guidance checks ...

    # Action intent: verbs like 열어줘, 켜줘, open, launch
    if _ACTION_VERB_RE.search(raw_text):
        return "action"

    return "qa"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_intent_classification.py -v`
Expected: 6 passed

- [ ] **Step 5: Run existing planner tests for regression**

Run: `pytest tests/unit/test_planner.py -v`
Expected: All existing tests pass

- [ ] **Step 6: Commit**

```bash
git add src/jarvis/core/planner.py tests/unit/test_intent_classification.py
git commit -m "feat: add action intent classification to planner"
```

---

### Task 3: Intent Policy + Menu Bridge — Wire Action Routing

**Files:**
- Modify: `src/jarvis/core/intent_policy.py` (lines 36-54)
- Modify: `src/jarvis/cli/menu_bridge.py` (lines 977-1019)
- Test: `tests/unit/test_intent_routing_e2e.py`

- [ ] **Step 1: Write failing end-to-end test**

```python
# tests/unit/test_intent_routing_e2e.py
"""End-to-end tests for intent-based response routing."""

from __future__ import annotations

from jarvis.service.application import JarvisApplicationService
from jarvis.service.protocol import RpcRequest


def _request(text: str) -> RpcRequest:
    return RpcRequest(
        request_id="req-1",
        session_id="session-1",
        request_type="ask_text",
        payload={"text": text},
    )


def test_youtube_open_returns_action_response(monkeypatch) -> None:
    """'YouTube 열어줘' should execute open command, not return HWP content."""
    service = JarvisApplicationService()

    monkeypatch.setattr(
        "jarvis.service.application._prime_tts_cache_async",
        lambda payload: None,
    )

    # Mock subprocess so we don't actually open YouTube
    open_calls = []

    def mock_subprocess_run(*args, **kwargs):
        open_calls.append(args[0] if args else kwargs.get("args"))

    monkeypatch.setattr(
        "jarvis.core.action_resolver.subprocess.run",
        mock_subprocess_run,
    )

    response = service.handle(_request("YouTube 열어줘"))

    assert response.ok is True
    assert "열었습니다" in response.payload["response"]["response"]
    assert len(open_calls) == 1
    assert "youtube.com" in open_calls[0][1]


def test_kakaotalk_open_returns_action_response(monkeypatch) -> None:
    service = JarvisApplicationService()

    monkeypatch.setattr(
        "jarvis.service.application._prime_tts_cache_async",
        lambda payload: None,
    )

    open_calls = []

    def mock_subprocess_run(*args, **kwargs):
        open_calls.append(args[0] if args else kwargs.get("args"))

    monkeypatch.setattr(
        "jarvis.core.action_resolver.subprocess.run",
        mock_subprocess_run,
    )

    response = service.handle(_request("카톡 켜줘"))

    assert response.ok is True
    assert "실행했습니다" in response.payload["response"]["response"]
    assert len(open_calls) == 1
    assert open_calls[0] == ["open", "-a", "KakaoTalk"]


def test_qa_query_still_uses_rag(monkeypatch) -> None:
    """Non-action queries should still go through RAG pipeline."""
    service = JarvisApplicationService()

    monkeypatch.setattr(
        "jarvis.service.application._prime_tts_cache_async",
        lambda payload: None,
    )

    bridge_called = []

    def fake_bridge(**kwargs):
        bridge_called.append(True)
        return {
            "kind": "query_result",
            "query_result": {
                "response": "서울 인구는 약 950만명입니다.",
                "citations": [],
                "render_hints": {},
            },
        }

    monkeypatch.setattr(
        "jarvis.service.application._run_menu_bridge_ask_with_fallback",
        fake_bridge,
    )

    response = service.handle(_request("서울 인구 알려줘"))

    assert response.ok is True
    assert len(bridge_called) == 1  # RAG pipeline was used


def test_builtin_time_still_works(monkeypatch) -> None:
    """Builtin capabilities should still take priority over action routing."""
    from datetime import datetime, timezone

    service = JarvisApplicationService()

    monkeypatch.setattr(
        "jarvis.service.application._prime_tts_cache_async",
        lambda payload: None,
    )
    monkeypatch.setattr(
        "jarvis.service.application._run_menu_bridge_ask_with_fallback",
        lambda **kwargs: (_ for _ in ()).throw(
            AssertionError("should not reach menu bridge")
        ),
    )

    def fake_now(zone_name: str) -> datetime:
        return datetime(2026, 3, 30, 10, 45, tzinfo=timezone.utc)

    monkeypatch.setattr(
        "jarvis.service.builtin_capabilities._now_in_zone",
        fake_now,
    )

    response = service.handle(_request("지금 몇시야"))

    assert response.ok is True
    assert "시간" in response.payload["response"]["response"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_intent_routing_e2e.py::test_youtube_open_returns_action_response -v`
Expected: FAIL — "YouTube 열어줘" still goes through RAG

- [ ] **Step 3: Add action policy to intent_policy.py**

In `src/jarvis/core/intent_policy.py`, add to `_MENU_INTENT_POLICIES` (after the `"weather"` entry):

```python
    "action": IntentPolicy(
        intent="action",
        mode="action_execute",
        response_text="",  # dynamic, filled by ActionResolver
        skill="action_resolver",
        suggested_replies=(),
        interaction_mode="action",
        response_type="action_result",
        primary_source_type="none",
        source_profile="none",
    ),
```

- [ ] **Step 4: Modify `_intent_override_response` in menu_bridge.py**

In `src/jarvis/cli/menu_bridge.py`, in the `_intent_override_response` function (around line 977), add action handling **after** `resolve_menu_intent_policy` returns and **before** the existing policy response builder:

```python
def _intent_override_response(query: str, *, model_id: str) -> MenuBarResponse | None:
    resolution = resolve_menu_intent_policy(query, knowledge_base_path=...)
    if resolution.policy is None:
        return None

    # --- NEW: action intent handling ---
    if resolution.policy.intent == "action":
        from jarvis.core.action_resolver import parse_action_target, execute_action

        target = parse_action_target(query)
        if target is None:
            return None  # fall through to RAG
        result = execute_action(target)
        return MenuBarResponse(
            query=query,
            response=result.display_response,
            has_evidence=False,
            spoken_response=result.spoken_response,
            citations=[],
            guide_directive=MenuBarGuideDirective(
                should_hold=False,
                loop_stage="idle",
            ),
        )
    # --- END NEW ---

    # ... existing smalltalk/weather handling ...
```

- [ ] **Step 5: Run e2e tests to verify they pass**

Run: `pytest tests/unit/test_intent_routing_e2e.py -v`
Expected: 4 passed

- [ ] **Step 6: Run full test suite for regression**

Run: `pytest tests/ -v --ignore=tests/unit/test_mcp_server.py --ignore=tests/unit/test_wake_word.py`
Expected: All pass (including existing builtin capability tests)

- [ ] **Step 7: Commit**

```bash
git add src/jarvis/core/intent_policy.py src/jarvis/cli/menu_bridge.py tests/unit/test_intent_routing_e2e.py
git commit -m "feat: wire action intent routing through intent policy and menu bridge"
```

---

### Task 4: System Prompt Hardening

**Files:**
- Modify: `src/jarvis/runtime/system_prompt.py` (lines 6-15)
- Test: manual verification (prompt text is a constant string)

- [ ] **Step 1: Read current system prompt**

Read: `src/jarvis/runtime/system_prompt.py` lines 6-15

- [ ] **Step 2: Update SYSTEM_PROMPT constant**

Replace the existing `SYSTEM_PROMPT` in `src/jarvis/runtime/system_prompt.py`:

```python
SYSTEM_PROMPT = (
    "당신은 JARVIS입니다. 사용자의 로컬 워크스페이스 AI 어시스턴트입니다.\n\n"
    "답변 규칙:\n"
    "- '확인된 데이터' 섹션의 값은 정확한 사실입니다. 그대로 사용하세요.\n"
    "- '참고 자료' 섹션은 배경 정보입니다. 질문과 직접 관련된 내용만 종합하여 자연어로 답변하세요.\n"
    "- 참고 자료가 질문과 무관하면 무시하고, 자신의 지식으로 답변하세요.\n"
    "- 핵심 답변만 1~3문장으로 간결하게 답하세요. 불필요한 서론이나 부연 없이 바로 본론을 말하세요.\n"
    "- 확인된 데이터나 참고 자료에 없는 내용을 지어내지 마세요.\n"
    "- 모르면 모른다고 솔직히 답하세요."
)
```

Key changes:
- "참고 자료에 관련 내용이 있으면 반드시 답변하세요" → "질문과 직접 관련된 내용만 종합하여"
- Added: "참고 자료가 질문과 무관하면 무시하고, 자신의 지식으로 답변하세요"

- [ ] **Step 3: Run existing tests for regression**

Run: `pytest tests/ -v --ignore=tests/unit/test_mcp_server.py --ignore=tests/unit/test_wake_word.py`
Expected: All pass

- [ ] **Step 4: Commit**

```bash
git add src/jarvis/runtime/system_prompt.py
git commit -m "fix: harden system prompt to ignore irrelevant evidence"
```

---

### Task 5: Final Integration Test + Cleanup

**Files:**
- All test files
- No new code

- [ ] **Step 1: Run complete test suite**

Run: `pytest tests/ -v --ignore=tests/unit/test_mcp_server.py --ignore=tests/unit/test_wake_word.py`
Expected: All pass, 0 failures

- [ ] **Step 2: Verify the full action routing chain manually**

Run in Python REPL:
```python
from jarvis.core.action_resolver import parse_action_target
for query in ["YouTube 열어줘", "카톡 켜줘", "네이버 열어", "open github", "설정 열어줘"]:
    t = parse_action_target(query)
    print(f"{query:25s} → {t.action_type:10s} {t.target:30s} [{t.confidence}]")
for query in ["서울 인구 알려줘", "안녕하세요", "HWP 문서 찾아줘"]:
    t = parse_action_target(query)
    print(f"{query:25s} → {t}")
```

Expected output:
```
YouTube 열어줘             → open_url    https://youtube.com            [high]
카톡 켜줘                   → open_app    KakaoTalk                      [high]
네이버 열어                  → open_url    https://naver.com              [high]
open github               → open_url    https://github.com             [high]
설정 열어줘                  → open_app    System Preferences             [high]
서울 인구 알려줘              → None
안녕하세요                   → None
HWP 문서 찾아줘              → None
```

- [ ] **Step 3: Commit final state and push**

```bash
git push origin feature/jarvis-dual-mode-guide-workspace
```
