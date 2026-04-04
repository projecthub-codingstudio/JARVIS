# Basic Task Layer Implementation Plan

> **For agentic workers:** 문서 RAG와 기본 작업을 섞지 말 것. `utility_result`와 `retrieval_result`를 분리한 뒤 순차적으로 구현한다.

**Goal:** 날짜/시간, 계산, 단위 변환, 기능 안내, 런타임 상태, 문서 열기 같은 기본 작업을 별도 계층으로 처리하고, 문서가 없는 질문이 `artifacts/citations`를 만들지 않도록 한다.

**Architecture:** `Planner -> BasicTaskRouter -> (deterministic handler | live capability handler | retrieval)`  
프론트는 `answer.kind` 기준으로 utility/action/live/retrieval UI를 구분한다.

**Success Criteria:**

1. `오늘 며칠이야`는 문서 없이 답한다.
2. `뉴욕 지금 몇 시`는 timezone utility로 답한다.
3. `420의 15%`는 deterministic evaluator로 답한다.
4. utility task 후 `Documents/Repository`가 흔들리지 않는다.
5. `README 열어줘`는 실제 문서를 연다.

---

## File Targets

### Backend

| File | Change |
|---|---|
| `alliance_20260317_130542/src/jarvis/core/planner.py` | `basic_task`, `response_kind`, `requires_retrieval` 분류 추가 |
| `alliance_20260317_130542/src/jarvis/core/orchestrator.py` | retrieval 전 short-circuit 추가 |
| `alliance_20260317_130542/src/jarvis/core/intent_policy.py` | basic/live capability policy 정리 |
| `alliance_20260317_130542/src/jarvis/core/basic_task_router.py` | 신규 |
| `alliance_20260317_130542/src/jarvis/core/basic_tasks/*.py` | 신규 handler |
| `alliance_20260317_130542/src/jarvis/web_api.py` | runtime-state 응답 활용 정리 |

### Frontend

| File | Change |
|---|---|
| `src/types.ts` | `Answer.kind`, `structured_payload`, `ui_hints` 타입 반영 |
| `src/hooks/useJarvis.ts` | answer kind 기준 상태 분기 |
| `src/store/app-store.ts` | utility state 필요 시 추가 |
| `src/components/workspaces/TerminalWorkspace.tsx` | utility/live/action 카드 렌더링 |
| `src/App.tsx` | utility result에서 documents/repository 진입 규칙 제한 |

---

## Task 1: Response Contract 분리

- [ ] `Answer.kind` 추가
- [ ] `Answer.task_id` 추가
- [ ] `Answer.structured_payload` 추가
- [ ] `GuideDirective.ui_hints` 추가
- [ ] 프론트 타입 동기화

검증:

- [ ] `npm run lint`
- [ ] 기존 retrieval 경로 회귀 없음

---

## Task 2: Planner에 Basic Task 분류 추가

- [ ] `datetime_now`
- [ ] `timezone_now`
- [ ] `date_arithmetic`
- [ ] `math_eval`
- [ ] `unit_convert`
- [ ] `capability_help`
- [ ] `runtime_status`
- [ ] `open_document`
- [ ] `recent_context`

규칙:

- [ ] 문서 없는 task는 `requires_retrieval=False`
- [ ] live capability는 `requires_live_data=True`
- [ ] retrieval task는 기존 분기 유지

테스트:

- [ ] `오늘 며칠이야` → `datetime_now`
- [ ] `뉴욕 지금 몇 시` → `timezone_now`
- [ ] `420의 15%` → `math_eval`
- [ ] `무엇을 할 수 있어?` → `capability_help`

---

## Task 3: BasicTaskRouter 추가

- [ ] `basic_task_router.py` 생성
- [ ] task id별 dispatcher 구현
- [ ] unknown task는 `None` 반환 후 retrieval fallback
- [ ] capability missing이면 `capability_gap` 반환

반환 계약:

- [ ] utility task는 `artifacts=[]`
- [ ] utility task는 `citations=[]`
- [ ] utility task는 `presentation=None`

---

## Task 4: Deterministic Handler 구현

### P0 handlers

- [ ] `datetime_handler.py`
- [ ] `timezone_handler.py`
- [ ] `date_arithmetic_handler.py`
- [ ] `math_handler.py`
- [ ] `unit_handler.py`
- [ ] `help_handler.py`
- [ ] `runtime_status_handler.py`

세부 규칙:

- [ ] 날짜/시간 응답은 절대 날짜를 포함할 것
- [ ] timezone 응답은 기준 timezone 이름을 포함할 것
- [ ] 계산은 eval 금지, safe parser 사용
- [ ] 단위 변환은 허용 단위 화이트리스트 기반

테스트:

- [ ] `오늘 며칠이야`
- [ ] `지금 몇 시야`
- [ ] `뉴욕 지금 몇 시`
- [ ] `3일 뒤 날짜`
- [ ] `34*18`
- [ ] `10MB는 몇 KB`

---

## Task 5: Open Document / Recent Context

- [ ] `open_document` task 구현
- [ ] 최근 assets / selected artifact / presentation 기반 대상 복원
- [ ] 실파일 경로가 없으면 clarification

테스트:

- [ ] `README 열어줘`
- [ ] `브로셔 보여줘`
- [ ] `방금 본 문서 다시`

---

## Task 6: Orchestrator Short-Circuit

- [ ] planner 결과에서 `requires_retrieval=False`면 retrieval 건너뛰기
- [ ] utility/live/action 결과는 answerability gate 우회 또는 별도 경로 사용
- [ ] retrieval은 기존 문서 질문에만 적용

회귀 테스트:

- [ ] utility task 후 evidence empty early return이 잘못 타지 않음
- [ ] utility task가 retrieval evidence를 만들지 않음

---

## Task 7: Frontend 분기

- [ ] `useJarvis.ts`에서 `answer.kind` 분기
- [ ] `utility_result`면 assets/citations/presentation 초기화
- [ ] `retrieval_result`만 documents/repository 상태 갱신
- [ ] `TerminalWorkspace` utility card renderer 추가
- [ ] `App.tsx`에서 utility 응답 후 document auto-open 금지

테스트:

- [ ] `오늘 며칠이야` 후 Documents 비활성 유지
- [ ] `뉴욕 지금 몇 시` 후 Repository 선택 루프 없음
- [ ] `README 열어줘` 후 Documents 정상 진입

---

## Task 8: Capability Registry

- [ ] capability 목록을 한 곳에서 관리
- [ ] support state, connector state, fallback reason 포함
- [ ] help 응답은 registry 기반 생성

예시 항목:

- [ ] `datetime`
- [ ] `timezone`
- [ ] `math`
- [ ] `unit_conversion`
- [ ] `runtime_status`
- [ ] `document_open`
- [ ] `document_summary`
- [ ] `table_lookup`
- [ ] `calendar`
- [ ] `weather`
- [ ] `route_guidance`

---

## Task 9: Live Capability 연결 준비

- [ ] `calendar_today`
- [ ] `weather_now`
- [ ] `route_guidance`

이번 단계 기준:

- [ ] connector 없으면 `capability_gap`
- [ ] retrieval로 잘못 fallback하지 않음

---

## Task 10: Regression Suite

- [ ] planner unit tests
- [ ] handler unit tests
- [ ] orchestrator utility path tests
- [ ] frontend state regression tests
- [ ] fixture 추가

필수 회귀 시나리오:

- [ ] `오늘 며칠이야`
- [ ] `뉴욕 지금 몇 시`
- [ ] `420의 15%`
- [ ] `무엇을 할 수 있어?`
- [ ] `README 열어줘`
- [ ] `day_chart 테이블의 컬럼 정보 보여줘`
- [ ] utility task 후 `Documents -> Repository` 루프 없음

---

## Rollout Order

1. Response contract
2. Planner classification
3. BasicTaskRouter
4. P0 deterministic handlers
5. Orchestrator short-circuit
6. Frontend utility renderer
7. Open document / recent context
8. Live capability gap handling
9. Regression suite

---

## Exit Condition

아래 5개가 모두 만족되면 1차 완료로 본다.

1. `오늘 며칠이야`가 utility result로 처리된다.
2. utility result는 `artifacts=[]`, `citations=[]`이다.
3. utility result 후 Repository/Documents 루프가 없다.
4. `README 열어줘`는 실제 문서를 연다.
5. `무엇을 할 수 있어?`가 capability registry 기반으로 답한다.
