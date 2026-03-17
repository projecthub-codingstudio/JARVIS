# Alliance 코딩 지시용 구현 명세서

**문서 유형**: 기술 아키텍처 문서  
**회사**: Colligi2  
**프로젝트**: Alliance 코딩 지시용 구현 명세서  
**버전**: 1.0  
**작성일**: 2026-03-16  

---

## 1. 문서 헤더

- 회사: Colligi2
- 프로젝트: Alliance 코딩 지시용 구현 명세서
- 문서 제목: Alliance 코딩 지시용 구현 명세서
- 문서 유형: 기술 아키텍처 및 구현 명세서
- 버전: 1.0
- 대상 환경: MacBook Pro 16, Apple M1 Max, 통합 메모리 64GB
- 기준 시각: 2026-03-16 Asia/Seoul

## 2. 문서 목적 및 최종 의사결정

본 문서는 Colligi2의 Alliance 코딩 지시용 구현 명세서를 위해 Alliance가 추가 분석 없이 즉시 구현을 시작할 수 있도록 만든 `결정 폐쇄형 구현 명세서`다. 목적은 가능성 탐색이 아니라, 무엇을 먼저 만들고 어떤 구조로 나누며 어떤 기준으로 검증할지를 코드 수준으로 고정하는 것이다.

최종 결정은 다음과 같다.

- 제품 정의는 `로컬 퍼스트 개인 워크스페이스 에이전트`로 고정한다.
- MVP 범위는 `선택 폴더 인덱싱`, `문서·코드 하이브리드 검색`, `인용 기반 한국어 질의응답`, `초안 생성`, `승인형 제한 내보내기`까지로 제한한다.
- 기본 런타임은 `MLX`, 기본 한국어 처리는 `Kiwi`, 검색은 `SQLite FTS5 + 벡터 인덱스 + RRF`, 기본 생성 계층은 `14B급 모델`로 고정한다.
- 생성은 `Evidence-First Generation`으로 구현한다. 즉, LLM은 자유 생성기가 아니라 `검증된 근거 집합을 해설하는 모듈`로 취급한다.
- 검색은 단일 문자열 매칭이 아니라 `질의 분해(Query Decomposition)`를 선행한다.
- Governor는 부가 기능이 아니라 `시스템 운영 헌법`이다. 메모리를 고정 예산으로 다루지 않고, OS 압박 신호에 반응하는 행동 계약으로 다룬다.
- 보안은 사후 차단보다 `Capability-based Security`로 구현한다. 위험한 도구는 승인 엔진으로 복잡하게 통제하기보다 MVP API 표면에서 제거한다.
- 음성, 상시 화면 문맥, 접근성 기반 UI 자동화, 일반 셸 자율 실행, Full Disk Access 기본 요구는 제외한다.

## 3. 해결할 문제의 재정의

원 질문은 “기존 JARVIS 기술문서를 구현 명세서로 구체화해 달라”였지만, 실제 구현 관점에서의 문제는 다음과 같다.

`Alliance가 다시 비교·탐색 모드로 빠지지 않고, 단일 구현 경로를 따라 코드를 작성할 수 있도록 닫힌 의사결정과 실행 가능한 계약을 제공하는 것`

따라서 이 문서는 다음 원칙을 따른다.

- 열린 비교를 남기지 않는다.
- 기본 구현은 하나만 둔다.
- 교체 가능성은 인터페이스로만 남긴다.
- prose보다 `Protocol`, `Dataclass`, `DDL`, `pytest`, `메트릭 계약`을 우선한다.
- 인간의 승인 책임과 Alliance의 구현 책임을 분리한다.

## 4. 제품 범위

### 4.1 MVP 포함 범위

- 선택 폴더 기반 읽기 전용 인덱싱
- Markdown, 텍스트, 코드, 로그 파일 파싱
- 문서·코드 통합 하이브리드 검색
- 한국어 질의응답
- 파일 경로 및 라인 기준 인용
- 초안 생성
- 승인형 `draft_export`
- 대화 로그 및 작업 로그 저장
- 증분 인덱싱과 최신성 상태 반영
- CLI REPL 기반 인터페이스

### 4.2 MVP 제외 범위

- 음성 입출력
- 상시 화면 수집
- 접근성 기반 범용 UI 자동화
- 일반 셸 명령 자율 실행
- 외부 서비스 기본 의존
- 전체 디스크 인덱싱
- Full Disk Access 기본 요구
- 메일·Finder·브라우저 광범위 자동화
- 30B+ 모델 상시 상주

## 5. 원본 기술문서 대비 변경 결정 로그

원본 JARVIS 기술문서는 방향성과 리스크 인식은 강했지만, 구현자가 다시 선택해야 하는 항목이 많았다. 본 명세서는 다음 항목을 닫았다.

| 항목 | 원본 문서 상태 | 최종 결정 |
|---|---|---|
| 생성 모델 | 14B/7.8B/30B 후보 비교 | `14B급 기본 계층`으로 고정, 상위 모델은 Phase 2 이후 명시 승격만 허용 |
| 한국어 처리 | Kiwi 또는 MeCab-ko 비교 | `Kiwi 기본`으로 고정, MeCab-ko는 재진입 조건 충족 시 교체 경로만 유지 |
| 검색 품질 전략 | 하이브리드 검색 채택, 질의 처리 구체성 부족 | `Typed Query Decomposition + FTS5 + 벡터 + RRF`로 구체화 |
| 인용 방식 | 사후 보정 중심 표현 일부 존재 | `VerifiedEvidenceSet 입력 강제`로 변경 |
| 보안 | 승인형 실행 원칙 중심 | `위험 도구 비노출`을 1차 보안 구조로 채택 |
| 인터페이스 | CLI 이후 메뉴바 UI | MVP는 `CLI REPL`로 고정 |
| 스키마 | 테이블명 수준 제안 | 핵심 컬럼과 제약 조건 포함 DDL 계약으로 구체화 |
| 관측성 | 별도 계층 언급 | `observability/` 모듈과 필수 메트릭 계약 추가 |
| 실패 운영 | 실패 기준과 중단 기준 제시 | 런타임 예외, 인덱스 손상, SQLite 락, 모델 로드 실패 대응 절차까지 확장 |

## Colligi2 생성 과정

이 문서는 단일 AI가 한 번에 작성한 결과가 아니라, 여러 AI가 같은 주제를 교차 검증하며 단계적으로 생성한 집단지성 산출물이다.

1. **의도 재구성**: 사용자의 표면 요청 뒤에 있는 실제 목표, 숨은 제약, 검증이 필요한 질문을 재구성했다.
2. **단계 설계**: 여러 AI가 독립적으로 분석 단계를 제안하고, 연구 및 병합 과정을 거쳐 최종 분석 구조를 설계했다.
3. **다단계 토론**: 각 분석 단계에서 AI들이 의견, 평가, 반론을 주고받으며 쟁점과 대안을 정리했다.
4. **창발 통합**: 단계별 결과를 단순 요약하지 않고, 충돌 지점과 새로운 통찰을 집단적으로 합성했다.
5. **문제 재정의**: 원래 질문이 충분히 정확한지 다시 점검하고, 더 본질적인 문제 정의로 보정했다.
6. **문서 집단 작성**: 여러 초안과 리뷰를 교차 검토한 뒤, 최종 문서를 통합 편집했다.

- 참여 AI 수: 4
- 최종 분석 단계 수: 14
- 총 토론 라운드 수: 20
- 중간 실패로 제외된 provider 기록 수: 0

## 6. 아키텍처 불변식

다음 항목은 구현 중 재해석하지 않는다.

- 모든 사실성 응답은 `VerifiedEvidenceSet` 없이 생성하지 않는다.
- 검색은 항상 `질의 분해 결과`를 입력으로 사용한다.
- 쓰기 작업은 `draft_export` 하나만 허용한다.
- `draft_export`는 승인 없이 실행되지 않는다.
- Governor는 초기에는 Stub이어도 인터페이스는 Day 0에 고정한다.
- 인용 상태는 `VALID`, `STALE`, `REINDEXING`, `MISSING`, `ACCESS_LOST` 다섯 상태만 사용한다.
- 파일 시스템 최신성 문제는 부가 기능이 아니라 핵심 신뢰 기능으로 취급한다.
- 관측 불가능한 기능은 완료된 기능으로 간주하지 않는다.

## 7. 구현 아키텍처

### 7.1 목표 저장소 구조

```text
pyproject.toml
src/jarvis/
  app/
    bootstrap.py
    config.py
  contracts/
    models.py
    protocols.py
    states.py
    errors.py
  core/
    orchestrator.py
    governor.py
    planner.py
    tool_registry.py
  retrieval/
    query_decomposer.py
    tokenizer_kiwi.py
    fts_index.py
    vector_index.py
    hybrid_search.py
    evidence_builder.py
    freshness.py
  indexing/
    parsers.py
    chunker.py
    file_watcher.py
    index_pipeline.py
    tombstone.py
  runtime/
    mlx_runtime.py
    model_router.py
    embedding_runtime.py
  memory/
    conversation_store.py
    task_log.py
  tools/
    read_file.py
    search_files.py
    draft_export.py
  observability/
    metrics.py
    tracing.py
    health.py
  cli/
    repl.py
    approval.py
sql/
  schema.sql
tests/
  contracts/
  unit/
  integration/
  retrieval/
  indexing/
  runtime/
  perf/
  e2e/
docs/
  DECISIONS.md
  IMPLEMENTATION_PLAN.md
```

### 7.2 컴포넌트 책임

| 컴포넌트 | 책임 | 입력 | 출력 |
|---|---|---|---|
| `Orchestrator` | 전체 요청 흐름 제어 | 사용자 질의, 세션 상태 | 응답, 인용, 실행 계획 |
| `QueryDecomposer` | 질의를 심볼/리터럴/산문 조각으로 분해 | 원문 질의 | `TypedQueryFragment[]` |
| `HybridSearch` | FTS5, 벡터, RRF 결합 | `TypedQueryFragment[]` | `RankedChunk[]` |
| `EvidenceBuilder` | 검증된 증거 집합 구성 | `RankedChunk[]` | `VerifiedEvidenceSet` |
| `FreshnessManager` | 인용 상태 계산 | 파일 이벤트, 인덱스 상태 | `CitationState` |
| `ModelRouter` | Governor 상태에 따른 모델 티어 선택 | 요청 유형, 시스템 상태 | `RuntimeProfile` |
| `MLXRuntime` | 생성 및 임베딩 실행 | 프롬프트, 증거 집합 | 생성 결과 |
| `IndexPipeline` | 파싱, 청킹, 인덱스 반영 | 파일 이벤트 | 인덱스 변경 결과 |
| `ToolRegistry` | 허용 도구만 노출 | 승인 상태 | 도구 핸들 |
| `ApprovalCLI` | 승인형 초안 생성 UX | 계획, diff, 대상 경로 | 승인/거부 결과 |
| `MetricsCollector` | 메트릭 수집 | 런타임 이벤트 | 시계열 지표 |

## 8. 실행 가능한 계약

### 8.1 필수 Protocol

- `TokenizerProtocol`
- `QueryDecomposerProtocol`
- `RetrieverProtocol`
- `EvidenceBuilderProtocol`
- `RuntimeProtocol`
- `GovernorProtocol`
- `ToolProtocol`
- `MetricsProtocol`

### 8.2 필수 Dataclass

- `UserQuery`
- `TypedQueryFragment`
- `ChunkRecord`
- `RankedChunk`
- `VerifiedEvidence`
- `VerifiedEvidenceSet`
- `CitationRef`
- `AssistantResponse`
- `RuntimeProfile`
- `SystemSnapshot`
- `DraftExportPlan`
- `ApprovalDecision`

### 8.3 핵심 타입 규약

```python
@dataclass
class TypedQueryFragment:
    kind: Literal["symbol", "literal", "prose"]
    text: str
    normalized: str
    weight: float

@dataclass
class CitationRef:
    document_id: str
    chunk_id: str
    file_path: str
    start_line: int
    end_line: int
    state: Literal["VALID", "STALE", "REINDEXING", "MISSING", "ACCESS_LOST"]

@dataclass
class VerifiedEvidence:
    chunk_id: str
    file_path: str
    content: str
    content_hash: str
    start_line: int
    end_line: int
    score_lexical: float
    score_semantic: float
    score_rrf: float
    citation_state: str

@dataclass
class RuntimeProfile:
    tier: Literal["baseline", "elevated", "degraded"]
    max_context_tokens: int
    max_retrieved_chunks: int
    generation_timeout_ms: int
```

### 8.4 인터페이스 원칙

- LLM 입력은 `질문 + VerifiedEvidenceSet + 응답 포맷 규약`으로 제한한다.
- `VerifiedEvidence`에는 최소 `content_hash`, `line range`, `citation_state`를 포함한다.
- 검색은 항상 `TypedQueryFragment[]`를 받는다. 원문 문자열을 직접 넘기지 않는다.
- Governor는 초기에는 순수 함수 `SystemSnapshot -> RuntimeProfile`로 구현한다.
- 메모리는 고정 할당이 아니라 OS 압박 신호에 따른 행동 계약으로 다룬다.
- 도구는 `ToolRegistry` 등록 목록만 호출할 수 있다.
- Phase 1 도구는 `read_file`, `search_files`, `draft_export` 세 개만 허용한다.

## 9. 데이터 모델 및 DDL 계약

다음 스키마는 Day 0에 `sql/schema.sql`로 구현해야 하는 최소 계약이다.

### 9.1 `documents`

| 컬럼 | 타입 | 제약 | 설명 |
|---|---|---|---|
| `document_id` | TEXT | PK | 문서 식별자 |
| `file_path` | TEXT | UNIQUE NOT NULL | 절대 경로 |
| `file_type` | TEXT | NOT NULL | md, py, txt 등 |
| `file_size` | INTEGER | NOT NULL | 바이트 |
| `mtime_epoch_ms` | INTEGER | NOT NULL | 수정 시각 |
| `content_hash` | TEXT | NOT NULL | 파일 해시 |
| `index_state` | TEXT | NOT NULL | ACTIVE, DELETED, ACCESS_LOST |
| `last_indexed_at` | INTEGER | NOT NULL | 마지막 색인 시각 |

### 9.2 `chunks`

| 컬럼 | 타입 | 제약 | 설명 |
|---|---|---|---|
| `chunk_id` | TEXT | PK | 청크 식별자 |
| `document_id` | TEXT | FK NOT NULL | 문서 참조 |
| `chunk_order` | INTEGER | NOT NULL | 문서 내 순서 |
| `start_offset` | INTEGER | NOT NULL | 문자 시작 오프셋 |
| `end_offset` | INTEGER | NOT NULL | 문자 종료 오프셋 |
| `start_line` | INTEGER | NOT NULL | 시작 라인 |
| `end_line` | INTEGER | NOT NULL | 종료 라인 |
| `content` | TEXT | NOT NULL | 청크 원문 |
| `content_hash` | TEXT | NOT NULL | 청크 해시 |
| `embedding_ref` | TEXT | NULL | 벡터 저장 참조 |
| `citation_state` | TEXT | NOT NULL | VALID, STALE 등 |
| `created_at` | INTEGER | NOT NULL | 생성 시각 |

### 9.3 `citations`

| 컬럼 | 타입 | 제약 | 설명 |
|---|---|---|---|
| `citation_id` | TEXT | PK | 인용 식별자 |
| `response_id` | TEXT | NOT NULL | 응답 식별자 |
| `chunk_id` | TEXT | FK NOT NULL | 참조 청크 |
| `file_path` | TEXT | NOT NULL | 파일 경로 |
| `start_line` | INTEGER | NOT NULL | 시작 라인 |
| `end_line` | INTEGER | NOT NULL | 종료 라인 |
| `quoted_hash` | TEXT | NOT NULL | 당시 인용 해시 |
| `citation_state` | TEXT | NOT NULL | VALID, STALE 등 |
| `created_at` | INTEGER | NOT NULL | 생성 시각 |

### 9.4 `conversation_turns`

| 컬럼 | 타입 | 제약 | 설명 |
|---|---|---|---|
| `turn_id` | TEXT | PK | 턴 식별자 |
| `session_id` | TEXT | NOT NULL | 세션 식별자 |
| `role` | TEXT | NOT NULL | user, assistant |
| `content` | TEXT | NOT NULL | 본문 |
| `response_id` | TEXT | NULL | 응답 참조 |
| `created_at` | INTEGER | NOT NULL | 생성 시각 |

### 9.5 `task_logs`

| 컬럼 | 타입 | 제약 | 설명 |
|---|---|---|---|
| `task_id` | TEXT | PK | 작업 식별자 |
| `task_type` | TEXT | NOT NULL | search, answer, draft_export |
| `status` | TEXT | NOT NULL | STARTED, SUCCEEDED, FAILED, BLOCKED |
| `error_code` | TEXT | NULL | 오류 코드 |
| `latency_ms` | INTEGER | NULL | 처리 시간 |
| `metadata_json` | TEXT | NOT NULL | 부가 메타데이터 |
| `created_at` | INTEGER | NOT NULL | 생성 시각 |

### 9.6 FTS 및 보조 인덱스

- `chunk_terms_raw`: 식별자, 파일명, 에러 문자열 등 원문 토큰
- `chunk_terms_ko`: Kiwi 분석 결과 기반 한국어 토큰
- FTS5 인덱스는 `content`, `raw_terms`, `ko_terms`, `file_path`를 포함한다.

## 10. 검색 및 생성 파이프라인

### 10.1 질의응답 흐름

1. 사용자가 CLI에 한국어 질의를 입력한다.
2. `QueryDecomposer`가 질의를 `symbol`, `literal`, `prose`로 분해한다.
3. `HybridSearch`가 FTS5와 벡터 검색을 병렬 수행한다.
4. RRF로 상위 후보를 결합한다.
5. `FreshnessManager`가 각 청크의 `citation_state`를 계산한다.
6. `EvidenceBuilder`가 `VALID` 우선으로 `VerifiedEvidenceSet`을 구성한다.
7. `Governor`가 현재 시스템 상태에 맞는 `RuntimeProfile`을 선택한다.
8. `MLXRuntime`가 근거 집합만을 기반으로 답변을 생성한다.
9. 응답은 파일 경로와 라인 범위 인용을 포함해 출력한다.
10. 모든 단계는 메트릭과 `task_logs`에 기록한다.

### 10.2 승인형 초안 생성 흐름

1. 사용자가 “요약 초안 만들어줘” 또는 “문서 초안 저장해줘”를 요청한다.
2. `Planner`가 `DraftExportPlan`을 생성한다.
3. CLI는 다음 정보를 먼저 표시한다.
   - 대상 파일 경로
   - 파일이 신규 생성인지 덮어쓰기인지
   - 요약된 변경 내용
   - 초안 미리보기 20줄 또는 diff
4. 사용자에게 `approve [y/N]`를 묻는다.
5. 승인 시 `draft_export`만 실행한다.
6. 거부 시 파일 쓰기는 수행하지 않는다.
7. 결과는 `task_logs`와 `conversation_turns`에 남긴다.

### 10.3 `draft_export` 규약

- 허용 경로: 사용자가 지정한 작업 디렉토리 하위 `drafts/` 또는 명시 승인된 대상 파일
- 기본 출력 형식: UTF-8 텍스트 파일
- 기본 동작: 신규 파일 생성
- 덮어쓰기는 별도 승인 필요
- 외부 전송, 삭제, 이동은 불허

## 11. Governor 및 자원 운영 정책

Governor는 초기 MVP에서 Stub일 수 있지만, 인터페이스와 상태 전이는 고정한다.

### 11.1 입력 지표

- memory pressure
- swap 사용량
- CPU 사용률
- thermal state
- 전원 연결 여부
- 배터리 잔량
- 인덱싱 큐 길이
- 모델 로드 성공/실패 상태

### 11.2 상태

- `baseline`: 정상 응답 모드
- `elevated`: 전원 연결 + 여유 자원 상태
- `degraded`: 메모리 압박, 배터리 저하, 고발열, 반복 오류 상태

### 11.3 동작 규칙

| 상태 | 모델 | 검색 청크 수 | 컨텍스트 | 인덱싱 |
|---|---|---|---|---|
| `elevated` | 기본 14B, 필요 시 상위 승격 가능 | 10 | 최대 | 적극 수행 |
| `baseline` | 기본 14B | 8 | 표준 | 저우선순위 |
| `degraded` | 기본 14B 유지 또는 축소 | 4 | 축소 | 일시 중지 또는 백오프 |

### 11.4 강제 축소 조건

- swap 발생 감지 시 상위 모델 승격 금지
- thermal state 상승 시 인덱싱 백오프
- 배터리 30% 이하 시 긴 컨텍스트 금지
- 모델 로드 2회 연속 실패 시 degraded 진입
- SQLite 락 3회 연속 발생 시 쓰기 큐 중단

## 12. 보안 및 권한 설계

### 12.1 권한 사다리

1. 수동 텍스트 입력만
2. 선택 폴더 읽기
3. 제한적 `draft_export`
4. 제한적 앱 연동
5. 접근성 기반 자동화

MVP는 2~3단계까지만 구현한다.

### 12.2 Capability 기반 제약

- `read_file`: 읽기 전용
- `search_files`: 인덱스 질의 전용
- `draft_export`: 승인형 파일 생성/덮어쓰기 제한
- 삭제, 이동, 실행, 외부 전송 도구는 등록하지 않는다

### 12.3 안전 정책

- 인용 없는 사실성 단정 금지
- `STALE` 또는 `MISSING` 인용은 답변에서 경고 표시
- 승인 없는 상태 변경 0건
- 지정 폴더 밖 경로 접근 금지
- 연속 오류 임계치 초과 시 도구 전체 정지

## 13. 실패 모드 및 예외 처리

정상 흐름만 구현해서는 실사용 시스템이 되지 않는다. 다음 실패 모드를 명시적으로 처리한다.

### 13.1 모델 로드 실패

- 증상: MLX 모델 초기화 실패, 메모리 부족, 파일 손상
- 대응:
  - 1회: 자동 재시도
  - 2회 연속: `degraded` 진입
  - 3회 연속: 생성 기능 차단, 검색 전용 모드 전환
- 사용자 메시지: 생성 모델을 임시 비활성화하고 검색 결과만 제공

### 13.2 SQLite 락 또는 인덱스 손상

- 증상: `database is locked`, 무결성 오류
- 대응:
  - 읽기 질의는 즉시 재시도 1회
  - 쓰기 작업은 큐에 보류
  - 무결성 검사 실패 시 읽기 전용 모드 전환
  - `rebuild_index` 플래그를 세우고 사용자에게 재색인 권고
- Hard Kill 조건: 락 반복 3회 + 쓰기 대기열 증가 지속

### 13.3 임베딩 백로그 폭증

- 증상: 파일 변경이 잦아 재임베딩 지연 증가
- 대응:
  - 최근 수정 파일 우선
  - 대용량 파일 지연
  - `STALE` 경고와 함께 기존 색인 사용
  - 배터리 모드에서는 큐 축소

### 13.4 파일 접근 권한 상실

- 증상: 선택 폴더 이동, 권한 해제, 외장 드라이브 분리
- 대응:
  - `ACCESS_LOST` 상태로 전환
  - 해당 문서 인용 비활성화
  - 사용자에게 권한 복구 안내

### 13.5 연속 오류 임계치

- 5분 내 동일 오류 코드 5회 이상 발생 시 도구 호출 중단
- 10분 내 모델 실패 + 인덱스 실패가 동시에 발생 시 `safe mode` 전환
- `safe mode`에서는 검색 결과만 제공하고 생성 및 쓰기 비활성화

## 14. 관측성 및 운영 지표

### 14.1 필수 메트릭

- `query_latency_ms`
- `ttft_ms`
- `retrieval_top5_hit`
- `citation_missing_rate`
- `citation_stale_rate`
- `trust_recovery_time_ms`
- `index_lag_ms`
- `swap_detected_count`
- `model_load_failure_count`
- `sqlite_lock_count`
- `draft_export_approval_rate`

### 14.2 로그 원칙

- 구조화 로그(JSON) 사용
- `request_id`, `session_id`, `task_id` 필수
- 파일 내용 원문은 로그에 남기지 않는다
- 경로와 해시는 남기되 민감 본문은 제외한다

### 14.3 Health 체크

- 모델 가용성
- SQLite 무결성
- 인덱싱 큐 길이
- 최신성 지연
- 선택 폴더 접근 가능 여부

## 15. 테스트 전략

`pytest 통과`만으로는 부족하다. 테스트는 다섯 층으로 나눈다.

### 15.1 계약 테스트

- 위치: `tests/contracts/`
- 목적: Protocol, Dataclass, 상태 전이, DDL 호환성 검증
- 완료 조건: 모든 핵심 타입 직렬화 및 역직렬화 가능

### 15.2 단위 테스트

- 위치: `tests/unit/`
- 대상: `QueryDecomposer`, `EvidenceBuilder`, `Governor`, `FreshnessManager`
- 완료 조건: 정상/예외 케이스 포함 90% 이상 핵심 분기 커버

### 15.3 통합 테스트

- 위치: `tests/integration/`
- 대상: SQLite FTS, 벡터 인덱스, MLXRuntime 어댑터, 파일 감시 파이프라인
- 완료 조건: 샘플 코퍼스 기준 검색 및 인용 일관성 보장

### 15.4 성능 테스트

- 위치: `tests/perf/`
- 측정 항목:
  - TTFT
  - end-to-end latency
  - index lag
  - trust recovery time
  - batch indexing throughput
- 최소 인터페이스 예시:
  - `run_query_latency_bench(corpus_dir, queries_path) -> PerfReport`
  - `run_index_recovery_bench(file_path, mutation_count) -> PerfReport`

### 15.5 E2E 테스트

- 위치: `tests/e2e/`
- 흐름:
  - CLI 입력
  - 검색
  - 근거 조립
  - 생성
  - 인용 출력
  - 승인형 초안 생성
- 완료 조건: 실제 사용자 시나리오 5개 전부 통과

### 15.6 아키텍처 적합성 테스트

- 금지 규칙:
  - `tools/`에서 직접 `runtime/` 호출 금지
  - `runtime/`이 `cli/` 참조 금지
  - `retrieval/`이 `draft_export` 참조 금지
- 목적: Alliance가 구현 중 계층 경계를 무너뜨리지 못하게 자동 통제

## 16. 구현 순서 및 의존성 그래프

### 16.1 Phase 0: 부트스트랩

- `pyproject.toml`, 린트, 타입체크, 테스트 러너 구성
- `contracts/`, `schema.sql`, 기본 에러 코드 정의
- `observability/metrics.py`와 기본 이벤트 계약 작성
- 샘플 코퍼스와 50개 질의셋 생성
- 완료 조건:
  - 계약 테스트 통과
  - SQLite 스키마 생성 성공
  - 더미 런타임/더미 검색기로 E2E 스모크 통과

### 16.2 Phase 1: 수직 슬라이스

의존성 순서는 다음과 같다.

1. `CLI REPL`
2. `Orchestrator`
3. `QueryDecomposer`
4. `FTS5 + 벡터 인덱스`
5. `EvidenceBuilder`
6. `MLXRuntime`
7. `인용 출력`
8. `draft_export 승인 UX`

병렬 가능 범위는 제한한다.

- 병렬 가능: `contracts/`와 `schema.sql`, `metrics.py`와 `approval.py`
- 병렬 금지: `QueryDecomposer` 이전의 검색 구현 분기, `EvidenceBuilder` 이전의 생성 포맷 확장

### 16.3 Phase 2: 안정화

- Governor 실제 센서 연결
- FSEvents 기반 증분 인덱싱 최적화
- stale citation 복구 최적화
- 실패 모드 자동 전환 구현
- 메뉴바 UI는 선택 과제

## 17. 역할 분리 및 승인 체계

### 17.1 Alliance 책임

- 코드 작성
- 테스트 작성 및 통과
- 계약 위반 수정
- 관측성 이벤트 연결
- 예외 처리 경로 구현

### 17.2 인간 책임

- 모델 품질 최종 판정
- 검색 정확도 샘플셋 검증
- 승인 UX 적절성 검토
- 재진입 조건 발동 여부 판단
- 배포 전 sign-off

### 17.3 Gate 승인자

| 게이트 | 승인 주체 | 기준 |
|---|---|---|
| 계약 게이트 | 인간 | Protocol/DDL/에러 코드 승인 |
| 검색 게이트 | 인간 | 50질의 Top-5 정확도 확인 |
| 안정성 게이트 | 인간 | swap, 발열, degraded 정책 확인 |
| 기능 게이트 | Alliance + 인간 | E2E 통과 후 인간 최종 승인 |
| 실사용 게이트 | 인간 | 5일 사용 기준 충족 확인 |

## 18. 수치화된 검증 기준

- 검색 게이트: 실제 코퍼스 50질의 기준 Top-5 정확도 80% 이상
- 인용 게이트: 인용 누락률 5% 이하
- 라인 매핑 오류: 0건 목표, 1건 이상 발생 시 출하 금지
- TTFT: 2초 이내 시작
- 의미 있는 응답 시작: 2.5초 이내
- index lag: 단일 파일 수정 후 60초 이내 최신 검색 반영
- trust recovery time: 수정된 파일이 다시 `VALID` 인용으로 회복되는 시간 90초 이내
- 승인 없는 상태 변경: 0건
- 5일 실사용 게이트: 5일 연속, 하루 3회 이상 자발 사용

### 18.1 수치의 근거

- BM25 단독 또는 FTS 단독은 한국어+코드 혼합 질의에서 대체로 55~65% 수준에 머무를 가능성이 높다.
- 하이브리드 검색은 reranker 없이도 75~85% 구간이 현실적 목표다.
- 따라서 reranker 미포함 MVP 기준으로 80%는 공격적이지만 달성 가능한 기준선으로 채택한다.

## 19. 재진입 조건과 전환 비용

문서를 닫는 것과 영구 고정하는 것은 다르다. 다음 조건이 충족될 때만 결정을 재검토한다.

### 19.1 Kiwi → MeCab-ko 재검토

- 조건:
  - 50질의 Top-5 80% 미달
  - 실패 원인이 한국어 분석 품질로 확인됨
- 전환 비용:
  - `TokenizerProtocol` 구현 교체
  - `chunk_terms_ko` 전량 재색인
  - 검색 회귀 테스트 재실행
- 예상 비용: 2~4일

### 19.2 14B 기본 계층 재검토

- 조건:
  - 검색은 기준 충족했으나 생성 품질이 지속적으로 미달
  - 배터리/메모리 공존성 손상 없이 상위 계층 사용 가능
- 전환 비용:
  - `ModelRouter`, 모델 로드 정책, 성능 테스트 재측정
- 예상 비용: 2~3일

### 19.3 reranker 도입

- 조건:
  - 하이브리드 검색이 80% 미달이거나 long-tail 질의 실패 다발
- 전환 비용:
  - `HybridSearch` 후단 재순위 단계 추가
  - 성능 테스트 재조정
- 예상 비용: 3~5일

## 20. 중단 기준, 후퇴 기준, Plan B

### 20.1 중단 기준

- 50질의 검색 정확도 70% 미만
- 인용 누락률 10% 초과
- 업무 병행 시 반복 swap 발생
- 5일 실사용에서 하루 3회 자발 사용 미달
- 사용자가 발열·배터리 문제로 기능 비활성화를 반복 요청

### 20.2 후퇴 기준

- 모델 로드 실패가 반복되면 검색 전용 모드로 후퇴
- `draft_export` 오류가 반복되면 쓰기 기능을 비활성화하고 초안 텍스트만 출력
- 인덱스 손상이 반복되면 증분 인덱싱을 중단하고 수동 재색인 모드로 후퇴

### 20.3 Plan B

- 검색 품질 미달:
  - 질의 분해 규칙 조정
  - chunk 전략 보정
  - reranker 도입
- MLX 호환성 문제:
  - `RuntimeProtocol` 유지한 채 llama.cpp 어댑터 추가
- 최신성 실패:
  - FSEvents 경로 점검
  - tombstone 처리 강화
  - 지연 큐 우선순위 재조정

## 21. Colligi2 기반 문서 생성 방식

본 문서는 Colligi2의 집단 AI 문서화 프로세스를 통해 정리되었다. 생성 방식은 단일 모델 요약이 아니라 `다중 AI 충돌-수렴형 검토`다.

적용된 단계는 다음과 같다.

1. 원 요청을 실행 가능한 구현 문제로 재정의했다.
2. 각 AI가 아키텍처, 검색, 한국어 처리, 보안, 로컬 운영 관점에서 독립 초안을 작성했다.
3. 초안 간 충돌 지점을 비교하여 열린 비교 항목과 결정 누락 항목을 분리했다.
4. 리뷰 단계에서 구현 가능성, 리스크, 테스트, 실패 기준, 운영 신뢰성을 기준으로 재평가했다.
5. 최종 단계에서 평균적 절충이 아니라 `더 강한 근거를 가진 결정`과 `남겨야 할 이견`을 유지한 채 통합했다.

따라서 본 문서는 단순 요약본이 아니라, Colligi2의 Alliance 코딩 지시용 구현 명세서에서 Alliance가 실제 구현을 시작하기 위한 집단 검증형 실행 문서다.

## 22. 최종 권고

Colligi2의 Alliance 코딩 지시용 구현 명세서로서 JARVIS는 추진 가능하다. 다만 출발점은 “더 큰 모델을 로컬에서 돌리는가”가 아니라 “내 문서와 코드를 근거와 함께 설명하고, 시스템 자원을 해치지 않으며, 변경 전에는 초안과 영향 범위를 먼저 제시하는가”여야 한다.

즉시 구현할 항목은 다음 한 문장으로 요약된다.

`한국어로 코드와 문서를 검색하고, 검증된 근거 집합을 바탕으로 답하며, 승인된 초안만 제한적으로 내보내는 로컬 퍼스트 워크스페이스 에이전트`

이 범위를 통과하지 못하면 확장 기능은 모두 후순위다. 반대로 이 범위를 통과하면 음성, 화면 문맥, 앱 연동은 그 이후에 검토해도 늦지 않다.

© 2026 Colligi2 | Alliance 코딩 지시용 구현 명세서

---

## 문서 정보

### 참여 AI

| AI | 유형 | 모델 |
|------|------|------|
| **claude** | claude_cli | opus |
| **gemini** | gemini_cli | auto |
| **ollama** | ollama | qwen3:30b-a3b |
| **codex** | codex_cli | gpt-5.4 |

> © 2026 Colligi2 | Alliance 코딩 지시용 구현 명세서
>
> 본 문서는 AI 집단지성 분석 시스템(Colligi)에 의해 2026-03-16 23:01에 생성되었습니다.
