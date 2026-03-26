# JARVIS RAG 검색 알고리즘 — 최종 합의안

Date: 2026-03-27
Participants: Claude Opus 4.6, Codex
Status: FINAL AGREEMENT

Related documents:
- 2026-03-27-retrieval-research-review.md (Codex 연구)
- 2026-03-27-retrieval-algorithm-comparison.md (Opus 연구 + 비교)
- 2026-03-27-retrieval-comparison-conclusion.md (Codex 비교 결론)
- 2026-03-27-retrieval-consensus.md (Opus 합의 도출)
- 2026-03-27-retrieval-consensus-proposal.md (Codex 합의 제안)

---

## 1. 합의된 원칙

양측이 명시적으로 동의한 원칙입니다. 새로운 근거가 나오지 않는 한 변경하지 않습니다.

### 원칙 1: 현재 문제는 구조적이다

- 쿼리 해석이 너무 많은 레이어에 분산되어 있음
- 검색 태스크 경계가 불명확
- 랭킹 규칙이 구조적 약점을 보상 중
- **Score boosting을 주요 해결 수단으로 사용하는 것을 중단한다**

### 원칙 2: 테이블 검색과 문서 검색은 반드시 분리한다

- 숫자 언급이 테이블 행으로 잘못 해석되는 오류 제거
- 문서 쿼리가 식단표 결과를 반환하는 오염 제거
- Generic orchestrator에서 테이블 특화 추론 로직 완전 제거

### 원칙 3: 쿼리 분석은 단일 단계에서 완결한다

- Planner가 retrieval_task를 포함한 구조화된 출력을 생산
- 하위 검색 레이어는 이 출력을 소비할 뿐, 의도를 재해석하지 않음

### 원칙 4: 장문 문서는 계층적 검색을 목표로 한다

- document -> section -> chunk 3단계 검색
- 단계적 도입 가능하나, 명시적 목표 아키텍처로 확정

### 원칙 5: 검색 평가는 생성 품질과 독립 측정한다

- 소스 문서 정확도, 섹션 정확도, 테이블 행/열 정확도를 별도 측정
- 엔드투엔드 어시스턴트 테스트에만 의존하지 않음

---

## 2. 합의된 결정 사항

### Decision 1: retrieval_task를 새로운 Planner 계약으로 채택

최소 스키마:

```json
{
  "retrieval_task": "document_qa",
  "entities": {
    "document": "한글문서 파일형식",
    "topic": "그리기 개체 자료 구조",
    "subtopic": "기본 구조"
  },
  "search_terms": [
    "한글문서 파일형식",
    "그리기 개체 자료 구조",
    "기본 구조"
  ]
}
```

최소 태스크 세트:
- document_qa
- table_lookup
- code_lookup
- multi_doc_qa
- live_data_request

### Decision 2: 2단계 라우터 채택

```
Query -> HeuristicRouter (~5ms)
          |-- confidence >= threshold -> retrieval_task 즉시 확정
          +-- confidence < threshold  -> LLM Router (~1.5s) -> retrieval_task 정밀 생성
```

- Phase 1에서는 휴리스틱 라우터만 구현
- LLM 라우터는 스키마와 평가 체계가 안정된 후 도입
- 근거: Adaptive-RAG(NAACL 2024), Codex "reduces moving parts during backend separation"

### Decision 3: 논리적 Strategy 분리 우선, 물리적 분리는 조건부

- 단일 인덱스 유지 + 검색 로직 분리를 먼저 적용
- TableStrategy, DocumentStrategy, CodeStrategy로 논리적 분리
- 물리적 Retriever 분리는 메트릭이 간섭이 남아있음을 보여줄 때만 진행
- 근거: Codex "lower migration cost, faster validation"

### Decision 4: 검색 회귀 테스트셋을 구조 개편과 병렬 구축

- 30-50개 쿼리로 시작
- 구조 개편 전 베이스라인 측정, 각 Phase 완료 후 재측정

최소 커버리지:
- 문서 섹션 검색
- 테이블 행/열 검색
- 인사 + 태스크 혼합 쿼리
- 산문 내 숫자 언급
- STT 왜곡 변형

### Decision 5: Quick Fix 범위를 의도적으로 제한

허용:
- LanceDB distance-to-score 변환 검증
- Reranker 텍스트 절단 한도 검증
- 가장 위험한 부스트 규칙 격리/제거

금지:
- generic orchestrator에 새로운 도메인 휴리스틱 추가
- 저수준 검색 코드에 추가 라우팅 로직 삽입
- Quick Fix 단계의 무기한 연장

### Decision 6: 고급 검색 기법은 구조 경계 안정 후 적용

Reranker 교체, Contextual Retrieval, Parent-Child Chunking, RAPTOR 등은 라우팅 + 백엔드 분리 이후에 벤치마크 및 적용.

근거: 구조적 노이즈 위에서 측정하면 효과 귀속이 불가능.

---

## 3. 조건부 합의 사항

양측 이견이 있었으나 조건부로 합의한 항목입니다.

### 3.1 Contextual Retrieval 적용 시점

- **Opus 입장**: Phase A와 병렬로 즉시 배치잡 시작 (인덱싱 변경이므로 구조와 독립)
- **Codex 입장**: 구조 개편 이후 적용 (효과 측정의 명확성)

**합의안**: Codex의 원칙을 존중하되, 실행 효율을 위한 예외를 둔다.

- Contextual Retrieval 배치잡의 **기술 검증**(소규모 파일럿, 50-100개 청크)은 Phase A에서 허용
- 전체 코퍼스 적용(22K 청크)은 Step 4(Retriever 분리) 완료 후 실행
- 파일럿 결과는 Phase D의 전체 적용 여부 판단 근거로 활용

근거: 파일럿은 기존 검색 로직에 영향 없이 기법의 유효성만 검증. 전체 적용은 구조 안정 후.

### 3.2 태스크별 동적 RRF 가중치

- **Opus 입장**: retrieval_task에 따라 vector_weight/fts_weight를 동적 조정
- **Codex 입장**: 명시적 언급 없음 (거부가 아닌 누락으로 판단)

**합의안**: 라우팅 도입의 자연스러운 확장으로 포함.

- Step 2(retrieval_task 도입) 시점에 가중치 매핑 테이블을 함께 구현
- 초기 가중치는 보수적 기본값으로 시작:

| retrieval_task | vector_weight | fts_weight |
|----------------|---------------|------------|
| document_qa | 2.0 | 1.0 |
| table_lookup | 0.5 | 2.0 |
| code_lookup | 0.5 | 2.0 |
| multi_doc_qa | 1.5 | 1.0 |
| live_data_request | 1.0 | 1.0 |

- 골드 테스트셋으로 가중치 튜닝, 데이터 기반으로 조정

### 3.3 계층적 검색 기법 도입 순서

- **Opus 입장**: Section-aware -> Parent-Child -> RAPTOR
- **Codex 입장**: 순서 미명시, 모두 구조 개편 이후

**합의안**: Opus의 난이도 순서를 채택하되 Codex의 시점 원칙을 적용.

1. **Section-aware 검색**: Phase D 첫 번째 (기존 heading_path 확장, 낮은 비용)
2. **Parent-Child Chunking**: Section-aware 효과 확인 후 (이중 인덱스, 중간 비용)
3. **RAPTOR**: 1, 2 적용 후에도 장문 문서 품질 부족 시에만 (높은 비용, 조건부)

---

## 4. 최종 실행 계획

### Step 1: Quick Validation (1-2일)

| # | 작업 | 완료 기준 |
|---|------|----------|
| 1.1 | LanceDB distance-to-score 변환 검증 | cosine vs L2 확인, 필요시 수정 |
| 1.2 | Cross-encoder 텍스트 절단 한도 검증 | 512자 vs 모델 실제 토큰 한도 비교, 한국어 밀도 고려하여 조정 |
| 1.3 | EvidenceBuilder 부스트 규칙 중 가장 위험한 항목 격리 | RRF 점수 대비 10x 이상 증폭하는 규칙 식별 및 격리 |
| 1.4 | Contextual Retrieval 파일럿 (50-100개 청크) | 소규모 기법 유효성 검증 (기존 검색 로직 변경 없음) |

**전환 기준**: 1.1-1.3 완료 시 Step 2로 이동. Quick Fix를 무기한 연장하지 않는다.

### Step 2: Planner retrieval_task 도입 (3-5일)

| # | 작업 | 완료 기준 |
|---|------|----------|
| 2.1 | retrieval_task JSON 스키마 확정 | Decision 1 스키마 기반 |
| 2.2 | HeuristicRouter 구현 | 5개 태스크 타입 분류, 신뢰도 점수 출력 |
| 2.3 | 기존 Planner 출력에 retrieval_task 추가 | 하위 호환 유지, 기존 동작 깨지지 않음 |
| 2.4 | 태스크별 동적 RRF 가중치 매핑 | 조건부 합의 3.2의 초기 가중치 적용 |
| 2.5 | 골드 테스트셋 30-50개 구축 시작 | Decision 4의 최소 커버리지 충족 |

### Step 3: 테이블 검색 로직 추출 (3-5일)

| # | 작업 | 완료 기준 |
|---|------|----------|
| 3.1 | orchestrator에서 테이블 특화 로직 추출 | _table_field_hints, _should_use_structured_row_lookup, row supplemental search 제거 |
| 3.2 | TableStrategy 구현 | heading_path 필터 + row/column 스코어링 |
| 3.3 | post-rerank Day=N 주입 로직 제거 | TableStrategy 내부로 이동 |
| 3.4 | 골드 테스트셋으로 before/after 비교 | 테이블 검색 정확도 유지/향상 확인 |

### Step 4: DocumentRetriever / CodeRetriever 분리 (1주)

| # | 작업 | 완료 기준 |
|---|------|----------|
| 4.1 | RetrievalStrategy 인터페이스 확정 | 검색 필터, 스코어링 규칙, top_k 파라미터 |
| 4.2 | DocumentStrategy 구현 | section hierarchy 우선 검색 |
| 4.3 | CodeStrategy 구현 | identifier 매칭 + AST 경계 인식 |
| 4.4 | 쿼리 분석 단일 단계 통합 완료 | query_normalization -> planner(retrieval_task) -> retrieval 단방향 흐름 |
| 4.5 | EvidenceBuilder 부스팅 규칙 축소 | 라우팅으로 불필요해진 보상적 부스트 제거 |
| 4.6 | 전체 골드 테스트셋 비교 측정 | Step 1 베이스라인 대비 개선 확인 |

### Step 5: 검색 회귀 데이터셋 확립 (Step 2-4와 병렬)

| # | 작업 | 완료 기준 |
|---|------|----------|
| 5.1 | 골드 테스트셋 30-50개 확정 | expected_document, expected_section, expected_row 기록 |
| 5.2 | 자동화된 회귀 테스트 스크립트 | 소스 정확도, 섹션 정확도, 행/열 정확도 별도 측정 |
| 5.3 | 베이스라인 + 각 Step 완료 시점 측정 결과 기록 | 정량적 비교 가능 |

### Step 6: 검색 품질 강화 (2-3주, Step 4 완료 후)

| # | 작업 | 조건 |
|---|------|------|
| 6.1 | BGE-Reranker-v2-m3 벤치마크 | 현 mmarco-mMiniLMv2 대비 골드셋 비교 |
| 6.2 | Section-aware 검색 구현 | heading_path 계층 확장, 문서 -> 섹션 -> 청크 |
| 6.3 | Contextual Retrieval 전체 적용 | 파일럿 결과 양호 시, 22K 청크 배치잡 |
| 6.4 | Parent-Child Chunking | Section-aware 효과 확인 후 |
| 6.5 | CRAG-style 검색 평가 게이트 | cross-encoder 점수 기반 신뢰도 분기 |
| 6.6 | HyDE (복잡 쿼리 한정) | LLM 라우터와 연동 |

### Step 7: 고급 기법 (향후, 조건부)

| # | 작업 | 진입 조건 |
|---|------|----------|
| 7.1 | RAPTOR 트리 인덱싱 | Step 6.2 + 6.4 적용 후에도 장문 문서 품질 부족 |
| 7.2 | LLM 라우터 도입 | 휴리스틱 라우터 한계 확인, 스키마/평가 안정 |
| 7.3 | 물리적 Retriever 분리 | 메트릭이 인덱스 간섭 잔존을 입증 |
| 7.4 | ColBERT / Late Interaction | 코퍼스 대폭 확장 시 |
| 7.5 | GraphRAG / LazyGraphRAG | 교차 문서 테마 검색 필요 시 |
| 7.6 | RAGAS/CRUX 기반 평가 대시보드 | Step 5 수동 평가의 한계 도달 시 |

---

## 5. 금지 사항

구조 개편 기간 동안 다음 행위를 금지합니다:

1. Generic orchestrator에 새로운 도메인 특화 휴리스틱 추가
2. 저수준 검색 코드에서 쿼리 의도 재해석
3. EvidenceBuilder에 새로운 보상적 부스트 규칙 추가
4. Quick Fix 단계의 무기한 연장
5. 구조 경계 안정 전에 고급 검색 기법 전체 적용
6. 골드 테스트셋 없이 "감으로" 구조 변경 효과 판단

---

## 6. 성공 기준

최종 실행 계획의 성공은 다음으로 측정합니다:

### 단기 (Step 1-4 완료 시)
- 테이블 쿼리가 문서 결과를 오염시키는 사례 0건 (골드셋 기준)
- 문서 쿼리가 테이블 행을 잘못 반환하는 사례 0건 (골드셋 기준)
- EvidenceBuilder 부스트 규칙 수 11개 -> 5개 이하로 축소
- Orchestrator에서 테이블/도메인 하드코딩 완전 제거

### 중기 (Step 6 완료 시)
- 골드 테스트셋 소스 문서 정확도 >= 85%
- 골드 테스트셋 섹션 정확도 >= 75%
- 골드 테스트셋 테이블 행/열 정확도 >= 90%

### 장기 (Step 7 진입 판단 시)
- 위 중기 목표 미달 영역에 대해서만 고급 기법 적용 검토

---

## 7. 서명

본 문서는 JARVIS RAG 검색 알고리즘 재설계에 대한 Claude Opus 4.6과 Codex의 최종 합의를 기록합니다.

- **Claude Opus 4.6**: 합의 확인
- **Codex**: (확인 대기)

합의 완료 후 Step 1부터 실행에 착수합니다.
