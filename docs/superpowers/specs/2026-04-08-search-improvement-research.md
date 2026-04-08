# JARVIS 검색 품질 향상 연구 보고서

> 작성일: 2026-04-08 | 대상: doc_find + RAG 파이프라인 전체

---

## 1. 현재 검색 아키텍처 요약

```
사용자 쿼리
  ├─ doc_find (builtin) ─→ 경로 매칭 + FTS ─→ 문서 목록 반환
  └─ RAG Pipeline ─→ Planner ─→ Query Decomposer
                        ├─ FTS (Kiwi 형태소 + BM25)
                        ├─ Vector (BGE-M3 + LanceDB)
                        └─→ RRF Fusion ─→ Reranker (cross-encoder) ─→ Evidence Builder ─→ LLM
```

### 핵심 구성요소 및 설정값

| 구성요소 | 모델/설정 | 비고 |
|---------|----------|------|
| Embeddings | BGE-M3 (CPU) | 22,692개 backfill 완료 |
| Vector DB | LanceDB | 파일 기반, serverless |
| FTS | SQLite FTS5 + Kiwi 형태소 | 한국어 NNG/NNP/VV/VA 태그 |
| Reranker | mmarco-mMiniLMv2-L12-H384-v1 | CPU, 배치=16 |
| Hybrid Fusion | RRF (k=60, vector_weight=2.0) | 벡터 2배 가중 |
| Chunking | 500 토큰, 80 오버랩 | 단락/테이블(행별)/코드(AST) 전략 |

---

## 2. 발견된 품질 병목 (우선순위 순)

### P1 — 즉시 개선 가능

#### 2.1 doc_find FTS AND 조인 과다 (builtin_capabilities.py:875)
- **현상**: `"term1" AND "term2" AND "term3"` — 모든 단어가 한 chunk에 동시 출현해야 매칭
- **영향**: "retrieval pipeline architecture" 검색 시 세 단어가 같은 chunk에 없으면 놓침
- **개선**: `AND` → `OR`로 변경하되, 매칭 term 수로 정렬 (현재 score=0 고정 문제도 해결)

#### 2.2 FTS 내용 검색 억제 조건 (builtin_capabilities.py:871)
- **현상**: 경로 매칭 결과가 5개 이상이면 FTS 내용 검색을 아예 건너뜀
- **영향**: 경로 매칭이 부정확한 5개를 찾으면 더 정확한 내용 매칭이 실행 안 됨
- **개선**: 항상 FTS 실행, 경로+내용 결과를 통합 랭킹

#### 2.3 이중언어 확장 사전 부족 (planner.py:82-111)
- **현상**: `_BILINGUAL_EXPANSIONS`에 ~20쌍만 하드코딩
- **영향**: "네트워크 매니저" → "network manager" 확장 안 됨 → 영문 코드 검색 실패
- **개선**: LLM 기반 동적 확장 또는 사전 확장 (200→500쌍)

### P2 — 품질 유의미 개선

#### 2.4 Reranker 점수 정규화 부재 (reranker.py:133)
- **현상**: `0.7 * ce_score + 0.3 * (rrf_score * 60)` — CE logit이 음수일 수 있어 유효 결과가 밀림
- **개선**: CE score에 sigmoid 적용 후 결합

#### 2.5 LanceDB 거리→점수 변환 오류 가능성 (vector_index.py:195)
- **현상**: `score = 1.0 - distance` — L2 거리일 경우 [0,1] 범위를 벗어남
- **개선**: cosine metric 명시적 설정 또는 거리 타입에 따른 정규화

#### 2.6 Section injection 풀 테이블 스캔 (strategy.py:356)
- **현상**: 모든 비-테이블 chunk를 매번 SELECT — 22K+ rows
- **개선**: heading_path 인덱스 추가 또는 FTS 기반 섹션 검색

### P3 — 장기 개선

#### 2.7 Learning 시스템 한계
- **현상**: 동일 세션 5분 내 재구성만 감지 (cross-session 학습 없음)
- **현상**: entity hints만 학습 (어떤 문서/chunk가 유용했는지 학습 안 함)
- **현상**: citation_paths가 저장되지만 활용 안 됨
- **개선**: 아래 섹션 3 참조

---

## 3. 피드백 기반 자동 검색 업그레이드 설계

### 3.1 피드백 수집 채널

```
[자동 수집]
1. 답변 후 사용자가 같은 주제로 재질문 → 불만족 시그널
2. 답변 후 "고마워", 추가 질문 없음 → 만족 시그널
3. 검색 결과에서 클릭한 문서 vs 안 한 문서 → 관련성 시그널
4. Clarify/Abstain 비율 추적 → 검색 실패율

[명시적 수집]
5. 답변에 👍/👎 버튼 → 직접 피드백
6. "이 문서가 아니라 다른 문서야" → 부정 피드백 + 올바른 문서 힌트
```

### 3.2 피드백 저장 스키마

```sql
CREATE TABLE search_feedback (
    feedback_id TEXT PRIMARY KEY,
    query_text TEXT NOT NULL,
    query_terms TEXT,          -- 추출된 검색어 (JSON array)
    retrieval_task TEXT,
    feedback_type TEXT,        -- 'implicit_satisfied', 'implicit_reformulated',
                               -- 'explicit_positive', 'explicit_negative',
                               -- 'document_click', 'document_skip'
    relevant_doc_paths TEXT,   -- 유용했던 문서 (JSON array)
    irrelevant_doc_paths TEXT, -- 관련 없었던 문서 (JSON array)
    citation_paths TEXT,       -- 실제 사용된 citation (JSON array)
    session_id TEXT,
    created_at REAL
);
```

### 3.3 자동 업그레이드 메커니즘

#### Phase 1: 쿼리-문서 연결 학습 (Query-Document Relevance)

현재 Learning 시스템이 entity hints만 학습하는 것을 확장:

```
피드백 수집 → 주기적 분석 (BatchScheduler, 10분)
  → 쿼리 패턴별 "자주 유용한 문서" 집계
  → QueryDocumentAffinity 테이블에 저장
    {query_pattern, document_path, affinity_score, hit_count}
  → 검색 시 RRF 점수에 affinity_score 부스트 적용
```

**예시**: "다이어트 식단" 쿼리에서 `14day_diet_supplements_final.xlsx`가 5회 선택됨
→ affinity_score=0.95 → 다음 "다이어트 관련" 검색 시 해당 문서 부스트

#### Phase 2: 검색어 확장 자동 학습

```
실패(abstain/clarify) → 성공(answer) 패턴에서:
  - 실패 쿼리의 검색어 → 성공 쿼리의 검색어 매핑
  - 자동으로 _BILINGUAL_EXPANSIONS에 추가
  - 또는 별도 learned_expansions 테이블로 관리
```

**예시**: "네트워크 매니저 찾아줘" 실패 → "NetworkManager 찾아줘" 성공
→ "네트워크 매니저" ↔ "NetworkManager" 확장 학습

#### Phase 3: 부스트 가중치 자동 튜닝

```
피드백 데이터 축적 (100+ 건) 후:
  → 현재 고정 부스트 값들을 피드백 기반으로 조정
  - filename_match_boost: 0.20 → 피드백 정확도에 따라 0.15~0.30
  - code_source_boost: 0.28 → 코드 질문 정확도에 따라 조정
  - vector_weight: 2.0 → 벡터 vs FTS 정확도 비교로 조정
```

### 3.4 구현 우선순위

| 단계 | 작업 | 예상 효과 | 난이도 |
|------|------|----------|--------|
| 1 | doc_find FTS OR 전환 + 점수 반영 | 문서 검색 recall 향상 | 낮음 |
| 2 | FTS 억제 조건 제거 | 검색 누락 방지 | 낮음 |
| 3 | 답변 피드백 UI (👍/👎) | 피드백 수집 시작 | 중간 |
| 4 | search_feedback 테이블 + 자동 수집 | 데이터 축적 | 중간 |
| 5 | Query-Document Affinity 학습 | 반복 쿼리 정확도 향상 | 중간 |
| 6 | 이중언어 확장 자동 학습 | 한→영 검색 향상 | 중간 |
| 7 | Reranker 점수 정규화 | 랭킹 정확도 | 낮음 |
| 8 | 부스트 가중치 자동 튜닝 | 전체 정확도 최적화 | 높음 |

---

## 4. 즉시 적용 가능한 Quick Wins

### 4.1 doc_find FTS 개선
```python
# 현재: AND (모든 term 동시 출현 필요)
fts_query = " AND ".join(f'"{t}"' for t in long_terms)

# 개선: OR + hit count 정렬
fts_query = " OR ".join(f'"{t}"' for t in long_terms)
# score = fts hit count (현재 0 고정 → 실제 hits 반영)
```

### 4.2 FTS 항상 실행
```python
# 현재: 경로 결과 5개 이상이면 FTS 건너뜀
if fts_query and len(results) < 5:

# 개선: 항상 실행
if fts_query:
```

### 4.3 Reranker sigmoid 정규화
```python
# 현재
combined = 0.7 * ce_score + 0.3 * (rrf_score * 60)

# 개선
import math
ce_normalized = 1.0 / (1.0 + math.exp(-ce_score))  # sigmoid [0,1]
combined = 0.7 * ce_normalized + 0.3 * min(1.0, rrf_score * 60)
```

---

## 5. 모니터링 지표

검색 품질 추적을 위한 핵심 메트릭:

| 지표 | 측정 방법 | 목표 |
|------|----------|------|
| Answer Rate | 1 - (abstain + clarify) / total | > 80% |
| Mean Reciprocal Rank | 정답 문서의 평균 역순위 | > 0.7 |
| Click-Through Rate | 검색 결과 중 클릭 비율 | > 60% |
| Reformulation Rate | 같은 주제 재질문 비율 | < 15% |
| Feedback Positive Rate | 👍 / (👍 + 👎) | > 85% |
| Cross-lingual Hit Rate | 한국어 쿼리→영문 문서 매칭 성공률 | > 70% |
