# JARVIS RAG 검색 알고리즘 연구 비교 리포트

Date: 2026-03-27
Purpose: Claude Opus 4.6 vs Codex 연구 결과 비교 분석 — 토의용 자료

---

## 1. 연구 범위 비교

| 항목 | Claude Opus 4.6 | Codex |
|------|-----------------|-------|
| **분석 대상** | 현재 구현 코드 전체 (14개 파일) + 외부 논문/블로그 | 현재 구현 관찰 (4개 핵심 파일) + 학술 논문 |
| **논문 수** | ~20편 (arxiv, 블로그 포함) | 13편 (ACL/EMNLP/NAACL/ICLR 학회 논문 중심) |
| **논문 소스 특성** | arxiv 프리프린트 + 기업 블로그 (Anthropic, Microsoft, Jina, Weaviate) | ACL Anthology 피어리뷰 논문 위주 |
| **접근 방식** | 기법 카탈로그 (기술별 분류) | 문제 진단 중심 (실패 모드별 분류) |
| **실행 관점** | 기술 적용 가능성 평가 (M1 Max 적합도) | 아키텍처 재설계 제안 (구조적 해결) |

---

## 2. 현재 문제 진단 — 공통 합의점

두 연구가 **동일하게 지적한 핵심 문제**:

### 2.1 Intent-Retrieval Entanglement (의도-검색 결합)

| | Claude Opus | Codex |
|--|-------------|-------|
| **진단** | Query rewriting이 5개 파일에 분산 (query_normalization, identifier_restoration, planner, query_decomposer, orchestrator) | Query rewriting이 여러 산발적 regex 분기에 분산 |
| **원인** | 각 레이어가 독립적으로 의도를 해석하려 시도 | 저수준 검색 코드가 "숫자가 테이블 행인가", "청크가 설명적인가" 같은 결정을 내림 |
| **제안** | Query routing을 하나의 명시적 단계로 통합 | Planner가 structured `retrieval_task` JSON 출력 |

**합의**: 쿼리 분석은 **단일 단계에서 완결**되어야 하며, 하위 레이어에 의도 판단이 누출되면 안 된다.

### 2.2 Table/Prose Retrieval 혼합

| | Claude Opus | Codex |
|--|-------------|-------|
| **진단** | `_table_field_hints()`에 한국어 식사 용어 하드코딩, `_should_use_structured_row_lookup()`에 도메인 용어 직접 삽입 | 테이블 행 검색 로직이 일반 검색 오케스트레이션 내부에서 호출됨 |
| **영향** | 문서 쿼리가 스프레드시트 결과로 오염 가능 | 숫자 언급이 잘못된 검색 경로를 트리거 |
| **제안** | 도메인 하드코딩을 설정 파일로 분리 | `DocumentRetriever`와 `TableRetriever`를 완전 분리 |

**합의**: 테이블 검색과 문서 검색은 **별도 백엔드**로 분리되어야 한다.

### 2.3 Score Boosting이 검색 품질을 대체

| | Claude Opus | Codex |
|--|-------------|-------|
| **진단** | 11개 boost/penalty 규칙, RRF 점수 ~0.016에 filename boost 0.20 = **12x 증폭** | 랭킹이 청킹/섹션인식/문서유형/의도분류 한계를 보상 중 |
| **근본 원인** | 검색 표현(representation)이 너무 평탄(flat) | 검색 표현이 너무 평탄 |
| **해결 방향** | 더 강한 reranker + contextual retrieval로 부스팅 불필요하게 | 계층적 문서 검색 + 태스크 라우팅으로 구조적 해결 |

**합의**: 부스팅 규칙 추가는 **증상 치료**이며, 검색 표현과 라우팅의 **근본 개선**이 필요하다.

### 2.4 문서 계층 구조 부재

| | Claude Opus | Codex |
|--|-------------|-------|
| **진단** | heading 3레벨만 저장, 섹션/문서 레벨 검색 단계 없음 | 장문 문서가 평탄 청크로만 인덱싱, 문서 구조 손실 |
| **제안** | RAPTOR 트리 인덱싱 (Priority 3) | document → heading → chunk 3단계 계층 검색 (Phase 2) |

**합의**: 장문 문서는 **계층적 검색** (문서 → 섹션 → 청크)이 필요하다.

---

## 3. 연구 결과 차이점

### 3.1 Codex만 강조한 영역

| 주제 | 내용 | 평가 |
|------|------|------|
| **FunnelRAG** (coarse-to-fine) | 모델 용량 증가 + 후보 수 감소의 점진적 검색 | RAPTOR/TreeRAG와 유사한 계층적 접근이지만 실행 프레임워크가 더 구체적 |
| **H-STAR** (테이블 추론 분리) | 의미 해석과 구조적 테이블 추론을 분리 | JARVIS 테이블 검색에 직접 적용 가능한 핵심 논문 |
| **TAP4LLM** (테이블 처리) | 테이블 샘플링, 증강, 패킹 전략 | 현재 row-level chunking 대비 더 정교한 테이블 표현 |
| **TreeRAG** (양방향 트리 순회) | 트리 청킹 + 양방향 순회로 장문 검색 | RAPTOR의 대안/보완 접근 |
| **BRIGHT** (추론 기반 검색) | 추론 단계를 검색 쿼리로 활용 | 복잡 쿼리에서 검색 품질 대폭 향상 |
| **Q-PRM** (적응형 쿼리 재작성) | 프로세스 감독 기반 적응적 쿼리 재작성 | LLM 활용 쿼리 분석의 이론적 근거 |
| **CRUX / GRADE** (검색 평가) | 검색 컨텍스트 직접 평가, 검색/추론 난이도 분리 | 평가 프레임워크 설계에 필수 |
| **Self-Route** (라우팅) | RAG vs 장문 컨텍스트 간 자기반성 기반 라우팅 | 쿼리 라우터 설계의 이론적 근거 |

### 3.2 Claude Opus만 다룬 영역

| 주제 | 내용 | 평가 |
|------|------|------|
| **Anthropic Contextual Retrieval** | 청크에 LLM 생성 컨텍스트 접두사 추가, 실패율 49-67% 감소 | Codex가 "Context is Gold" 논문으로 유사 문제 언급했으나 Anthropic 구현은 미포함 |
| **Parent-Child Chunking** | 소형 청크(검색용) + 대형 청크(컨텍스트용) 이중 인덱스 | 실용적이고 구현 난이도 낮음, Codex 미언급 |
| **ColBERT/Jina-ColBERT-v2** (Late Interaction) | 토큰 수준 MaxSim, 다국어 89개 언어 | 정확도 높지만 복잡도도 높음 |
| **CRAG** (Corrective RAG) | 검색 품질 평가 후 교정/재시도 | Self-RAG와 함께 자기교정 아키텍처의 핵심 |
| **Self-RAG** (자기반성 검색) | 검색 필요성 판단 + 결과 자기비평 | ICLR 2024 Oral, 개념 차용 가능 |
| **SPLADE** (학습된 희소 검색) | BM25 대체 의미 기반 희소 벡터 | 미래 검토 대상 |
| **Late Chunking** (Jina) | 문서 전체 임베딩 후 청킹 | 3.6% 개선으로 효과 제한적 |
| **Proposition-Based Indexing** | 원자적 사실 단위 인덱싱 | 팩트 밀집 문서에 효과적 |
| **RAGAS** (평가 프레임워크) | 참조 없는 검색+생성 평가 | Codex도 RAGAs 언급했으나 Claude가 더 상세 |
| **BGE-Reranker-v2-m3** | 현 reranker 드롭인 교체 후보 | 실용적 즉시 적용 가능 |
| **MICE** (Minimal Interaction Cross-Encoder) | Cross-encoder 4x 속도 향상 | 2025년 최신, 로컬 시스템에 유망 |
| **GraphRAG / LazyGraphRAG** | 지식 그래프 기반 RAG, 경량 변형 | 교차 문서 테마 검색용 |
| **LanceDB distance→score 버그** | cosine vs L2 변환 오류 가능성 | 즉시 확인 필요한 실제 버그 |
| **Cross-encoder 512자 절단** | 한국어 밀도 미고려 | 즉시 수정 가능한 Quick Fix |

---

## 4. 제안된 아키텍처 비교

### 4.1 Codex 제안: 구조적 재설계

```
Query → [Normalize] → [Planner: retrieval_task JSON]
                            ↓
                    ┌───────┼───────┐
                    ↓       ↓       ↓
            DocumentRetriever  TableRetriever  CodeRetriever
            (heading-aware)    (row/col-aware)  (file/id-aware)
                    ↓       ↓       ↓
                    └───────┼───────┘
                            ↓
                    [Stronger Reranker]
                            ↓
                    [Answer Grounding]
```

**특징**: 태스크 라우팅 우선, 백엔드 분리, 계층 검색

### 4.2 Claude Opus 제안: 점진적 기술 적용

```
Phase 1: Quick Fix (distance 버그, 512자 확장, 부스팅 정리)
    ↓
Phase 2: Hybrid Search (LanceDB BM25) + Query Routing
    ↓
Phase 3: Contextual Retrieval + Parent-Child Chunking + CRAG
    ↓
Phase 4: RAPTOR Tree + BGE-Reranker-v2-m3 업그레이드
    ↓
Phase 5: ColBERT / GraphRAG (코퍼스 확장 시)
```

**특징**: 기존 구조 위에 기술 레이어 적용, ROI 기반 우선순위

---

## 5. 실행 전략 비교

| 관점 | Codex | Claude Opus |
|------|-------|-------------|
| **최우선 조치** | Planner에 `retrieval_task` 출력 + 테이블/문서 검색 분리 | LanceDB distance 버그 수정 + Hybrid Search 활성화 |
| **접근 철학** | "구조를 먼저 고치면 증상이 사라진다" | "가장 쉬운 것부터 적용하며 점진적으로 개선" |
| **리스크** | 대규모 리팩터링 필요, 회귀 위험 높음 | 구조적 문제가 계속 잔존할 수 있음 |
| **평가** | 검색 회귀 데이터셋 + 메트릭 대시보드 (Phase 4) | RAGAS 배치 평가 (별도 언급) |
| **LLM 활용** | Planner에서 retrieval_task JSON 생성에 LLM 사용 | HyDE, Contextual Retrieval, Multi-query에 LLM 사용 |

---

## 6. 논문 출처 품질 비교

| 기준 | Codex | Claude Opus |
|------|-------|-------------|
| **피어리뷰 논문** | 13/13 (100%) | ~10/20 (50%) |
| **기업 블로그/문서** | 0 | ~10/20 (Anthropic, Microsoft, Jina, Weaviate 등) |
| **학회 수준** | ACL, EMNLP, NAACL, ICLR, EACL | arxiv 프리프린트 + 일부 학회 |
| **최신성** | 2023-2025 | 2022-2026 |
| **실용 검증** | 학술 벤치마크 위주 | 산업 적용 사례 포함 |

**평가**: Codex는 학술적 엄밀성이 높고, Claude Opus는 실용적 범위가 넓다. 두 관점은 **상호 보완적**이다.

---

## 7. 통합 권장 로드맵

두 연구를 종합한 최적 실행 순서:

### Phase 1: 즉시 수정 (1-2일)

| # | 작업 | 출처 | 근거 |
|---|------|------|------|
| 1 | LanceDB distance→score 변환 검증/수정 | Opus | 실제 버그 가능성 |
| 2 | Cross-encoder 입력 512자→1024자 확장 | Opus | 한국어 토큰 활용률 향상 |
| 3 | `_table_field_hints()` / `_should_use_structured_row_lookup()` 설정 파일 분리 | 공통 | 하드코딩 제거 |

### Phase 2: 태스크 라우팅 도입 (3-5일)

| # | 작업 | 출처 | 근거 |
|---|------|------|------|
| 4 | Planner에 `retrieval_task` JSON 출력 추가 | Codex | Self-Route, Adaptive-RAG 근거 |
| 5 | `TableRetriever` 분리 (orchestrator에서 테이블 로직 추출) | Codex | H-STAR, TAP4LLM 근거 |
| 6 | Query rewriting을 단일 단계로 통합 | 공통 | HyDE, Q-PRM, BRIGHT 근거 |

### Phase 3: 검색 품질 강화 (1-2주)

| # | 작업 | 출처 | 근거 |
|---|------|------|------|
| 7 | Contextual Retrieval 적용 (청크 컨텍스트 접두사) | Opus | Anthropic 연구, 실패율 49-67% 감소 |
| 8 | Parent-Child Chunking 도입 | Opus | 검색 정밀도 + 컨텍스트 품질 동시 향상 |
| 9 | BGE-Reranker-v2-m3 벤치마크 및 교체 | Opus | 다국어 reranking 성능 향상 |
| 10 | CRAG-style 검색 평가 게이트 | Opus | 신뢰도 미달 시 쿼리 재구성 |

### Phase 4: 계층적 검색 (2-3주)

| # | 작업 | 출처 | 근거 |
|---|------|------|------|
| 11 | Document → Section → Chunk 계층 인덱스 | Codex | RAPTOR, TreeRAG, FunnelRAG 근거 |
| 12 | Section-aware `DocumentRetriever` 구현 | Codex | "Context is Gold" 논문 근거 |
| 13 | EvidenceBuilder 부스팅 규칙 축소 | 공통 | 구조적 개선으로 보상적 부스팅 불필요 |

### Phase 5: 평가 체계 (병렬 진행)

| # | 작업 | 출처 | 근거 |
|---|------|------|------|
| 14 | 검색 회귀 골드 테스트셋 구축 | Codex | RAGAs, CRUX, GRADE 근거 |
| 15 | 소스 문서/섹션/테이블행 정확도 별도 측정 | Codex | 검색 평가와 생성 평가 분리 |
| 16 | RAGAS 배치 평가 파이프라인 | Opus | 오프라인 파이프라인 튜닝용 |

### Phase 6: 고급 기법 (향후 검토)

| 기법 | 조건 | 출처 |
|------|------|------|
| RAPTOR 트리 인덱싱 | 장문 문서 검색 품질 부족 시 | 공통 |
| ColBERT / Late Interaction | 코퍼스 대폭 확장 시 | Opus |
| GraphRAG / LazyGraphRAG | 교차 문서 테마 검색 필요 시 | Opus |
| HyDE | 복잡 쿼리 Router와 결합 시 | 공통 |
| SPLADE | BM25 한계 도달 시 | Opus |

---

## 8. 토의 안건

### 안건 1: 구조 우선 vs 기술 우선

- **Codex 관점**: 아키텍처(라우팅, 백엔드 분리)를 먼저 정리해야 기술 적용 효과가 극대화
- **Opus 관점**: Quick Fix와 기술 레이어(Hybrid Search, Contextual Retrieval)를 빠르게 적용하여 즉시 품질 향상
- **질문**: Phase 1 Quick Fix 후 바로 Phase 2 구조 개편으로 가는 **하이브리드 접근**이 적절한가?

### 안건 2: LLM 활용 범위

- Planner의 `retrieval_task` JSON 생성에 LLM을 사용할 경우 추가 1.5초 레이턴시
- 휴리스틱 라우터로 시작 후 LLM 라우터로 점진적 전환이 합리적인가?
- Contextual Retrieval의 1회성 LLM 배치잡(~9시간)은 수용 가능한가?

### 안건 3: 테이블 검색 분리 범위

- 현재 `table-row-*` heading_path 기반 청크가 일반 벡터 인덱스에 혼재
- 완전 분리(별도 인덱스) vs 라우팅만 분리(같은 인덱스, 다른 검색 로직)?
- H-STAR 논문의 의미 해석/구조적 추론 분리를 어디까지 적용할 것인가?

### 안건 4: 평가 체계 우선순위

- Codex: 검색 회귀 데이터셋을 Phase 4에 배치 (나중)
- 제안: Phase 2와 **병렬로** 골드 테스트셋 구축 시작하여 이후 변경의 효과를 정량 측정
- 최소 몇 개의 테스트 케이스로 시작해야 유의미한가?

### 안건 5: Reranker 업그레이드 타이밍

- 현재 mmarco-mMiniLMv2 (CPU, ~450MB) → BGE-Reranker-v2-m3 교체 시
- 구조 개편 전에 교체하면 효과 측정이 어려울 수 있음
- 구조 개편 후 교체하여 순수 reranker 효과를 분리 측정하는 것이 나은가?

---

## 9. 핵심 논문 통합 목록

### 검색 아키텍처
| 논문 | 핵심 기여 | 출처 |
|------|----------|------|
| FunnelRAG (Zhao 2025) | Coarse-to-fine 점진적 검색 | Codex |
| RAPTOR (Sarthi 2024) | 계층적 요약 트리 검색, QuALITY +20% | 공통 |
| TreeRAG (Tao 2025) | 양방향 트리 순회 장문 검색 | Codex |
| Self-RAG (2024 ICLR Oral) | 자기반성 토큰 기반 검색/생성 | Opus |
| CRAG (2024) | 교정적 검색, Self-RAG 대비 +20% 정확도 | Opus |
| Adaptive-RAG (NAACL 2024) | 쿼리 복잡도 기반 검색 라우팅 | Opus |
| GraphRAG / LazyGraphRAG (Microsoft) | 지식 그래프 + 커뮤니티 요약 | Opus |

### 테이블 검색
| 논문 | 핵심 기여 | 출처 |
|------|----------|------|
| TAP4LLM (Sui 2024) | 테이블 샘플링/증강/패킹 전략 | Codex |
| H-STAR (Abhyankar 2025) | 의미 해석 vs 구조적 추론 분리 | Codex |

### 쿼리 처리
| 논문 | 핵심 기여 | 출처 |
|------|----------|------|
| HyDE (Gao 2023) | 가상 문서 임베딩으로 쿼리-문서 간극 해소 | 공통 |
| BRIGHT (2024) | 추론 단계를 검색 쿼리로 활용 | Codex |
| Q-PRM (Ye 2025) | 프로세스 감독 기반 적응적 쿼리 재작성 | Codex |
| Self-Route (Li 2024) | RAG vs 장문 컨텍스트 자기반성 라우팅 | Codex |

### 인덱싱/청킹
| 논문 | 핵심 기여 | 출처 |
|------|----------|------|
| Contextual Retrieval (Anthropic) | 청크 컨텍스트 접두사, 실패율 49-67% 감소 | Opus |
| "Context is Gold" (Conti 2025) | 청크 임베딩의 문서 컨텍스트 손실 증명 | Codex |
| Late Chunking (Jina 2024) | 문서 전체 임베딩 후 청킹, +3.6% | Opus |
| Dense X Retrieval (2023) | 원자적 사실 단위 인덱싱, +4.9~7.8 EM | Opus |
| ColBERTv2 (2022) | Late interaction, 단일 벡터 대비 +4-10 nDCG | 공통 |

### 리랭킹
| 논문/모델 | 핵심 기여 | 출처 |
|-----------|----------|------|
| BGE-Reranker-v2-m3 | M3 백본 다국어 cross-encoder | Opus |
| MICE (2025) | Cross-encoder 4x 속도 향상 | Opus |
| RankGPT / RankZephyr | LLM 기반 listwise 리랭킹 | Opus |

### 평가
| 논문 | 핵심 기여 | 출처 |
|------|----------|------|
| RAGAs (Es 2024) | 참조 없는 검색+생성 평가 | 공통 |
| CRUX (Ju 2025) | 검색 증강 컨텍스트 직접 평가 | Codex |
| GRADE (Lee 2025) | 검색/추론 난이도 분리 평가 | Codex |

---

## 10. Claude Opus 독립 의견 (Codex 검토용)

본 섹션은 Claude Opus 4.6의 독립적 기술 판단을 기록합니다. Codex와의 합의가 아닌, 이견이나 우려 사항을 포함합니다.

### 의견 1: 구조 개편 전에 Quick Fix가 선행되어야 한다

Codex는 "Planner에 retrieval_task 도입 + 백엔드 분리"를 최우선으로 제안합니다. 동의하지만, **순서에 이견이 있습니다**.

LanceDB distance→score 변환과 cross-encoder 512자 절단은 **현재 검색 결과의 정확도를 직접 훼손하는 버그**입니다. 구조 개편은 최소 3-5일이 소요되는데, 그 기간 동안 버그가 있는 파이프라인 위에서 작업하게 됩니다. 또한 구조 개편 후 성능 비교를 하려면, **개편 전 베이스라인이 버그 없는 상태**여야 정확한 효과 측정이 가능합니다.

**제안**: Quick Fix (1-2일) → 베이스라인 측정 → 구조 개편 순서가 과학적으로 올바릅니다.

### 의견 2: Codex의 `retrieval_task` JSON 설계에 LLM 의존도 우려

Codex가 제안한 retrieval_task JSON 예시:

```json
{
  "task": "document_qa",
  "entities": {
    "target_document": "한글문서 파일형식",
    "section_topic": "그리기 개체 자료 구조",
    "subtopic": "기본 구조"
  }
}
```

이 수준의 구조화된 출력을 **정확하게** 생성하려면 LLM 호출이 필수적입니다. 현재 EXAONE-3.5-7.8B로 1.5초가 추가되는데, 이는 **모든 쿼리에** 적용됩니다. 현재 Planner의 휴리스틱 분석은 ~5ms입니다.

"안녕 자비스, 오늘 점심 뭐야?" 같은 단순 쿼리에도 1.5초 LLM 호출을 하는 것은 과도합니다.

**제안**: 2단계 라우터가 필요합니다.
1. **Fast Path** (휴리스틱, ~5ms): 단순 패턴 매칭으로 `table_lookup`, `smalltalk`, `simple_qa` 분류
2. **Deep Path** (LLM, ~1.5s): 휴리스틱 신뢰도 < 0.7일 때만 LLM으로 정밀한 retrieval_task JSON 생성

이것은 Adaptive-RAG 논문의 쿼리 복잡도 라우팅과 정확히 일치하는 접근입니다.

### 의견 3: 백엔드 완전 분리보다 라우팅 분리가 현실적

Codex는 `DocumentRetriever`, `TableRetriever`, `CodeRetriever`를 완전 별개 백엔드로 분리할 것을 제안합니다. 원칙적으로 동의하지만, **현실적 우려**가 있습니다:

1. **인덱스 중복**: 동일 문서가 테이블과 텍스트를 모두 포함하는 경우 (HWP 파일이 대표적) 어느 Retriever가 담당하는가?
2. **교차 검색**: "이 HWP 문서의 3페이지 표에서..." 같은 쿼리는 DocumentRetriever와 TableRetriever를 **모두** 호출해야 함
3. **코드량**: 3개 Retriever 각각에 FTS + Vector + Rerank 파이프라인을 구현하면 코드 3배 증가

**제안**: 물리적 백엔드 분리 대신 **논리적 라우팅 분리**를 먼저 적용합니다.
- 단일 HybridSearch 엔진 유지
- `RetrievalStrategy` 인터페이스로 검색 파라미터/필터/부스팅을 분리
- `TableStrategy`는 `heading_path LIKE 'table-%'` 필터 + row/column 특화 스코어링
- `DocumentStrategy`는 section hierarchy 우선 검색 + prose 특화 스코어링
- `CodeStrategy`는 identifier 매칭 + AST 경계 인식

이 방식이면 인덱스 중복 없이, 기존 인프라 위에서 라우팅 효과를 얻을 수 있습니다. 이후 성능 병목이 확인되면 물리적 분리로 전환해도 늦지 않습니다.

### 의견 4: Contextual Retrieval이 Codex 리뷰에서 누락된 점이 아쉽다

Codex는 "Context is Gold" 논문(Conti 2025)으로 "청크가 문서 컨텍스트를 잃는다"는 문제를 정확히 진단했습니다. 그런데 이 문제의 **가장 직접적인 해결책**인 Anthropic의 Contextual Retrieval을 언급하지 않았습니다.

Contextual Retrieval은:
- 검색 실패율 **49-67% 감소** (Anthropic 벤치마크)
- 1회성 배치잡으로 기존 인덱스에 적용 가능
- 구조 개편과 **독립적으로** 적용 가능 (기존 청크에 컨텍스트 접두사만 추가)

계층적 검색(RAPTOR/TreeRAG)은 인덱스 구조 자체를 변경해야 하지만, Contextual Retrieval은 **기존 flat 인덱스 위에서** 즉시 효과를 볼 수 있습니다. 구조 개편 기간 동안 검색 품질을 높이는 **중간 다리** 역할을 할 수 있습니다.

**제안**: Phase 2 (태스크 라우팅)과 병렬로 Contextual Retrieval 배치잡 실행. ~9시간 EXAONE 인퍼런스로 22K 청크 처리.

### 의견 5: 평가 체계가 Phase 4에 있으면 너무 늦다

Codex는 검색 회귀 데이터셋을 Phase 4에 배치했습니다. 이것은 **심각한 문제**입니다.

Phase 2-3에서 대규모 구조 변경(라우팅 도입, Retriever 분리, 계층 검색)을 수행하는데, 변경의 효과를 **정량적으로 측정할 방법이 없는 상태**에서 진행하게 됩니다. 이는 "감으로 튜닝"하는 현재 상황과 본질적으로 동일합니다.

**제안**: 최소 골드 테스트셋(20-30개 쿼리)을 Phase 1과 **동시에** 구축해야 합니다. 구성:
- 문서 QA 5개 (HWP/PDF 섹션 검색)
- 테이블 lookup 5개 (정확한 행/열 검색)
- 코드 검색 5개 (함수/클래스 찾기)
- 혼합 쿼리 5개 (인사 + 태스크, 숫자 포함 산문)
- STT 오류 쿼리 5개 (음성 인식 왜곡)
- Edge case 5개 (다국어 혼합, 긴 쿼리, 다중 의도)

각 쿼리에 expected_document, expected_section, expected_answer_span을 기록합니다.

### 의견 6: Parent-Child Chunking과 RAPTOR의 우선순위

두 기법 모두 계층적 검색을 다루지만, **복잡도 차이가 크다**:

| 기준 | Parent-Child Chunking | RAPTOR |
|------|----------------------|--------|
| 구현 난이도 | 낮음 (이중 인덱스) | 높음 (클러스터링 + 요약 트리) |
| 인덱싱 비용 | 청킹 2x | LLM 요약 수천 회 |
| 쿼리 시 동작 | child 검색 → parent 반환 | 전체 트리 플래트닝 + 검색 |
| 효과 범위 | 컨텍스트 품질 향상 | 문서 간 테마 + 계층 이해 |

RAPTOR는 "문서 전체를 이해해야 하는 복잡한 QA"에 강하지만, JARVIS의 현재 주요 실패 모드는 "올바른 청크를 찾았지만 컨텍스트가 부족"하거나 "잘못된 타입의 청크를 반환"하는 것입니다.

**제안**: Parent-Child를 먼저 적용하고, 그래도 해결되지 않는 장문 문서 문제에 대해서만 RAPTOR를 검토. Codex의 Section-aware 검색은 Parent-Child의 자연스러운 확장이므로 양립 가능합니다.

### 의견 7: RRF vector_weight=2.0의 재검토 필요성

현재 RRF에서 벡터 검색 가중치가 2.0으로 FTS 대비 2배입니다. 이유는 "한국어→영어 교차 언어 검색"을 위함인데, 이 가중치가 **모든 쿼리에 일률적으로** 적용됩니다.

문제:
- 순수 한국어 문서에 대한 한국어 쿼리는 FTS가 더 정확할 수 있음 (형태소 분석 Kiwi가 정밀)
- 코드 검색에서는 정확한 식별자 매칭(FTS)이 의미 유사도(Vector)보다 중요
- 테이블 row 검색에서 "Day=5"는 FTS 완전 일치가 벡터 유사도보다 확실

**제안**: 라우팅 도입 시 `retrieval_task`에 따라 RRF 가중치를 동적으로 조정:
- `document_qa` (교차 언어): vector_weight=2.0 유지
- `table_lookup`: vector_weight=0.5, fts_weight=2.0
- `code_lookup`: vector_weight=0.5, fts_weight=2.0
- `multi_doc_qa`: vector_weight=1.5

이것은 Codex의 라우팅 제안과 Opus의 기존 Hybrid Search를 **결합하는** 자연스러운 확장입니다.

### 의견 요약

| # | 주제 | Opus 입장 | Codex와의 차이 |
|---|------|----------|---------------|
| 1 | 실행 순서 | Quick Fix → 베이스라인 → 구조 개편 | Codex는 구조 우선 |
| 2 | LLM 라우팅 | 2단계 라우터 (휴리스틱 + LLM 폴백) | Codex는 LLM 기반 retrieval_task |
| 3 | 백엔드 분리 | 논리적 Strategy 분리 먼저, 물리적 분리는 나중 | Codex는 물리적 Retriever 분리 |
| 4 | Contextual Retrieval | 구조 개편과 병렬로 즉시 적용 | Codex 미언급 |
| 5 | 평가 체계 | Phase 1과 동시 시작 (최소 30개 골드셋) | Codex는 Phase 4 |
| 6 | 계층 검색 | Parent-Child 먼저, RAPTOR는 후순위 | Codex는 RAPTOR/TreeRAG 중심 |
| 7 | RRF 가중치 | 태스크별 동적 가중치 | 현재 고정 가중치에 대한 언급 없음 |

---

## 11. 결론

### 공통 결론
1. 현재 파이프라인의 핵심 문제는 **구조적** (부스팅 누적, 의도 누출, 테이블/문서 혼합)
2. 더 많은 휴리스틱 튜닝은 **역효과** — 근본 개선 필요
3. **계층적 검색**과 **태스크 라우팅**이 가장 높은 우선순위

### 상호 보완
- **Codex**: 문제 진단과 아키텍처 재설계의 논리적 근거가 강함 (학술 논문 기반)
- **Opus**: 구체적 기술 적용 방안과 M1 Max 실행 가능성 평가가 강함 (실용 관점)
- **최적 전략**: Codex의 구조적 재설계를 뼈대로, Opus의 기술 레이어를 살로 붙이는 접근

### 즉시 합의 가능 사항
1. LanceDB distance 변환 버그 수정
2. Cross-encoder 입력 확장
3. 테이블 검색 로직 orchestrator에서 분리
4. Planner에 `retrieval_task` 구조화 출력 추가
5. 검색 평가 골드 테스트셋 구축 시작
