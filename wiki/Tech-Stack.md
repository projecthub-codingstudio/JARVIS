# Tech Stack

Every technology in JARVIS was chosen through a structured evaluation process — two rounds of [Colligi2](https://colligi.ai) collective intelligence analysis followed by hands-on validation on the target hardware.

## Component Decisions

| Component | Technology | Why This? | Alternatives Considered |
|-----------|-----------|-----------|------------------------|
| **LLM** | qwen3.5:9b (default), exaone4.0:32b (deep tier) | Default path stays light; deep tier is available only when the Governor permits it | qwen3:14b, Kanana-2-30B-A3B (MoE) |
| **Query Planner** | Heuristic baseline + lightweight enrichment | Always-available planning, bilingual keyword expansion, no separate planner model dependency | Dedicated planner LLM, main LLM planning on every query |
| **LLM Runtime** | MLX (primary) + Ollama (fallback) | MLX: native Metal acceleration; Ollama: stability safety net | MLX-only (no fallback), Ollama-only (slower) |
| **Embeddings** | BGE-M3 via sentence-transformers | Best multilingual embedding model; MPS accelerated | Qwen3-Embedding (untested), BGE-M3 on MLX (unavailable) |
| **Vector DB** | LanceDB | Serverless, file-based, zero-config | ChromaDB (heavier), FAISS (no persistence) |
| **Full-text Search** | SQLite FTS5 | Built-in, zero-dependency, excellent performance | Elasticsearch (overkill), Whoosh (unmaintained) |
| **Korean NLP** | Kiwi (kiwipiepy) | Best accuracy, actively maintained, morpheme extraction | MeCab-ko (complex install), Komoran (slower) |
| **STT** | whisper.cpp | Native Metal acceleration, proven accuracy | CoreML Whisper (Phase 0 benchmark candidate) |
| **TTS** | Qwen3-TTS | Locally validated Korean quality | Kokoro-82M (eliminated: no Korean support) |
| **VAD** | Silero VAD | Small, accurate, offline | WebRTC VAD (less accurate) |
| **File Watching** | watchdog (FSEvents) | Native macOS FSEvents integration | polling (inefficient) |
| **System Monitoring** | psutil + pmset | Cross-platform + macOS battery/thermal | Custom IOKit (too complex) |

## Target Hardware

| Spec | Value |
|------|-------|
| Machine | MacBook Pro 16" |
| Chip | Apple M1 Max |
| Memory | 64GB Unified Memory |
| OS | macOS Tahoe 26.3 |
| Available for JARVIS | 15-20GB (worst-case design) |

## Memory Budget

JARVIS is designed for a **16GB worst-case memory budget** — not the full 64GB, because macOS, other apps, and system services consume significant memory.

### Sequential Loading Strategy

Models are loaded **one at a time, never concurrently**:

```
STT (whisper.cpp)  ──load──►  process  ──unload──►
                                                    LLM (qwen3.5:9b / exaone4.0:32b)  ──load──►  generate  ──unload──►
                                                                                                      TTS (Qwen3-TTS)  ──load──►  speak  ──unload──►
```

| Model | Memory Estimate |
|-------|----------------|
| whisper.cpp (large-v3) | ~3GB |
| qwen3.5:9b (default) | ~6-8GB |
| exaone4.0:32b (deep) | ~14-16GB |
| BGE-M3 embeddings | ~2GB |
| Qwen3-TTS | ~4GB |
| **Peak sequential** | **~10GB** (one model at a time) |

The Governor monitors actual usage and downgrades tiers if memory pressure is detected. See [[Security Model]] for the Governor threshold rules.

## Governor-Driven Model Tiers

The Governor automatically selects the right model based on system resources:

| Tier | Model | Context Window | Max Chunks | Timeout |
|------|-------|---------------|------------|---------|
| `fast` | qwen3.5:9b | 4,096 tokens | 4 | 15s |
| `balanced` | qwen3.5:9b | 8,192 tokens | 8 | 30s |
| `deep` | exaone4.0:32b | 16,384 tokens | 10 | 45s |
| `unloaded` | (search-only) | 2,048 tokens | 2 | 8s |

## Dependencies

### Core

```
kiwipiepy >= 0.18        # Korean morphological analysis
mlx >= 0.22              # Apple Silicon ML framework
mlx-lm                   # MLX language model support
sentence-transformers >= 3.0  # BGE-M3 embeddings
lancedb >= 0.8           # Vector database
watchdog >= 4.0          # File system monitoring
psutil >= 5.9            # System resource monitoring
numpy >= 1.26            # Numerical operations
```

### Document Parsers

```
pymupdf >= 1.24          # PDF parsing
python-docx >= 1.1       # Word documents
python-pptx >= 1.0       # PowerPoint
openpyxl >= 3.1          # Excel spreadsheets
python-hwpx >= 0.1       # Korean HWP (new format)
pyhwp >= 0.1b12          # Korean HWP (legacy format)
olefile >= 0.46          # OLE compound files
```

### Development

```
pytest >= 8.0            # Test framework
pytest-asyncio >= 0.23   # Async test support
ruff >= 0.6              # Linter + formatter
mypy >= 1.11             # Static type checking
```

> **Note**: Parser dependencies are optional — JARVIS gracefully degrades if a parser is missing. Tests for unavailable parsers are automatically skipped.

## Related Pages

- [[Design Decisions]] — The full story behind each technology choice
- [[Architecture Overview]] — How these technologies fit together
- [[Configuration]] — How to configure and tune the stack

---

## :kr: 한국어

# 기술 스택

JARVIS의 모든 기술은 [Colligi2](https://colligi.ai) 집단지성 분석 2회와 실제 하드웨어 검증을 거쳐 선택되었습니다.

### 핵심 기술 선택

| 구성 요소 | 기술 | 선택 이유 |
|-----------|------|----------|
| LLM | qwen3.5:9b 기본, exaone4.0:32b deep tier | 기본 경로는 가볍게 유지하고, 여유가 있을 때만 deep tier 승격 |
| 쿼리 플래너 | 휴리스틱 baseline + 경량 보강 | 별도 planner 모델 의존 없이 항상 동작, 한영 키워드 보강 |
| 런타임 | MLX + Ollama | Metal 네이티브 가속 + 안정성 폴백 |
| 임베딩 | BGE-M3 | 다국어 최고 성능, MPS 가속 |
| 벡터 DB | LanceDB | 서버리스, 파일 기반, 설정 불필요 |
| 한국어 NLP | Kiwi | 최고 정확도, 활발한 유지보수 |
| STT | whisper.cpp | Metal 가속, 검증된 정확도 |
| TTS | Qwen3-TTS | 한국어 품질 로컬 검증 완료 |

### 메모리 예산

설계 타겟은 **16GB worst-case** (64GB 중 macOS와 다른 앱이 사용하는 메모리 제외). 모델은 **순차 로딩** — 동시에 여러 모델을 올리지 않습니다.

### 거버너 자동 티어 선택

| 티어 | 모델 | 컨텍스트 | 최대 청크 | 타임아웃 |
|------|------|---------|----------|---------|
| `fast` | qwen3.5:9b | 4,096 | 4 | 15초 |
| `balanced` | qwen3.5:9b | 8,192 | 8 | 30초 |
| `deep` | exaone4.0:32b | 16,384 | 10 | 45초 |
| `unloaded` | 검색 전용 | 2,048 | 2 | 8초 |
