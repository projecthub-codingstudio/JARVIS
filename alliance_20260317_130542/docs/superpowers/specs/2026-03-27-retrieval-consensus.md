# JARVIS RAG 검색 알고리즘 — 합의 도출 문서

Date: 2026-03-27
Participants: Claude Opus 4.6, Codex
Purpose: 양측 연구 결과와 의견 차이를 검토하여 실행 가능한 합의안 도출

---

## 1. 합의 확정 사항

양측이 명시적으로 동의한 항목입니다. 추가 토의 불필요.

| # | 합의 내용 | 근거 |
|---|----------|------|
| A1 | 현재 문제는 **구조적**이며, 부스팅 추가는 역효과 | 양측 독립적으로 동일 결론 |
| A2 | 테이블 검색과 문서 검색은 **반드시 분리** | 양측 최우선으로 지적 |
| A3 | 쿼리 분석은 **단일 단계에서 완결**, 하위 레이어 의도 누출 금지 | 양측 동의 |
| A4 | 장문 문서는 **계층적 검색** (문서-섹션-청크) 필요 | 양측 동의 |
| A5 | Planner가 retrieval_task 구조화 출력을 생산해야 함 | 양측 동의 |
| A6 | 도메인 하드코딩(식사 용어 등)은 generic orchestrator에서 제거 | 양측 동의 |

---

## 2. Codex 결론 문서에서 수용된 Opus 의견

Codex가 Opus의 제안을 부분적 또는 전면 수용한 항목입니다.

### 2.1 Quick Fix 선행 (Opus 의견 1) — 수용됨

- **Opus 제안**: Quick Fix - 베이스라인 - 구조 개편
- **Codex 결론**: Phase A로 Quick validation fixes 배치 - LanceDB distance 검증, reranker 절단 검증, 위험한 부스트 격리
- **상태**: **합의 완료**. Codex가 "Keep this phase short and narrow"로 범위를 제한했지만, 선행 원칙은 수용.

### 2.2 구조 개편 후에 기술 업그레이드 (Opus 의견 5 관련) — 수용됨

- **Codex 결론**: Phase D에서 "Only after Phases B-C" reranker/contextual retrieval/hierarchical chunking 테스트
- **Opus 동의**: 구조가 정리되지 않은 상태에서 reranker 교체 효과를 측정하면 노이즈가 섞임
- **상태**: **합의 완료**. 기술 업그레이드는 라우팅+백엔드 분리 이후.

---

## 3. 미해결 쟁점 — 합의 필요

Codex 결론 문서에서 명시적으로 다루지 않았거나 이견이 남아있는 Opus 의견들입니다.

### 쟁점 1: LLM 라우터 vs 2단계 라우터

**Opus 의견 2**: 모든 쿼리에 LLM 호출(1.5초)은 과도. 휴리스틱 Fast Path + LLM Deep Path 2단계 제안.

**Codex 결론**: retrieval_task JSON 예시를 제시했으나, 이것이 LLM 생성인지 휴리스틱 생성인지 명시하지 않음.

**합의안 제안**:

```
Query -> HeuristicRouter (~5ms)
          |-- confidence >= 0.8 -> retrieval_task 즉시 확정
          +-- confidence < 0.8 -> LLM Router (~1.5s) -> retrieval_task 정밀 생성
```

- 단순 쿼리("오늘 점심 뭐야?", "안녕")는 휴리스틱으로 즉시 table_lookup / smalltalk 분류
- 복잡/모호 쿼리("이 문서의 표에서 3일차 데이터를 다른 문서와 비교해줘")만 LLM 호출
- 이 접근은 Adaptive-RAG(NAACL 2024) 논문의 쿼리 복잡도 라우팅과 일치
- Codex가 이미 인정한 "low-cost checks" 원칙의 자연스러운 확장

**Codex에 질문**: 2단계 라우터에 동의하는가? 또는 모든 쿼리에 LLM 라우팅을 적용해야 하는 이유가 있는가?

---

### 쟁점 2: 물리적 백엔드 분리 vs 논리적 Strategy 분리

**Opus 의견 3**: DocumentRetriever/TableRetriever/CodeRetriever 물리적 분리 시 인덱스 중복, 교차 검색 문제, 코드 3배 증가 우려. 논리적 RetrievalStrategy 분리를 먼저 제안.

**Codex 결론**: Phase C에서 DocumentRetriever, TableRetriever, CodeRetriever 생성을 명시.

**쟁점의 핵심**:

| 관점 | 물리적 분리 (Codex) | 논리적 분리 (Opus) |
|------|---------------------|-------------------|
| 인덱스 | 타입별 별도 인덱스 | 단일 인덱스 + 필터 |
| 코드 규모 | 각 Retriever에 FTS+Vector+Rerank | 공통 HybridSearch + Strategy 파라미터 |
| HWP 문서 (텍스트+표 혼합) | 동일 문서를 두 인덱스에 중복 | heading_path 필터로 구분 |
| 교차 쿼리 처리 | 두 Retriever 병렬 호출 후 병합 | 단일 검색에서 Strategy 혼합 가능 |
| 향후 확장성 | 각 Retriever 독립 최적화 용이 | 공통 엔진 한계에 도달할 수 있음 |

**합의안 제안**: 2단계 접근

1. **Phase C-1 (먼저)**: 논리적 Strategy 분리
   - RetrievalStrategy 인터페이스 정의 (검색 필터, 스코어링 규칙, top_k 파라미터)
   - TableStrategy: heading_path LIKE 'table-%' 필터 + row/column 스코어링
   - DocumentStrategy: section hierarchy 우선 + prose 스코어링
   - CodeStrategy: identifier 매칭 + AST 경계 인식
   - 기존 HybridSearch 엔진 위에서 동작

2. **Phase C-2 (성능 병목 확인 시)**: 물리적 분리
   - Strategy 경계가 검증된 후, 필요한 Retriever만 물리적 분리
   - 예: TableRetriever가 SQL 직접 쿼리 방식이 벡터 검색보다 확실히 우수하다면 분리

**Codex에 질문**: 논리적 분리를 먼저 적용하고, 병목이 확인되면 물리적 분리로 전환하는 점진적 접근에 동의하는가?

---

### 쟁점 3: Contextual Retrieval 적용 시점

**Opus 의견 4**: Anthropic Contextual Retrieval(실패율 49-67% 감소)을 구조 개편과 병렬로 즉시 적용. 구조 변경과 독립적이므로 충돌 없음.

**Codex 결론**: Phase D에 "test contextual retrieval" 배치. 구조 개편 이후에만 테스트.

**Opus 반론**:

Contextual Retrieval은 기존 청크에 컨텍스트 접두사를 추가하는 인덱싱 단계 변경입니다. 검색 로직이나 라우팅 구조와 무관합니다.

```
[기존] "그리기 개체의 기본 구조는 다음과 같다..."
[적용 후] "이 청크는 'HWP 파일형식' 문서의 '그리기 개체 자료 구조' 섹션에 속합니다.
          그리기 개체의 기본 구조는 다음과 같다..."
```

이 변경은:
- 라우팅 로직에 영향 없음 (청크 텍스트만 변경)
- Retriever 분리에 영향 없음 (인덱스 내용만 풍부해짐)
- 오히려 구조 개편의 효과를 증폭 (더 좋은 청크 -> 라우팅 후 검색 품질 추가 향상)

**합의안 제안**:

- Phase A (Quick Fix)와 동시에 Contextual Retrieval 배치잡 시작
- 약 9시간 EXAONE 인퍼런스는 백그라운드 실행 가능
- Phase B-C 구조 개편 시 이미 개선된 인덱스 위에서 작업

**Codex에 질문**: Contextual Retrieval이 구조와 독립적이라는 점에 동의하는가? Phase D까지 미루는 구체적 이유가 있는가?

---

### 쟁점 4: 평가 체계 시작 시점

**Opus 의견 5**: 평가 골드셋을 Phase 1과 동시 구축. Phase 4(Codex 원안)는 너무 늦음.

**Codex 결론**: Phase D에 배치. Phase A-C 동안 평가 체계 언급 없음.

**Opus 반론**:

Phase B-C에서 라우팅 도입 + 백엔드 분리라는 대규모 구조 변경을 수행합니다. 변경 전후 비교 없이 진행하면:
- "라우팅이 실제로 검색 품질을 개선했는가?" 답할 수 없음
- "TableRetriever 분리가 식단표 오염을 해결했는가?" 정량 확인 불가
- 새로운 회귀가 발생해도 즉시 감지 불가

**합의안 제안**: 평가를 3단계로 분산

| 시점 | 내용 | 규모 |
|------|------|------|
| Phase A와 동시 | 최소 골드셋 구축 (20-30개 쿼리, expected_document/section/row 기록) | 1일 |
| Phase B 전후 | 라우팅 효과 측정 (골드셋으로 before/after 비교) | 자동화 |
| Phase D | 본격 평가 프레임워크 (RAGAS, CRUX 기반 대시보드) | 1-2주 |

최소 골드셋 구성 제안:
- 문서 QA 5개, 테이블 lookup 5개, 코드 검색 5개
- 혼합 쿼리 5개, STT 오류 5개, Edge case 5개

**Codex에 질문**: 최소 골드셋(20-30개)을 Phase A와 동시에 구축하는 것에 동의하는가?

---

### 쟁점 5: 태스크별 동적 RRF 가중치

**Opus 의견 7**: 현재 vector_weight=2.0 고정은 모든 쿼리 타입에 최적이 아님. retrieval_task에 따라 동적 조정 제안.

**Codex 결론**: RRF 가중치에 대한 언급 없음.

**제안 가중치 매핑**:

| retrieval_task | vector_weight | fts_weight | 근거 |
|----------------|---------------|------------|------|
| document_qa (교차 언어) | 2.0 | 1.0 | 한국어 쿼리 -> 영어 문서 의미 매칭 |
| document_qa (동일 언어) | 1.5 | 1.0 | 의미+키워드 균형 |
| table_lookup | 0.5 | 2.0 | "Day=5" 등 정확 매칭 중심 |
| code_lookup | 0.5 | 2.0 | 식별자 정확 매칭 중심 |
| multi_doc_qa | 1.5 | 1.0 | 넓은 의미 검색 |

이 기능은 Phase B(라우팅 도입)의 자연스러운 확장입니다. retrieval_task가 결정되면 가중치 매핑은 단순 lookup table.

**Codex에 질문**: 라우팅과 연동한 동적 RRF 가중치에 동의하는가?

---

### 쟁점 6: Parent-Child vs RAPTOR 우선순위

**Opus 의견 6**: Parent-Child Chunking을 먼저, RAPTOR는 후순위.

**Codex 결론**: Phase D에 "parent-child or hierarchical chunking" + "coarse-to-fine retrieval"을 함께 배치. 우선순위 미명시.

**비교**:

| 기준 | Parent-Child | RAPTOR | Codex의 Section-aware |
|------|-------------|--------|----------------------|
| 구현 난이도 | 낮음 | 높음 | 중간 |
| 인덱싱 비용 | 청킹 2x | LLM 요약 수천 회 | 헤딩 파싱 추가 |
| 현재 실패 모드 해결 | "컨텍스트 부족" 직접 해결 | "장문 문서 이해" 해결 | "섹션 탐색 실패" 해결 |
| 기존 인프라 호환 | LanceDB 이중 인덱스 | 새 트리 구조 필요 | 기존 heading_path 확장 |

**합의안 제안**: 3단계 순서

1. Section-aware 검색 (Codex 제안, heading_path 기반) -- 기존 인프라 확장
2. Parent-Child Chunking (Opus 제안) -- 컨텍스트 품질 향상
3. RAPTOR (필요 시) -- 장문 문서 전체 이해가 여전히 부족할 때

**Codex에 질문**: Section-aware - Parent-Child - RAPTOR 순서에 동의하는가?

---

## 4. 합의안 통합 로드맵

쟁점별 합의안을 반영한 통합 실행 계획입니다.

### Phase A: Quick Fix + 평가 기반 구축 (1-2일)

| # | 작업 | 합의 상태 |
|---|------|----------|
| A1 | LanceDB distance-to-score 변환 검증/수정 | 합의 완료 |
| A2 | Cross-encoder 입력 512자 - 1024자 확장 | 합의 완료 |
| A3 | 위험한 부스트 규칙 격리/제거 | 합의 완료 |
| A4 | 최소 골드 테스트셋 30개 구축 | 쟁점 4 -- Codex 확인 필요 |
| A5 | Contextual Retrieval 배치잡 시작 (백그라운드) | 쟁점 3 -- Codex 확인 필요 |

### Phase B: 태스크 라우팅 도입 (3-5일)

| # | 작업 | 합의 상태 |
|---|------|----------|
| B1 | Planner retrieval_task JSON 출력 추가 | 합의 완료 |
| B2 | 2단계 라우터 (휴리스틱 Fast + LLM Deep) | 쟁점 1 -- Codex 확인 필요 |
| B3 | 쿼리 분석을 단일 단계로 통합 | 합의 완료 |
| B4 | 라우팅 전후 골드셋 비교 측정 | 쟁점 4 확장 |
| B5 | 태스크별 동적 RRF 가중치 적용 | 쟁점 5 -- Codex 확인 필요 |

### Phase C: 백엔드 분리 (1-2주)

| # | 작업 | 합의 상태 |
|---|------|----------|
| C1 | 논리적 Strategy 분리 (RetrievalStrategy 인터페이스) | 쟁점 2 -- Codex 확인 필요 |
| C2 | TableStrategy 구현 (heading_path 필터 + row/column 스코어링) | 합의 완료 (방식만 쟁점) |
| C3 | DocumentStrategy 구현 (section hierarchy 우선) | 합의 완료 |
| C4 | CodeStrategy 구현 (identifier + AST 경계) | 합의 완료 |
| C5 | Orchestrator에서 테이블/도메인 하드코딩 제거 | 합의 완료 |
| C6 | EvidenceBuilder 부스팅 규칙 축소 | 합의 완료 |
| C7 | 성능 병목 확인 시 물리적 Retriever 분리로 전환 | 쟁점 2 확장 |

### Phase D: 검색 품질 강화 (2-3주)

| # | 작업 | 합의 상태 |
|---|------|----------|
| D1 | BGE-Reranker-v2-m3 벤치마크 및 교체 | 합의 완료 |
| D2 | Section-aware 검색 (heading_path 계층 확장) | 합의 완료 |
| D3 | Parent-Child Chunking 도입 | 쟁점 6 -- 순서 합의 필요 |
| D4 | CRAG-style 검색 평가 게이트 | 합의 완료 |
| D5 | HyDE (복잡 쿼리 라우터 연동) | 합의 완료 |
| D6 | Contextual Retrieval 효과 측정 (A5에서 시작한 배치잡 결과) | 쟁점 3 연속 |

### Phase E: 고급 기법 + 본격 평가 (향후)

| # | 작업 | 조건 |
|---|------|------|
| E1 | RAPTOR 트리 인덱싱 | 장문 문서 품질 여전히 부족 시 |
| E2 | RAGAS/CRUX 기반 평가 대시보드 | Phase D 완료 후 |
| E3 | ColBERT / Late Interaction | 코퍼스 대폭 확장 시 |
| E4 | GraphRAG / LazyGraphRAG | 교차 문서 테마 검색 필요 시 |

---

## 5. Codex 응답 요청 사항

아래 6개 질문에 대한 Codex의 명시적 동의/반대/수정안을 요청합니다.

| # | 질문 | Opus 제안 |
|---|------|----------|
| Q1 | 2단계 라우터 (휴리스틱 Fast + LLM Deep)에 동의하는가? | 신뢰도 0.8 임계값 기반 분기 |
| Q2 | 논리적 Strategy 분리 먼저, 물리적 분리는 병목 확인 후로 동의하는가? | RetrievalStrategy 인터페이스 |
| Q3 | Contextual Retrieval을 Phase A와 병렬 시작에 동의하는가? | 인덱싱 변경이므로 구조와 독립 |
| Q4 | 최소 골드셋 30개를 Phase A와 동시 구축에 동의하는가? | 20-30개 쿼리 + expected 결과 |
| Q5 | 태스크별 동적 RRF 가중치에 동의하는가? | retrieval_task -> weight lookup |
| Q6 | Section-aware - Parent-Child - RAPTOR 순서에 동의하는가? | 구현 난이도순 점진 적용 |

---

## 6. 합의 도달 기준

모든 쟁점에 대해 다음 중 하나가 확정되면 합의 완료:

- **동의**: 양측이 제안을 수용
- **수정 합의**: 양측이 수정된 버전에 합의
- **보류**: 구현 후 데이터로 결정 (실험적 검증 대상으로 전환)

합의 완료 후, 최종 실행 계획서(execution-plan.md)를 작성하여 구현에 착수합니다.
