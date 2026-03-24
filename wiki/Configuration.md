# Configuration

JARVIS is configured through a combination of Python dataclass defaults, CLI arguments, and environment variables.

## JarvisConfig

The central configuration dataclass with all tunable parameters:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `watched_folders` | `list[Path]` | `[]` | Folders to index (typically `knowledge_base/`) |
| `data_dir` | `Path` | `~/.jarvis` | JARVIS data directory (database, exports) |
| `db_path` | `Path` | `{data_dir}/jarvis.db` | SQLite database path |
| `llm_model_id` | `str` | `"default-14b-q4"` | LLM model identifier |
| `embedding_model_id` | `str` | `"default-embedding"` | Embedding model identifier |
| `fts_top_k` | `int` | `10` | Max results from FTS5 search |
| `vector_top_k` | `int` | `10` | Max results from vector search |
| `hybrid_top_k` | `int` | `10` | Max results after RRF fusion |
| `rrf_k` | `int` | `60` | RRF fusion constant (higher = more weight to lower-ranked items) |
| `memory_limit_gb` | `float` | `16.0` | Memory budget for JARVIS (worst-case) |
| `export_dir` | `Path` | `{data_dir}/exports` | Draft export output directory |

## CLI Arguments

```bash
python -m jarvis [OPTIONS]
```

| Argument | Description | Example |
|----------|-------------|---------|
| `--model=<id>` | LLM model to use | `--model=exaone3.5:7.8b` |
| `--voice-file=<path>` | Audio file for voice input | `--voice-file=question.wav` |
| `--voice-output=<path>` | TTS output path | `--voice-output=answer.wav` |
| `--voice-ptt` | Push-to-talk once mode | `--voice-ptt` |
| `--voice-device=<name>` | Microphone input device | `--voice-device="MacBook Pro Microphone"` |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `JARVIS_LOG_FORMAT` | `text` | Set to `json` for structured JSON logging |
| `JARVIS_KNOWLEDGE_BASE` | `./knowledge_base` | Override the knowledge base directory |
| `JARVIS_STT_MODEL` | (built-in) | Custom whisper.cpp model path |
| `JARVIS_TTS_VOICE` | `Sora` | TTS voice selection |
| `JARVIS_PTT_SECONDS` | `8` | Push-to-talk recording duration (seconds) |
| `JARVIS_PTT_DEVICE` | (system default) | Microphone input device name |

## Directory Structure

```
~/.jarvis/                    # JARVIS data directory
├── jarvis.db                 # SQLite database (FTS5 + metadata)
├── exports/                  # Draft export output
└── lancedb/                  # Vector index data (LanceDB)

JARVIS/
├── knowledge_base/           # Default document location (resolved from cwd)
└── alliance_20260317_130542/ # Source code

## Knowledge Base Resolution

JARVIS resolves the knowledge base path in this order:

1. Explicit runtime argument
2. `JARVIS_KNOWLEDGE_BASE`
3. `./knowledge_base` under the current working directory
```

## Search Parameter Tuning

### RRF Constant (`rrf_k`)

The Reciprocal Rank Fusion constant controls how FTS and vector results are blended:

- **Lower k (e.g., 30)** → Heavily favors top-ranked results from each method
- **Default k = 60** → Balanced blend (recommended)
- **Higher k (e.g., 120)** → More uniform weighting across ranks

### Top-K Settings

| Parameter | Effect |
|-----------|--------|
| `fts_top_k` | How many FTS5 results to retrieve before fusion |
| `vector_top_k` | How many vector results to retrieve before fusion |
| `hybrid_top_k` | Final number of results after RRF fusion |

**Tip**: Increasing `fts_top_k` and `vector_top_k` beyond `hybrid_top_k` gives the fusion algorithm more candidates to choose from, potentially improving relevance at the cost of slightly higher latency.

## Logging

```bash
# Default: human-readable text logs
python -m jarvis

# Structured JSON logging (for observability tools)
JARVIS_LOG_FORMAT=json python -m jarvis
```

JARVIS tracks 11 metrics including query latency, time-to-first-token (TTFT), retrieval quality, and governor state changes.

## Related Pages

- [[Getting Started]] — Installation and first run
- [[Tech Stack]] — Available models and their requirements
- [[Retrieval Pipeline]] — How search parameters affect results

---

## :kr: 한국어

# 설정

JARVIS는 Python 데이터클래스 기본값, CLI 인수, 환경변수의 조합으로 설정됩니다.

### 주요 설정값

| 필드 | 기본값 | 설명 |
|------|--------|------|
| `watched_folders` | `[]` | 인덱싱할 폴더 (`knowledge_base/`) |
| `data_dir` | `~/.jarvis` | 데이터 디렉토리 |
| `fts_top_k` | `10` | FTS5 검색 최대 결과 수 |
| `vector_top_k` | `10` | 벡터 검색 최대 결과 수 |
| `rrf_k` | `60` | RRF 융합 상수 |
| `memory_limit_gb` | `16.0` | 메모리 예산 (GB) |

### 환경변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `JARVIS_LOG_FORMAT` | `text` | `json`으로 설정하면 구조화 로깅 |
| `JARVIS_KNOWLEDGE_BASE` | `./knowledge_base` | 지식 베이스 디렉토리 override |
| `JARVIS_STT_MODEL` | 내장 | whisper.cpp 모델 경로 |
| `JARVIS_TTS_VOICE` | `Sora` | TTS 음성 선택 |
| `JARVIS_PTT_SECONDS` | `8` | 녹음 시간(초) |
| `JARVIS_PTT_DEVICE` | 시스템 기본 | 마이크 장치 이름 |

### 검색 파라미터 튜닝

- **rrf_k 낮추기 (30)** → 각 방법의 상위 결과를 강하게 선호
- **rrf_k 기본값 (60)** → 균형 잡힌 혼합 (권장)
- **rrf_k 올리기 (120)** → 순위 간 균등한 가중치
