# RAG 검색 최종 합의안 — 구현 검토 리포트

Date: 2026-03-27
Reviewer: Claude Opus 4.6
Purpose: 최종 합의안(2026-03-27-retrieval-final-consensus.md) 대비 실제 소스 구현 상태 검토

---

## Codex 현행화 메모

이 문서는 구조 진단 관점에서 유효하지만, 아래 항목은 최신 구현 상태를 반영해 보정해야 한다.

- `Phase 4 | 회귀셋 벤치마크 | 미구현`
  - 최신 상태에서는 미구현이 아니다.
  - 저장된 baseline report:
    - [2026-03-27-retrieval-baseline-report.json](/Users/codingstudio/__PROJECTHUB__/JARVIS/alliance_20260317_130542/docs/superpowers/specs/2026-03-27-retrieval-baseline-report.json)
  - 현재 baseline:
    - `total_cases=40`
    - `passed_cases=40`
    - `pass_rate=1.0`
    - `task/source/section/row accuracy=1.0`

- `골드 테스트셋 없이 구조 변경 효과 판단 금지 | 부분 준수`
  - 최신 상태에서는 baseline report까지 저장되어 있어 이 평가는 완화되어야 한다.

- `즉시 조치: _ROW_NUMBER_MATCH_BOOST 제거`
  - 이 지적은 최신 상태에서도 유효하다.
  - [evidence_builder.py](/Users/codingstudio/__PROJECTHUB__/JARVIS/alliance_20260317_130542/src/jarvis/retrieval/evidence_builder.py)에 `_ROW_NUMBER_MATCH_BOOST`가 남아 있으며, [strategy.py](/Users/codingstudio/__PROJECTHUB__/JARVIS/alliance_20260317_130542/src/jarvis/retrieval/strategy.py)의 `TableStrategy`와 역할 중복 가능성이 있다.

따라서 이 문서의 최신 해석은 다음과 같다.

- 구조 개편은 합의안과 대체로 일치하게 진행되었다.
- baseline 측정 및 저장은 이미 완료되었다.
- 남은 핵심 retrieval 정리 작업은 `EvidenceBuilder` 보상 규칙 축소, 특히 table-specific boost 제거다.

---

## 1. 전체 상태 요약

| Phase | 항목 | 상태 | 비고 |
|-------|------|------|------|
| Phase 1 | distance-to-score 검증 | 구현됨 | 전용 테스트 미존재 |
| Phase 1 | reranker 절단 검증 | 구현 + 테스트 완료 | test_reranker.py에서 1200자 한국어 검증 |
| Phase 1 | 부스트 규칙 격리 | 부분 구현 | _ROW_NUMBER_MATCH_BOOST 잔존 (위반) |
| Phase 1 | 30-query 회귀 테스트셋 | 구현 완료 | 40개 쿼리, 초과 달성 |
| Phase 2 | retrieval_task 출력 | 구현 완료 | QueryAnalysis에 retrieval_task, entities, search_terms 포함 |
| Phase 2 | 2단계 라우터 | 구현 완료 | HeuristicPlanner + LLMIntentJSONBackend |
| Phase 2 | 쿼리 분석 단일 단계 통합 | 구현 완료 | Orchestrator가 Planner 출력만 소비 |
| Phase 3 | RetrievalStrategy 인터페이스 | 구현 완료 | Protocol 기반 인터페이스 |
| Phase 3 | DocumentStrategy | 구현 완료 | section-aware, topic terms, negative term |
| Phase 3 | TableStrategy | 구현 완료 | row-ID 보조 검색, 필드 매칭, post-rerank 보호 |
| Phase 3 | CodeStrategy | 구현됨 | DocumentStrategy 상속 플레이스홀더 |
| Phase 3 | Orchestrator 테이블 휴리스틱 제거 | 구현 완료 | 테이블 특화 로직 완전 제거 확인 |
| Phase 4 | Section-aware 검색 | 부분 구현 | DocumentStrategy에 구현, 성능 이슈 존재 |
| Phase 4 | 부스트 규칙 축소 | 미구현 | 11개 부스트 상수 잔존 |
| Phase 4 | 회귀셋 벤치마크 | 미구현 | 인프라는 준비됨, 베이스라인 미저장 |
| Phase 5 | 전체 | 미구현 | 예정대로 (구조 안정 후) |
| Phase 6 | 전체 | 미구현 | 예정대로 (조건부) |

---

## 2. Phase별 상세 검토

### 2.1 Phase 1: Quick Validation and Regression Baseline

#### distance-to-score 변환 — 구현됨, 테스트 부재

파일: src/jarvis/retrieval/vector_index.py (193-196행)

```python
score = max(0.0, 1.0 - distance)
```

LanceDB의 기본 L2 distance metric에 대해 합리적인 변환이나, 경계값(distance=0, 0.5, 1.0, >1.0)에 대한 전용 단위 테스트가 없다. 합의안은 "validate distance-to-score behavior"를 요구했으며, 이는 코드 존재가 아닌 의도적 검증을 의미한다.

#### reranker 절단 — 구현 + 테스트 완료

파일: src/jarvis/retrieval/reranker.py (106-116행)

naive 512자 절단을 명시적으로 제거하고, CrossEncoder의 자체 max_length에 위임한다. 코멘트: "Do not apply naive character-based truncation here. CrossEncoder already tokenizes with its own max_length, and a 512-character cutoff is especially harmful for Korean passages."

테스트: tests/retrieval/test_reranker.py의 test_reranker_does_not_apply_naive_512_char_truncation에서 1200자 한국어 패시지가 미절단 상태로 모델에 전달됨을 검증.

#### 부스트 규칙 격리 — 부분 구현 (위반 사항 포함)

파일: src/jarvis/retrieval/evidence_builder.py

현재 잔존하는 부스트/페널티 상수 (44-55행):

| 상수 | 값 | 유형 |
|------|---|------|
| _FILENAME_MATCH_BOOST | 0.20 | 파일명 정확 매칭 |
| _FILENAME_STEM_BOOST | 0.15 | 파일명 stem 매칭 |
| _IDENTIFIER_MATCH_BOOST | 0.08 | 코드 식별자 매칭 |
| _ROW_NUMBER_MATCH_BOOST | 0.18 | 테이블 행 번호 매칭 |
| _CODE_SOURCE_BOOST | 0.28 | 코드 쿼리 + 코드 파일 |
| _NON_CODE_PENALTY | 0.14 | 코드 쿼리 + 비코드 파일 |
| _CLASS_SIGNATURE_BOOST | 0.16 | class 정의 매칭 |
| _FUNCTION_SIGNATURE_BOOST | 0.12 | def 정의 매칭 |
| _DOCUMENT_PHRASE_BOOST | 0.08 | n-gram 구문 매칭 |
| _DOCUMENT_EXPLANATORY_BOOST | 0.05 | 한국어 설명문 종결어미 |
| _DOCUMENT_REFERENCE_PENALTY | 0.12 | 참조 전용 텍스트 |

위반 사항: _ROW_NUMBER_MATCH_BOOST 로직(197-209행)이 Day=N 패턴 기반 테이블 행 부스트를 수행. TableStrategy가 이미 동일한 row-ID 스코어링을 수행하므로 이중 채점이 발생하며, 합의안의 "generic evidence layer에 도메인 특화 휴리스틱 금지" 원칙을 위반.

#### 회귀 테스트셋 — 구현 완료 (40개, 초과 달성)

파일:
- tests/fixtures/retrieval_regression_v1.json — 40개 쿼리
- src/jarvis/retrieval/regression_runner.py — 회귀 실행기
- src/jarvis/cli/retrieval_regression.py — CLI 도구

카테고리 커버리지:
- document_section_lookup
- table_row_field_lookup (table_row_lookup, table_multi_row, table_multi_row_multi_field)
- mixed_greeting_task
- numeric_in_prose / numeric_table_lookup
- stt_corruption
- mixed_task_disambiguation
- live_data_request
- smalltalk

인프라: RetrievalRegressionCase, RetrievalRegressionResult, RetrievalRegressionReport 데이터 클래스, task routing / source accuracy / section accuracy / row accuracy 평가, 한국어 Unicode 정규화 포함.

테스트: test_regression_runner.py, test_regression_runner_integration.py, test_retrieval_regression_fixture.py, test_retrieval_regression_cli.py

---

### 2.2 Phase 2: Planner Routing — 완벽 구현

#### retrieval_task 출력

파일: src/jarvis/core/planner.py

QueryAnalysis (87행)에 retrieval_task, entities, search_terms 포함. 지원 태스크: document_qa, table_lookup, code_lookup, multi_doc_qa, live_data_request, smalltalk.

_classify_retrieval_task 함수(514-567행)가 구조화된 라우팅과 엔티티 추출(row_ids, fields, topic_terms, negative_terms, target_file, capability)을 수행.

합의안 최소 스키마와 일치:
```json
{
  "retrieval_task": "document_qa",
  "entities": { "document": "...", "topic": "...", "subtopic": "..." },
  "search_terms": ["...", "..."]
}
```

#### 2단계 라우터

파일: src/jarvis/core/planner.py

구현 아키텍처:
1. HeuristicPlanner (192행) — 빠른 결정적 베이스라인 (~5ms)
2. LightweightKeywordExpander (235행) — 저비용 이중언어 확장
3. LLMIntentJSONBackend (275행) — 저신뢰도 시 모델 기반 보강

_should_use_lightweight (407행) 게이트 조건:
- baseline.confidence < 0.7 (저신뢰도 트리거)
- 혼합 언어 감지
- 파일 범위 쿼리
- 복잡 쿼리

합의안의 "heuristic fast router first, LLM router on low confidence"와 정확히 일치.

#### 쿼리 분석 단일 단계 통합

파일: src/jarvis/core/orchestrator.py (137-144행)

```python
analysis = self._planner.analyze(user_input)
if analysis.search_terms:
    search_query = " ".join(analysis.search_terms)
```

Orchestrator가 Planner의 QueryAnalysis 출력만 소비. 자체 의도 분류나 쿼리 재작성을 수행하지 않음.

---

### 2.3 Phase 3: Retrieval Strategy Split — 우수 구현

#### RetrievalStrategy 인터페이스

파일: src/jarvis/retrieval/strategy.py (29행)

```python
class RetrievalStrategy(Protocol):
    def augment_candidates(self, inputs: RetrievalInputs) -> tuple[list[SearchHit], list[VectorHit]]: ...
    def protect_post_rerank(self, ...) -> list[HybridSearchResult]: ...
```

#### DocumentStrategy (42행)

- 파일 범위 검색 지원
- topic_terms 기반 section-aware 검색
- negative_terms 페널티
- 테이블 콘텐츠 페널티

#### TableStrategy (91행)

- row-ID 기반 보조 SQL 검색
- 필드 매칭
- post-rerank 보호 (reranker가 정확한 행 매치를 제거하는 것 방지)

#### CodeStrategy (87행)

- DocumentStrategy 상속, 오버라이드 없음 (플레이스홀더)
- Phase 3에서 합리적 — 코드 특화 동작은 이후 Phase에서 구현

#### Orchestrator 테이블 휴리스틱 제거

파일: src/jarvis/core/orchestrator.py

_retrieve_evidence 메서드(324행)가 모든 전략 특화 로직을 Strategy 패턴에 위임:

```python
strategy = select_retrieval_strategy(analysis)
fts_hits, vector_hits = strategy.augment_candidates(...)
...
hybrid_results = strategy.protect_post_rerank(...)
```

Orchestrator 전체에서 테이블 특화 패턴(Day=, table-row, meal 등) 검색 결과: 0건. 완전 제거 확인.

#### Strategy 선택 함수 (178행)

select_retrieval_strategy가 analysis.retrieval_task 기반으로 라우팅.

#### 테스트 커버리지

tests/retrieval/test_strategy.py에 5개 테스트:
- Strategy 선택
- 테이블 행 보호
- 문서 전략의 테이블 로직 격리
- Section-aware 히트
- Negative term 페널티

---

### 2.4 Phase 4: Structural Retrieval Improvement — 부분 구현

#### Section-aware 검색 — 부분 구현

파일: src/jarvis/retrieval/strategy.py

DocumentStrategy._prepend_document_section_hits (224행)가 구현됨:
- topic_terms로 관련 섹션 탐색
- heading 매칭 (20.0), text 매칭 (4.0), phrase 매칭 (12.0)
- 설명 콘텐츠 보너스 (6.0), 테이블 페널티 (-10.0)
- negative term 페널티 (-20.0)

성능 이슈: chunks 테이블 전체를 .fetchall()로 조회(236행). 코퍼스 확장 시 병목.

#### 부스트 규칙 축소 — 미구현

EvidenceBuilder에 11개 부스트 상수 잔존. Phase 4 범위 내 축소 계획 필요.

#### 회귀셋 벤치마크 — 미구현

인프라(regression_runner, CLI)는 준비됨. 베이스라인 리포트 미저장.

---

### 2.5 Phase 5-6 — 미구현 (예정대로)

합의안에서 Phase 5-6은 구조 경계 안정 후 진행으로 합의. 현재 미구현은 정상.

---

## 3. 합의안 금지 사항 준수 현황

| 금지 사항 | 상태 | 근거 |
|----------|------|------|
| Generic orchestrator에 새 도메인 휴리스틱 추가 금지 | 준수 | Orchestrator에 테이블/도메인 특화 코드 0건 |
| 저수준 검색 코드에서 의도 재해석 금지 | 준수 | hybrid_search, vector_index, fts_index에서 의도 해석 없음 |
| EvidenceBuilder에 새 보상적 부스트 추가 금지 | 부분 위반 | _ROW_NUMBER_MATCH_BOOST 잔존 (TableStrategy와 중복) |
| Quick Fix 단계 무기한 연장 금지 | 준수 | Phase 2-3 구조 개편으로 전환 완료 |
| 골드 테스트셋 없이 구조 변경 효과 판단 금지 | 부분 준수 | 테스트셋 존재하나 베이스라인 미저장 |

---

## 4. 조치 필요 사항

### 4.1 즉시 조치 (Critical)

| # | 작업 | 파일 | 근거 |
|---|------|------|------|
| 1 | _ROW_NUMBER_MATCH_BOOST 로직 제거 (197-209행) | evidence_builder.py | TableStrategy와 이중 채점. 합의안 위반 |

TableStrategy.augment_candidates()와 TableStrategy.protect_post_rerank()가 이미 row-ID 스코어링을 완전히 처리하므로, EvidenceBuilder의 중복 로직은 안전하게 삭제 가능.

### 4.2 중요 조치

| # | 작업 | 파일 | 근거 |
|---|------|------|------|
| 2 | distance-to-score 경계값 전용 테스트 추가 | tests/retrieval/test_vector_index.py | 합의안 "validate" 요구 충족 |
| 3 | Section-aware 검색의 .fetchall() 성능 개선 | strategy.py (236행) | FTS 사전 필터링 또는 문서 범위 제한 |
| 4 | 회귀 테스트 베이스라인 JSON 저장 | tests/fixtures/ | 향후 변경 효과 정량 비교 가능 |

### 4.3 Phase 4 진행 시 필요 작업

| # | 작업 | 근거 |
|---|------|------|
| 5 | EvidenceBuilder 잔여 부스트를 Strategy 패턴으로 점진 이관 | _CODE_SOURCE_BOOST(0.28), _FILENAME_MATCH_BOOST(0.20) 등 RRF 대비 10x+ 증폭 |
| 6 | CodeStrategy를 DocumentStrategy에서 독립, 코드 특화 동작 구현 | 현재 플레이스홀더 상태 |
| 7 | 회귀셋으로 Phase 1-3 전체 효과 정량 측정 | 구조 변경 효과 검증 |

---

## 5. HWP 파싱 반영 사항

별도 작업으로 진행된 HWP 파싱 개선 반영 현황:

| 항목 | 상태 |
|------|------|
| lxml을 pyproject.toml에 명시 (lxml>=5.2) | 반영됨 |
| HWP inline heading 승격 helper | 반영됨 |
| HWP recent heading context 전파 | 반영됨 |
| HWPX table caption 추출 보강 | 반영됨 |
| parser 회귀 테스트 추가/보강 | 반영됨 |
| hwp5proc 정상 실행 확인 | 확인됨 |
| live HWP 재인덱싱 후 DB 반영 확인 | 확인됨 |

이 변경은 합의안 Phase 4 (Section-aware retrieval)의 전제 조건인 HWP 헤딩 계층 추출을 부분적으로 충족한다.

---

## 6. 결론

### 잘 된 점
- Phase 2 (Planner 라우팅)와 Phase 3 (Strategy 분리)가 합의안과 정확히 일치
- 회귀 테스트 인프라가 목표를 초과 달성 (40/30 쿼리)
- Orchestrator에서 도메인 특화 로직 완전 제거
- 2단계 라우터(휴리스틱 + LLM)가 합의안 설계대로 구현
- 금지 사항 대부분 준수

### 즉시 필요한 조치
- EvidenceBuilder의 _ROW_NUMBER_MATCH_BOOST 제거 (유일한 합의안 위반 사항)

### 다음 단계
- Phase 4 진행: 부스트 규칙 축소, 회귀셋 베이스라인 측정, section-aware 검색 성능 개선
- Phase 5는 Phase 4 완료 및 구조 경계 안정 확인 후 시작
