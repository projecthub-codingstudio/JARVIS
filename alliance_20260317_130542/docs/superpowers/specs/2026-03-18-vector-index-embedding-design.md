# Vector Index + Embedding Runtime Design

> **Status note (2026-03-25):** This is a historical design document. The current runtime still degrades gracefully when optional vector dependencies are unavailable, but it no longer treats missing retrieval state as a stub-evidence path for grounded answering.

**Date**: 2026-03-18
**Status**: Approved (spec review passed)
**Spec References**: TASK-E93DF600 (Sec 5, 7, 9, 11, 12, 13), TASK-9A8DC5D5 (Sec 4, 7, 10, 13)
**Embedding Dimension**: 1024 (BGE-M3 output)

---

## Overview

Implement the semantic search component of JARVIS's hybrid retrieval pipeline. Currently FTS5 (keyword) is fully operational but the vector (semantic) side is a stub. This design adds BGE-M3 embedding generation and LanceDB vector storage to enable true hybrid search via RRF fusion.

## Tech Stack (per Spec)

| Component | Technology | Reason |
|-----------|-----------|--------|
| Embedding model | BGE-M3 via sentence-transformers | MLX 불가 (MEMORY.md), MPS(Metal) 가속 |
| Vector DB | LanceDB (serverless, file-based) | 서버 불필요, 로컬 파일 기반 |
| Search fusion | Existing HybridSearch (RRF k=60) | 이미 구현됨 |

## Architecture

### Component Responsibilities

**EmbeddingRuntime** (`runtime/embedding_runtime.py`):
- sentence-transformers + MPS 백엔드로 BGE-M3 로드 (1024차원)
- 온디맨드 로드/언로드 (첫 호출 시 로드, 유휴 시 타이머 언로드)
- 프로토콜 준수: `embed(texts: Sequence[str]) → list[list[float]]` (EmbeddingRuntimeProtocol)
- 내부 편의 메서드: `_embed_np(texts) → numpy.ndarray` (내부용, 프로토콜 외)
- Governor 연동: 리소스 부족 시 로드 거부 → 빈 리스트 반환
- `sentence-transformers` / `torch` 미설치 시 `ImportError` → stub 모드 유지 (FTS 전용)
- 배치 크기: MPS 기준 32-64 texts (메모리 안전 범위)

**VectorIndex** (`retrieval/vector_index.py`):
- LanceDB 파일 기반 저장 (`~/.jarvis/vectors.lance`, 1024차원)
- `add(chunk_ids, document_ids, embeddings)` — 벡터 추가/업데이트
- `remove(chunk_ids)` — 벡터 삭제 (tombstone 연동)
- 프로토콜 준수: `search(fragments: Sequence[TypedQueryFragment], top_k) → list[VectorHit]`
  - 내부에서 EmbeddingRuntime.embed()를 호출하여 질의 벡터 생성
  - Orchestrator 코드 변경 불필요 (기존 `self._vector_retriever.search(fragments)` 유지)
- DB 없거나 비어있으면 빈 결과 반환 (FTS만 동작)
- `lancedb` 미설치 시 `ImportError` → stub 모드 유지
- 기존 `VectorRetrieverProtocol` 인터페이스 유지

**Protocol Compliance Note**:
- 프로토콜은 Day 0에 frozen. `EmbeddingRuntimeProtocol.embed()` 시그니처 유지
- `VectorRetrieverProtocol.search(fragments, top_k)` 시그니처 유지
- VectorIndex가 내부적으로 EmbeddingRuntime 참조를 보유하여 질의 임베딩 생성
- 추가 메서드는 concrete class에만 존재 (프로토콜 불변)

**IndexPipeline 확장** (`indexing/index_pipeline.py`):
- 기존 즉시 경로: parse → chunk → FTS5 INSERT (변경 없음)
- 추가 지연 경로: `backfill_embeddings(batch_size)` — daemon thread
  - chunks 테이블에서 embedding_ref가 없는 chunk 조회
  - EmbeddingRuntime.embed() → LanceDB.add()
  - chunks.embedding_ref 업데이트
- 파일 삭제/이동 시 LanceDB에서도 벡터 제거

### Data Flow

```
[인덱싱 — 즉시]
  파일 → parse → chunk → FTS5 INSERT (즉시 검색 가능)

[인덱싱 — 지연 큐 (백그라운드 daemon)]
  chunks (embedding_ref IS NULL)
    → EmbeddingRuntime.embed(batch_texts)
    → VectorIndex.add(chunk_ids, embeddings)
    → UPDATE chunks SET embedding_ref = lance_id

[검색 — 사용자 질의]
  query → QueryDecomposer → fragments
           ↓                     ↓
     FTSIndex.search()    EmbeddingRuntime.embed_query(query)
           ↓                     ↓
     fts_hits              VectorIndex.search(query_vec, top_k)
           ↓                     ↓
          HybridSearch.fuse(fts_hits, vector_hits)
                    ↓
           EvidenceBuilder.build()
```

### Governor Integration (per Spec Section 12.2)

| 시스템 상태 | 임베딩 인덱싱 | 검색 시 질의 임베딩 |
|------------|-------------|-------------------|
| 전원 연결 + 유휴 | 적극 배치 수행 | 사용 |
| 전원 연결 + 업무 | 저우선 배치 | 사용 |
| 배터리 모드 | 중지 | 스킵 (FTS 전용) |
| 고부하/thermal | 중지 | 스킵 (FTS 전용) |
| 메모리 부족 | 중지 + 모델 언로드 | 스킵 (FTS 전용) |

### Memory Budget

- BGE-M3 모델: ~2.2GB (MPS 로드 시, fp16 ~1.1GB + sentence-transformers/MPS 오버헤드)
- LanceDB 인덱스: 파일 크기 비례 (chunk당 ~4KB, 1000 chunks ≈ 4MB)
- 검색 시 동시 로드: 임베딩(~2.2GB) + LLM(~9.3GB) = ~11.5GB
  - 15GB worst-case 기준 여유 ~3.5GB (OS/IDE/브라우저 포함)
  - Governor가 메모리 압박 감지 시 임베딩 언로드 → FTS 전용으로 전환
- 인덱싱 시: 임베딩만 로드 (~2.2GB), LLM 불필요 → 충분한 여유
- 질의 임베딩은 짧은 텍스트 1회 추론이므로 로드 후 즉시 언로드 가능

### Error Handling / Graceful Degradation

| 상황 | 동작 |
|------|------|
| BGE-M3 모델 미설치 / 로드 실패 | FTS5 전용 모드, 시작 시 경고 출력 |
| LanceDB 파일 손상 | 빈 벡터 결과 반환 → FTS만 사용 |
| Governor가 메모리 부족 판정 | 임베딩 로드 거부 → FTS 전용 |
| 임베딩 백로그 폭증 (Spec 13.3) | 최근 수정 파일 우선, 대용량 지연 |
| 검색 시 벡터 없는 chunk | FTS 점수만으로 RRF 순위 결정 (기존 동작) |

### Schema Changes

`chunks` 테이블에 `embedding_ref` 컬럼 추가:
- schema.sql에 `embedding_ref TEXT DEFAULT NULL` 추가
- 기존 DB 마이그레이션: bootstrap.py에서 `ALTER TABLE chunks ADD COLUMN embedding_ref TEXT DEFAULT NULL` (IF NOT EXISTS 패턴)
- `ChunkRecord` dataclass에 `embedding_ref: str = ""` 필드 추가
- NULL/빈 값이면 아직 임베딩 미생성 → 지연 큐 대상

### Thread Safety

- LanceDB: concurrent reads 지원, writes는 단일 스레드에서 수행
- backfill daemon: 전용 DB connection + 전용 LanceDB 테이블 핸들 사용 (기존 morpheme backfill 패턴과 동일)
- 검색 시 LanceDB read는 main thread에서 수행 (read-safe)

### Dependencies

```toml
# pyproject.toml 추가
"sentence-transformers>=3.0",
"lancedb>=0.8",
```

### Files to Create/Modify

| File | Action | Description |
|------|--------|-------------|
| `runtime/embedding_runtime.py` | **Rewrite** | stub → 실제 BGE-M3 로드/임베딩 |
| `retrieval/vector_index.py` | **Rewrite** | stub → LanceDB 기반 ANN 검색 |
| `indexing/index_pipeline.py` | **Modify** | backfill_embeddings() 추가 |
| `core/orchestrator.py` | **No change** | VectorIndex가 내부에서 임베딩 처리 (프로토콜 유지) |
| `contracts/models.py` | **Modify** | ChunkRecord에 embedding_ref 필드 추가 |
| `app/bootstrap.py` | **Modify** | 기존 DB 마이그레이션 (ALTER TABLE) |
| `__main__.py` | **Modify** | EmbeddingRuntime 초기화, backfill daemon |
| `sql/schema.sql` | **Modify** | chunks에 embedding_ref 컬럼 |
| `pyproject.toml` | **Modify** | sentence-transformers, lancedb 추가 |

### Testing Strategy

- Unit: EmbeddingRuntime.embed() 출력 shape/type 검증
- Unit: VectorIndex.add() + search() 왕복 테스트
- Integration: IndexPipeline → backfill → VectorIndex 검색 확인
- E2E: 질의 → hybrid search (FTS + vector) → 답변 생성
- Degradation: Governor 리소스 부족 시 FTS 전용 폴백 확인
