# Intent Skill Registry Design

## 결론

질문별 하드코딩을 계속 늘리는 방향은 맞지 않다.  
맞는 구조는 아래 4단계다.

1. `intent/skill registry`
2. `router/planner`
3. `session memory`
4. `automation + behavior log`

즉, LLM은 "무슨 요구인가"를 판정하는 계층이고, 실제 실행 가능성은 `registry`가 결정해야 한다.

## 왜 registry가 필요한가

현재 구조는 built-in capability가 늘어날수록 코드 안의 정규식과 분기문이 커진다.  
이 방식은 초기 속도는 빠르지만, 아래 문제가 생긴다.

- 지원 범위를 한눈에 보기 어렵다.
- 어떤 intent가 구현되었고 무엇이 미구현인지 추적이 어렵다.
- 동일 intent의 변형 질의를 테스트 자산으로 연결하기 어렵다.
- live capability와 retrieval capability를 분리해 운영하기 어렵다.
- 행동 로그를 어떤 단위로 수집할지 불명확하다.

registry가 있으면 최소한 아래가 가능해진다.

- `사용자 질의 -> intent -> skill -> executor` 경로를 명시적으로 관리
- 구현 상태 `implemented / implemented_gap / planned` 분리
- 세션에 남길 context key 정의
- automation 후보군 식별
- 미구현 요구를 `planned intent`로 축적

## 권장 아키텍처

### 1. Registry

registry는 단순 문서가 아니라 실행 메타데이터여야 한다.

필수 필드:

- `intent_id`
- `skill_id`
- `category`
- `executor`
- `response_kind`
- `requires_retrieval`
- `requires_live_data`
- `stores_context`
- `automation_ready`
- `implementation_status`
- `example_queries`

### 2. Router

router의 책임은 하나다.

- 입력 질의를 registry에 있는 intent 후보로 정규화

여기서 LLM은 자유 생성기가 아니라 `candidate ranking` 역할을 맡아야 한다.
즉, 전체 답을 만들기보다 registry 항목 중 어느 intent에 가장 가깝나를 판정하는 쪽이 안정적이다.

### 3. Session Memory

session memory는 문서만 기억하면 부족하다.  
아래와 같이 intent별 state key를 분리해야 한다.

- `last_relative_date`
- `last_calendar_date`
- `active_target`
- `recent_targets`
- `last_sheet_index`
- `last_section_index`
- `last_action_result`

이 레이어가 있어야:

- `그날 일정 잡아줘`
- `그 문서 다시 열어줘`
- `다음 슬라이드 보여줘`

같은 follow-up이 가능하다.

### 4. Behavior Log

실사용 데이터는 `학습 데이터` 이전에 `behavior log`로 먼저 쌓는 게 맞다.

기록 단위 예시:

- `timestamp`
- `session_id`
- `raw_query`
- `resolved_intent`
- `resolved_skill`
- `resolved_executor`
- `resolution_status`
- `clarification_required`
- `user_confirmed`
- `completed`

여기서 바로 모델 재학습으로 가는 것은 이르다.  
먼저 해야 할 것은 아래다.

- 어떤 intent가 자주 나오나
- 어떤 시간대/요일에 어떤 요청이 반복되나
- 어떤 intent가 미구현 때문에 실패하나
- 어떤 follow-up 패턴이 많이 발생하나

즉, 1차 목적은 `analytics + automation candidate discovery`다.

## proactive AI로 가는 단계

사용자가 요구하지 않아도 알아서 해 주는 AI는 가능하지만, 바로 모델 학습으로 가지 않는 편이 맞다.

권장 순서는 아래다.

1. `intent/skill registry` 고정
2. `behavior log` 축적
3. `recurring pattern detector` 추가
4. `proposal engine` 추가
5. 마지막에만 `auto-execute with confirmation`

예:

- 금요일 오후에 반복적으로 식재료 정리 요청
- 매주 월요일 오전에 특정 회의 일정 조회
- 특정 문서를 연 뒤 항상 요약과 목차를 요청

이런 패턴은 먼저 아래처럼 제안형으로 가야 한다.

- "지난 4주 동안 금요일 오후에 장보기 관련 요청이 반복되었습니다. 이번 주 식재료 주문 초안을 만들까요?"
- "월요일 오전 회의 준비가 반복됩니다. 다음 주 브리핑을 미리 생성할까요?"

즉, 초기 proactive는 `자동 실행`이 아니라 `정확한 제안`이 맞다.

## 이번 초안

이번에 추가한 산출물:

- `intent_skill_map.v1.json`
- `intent_skill_registry.py`

이 파일은 아직 runtime dispatch의 source of truth는 아니다.  
하지만 이제부터는 신규 skill을 추가할 때 먼저 registry에 entry를 만들고, 그 다음 executor를 구현하는 순서로 바꾸는 기준점이 된다.

## 다음 단계

1. `resolve_builtin_capability()` 앞단에서 registry를 읽는 layer 추가
2. `planned` intent를 별도 로그로 적재
3. `implemented_gap` intent를 UI에서 구분 표시
4. `behavior log` 스키마 추가
5. `추천/제안 엔진` 초안 추가
