# Basic Task Layer Design

**Date:** 2026-04-04
**Status:** Proposed
**Scope:** 문서 RAG와 분리된 기본 작업 계층 설계, 응답 계약 분리, 프론트/백엔드 처리 규칙 정리

---

## 1. 문제 정의

현재 구조는 대부분의 질의를 `retrieval + artifacts + citations + presentation` 흐름으로 처리한다.

이 구조는 문서 기반 질의에는 적합하지만 아래와 같은 기본 작업에는 맞지 않는다.

1. `오늘 며칠이야`
2. `지금 몇 시야`
3. `뉴욕 지금 몇 시`
4. `420의 15%는?`
5. `무엇을 할 수 있어?`
6. `백엔드 상태 보여줘`
7. `README 열어줘`

이런 요청은 근거 문서가 없거나, 문서가 있더라도 retrieval보다 deterministic handler가 우선되어야 한다.  
문서가 없는 작업까지 artifact/citation으로 포장하면 다음 문제가 반복된다.

1. pseudo artifact 생성
2. Repository/Documents 상태 오염
3. 선택 루프와 뷰 전환 불안정
4. 질문별 하드코딩 누적

따라서 `기본 작업 = 문서 RAG의 하위 케이스`가 아니라, 별도 실행 계층으로 분리해야 한다.

---

## 2. 설계 원칙

1. 문서가 없는 작업은 절대 문서처럼 보이지 않아야 한다.
2. deterministic하게 처리 가능한 작업은 LLM보다 handler를 우선한다.
3. live connector가 필요한 작업은 capability 상태를 먼저 점검한다.
4. retrieval이 필요한 작업만 artifacts/citations/presentation을 생성한다.
5. 프론트는 `answer.kind` 기준으로 UI를 나눠 그린다.

---

## 3. 기본 작업 분류

### P0: 즉시 지원해야 하는 작업

| task_id | 예시 질의 | 처리 방식 | artifacts/citations |
|---|---|---|---|
| `datetime_now` | `오늘 며칠이야`, `지금 몇 시야`, `오늘 무슨 요일이야` | 로컬 시간 계산 | 없음 |
| `timezone_now` | `뉴욕 지금 몇 시`, `런던 시간 알려줘` | IANA timezone 변환 | 없음 |
| `date_arithmetic` | `3일 뒤 날짜`, `다음 주 월요일은?` | 날짜 계산 | 없음 |
| `math_eval` | `420의 15%`, `34*18`, `1.2GB의 10%` | safe math evaluator | 없음 |
| `unit_convert` | `10MB는 몇 KB`, `3km는 몇 m` | 변환 테이블 | 없음 |
| `capability_help` | `무엇을 할 수 있어?`, `예시 질문 보여줘` | capability registry | 없음 |
| `runtime_status` | `백엔드 상태`, `현재 모델`, `인덱스 상태` | runtime state 조회 | 없음 |
| `open_target` | `깃허브 열어줘`, `사파리 켜줘` | action resolver | 없음 |
| `open_document` | `README 열어줘`, `브로셔 보여줘` | 파일 매칭 후 artifact 선택 | 있음 |
| `doc_summary` | `이 문서 요약`, `이 파일 요약` | selected artifact 우선 처리 | 문서가 있으면 있음 |
| `doc_outline` | `목차 보여줘`, `슬라이드 제목만` | parser 기반 추출 | 문서가 있으면 있음 |
| `table_basic` | `3일차 아침`, `컬럼 정보`, `sheet 목록` | structured parser | 있음 |
| `recent_context` | `방금 본 문서`, `최근 근거 다시` | session recall | 문서가 있으면 있음 |
| `clarify_target` | `뉴욕 문서? 시간대?` | clarification first | 없음 |

### P1: connector 또는 외부 capability가 필요한 작업

| task_id | 예시 질의 | 처리 방식 | 현재 상태 |
|---|---|---|---|
| `calendar_today` | `오늘 일정`, `다음 회의` | calendar connector | 미연결 시 gap |
| `weather_now` | `오늘 서울 날씨` | weather capability | 현재 gap |
| `route_guidance` | `강남역 가는 길` | maps/route capability | 현재 미구현 |

---

## 4. QueryAnalysis 확장

현재 planner는 `intent`, `retrieval_task`, `entities`, `search_terms` 중심이다.  
기본 작업 레이어를 위해 아래 필드를 추가한다.

```python
@dataclass
class QueryAnalysis:
    intent: str
    retrieval_task: str
    basic_task: str = ""
    capability: str = ""
    requires_retrieval: bool = True
    requires_live_data: bool = False
    response_kind: str = "retrieval_result"
    entities: dict[str, object] = field(default_factory=dict)
    search_terms: list[str] = field(default_factory=list)
```

### 필드 의미

| 필드 | 의미 |
|---|---|
| `basic_task` | `datetime_now`, `math_eval` 같은 구체 task id |
| `capability` | `calendar`, `weather`, `runtime_state` 등 handler 분류 |
| `requires_retrieval` | 문서 검색이 필요한지 여부 |
| `requires_live_data` | 외부/실시간 상태가 필요한지 여부 |
| `response_kind` | 프론트 렌더링 타입 |

---

## 5. Router 구조

새 모듈:

```text
alliance_20260317_130542/src/jarvis/core/basic_task_router.py
```

역할:

1. query를 `basic_task`로 정규화
2. deterministic handler 선택
3. connector 필요 여부 판정
4. fallback이 필요한 경우에만 retrieval로 넘김

### 권장 실행 순서

1. `smalltalk`
2. `basic_task`
3. `action`
4. `live_data_request`
5. `retrieval`

즉, orchestrator는 retrieval 전에 `basic_task_router`를 먼저 타야 한다.

---

## 6. Handler 설계

### Deterministic handler

새 모듈 예시:

```text
jarvis/core/basic_tasks/
├── datetime_handler.py
├── math_handler.py
├── unit_handler.py
├── runtime_status_handler.py
├── help_handler.py
├── context_handler.py
└── dispatcher.py
```

### handler 인터페이스

```python
@dataclass
class BasicTaskResult:
    task_id: str
    response_kind: str
    text: str
    spoken_text: str
    structured_payload: dict[str, object]
    artifacts: list[dict[str, object]]
    citations: list[dict[str, object]]
    presentation: dict[str, object] | None
    ui_hints: dict[str, object]
```

### 규칙

1. `datetime_now`, `timezone_now`, `math_eval`, `unit_convert`, `runtime_status`, `capability_help`
   `artifacts=[]`, `citations=[]`, `presentation=None`
2. `open_document`, `doc_summary`, `doc_outline`, `table_basic`, `recent_context`
   실제 문서 대상이 있을 때만 artifact 생성
3. `weather_now`, `calendar_today`, `route_guidance`
   connector 없으면 `capability_gap` 반환

---

## 7. 응답 계약

현재 프론트는 대부분의 응답을 문서형 결과처럼 저장한다.  
이 계약을 아래처럼 명시적으로 분리한다.

### Answer 확장

```typescript
interface Answer {
  text: string;
  spoken_text: string;
  has_evidence: boolean;
  citation_count: number;
  kind: 'utility_result' | 'action_result' | 'live_data_result' | 'retrieval_result' | 'capability_gap';
  task_id?: string;
  structured_payload?: Record<string, unknown>;
  full_response_path?: string;
}
```

### GuideDirective 확장

```typescript
interface GuideDirective {
  ...
  ui_hints?: {
    show_documents: boolean;
    show_repository: boolean;
    show_inspector: boolean;
    preferred_view?: 'dashboard' | 'detail_viewer' | 'repository' | 'admin';
  };
}
```

### 필수 규칙

| `answer.kind` | `guide.artifacts` | `response.citations` | Documents/Repository |
|---|---|---|---|
| `utility_result` | `[]` | `[]` | 비활성 또는 유지 |
| `action_result` | `[]` | `[]` | 비활성 |
| `live_data_result` | 기본 `[]` | `[]` 또는 connector source | 비활성 |
| `capability_gap` | `[]` | `[]` | 비활성 |
| `retrieval_result` | 실제 결과만 | 실제 근거만 | 활성 |

이 규칙이 핵심이다.  
`오늘 며칠이야` 같은 질문은 절대 날짜 리스트를 artifact처럼 내려보내면 안 된다.

---

## 8. 프론트 처리 방식

### useJarvis

현재는 응답이 오면 거의 무조건 `citations`, `assets`, `presentation`을 store에 넣는다.  
앞으로는 `answer.kind` 기준으로 분기한다.

```typescript
if (response.answer.kind === 'retrieval_result') {
  setCitations(...)
  setAssets(...)
  setPresentation(...)
} else {
  setCitations([])
  setAssets([])
  setPresentation(null)
}
```

### TerminalWorkspace

utility/live-data/action 응답은 문서형 블록이 아니라 전용 카드로 렌더링한다.

예시:

- `datetime_now` → 날짜/시간 카드
- `math_eval` → 계산 결과 카드
- `runtime_status` → 시스템 상태 카드
- `capability_help` → 지원 기능 목록 카드

### Repository / Documents 활성화 규칙

1. `answer.kind !== 'retrieval_result'` 이면 문서 화면 자동 진입 금지
2. `assets.length === 0` 이면 repository 상세 선택 동기화 금지
3. `selectedArtifact`는 실제 파일 경로가 있는 artifact에만 설정

---

## 9. 개발 단계

### Phase 1

1. 응답 계약 확장
2. `basic_task_router` 추가
3. `datetime_now`, `timezone_now`, `date_arithmetic`, `math_eval`, `unit_convert`
4. `runtime_status`, `capability_help`
5. 프론트 utility renderer

### Phase 2

1. `open_document`
2. `recent_context`
3. `doc_summary`
4. `doc_outline`
5. `table_basic`

### Phase 3

1. `calendar_today`
2. `weather_now`
3. `route_guidance`

---

## 10. 테스트 매트릭스

| task_id | 테스트 입력 | 기대 결과 |
|---|---|---|
| `datetime_now` | `오늘 며칠이야` | 절대 날짜 포함, artifacts 없음 |
| `timezone_now` | `뉴욕 지금 몇 시` | KST와 구분된 시간대 응답, artifacts 없음 |
| `date_arithmetic` | `3일 뒤 날짜` | 올바른 날짜 계산 |
| `math_eval` | `420의 15%` | `63` |
| `unit_convert` | `10MB는 몇 KB` | 변환 수치 |
| `capability_help` | `무엇을 할 수 있어?` | capability registry 기반 목록 |
| `runtime_status` | `현재 모델 뭐야` | runtime state 카드 |
| `open_target` | `깃허브 열어줘` | action result |
| `open_document` | `README 열어줘` | 실제 artifact 선택 |
| `doc_outline` | `슬라이드 제목만` | outline block |
| `table_basic` | `day_chart 컬럼` | structured schema 응답 |

### 회귀 방지 테스트

1. utility task는 `artifacts=[]`, `citations=[]`
2. utility task 후 `Repository` 진입 시 선택 루프가 발생하지 않음
3. `Documents -> Repository -> Documents` 전환에서 pseudo artifact가 생기지 않음
4. live capability 미연결 시 문서 검색으로 잘못 fallback하지 않음

---

## 11. 비목표

이번 단계에서 하지 않는 것:

1. 자유 형식 agent tool use 일반화
2. 외부 SaaS 전체 통합
3. 장문 planning agent 설계
4. 모든 질문을 LLM planner로만 판단하는 구조

기본 작업은 먼저 deterministic하고 안전하게 처리해야 한다.
