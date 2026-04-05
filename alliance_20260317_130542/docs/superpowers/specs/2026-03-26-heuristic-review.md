# 2026-03-26 Heuristic Review

## 배경

메뉴바 안정화 과정에서 반복 크래시와 빈 응답 문제를 우회하기 위해
`stub + heuristic` 경로가 넓어졌다.

단기적으로는 효과가 있었지만, 현재는 다음 문제가 커졌다.

- 의미 해석이 엉뚱해짐
- 답변 문장과 TTS 문장이 부자연스러워짐
- 규칙 추가 공수가 계속 발생함
- LLM 중심 설계와 어긋남

사용자 요구는 다음과 같다.

- 휴리스틱을 전면 금지하지는 않음
- 그러나 현재 효용이 낮은 휴리스틱은 줄여야 함
- `intent JSON -> policy -> response JSON -> speech_text` 구조로 복귀해야 함
- 하드코딩이 필요하면 사유 설명과 사용자 동의가 먼저 필요함

## 현재 휴리스틱 개입 지점

### 1. Query Intent 분류

파일:
- `src/jarvis/core/planner.py`

현재 상태:
- `smalltalk`, `weather`를 regex/keyword로 분류

판단:
- 완전 제거 대상은 아님
- 다만 현재는 LLM intent JSON이 아니라 baseline heuristic이 intent source of truth 역할을 하고 있음

조치:
- 유지하되, baseline fallback로 격하
- 최종 intent 결정은 LLM 경로 복구 후 backend JSON으로 이동

### 2. Frontend Intent Override Policy

파일:
- `src/jarvis/core/intent_policy.py`
- `src/jarvis/cli/menu_bridge.py`

현재 상태:
- `smalltalk`, `weather`는 retrieval을 생략하고 고정 응답 반환

판단:
- 현재 효용 낮음
- capability gap 공지는 가능하지만, 답변 본문을 policy가 직접 소유하는 구조는 과함

조치:
- 축소 우선순위 높음
- 장기적으로는 LLM이 `intent`, `capability_status`, `answer_text`, `speech_text`를 함께 반환해야 함

### 3. Table Retrieval 보강

파일:
- `src/jarvis/core/orchestrator.py`

현재 상태:
- `Day=n`, `Breakfast/Lunch/Dinner` 필드 힌트로 table row를 직접 보강

판단:
- 현재 효용 있음
- 이건 답변 문장 하드코딩이 아니라 retrieval bias에 가까움
- structured data lookup 품질 개선 측면에서 당분간 유지 가능

조치:
- 유지
- 다만 field alias 확장은 사용자 승인 없는 무분별한 증가 금지

### 4. Stub Answer / Speech Shaping

파일:
- `src/jarvis/runtime/mlx_runtime.py`
- `src/jarvis/cli/menu_bridge.py`
- `src/jarvis/service/application.py`

현재 상태:
- table row를 자연어 문장으로 렌더링
- `speech_text`도 rule 기반으로 조립

판단:
- 현재 문제의 핵심 영역
- 자연스러움 개선에는 일부 도움되지만, 규칙이 늘수록 품질과 유지보수가 악화됨

조치:
- 축소 우선순위 최상
- LLM 경로 복구 전까지는 structured row rendering 정도만 제한적으로 유지
- 기호/수량/분수 발화 변환은 장기적으로 LLM speech generation으로 대체

### 5. Menu Bar Forced Stub Model

파일:
- `src/jarvis/service/application.py`
- `macos/JarvisMenuBar/Sources/JarvisServiceClient.swift`
- `src/jarvis/app/runtime_context.py`

현재 상태:
- 메뉴바 `ask_text`가 `stub` 모델에 강하게 묶여 있음

판단:
- 휴리스틱 증가의 근본 원인
- 생성 모델이 비활성이라 rule-based answer shaping이 계속 필요해짐

조치:
- 제거 우선순위 최상
- 안정적인 model-backed ask path 복귀가 핵심

## 유지 / 축소 / 제거 기준

### 유지

- transport fallback
- subprocess lifecycle retry
- table retrieval bias

### 축소

- regex intent 분류
- intent override policy
- speech text rule shaping

### 제거 목표

- frontend/bridge가 직접 답변 문장을 조립하는 경로
- policy가 answer text를 소유하는 경로
- 식단표/도메인별 발화 규칙의 지속적 확장

## 구현 순서

1. 현재 휴리스틱 개입 지점을 문서화하고 유지/축소/제거 기준 고정
2. `intent_policy`와 `stub speech shaping`의 책임을 축소
3. menu bar `ask_text`를 model-backed JSON 응답으로 복귀
4. backend가 `intent_json`, `answer_text`, `speech_text`, `citations`를 생성
5. heuristic은 fallback 계층으로만 남김

## 합의된 원칙

- 휴리스틱은 금지 대상이 아니라 fallback 수단이다.
- 효용이 낮은 휴리스틱은 계속 늘리지 않는다.
- 의미 해석과 답변 생성의 주 경로는 LLM이어야 한다.
- 새로운 하드코딩이 필요하면 먼저 사유를 설명하고 사용자 동의를 받는다.
