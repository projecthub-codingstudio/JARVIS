# Design Decisions

This page documents the key engineering decisions behind JARVIS — what was chosen, what was rejected, and why. These decisions were informed by two rounds of [Colligi2](https://colligi.ai) collective intelligence analysis (AI agents debating architecture trade-offs) and validated through hands-on implementation on the target hardware.

## How Decisions Were Made

```
Round 1 (Colligi2)          Round 2 (Colligi2)           Implementation
─────────────────           ─────────────────           ──────────────
Architecture design    →    Conflict resolution    →    Build + validate
Tech stack analysis         Implementation spec         Adjust from reality
Memory budget               Phase 0/1 detailed spec     Commit to decisions
Risk assessment             Error handling strategy      Document in DECISIONS.md
```

The Colligi2 analysis outputs are preserved in the repository:
- `colligi2_20260316_021200/` — Round 1: architecture, tech stack, memory budget
- `colligi2_20260316_133406/` — Round 2: implementation spec, conflict resolution

---

## Decision 1: Local-Only Architecture

### Context
Building an AI assistant that handles personal and work documents — potentially sensitive content that shouldn't leave the device.

### Options Considered
| Option | Pros | Cons |
|--------|------|------|
| **Cloud APIs** (OpenAI, Claude) | Best model quality, easy scaling | Privacy violation, latency, cost, internet required |
| **Hybrid** (local + cloud fallback) | Best of both worlds | Complex, still has privacy concerns |
| **Fully local** | Complete privacy, offline-capable | Limited by hardware, smaller models |

### Decision: Fully Local

**Rationale**: For a personal assistant handling work documents (Korean government/corporate files including HWP), privacy is non-negotiable. The M1 Max 64GB provides enough compute for capable local models.

**Trade-off accepted**: Smaller models (14B) vs cloud (70B+), but privacy > capability for this use case.

---

## Decision 2: Monolith with Protocol Interfaces

### Context
How to structure the application — as distributed microservices or as a single process?

### Options Considered
| Option | Pros | Cons |
|--------|------|------|
| **Microservices** | Independent scaling, language flexibility | Overhead, complexity, overkill for single machine |
| **Monolith (no interfaces)** | Simple, fast to build | Hard to refactor, tight coupling |
| **Monolith + Protocol interfaces** | Simple deployment, clean boundaries | Slightly more upfront design |

### Decision: Monolith with 13 Protocol Interfaces

**Rationale**: JARVIS runs on a single machine — microservice overhead (networking, serialization, deployment) adds complexity with no benefit. But Protocol interfaces at module boundaries give us the option to extract components later if needed.

**Key insight**: The 13 Protocols were frozen at Day 0, meaning all downstream code programs against stable interfaces. This is "monolith that's ready to split" rather than "monolith that's impossible to split."

---

## Decision 3: Hybrid FTS5 + Vector Retrieval

### Context
How to search the knowledge base — full-text only, vector-only, or hybrid?

### Options Considered
| Option | Pros | Cons |
|--------|------|------|
| **FTS5 only** | Fast, exact matching, zero latency for indexing | Misses semantic similarity |
| **Vector only** | Semantic understanding, handles synonyms | Misses exact keywords, slow indexing |
| **Hybrid + RRF** | Best of both, proven in production systems | More complex, two indexes to maintain |

### Decision: FTS5 + LanceDB Vectors + RRF Fusion (k=60)

**Rationale**: Single-method search has fundamental blind spots:
- FTS5 can't find "AI model" when the document says "인공지능 엔진"
- Vector search can't reliably match exact identifiers like "Qwen3-14B"

RRF fusion is simple (rank-based, no score normalization needed) and robust (handles missing results naturally).

**Implementation detail**: FTS5 indexing is synchronous (instant), vector embedding is asynchronous (background backfill). This means text search works immediately on file add, while vector search catches up within seconds.

---

## Decision 4: MLX Primary, Ollama Fallback

### Context
Which runtime to use for LLM inference on Apple Silicon?

### Options Considered
| Option | Pros | Cons |
|--------|------|------|
| **MLX only** | Native Metal, fastest inference | Less mature, fewer model formats |
| **Ollama only** | Stable, wide model support, easy setup | Slower (extra process overhead) |
| **MLX primary + Ollama fallback** | Best speed normally, reliability always | Two backends to maintain |

### Decision: MLX Primary + Ollama Fallback

**Rationale**: MLX provides native Metal acceleration for maximum performance on Apple Silicon. But MLX is still maturing — if a model format isn't available or MLX hits an issue, Ollama provides a reliable fallback through its REST API.

**Ollama-specific**: Uses `keep_alive=0` to immediately unload models after generation, freeing memory for the next step in the sequential loading strategy.

---

## Decision 5: Memory Budget 16GB (Worst-Case Design)

### Context
The M1 Max has 64GB unified memory, but how much can JARVIS actually use?

### Initial assumption (wrong)
"We have 64GB, so 30-35GB should be available for JARVIS."

### Reality (measured)
macOS + common apps (browser, IDE, Slack) routinely consume 40-50GB. **Only 15-20GB is reliably available**.

### Decision: Design for 16GB worst-case

**Rationale**: Optimistic memory estimates lead to OOM crashes in real-world usage. By designing for 16GB worst-case:
- Sequential model loading is mandatory (not concurrent)
- Governor monitors actual usage and downgrades tiers proactively
- Users don't have to close other apps to use JARVIS

**Key learning**: Always measure real-world memory availability, not theoretical maximum.

---

## Decision 6: Kiwi Morphological Analyzer

### Context
Korean text search requires morphological analysis — "기술이" should match "기술".

### Options Considered
| Option | Pros | Cons |
|--------|------|------|
| **MeCab-ko** | Fast, widely used | Complex installation (C library + dictionary), less accurate on modern Korean |
| **Komoran** | Java-based, good accuracy | Slower, Java dependency |
| **Kiwi (kiwipiepy)** | Best accuracy, pure Python, actively maintained | Slightly newer |

### Decision: Kiwi (kiwipiepy)

**Rationale**: Kiwi provides the best accuracy on modern Korean text, installs cleanly via pip (no C library or dictionary management), and is actively maintained. MeCab-ko was explicitly deferred per DECISIONS.md.

**Async support**: Kiwi supports asynchronous batch processing, which JARVIS uses for efficient indexing of multiple documents.

---

## Pivots and Failures

Honest engineering means acknowledging what didn't work. These pivots improved the final design:

### Kokoro-82M TTS: Eliminated

- **What happened**: Initially considered as TTS engine
- **Discovery**: Kokoro-82M has no Korean language support
- **Resolution**: Replaced with Qwen3-TTS, which was locally validated for Korean quality
- **Lesson**: Always validate language support before committing to a model

### BGE-M3 on MLX: Unavailable

- **What happened**: Planned to run BGE-M3 embeddings on MLX for maximum speed
- **Discovery**: BGE-M3 is not available in MLX format
- **Resolution**: Use sentence-transformers with MPS (Metal Performance Shaders) acceleration instead
- **Lesson**: Check framework compatibility early, have a fallback plan

### EXAONE Model Name: Corrected

- **What happened**: Initial documents referenced "Exaone-4.0-7.8B"
- **Discovery**: This model doesn't exist — the correct name is EXAONE-3.5-7.8B (or EXAONE Deep 7.8B)
- **Resolution**: Corrected across all documentation and code
- **Lesson**: Verify exact model identifiers from official sources

### Kanana-2-30B-A3B: Considered but Deferred

- **What happened**: Identified as a promising MoE model for the Phase 0 benchmark
- **Discovery**: Requires ~30 minutes of format conversion before use
- **Resolution**: Added to benchmark candidate list, but not blocking
- **Lesson**: Conversion time is a practical consideration for local deployment

### Memory Budget: Corrected Downward

- **What happened**: Initial design assumed 30-35GB available
- **Discovery**: Real-world measurement showed only 15-20GB reliably available
- **Resolution**: Redesigned for 16GB worst-case, mandatory sequential loading
- **Lesson**: Measure, don't assume

---

## Colligi2 Analysis Process

JARVIS is one of the first projects to use **collective intelligence analysis** for architecture decisions:

1. **Round 1**: Multiple AI agents independently analyzed requirements, then debated architecture trade-offs. Output: technology choices, memory budget, risk assessment.

2. **Round 2**: Agents reviewed Round 1 conflicts and resolved them through structured debate. Output: implementation spec, error handling strategy, Phase 0/1 detailed spec.

The result is an architecture that has been stress-tested by multiple perspectives before any code was written. The analysis documents are available in the repository for full transparency.

## Related Pages

- [[Tech Stack]] — The technologies that resulted from these decisions
- [[Architecture Overview]] — How these decisions shaped the system
- [[Security Model]] — Why Levels 3-4 were excluded

---

## :kr: 한국어

# 설계 의사결정

JARVIS의 핵심 엔지니어링 결정을 문서화합니다 — 무엇을 선택했고, 무엇을 거부했으며, 그 이유는 무엇인지.

### 의사결정 방법

[Colligi2](https://colligi.ai) 집단지성 분석 2라운드(AI 에이전트들의 아키텍처 토론)와 실제 하드웨어 검증을 통해 결정되었습니다.

### 6가지 핵심 결정

1. **완전 로컬 아키텍처** — 개인 문서(한국 정부/기업 파일 포함)의 프라이버시가 최우선. 성능보다 프라이버시.
2. **Protocol 인터페이스가 있는 모놀리스** — 단일 머신에서 마이크로서비스 오버헤드는 불필요. 13개 Protocol로 향후 분리 가능성 확보.
3. **하이브리드 FTS5 + 벡터 검색** — 단일 방법의 한계(FTS는 의미 검색 불가, 벡터는 정확 매칭 불가)를 극복.
4. **MLX primary + Ollama fallback** — Metal 네이티브 가속 + 안정성 폴백.
5. **메모리 예산 16GB (worst-case)** — 낙관적 추정이 아닌 실측 기반 설계. 순차 로딩 필수.
6. **Kiwi 형태소 분석기** — 최고 정확도, pip 설치, 활발한 유지보수.

### 피봇과 실패

- **Kokoro-82M TTS 제거** — 한국어 미지원 발견
- **BGE-M3 MLX 불가** — sentence-transformers + MPS로 대체
- **EXAONE 모델명 수정** — "Exaone-4.0-7.8B"는 존재하지 않음, EXAONE-3.5-7.8B로 정정
- **메모리 예산 하향 조정** — 30-35GB → 15-20GB (실측 결과)

### Colligi2 분석 과정

JARVIS는 아키텍처 결정에 **집단지성 분석**을 사용한 최초의 프로젝트 중 하나입니다. 복수의 AI 에이전트가 독립적으로 요구사항을 분석하고, 아키텍처 트레이드오프를 토론했습니다. 분석 문서는 리포지토리에서 투명하게 공개됩니다.
