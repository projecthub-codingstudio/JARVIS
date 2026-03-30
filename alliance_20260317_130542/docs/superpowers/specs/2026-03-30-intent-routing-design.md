# Intent-Based Response Routing Design

**Date:** 2026-03-30
**Status:** Approved
**Problem:** "YouTube 열어줘" 같은 액션 요청이 RAG 파이프라인으로 빠져 HWP 문서를 답변하는 문제

---

## 1. 근본 원인 분석

5단계 연쇄 실패로 인해 액션 요청이 오동작한다:

1. **builtin_capabilities.py** — "X 열어줘" 패턴 핸들러 없음
2. **planner.py:_classify_intent** — `"action"` 인텐트 클래스 없음, 모든 것이 `"qa"`로 분류
3. **intent_policy.py** — override 맵에 `smalltalk`/`weather`만 존재
4. **orchestrator.py:handle_turn** — 모든 쿼리에 무조건 RAG 검색, 인텐트 기반 바이패스 없음
5. **system_prompt.py** — 액션 요청 관련 지시 없음 + "반드시 답변하세요"로 HWP 내용 강제 출력

### 호출 경로 (현재)

```
"YouTube 열어줘"
  → builtin_capabilities: "YouTube"에 점(.)이 없어 URL 아님 → None
  → planner: "열어줘"가 stopword로 제거, intent="qa"
  → intent_policy: "qa"는 override 대상 아님
  → orchestrator: 무조건 RAG 검색 → "youtube" 키워드로 HWP 문서 매칭
  → LLM: "참고 자료에 관련 내용이 있으면 반드시 답변하세요" → HWP 내용을 답변
```

---

## 2. 목표 파이프라인

```
쿼리 → builtin_capabilities(시간/날씨/계산/웹검색) → (miss)
     → IntentClassifier(휴리스틱)
         ├─ action(high)  → ActionResolver → macOS open 실행 + 응답
         ├─ action(low)   → LLM fallback (향후 function calling)
         ├─ qa            → RAG → LLM 답변 (기존 경로)
         ├─ smalltalk     → 직접 응답 (기존)
         └─ weather       → 기존 처리
```

### 설계 원칙

- **기존 builtin_capabilities는 그대로 유지** — 가장 빠른 경로로 먼저 체크
- **기존 RAG 경로에 영향 없음** — qa 인텐트는 현재와 동일하게 동작
- **확장 가능한 프레임워크** — 시스템 제어, 파일 작업, 자동화를 점진적으로 추가
- **하이브리드 전략** — 휴리스틱 우선, 향후 LLM function calling fallback

---

## 3. IntentClassifier — 인텐트 분류

기존 `Planner._classify_intent`를 확장한다.

### 액션 감지 패턴

```python
# 한국어 액션 동사
_ACTION_VERBS_KO = r"(열어줘|열어|실행해줘|실행해|켜줘|켜|틀어줘|틀어|보여줘|재생해줘|재생해|시작해줘|시작해|닫아줘|닫아|꺼줘|종료해줘)"

# 영어 액션 동사
_ACTION_VERBS_EN = r"\b(open|launch|start|run|play|close|quit|show)\b"
```

### 대상 매핑 테이블

```python
_KNOWN_TARGETS = {
    # 웹 서비스
    "유튜브": ("url", "https://youtube.com", "YouTube"),
    "youtube": ("url", "https://youtube.com", "YouTube"),
    "구글": ("url", "https://google.com", "Google"),
    "google": ("url", "https://google.com", "Google"),
    "네이버": ("url", "https://naver.com", "네이버"),
    "naver": ("url", "https://naver.com", "네이버"),
    "인스타": ("url", "https://instagram.com", "Instagram"),
    "instagram": ("url", "https://instagram.com", "Instagram"),
    "깃허브": ("url", "https://github.com", "GitHub"),
    "github": ("url", "https://github.com", "GitHub"),
    "지메일": ("url", "https://mail.google.com", "Gmail"),
    "gmail": ("url", "https://mail.google.com", "Gmail"),
    # 로컬 앱
    "카카오톡": ("app", "KakaoTalk", "카카오톡"),
    "카톡": ("app", "KakaoTalk", "카카오톡"),
    "사파리": ("app", "Safari", "Safari"),
    "safari": ("app", "Safari", "Safari"),
    "파인더": ("app", "Finder", "Finder"),
    "finder": ("app", "Finder", "Finder"),
    "터미널": ("app", "Terminal", "Terminal"),
    "terminal": ("app", "Terminal", "Terminal"),
    "메모": ("app", "Notes", "메모"),
    "notes": ("app", "Notes", "Notes"),
    "설정": ("app", "System Preferences", "시스템 설정"),
    "캘린더": ("app", "Calendar", "캘린더"),
    "calendar": ("app", "Calendar", "Calendar"),
    "음악": ("app", "Music", "음악"),
    "music": ("app", "Music", "Music"),
    "메시지": ("app", "Messages", "메시지"),
    "messages": ("app", "Messages", "Messages"),
    "슬랙": ("app", "Slack", "Slack"),
    "slack": ("app", "Slack", "Slack"),
}
```

### 분류 로직

```
1. 쿼리에 ACTION_VERB가 있는가?
2. 있다면 → 대상(target) 추출 (동사 제거 후 남은 명사)
3. target이 KNOWN_TARGETS에 있으면 → intent="action", confidence="high"
4. target이 없지만 동사 있으면 → intent="action", confidence="low"
5. confidence="low" → 향후 LLM function calling fallback 대상
6. ACTION_VERB 없으면 → 기존 분류 로직 (qa/smalltalk/weather)
```

### 반환 구조

```python
@dataclass
class IntentResult:
    intent: str          # "action", "qa", "smalltalk", "weather"
    confidence: str      # "high", "low"
    action_type: str     # "open_url", "open_app", ""
    action_target: str   # "https://youtube.com", "KakaoTalk", ""
    action_label: str    # "YouTube", "카카오톡", ""
    search_terms: list   # qa일 때만 사용
```

---

## 4. ActionResolver — 액션 실행

새 모듈: `src/jarvis/core/action_resolver.py`

### 인터페이스

```python
@dataclass
class ActionResult:
    success: bool
    spoken_response: str    # TTS용 ("유튜브를 열었습니다")
    display_response: str   # 메뉴바 표시용
    artifacts: list         # 워크스페이스 표시용 (optional)
    error_message: str      # 실패 시

class ActionResolver:
    def resolve(self, intent: IntentResult) -> ActionResult
```

### 실행 방식

- **URL 열기:** `subprocess.run(["open", url], timeout=5)`
- **앱 열기:** `subprocess.run(["open", "-a", app_name], timeout=5)`
- **미지의 대상:** `open -a "{target}"` 시도 → 실패 시 graceful 메시지

### 안전장치

- `subprocess.run`에 `timeout=5` 설정
- `open` 명령만 허용 (임의 쉘 명령 차단)
- 앱/URL 대상만 전달 (인젝션 방지: shlex.quote 또는 리스트 인자)
- 실패 시: "해당 앱을 찾을 수 없습니다. 이름을 확인해 주세요."

### 응답 생성 규칙

| 시나리오 | spoken_response | display_response |
|---------|----------------|-----------------|
| URL 열기 성공 | "{label}을(를) 열었습니다." | "{label}을(를) 열었습니다." |
| 앱 열기 성공 | "{label}을(를) 실행했습니다." | "{label}을(를) 실행했습니다." |
| 앱 없음 | "{target}을(를) 찾을 수 없습니다." | "{target}을(를) 찾을 수 없습니다. 이름을 확인해 주세요." |
| 타임아웃 | "실행 중 시간이 초과되었습니다." | "실행 중 시간이 초과되었습니다." |

---

## 5. Orchestrator 변경

`orchestrator.py:handle_turn()` 시작부에 인텐트 분기 추가.

```python
def handle_turn(self, query: str) -> TurnResult:
    # 1. 인텐트 분류
    intent = self.planner.classify_intent(query)

    # 2. 액션 인텐트 → RAG 바이패스
    if intent.intent == "action" and intent.confidence == "high":
        result = self.action_resolver.resolve(intent)
        return TurnResult(
            response=result.display_response,
            spoken=result.spoken_response,
            citations=[],
            has_evidence=False,
        )

    # 3. 기존 경로 (qa, smalltalk, weather 등)
    analysis = self.planner.analyze(query)
    evidence = self._retrieve_evidence(analysis.search_query)
    ...
```

### intent_policy.py 변경

`_MENU_INTENT_POLICIES`에 `"action"` 정책 등록:

```python
_MENU_INTENT_POLICIES = {
    "smalltalk": MenuIntentPolicy(...),
    "weather": MenuIntentPolicy(...),
    "action": MenuIntentPolicy(bypass_rag=True, handler="action_resolver"),
}
```

---

## 6. system_prompt.py 보완

현재 문제: "참고 자료에 관련 내용이 있으면 반드시 답변하세요" → 무관한 검색 결과도 강제 사용.

변경:

```
답변 규칙:
- '확인된 데이터' 섹션의 값은 정확한 사실입니다. 그대로 사용하세요.
- '참고 자료' 섹션은 배경 정보입니다. 질문과 직접 관련된 내용만 사용하세요.
- 참고 자료가 질문과 무관하면 무시하고, 자신의 지식으로 답변하세요.
- 핵심 답변만 1~3문장으로 간결하게 답하세요.
```

핵심 변경: "반드시 답변하세요" → "질문과 직접 관련된 내용만 사용하세요" + "무관하면 무시"

---

## 7. 테스트 계획

### 단위 테스트

| 테스트 | 검증 내용 |
|--------|----------|
| `test_classify_intent_action_youtube` | "YouTube 열어줘" → intent="action", confidence="high", target="https://youtube.com" |
| `test_classify_intent_action_kakaotalk` | "카톡 켜줘" → intent="action", confidence="high", target="KakaoTalk" |
| `test_classify_intent_action_unknown` | "모르는앱 열어줘" → intent="action", confidence="low" |
| `test_classify_intent_qa_unchanged` | "서울 인구 알려줘" → intent="qa" (기존 동작 유지) |
| `test_action_resolver_open_url` | subprocess.run 호출 검증 (mock) |
| `test_action_resolver_open_app` | subprocess.run 호출 검증 (mock) |
| `test_action_resolver_app_not_found` | 실패 시 graceful 메시지 |
| `test_orchestrator_action_bypasses_rag` | action 인텐트 시 _retrieve_evidence 미호출 |
| `test_orchestrator_qa_unchanged` | qa 인텐트 시 기존 RAG 경로 유지 |
| `test_system_prompt_ignores_irrelevant` | 무관한 참고자료 무시 확인 |

### 통합 테스트

| 테스트 | 검증 내용 |
|--------|----------|
| `test_e2e_youtube_open` | "YouTube 열어줘" → open 명령 실행 + "유튜브를 열었습니다" 응답 |
| `test_e2e_hwp_query` | "HWP 문서 내용" → 기존 RAG 경로 유지 (회귀 없음) |
| `test_e2e_builtin_time` | "지금 몇시" → 기존 builtin 경로 유지 (회귀 없음) |

---

## 8. 향후 확장 (이번 스코프 아님)

- **LLM Function Calling:** confidence="low" 시 LLM에 tool 정의 전달하여 액션 결정 위임
- **시스템 제어:** 볼륨, 밝기, 와이파이 등 — ActionResolver에 새 핸들러 등록
- **파일 작업:** 폴더 열기, 파일 검색 — ActionResolver 확장
- **자동화:** 알람, 메일 전송 — ActionResolver + 외부 서비스 연동

---

## 9. 변경 파일 목록

| 파일 | 변경 유형 | 설명 |
|------|----------|------|
| `src/jarvis/core/planner.py` | 수정 | `_classify_intent`에 action 인텐트 추가, `IntentResult` 반환 |
| `src/jarvis/core/action_resolver.py` | 신규 | ActionResolver, ActionResult |
| `src/jarvis/core/orchestrator.py` | 수정 | handle_turn()에 인텐트 분기 추가 |
| `src/jarvis/core/intent_policy.py` | 수정 | action 정책 등록 |
| `src/jarvis/runtime/system_prompt.py` | 수정 | LLM 지시 보완 |
| `tests/unit/test_intent_classification.py` | 신규 | 인텐트 분류 테스트 |
| `tests/unit/test_action_resolver.py` | 신규 | 액션 실행 테스트 |
| `tests/unit/test_orchestrator_routing.py` | 신규 | 오케스트레이터 라우팅 테스트 |
