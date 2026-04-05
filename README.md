# JARVIS

**Just A Rather Very Intelligent System**

A privacy-first, local AI assistant for Apple Silicon — inspired by Iron Man's JARVIS.

[![Built with Claude](https://img.shields.io/badge/Built_with-Claude-D97706?logo=anthropic&logoColor=white)](https://claude.com/claude-code)
[![Analyzed with Codex](https://img.shields.io/badge/Analyzed_with-OpenAI_Codex-412991?logo=openai&logoColor=white)](https://openai.com/codex)
[![Evaluated with Gemini](https://img.shields.io/badge/Evaluated_with-Gemini-4285F4?logo=google&logoColor=white)](https://deepmind.google/technologies/gemini/)
[![Orchestrated with Colligi²](https://img.shields.io/badge/Orchestrated_with-Colligi²-7C3AED)](https://colligi.ai)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Apple Silicon](https://img.shields.io/badge/Apple_Silicon-M1/M2/M3-000000?logo=apple&logoColor=white)](https://www.apple.com/mac/)

## Overview

JARVIS is a fully local AI assistant that runs on MacBook Pro M1 Max (64GB). It provides document-grounded Q&A with citations, hybrid query planning, multi-modal vision, session-based learning, and a rich web interface — all without cloud dependencies.

### Core Features

- **Personal RAG** — Document-grounded Q&A over PDF, DOCX, XLSX, HWP, PPTX, Markdown, and code files with evidence-backed citations
- **Web Interface** — React/TypeScript SPA with Terminal (chat), Repository (file browser + viewer), Skills, and Admin workspaces
- **Repository Viewer** — 12 specialized renderers (PDF, DOCX, PPTX, XLSX, HWP, code, markdown, text, HTML, image, video) with syntax highlighting, GFM markdown, encoding detection, WRAP/NOWRAP toggle
- **Vision Q&A** — Upload images to the Terminal for Gemma 4 E4B multimodal analysis (128K context)
- **Session Query Learning** — 3-layer system that captures failure→success query reformulations, learns entity hints, injects them into future similar queries — independent of the generation LLM
- **Hybrid Retrieval** — SQLite FTS5 (morpheme-expanded Korean) + LanceDB vector search + RRF fusion + cross-encoder reranking
- **Citation-backed Answers** — Factual answers require retrieved source evidence with relevance scores
- **Answerability Gate** — Pre-generation decision layer protects against hallucination on weak/ambiguous evidence
- **Real-time Indexing** — File watcher auto-indexes new/modified documents in the knowledge base
- **Resource Governor** — System monitoring (memory, swap, thermal, battery) with automatic model tier selection
- **Voice Interaction** — Local STT/TTS with file mode, push-to-talk, and menu bar live loop

### Tech Stack

| Layer | Technology |
|-------|-----------|
| **Generation LLM (Fast/Balanced)** | EXAONE-3.5-7.8B-Instruct-4bit (MLX) — 1.5s, primary |
| **Generation LLM (Deep)** | EXAONE-4.0-32B-4bit (128K context) |
| **Vision LLM** | Gemma 4 E4B (multimodal, 128K context, via mlx-vlm) |
| **Alternative LLMs** | Qwen3.5:9B, EXAONE-Deep (reasoning), Gemma 4 E2B (routing) |
| **Embeddings** | BGE-M3 (multilingual, CPU) |
| **Vector DB** | LanceDB (serverless, file-based) |
| **Reranker** | cross-encoder/mmarco-mMiniLMv2-L12-H384-v1 |
| **FTS** | SQLite FTS5 + Kiwi morphological analyzer |
| **Parsers** | PyMuPDF, python-docx, openpyxl, python-pptx, python-hwpx, pyhwp |
| **STT / TTS** | whisper.cpp / Qwen3-TTS |
| **Backend** | Python 3.12 + FastAPI + uvicorn |
| **Frontend** | React 19 + TypeScript + Vite + Zustand + Tailwind CSS v4 |

### Target Environment

- MacBook Pro 16" / Apple M1 Max / 64GB Unified Memory
- macOS 15+ (Sequoia/Tahoe)
- Privacy-first, fully offline-capable

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Web Interface (React SPA, localhost:3000)                  │
│  Terminal · Repository · Skills · Admin · Viewers           │
└────────────────────────────┬────────────────────────────────┘
                             │ HTTP + WebSocket
┌────────────────────────────▼────────────────────────────────┐
│  FastAPI Backend (localhost:8000, alliance/src/jarvis/)     │
│  /api/ask · /api/ask/vision · /api/browse · /api/file       │
│  /api/learned-patterns · /api/skills · /ws/{session_id}     │
├─────────────────────────────────────────────────────────────┤
│  Orchestrator                                                │
│    → Planner (HintInjector)  ← Session Query Learning       │
│    → Retrieval (FTS + Vector + RRF + Reranker)              │
│    → Answerability Gate                                      │
│    → LLM Generation (MLX / GemmaVlm / LlamaCpp)             │
│    → Post-generation Guard                                   │
├─────────────────────────────────────────────────────────────┤
│  Learning Layer (decoupled from LLM)                         │
│    SessionEventCapture → ReformulationDetector →            │
│    PatternExtractor → PatternStore → PatternMatcher →       │
│    HintInjector                                              │
├─────────────────────────────────────────────────────────────┤
│  Indexing Pipeline                                           │
│    Parsers → Chunking → BGE-M3 Embedding → FTS5 + LanceDB   │
└─────────────────────────────────────────────────────────────┘
                             │
                  ~/.jarvis-menubar/jarvis.db
                  ~/.jarvis-menubar/vectors.lance
                  knowledge_base/
```

## Project Structure

```
JARVIS/
├── alliance_20260317_130542/        # Python backend (see below)
├── ProjectHub-terminal-architect/   # React frontend (see below)
├── colligi2_20260316_021200/        # Colligi2 analysis round 1
├── colligi2_20260316_133406/        # Colligi2 analysis round 2
├── knowledge_base/                  # User documents (local only, git-ignored)
└── .gitignore
```

### Backend: `alliance_20260317_130542/`

```
alliance_20260317_130542/
├── pyproject.toml
├── macos/JarvisMenuBar/             # SwiftUI menu bar app
├── sql/schema.sql                   # SQLite schema
├── src/jarvis/
│   ├── __main__.py                  # CLI entry point
│   ├── web_api.py                   # FastAPI + WebSocket bridge
│   ├── app/                         # Bootstrap, configuration
│   │   └── runtime_context.py       # Runtime factory
│   ├── service/
│   │   ├── application.py           # JarvisApplicationService (RPC facade)
│   │   ├── protocol.py              # RpcRequest/RpcResponse
│   │   ├── intent_skill_registry.py # Skill profile registry
│   │   └── intent_skill_store.py    # Skill storage
│   ├── core/
│   │   ├── orchestrator.py          # End-to-end turn pipeline
│   │   ├── planner.py               # Query analysis + HintInjector hook
│   │   ├── answerability_gate.py    # Pre-generation decision layer
│   │   └── governor.py              # Resource monitoring
│   ├── runtime/
│   │   ├── mlx_backend.py           # MLX (EXAONE/Qwen) backend
│   │   ├── gemma_vlm_backend.py     # Gemma 4 multimodal (NEW)
│   │   ├── llamacpp_backend.py      # GGUF fallback
│   │   └── mlx_runtime.py           # LLMGeneratorProtocol wrapper
│   ├── retrieval/
│   │   ├── strategy.py              # Per-task hybrid strategies
│   │   ├── evidence_builder.py      # Verified evidence with boosts
│   │   ├── fts_index.py             # SQLite FTS5
│   │   ├── vector_index.py          # LanceDB
│   │   └── reranker.py              # Cross-encoder
│   ├── indexing/
│   │   ├── index_pipeline.py        # Parse → chunk → embed → store
│   │   └── parsers.py               # Format-specific parsers
│   ├── learning/                    # Session Query Learning (NEW)
│   │   ├── coordinator.py           # Facade
│   │   ├── session_event.py         # SessionEvent + ReformulationPair
│   │   ├── learned_pattern.py       # LearnedPattern + 4 types
│   │   ├── pattern_store.py         # SQLite CRUD
│   │   ├── event_capture.py         # Orchestrator hook
│   │   ├── reformulation_detector.py # Pair detection
│   │   ├── pattern_extractor.py     # 4-class classification
│   │   ├── pattern_matcher.py       # Vector similarity
│   │   ├── hint_injector.py         # Planner integration
│   │   ├── embedding_adapter.py     # BGE-M3 bridge
│   │   └── batch_scheduler.py       # 10-min analysis loop
│   └── memory/
│       └── conversation_store.py    # Turn history
└── tests/                           # 420+ tests
```

### Frontend: `ProjectHub-terminal-architect/`

```
ProjectHub-terminal-architect/
├── package.json
├── scripts/
│   ├── start.sh                     # Start backend + frontend
│   └── stop.sh
├── src/
│   ├── App.tsx                      # Main shell (5 tabs)
│   ├── types.ts                     # All TypeScript types
│   ├── store/
│   │   └── app-store.ts             # Zustand state
│   ├── hooks/
│   │   └── useJarvis.ts             # sendMessage, sendMessageWithImage
│   ├── lib/
│   │   └── api-client.ts            # API methods
│   ├── components/
│   │   ├── workspaces/
│   │   │   ├── TerminalWorkspace.tsx    # Chat + image attach
│   │   │   ├── SkillsWorkspace.tsx      # Skill registry + action maps
│   │   │   └── AdminWorkspace.tsx       # Admin panel
│   │   ├── repository/
│   │   │   ├── RepositoryWorkspace.tsx  # File tree + viewer layout
│   │   │   └── FileTreePanel.tsx        # Lazy-loaded directory tree
│   │   ├── viewer/
│   │   │   ├── ViewerShell.tsx          # Multi-pane viewer layout
│   │   │   ├── ViewerRouter.tsx         # Extension → renderer routing
│   │   │   └── renderers/
│   │   │       ├── TextRenderer.tsx     # .txt, .log, .csv (WRAP toggle)
│   │   │       ├── CodeRenderer.tsx     # Syntax highlighting (WRAP toggle)
│   │   │       ├── MarkdownRenderer.tsx # React-markdown + GFM
│   │   │       ├── HtmlRenderer.tsx     # Rendered/Source toggle
│   │   │       ├── ImageRenderer.tsx    # Zoom controls
│   │   │       ├── VideoRenderer.tsx
│   │   │       ├── WebRenderer.tsx
│   │   │       ├── PdfRenderer.tsx      # react-pdf
│   │   │       ├── DocxRenderer.tsx
│   │   │       ├── PptxRenderer.tsx
│   │   │       ├── XlsxRenderer.tsx
│   │   │       └── HwpRenderer.tsx      # Indexed chunks
│   │   └── admin/
│   │       └── LearnedPatternsPanel.tsx # Learning system UI
│   └── index.css                    # Tailwind + typography
└── docs/superpowers/
    ├── specs/                       # Design documents
    └── plans/                       # Implementation plans
```

### Knowledge Base (`knowledge_base/`)

By default, JARVIS looks for `./knowledge_base/` under the current working directory. Override with `JARVIS_KNOWLEDGE_BASE=/path/to/kb`.

Supported formats: `.pdf`, `.docx`, `.pptx`, `.xlsx`, `.hwpx`, `.hwp`, `.md`, `.txt`, `.py`, `.ts`, `.tsx`, `.js`, `.swift`, `.json`, `.yaml`, `.sql`, `.sh`, `.html`, `.css`, and more.

## Quick Start

### Full Stack (Web Interface)

```bash
cd ProjectHub-terminal-architect
./scripts/start.sh
# Opens backend at :8000 and frontend at :3000
```

Visit http://localhost:3000 — the Terminal tab is ready for chat.

### Backend Only (CLI)

```bash
cd alliance_20260317_130542

# Setup
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pip install mlx-vlm  # For Gemma 4 vision support

# Run
python -m jarvis                              # Default model chain
python -m jarvis --model=gemma4:e4b           # Gemma 4 with vision
python -m jarvis --model=exaone3.5:7.8b       # EXAONE fast tier
python -m jarvis --model=exaone4.0:32b        # EXAONE deep tier

# Tests
python -m pytest tests/ -v                    # 420+ tests
```

### Model Chain Configuration

```bash
# Primary: EXAONE with stub fallback (default in start.sh)
JARVIS_MENU_BAR_MODEL_CHAIN="exaone3.5:7.8b,stub" ./scripts/start.sh

# Use Gemma 4 for text + vision
JARVIS_MENU_BAR_MODEL_CHAIN="gemma4:e4b,stub" ./scripts/start.sh

# Hybrid: Gemma first, EXAONE fallback
JARVIS_MENU_BAR_MODEL_CHAIN="gemma4:e4b,exaone3.5:7.8b,stub" ./scripts/start.sh
```

## API Reference

### HTTP Endpoints (FastAPI, `localhost:8000`)

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/ask` | Query with RAG, returns answer + citations + guide |
| POST | `/api/ask/vision` | Multimodal Q&A (multipart: text + image) → Gemma 4 |
| POST | `/api/normalize` | Normalize Korean query text |
| GET | `/api/health` | Service health + runtime state |
| GET | `/api/runtime-state` | Current LLM runtime info |
| GET | `/api/browse?path=` | List directory contents (FileNode[]) |
| GET | `/api/file?path=` | Fetch file content (auto encoding detection) |
| GET | `/api/file/extracted?path=&limit=` | Extract indexed text chunks from binary files |
| GET | `/api/skills` | List skill profiles |
| POST / PUT | `/api/skills[/{id}]` | Create / update skill profile |
| GET | `/api/action-maps` | List action maps |
| POST / PUT | `/api/action-maps[/{id}]` | Create / update action maps |
| GET | `/api/learned-patterns` | List learned patterns |
| POST | `/api/learned-patterns/forget` | Delete pattern(s) |

### Custom Response Headers (on `/api/file`)

- `X-Detected-Encoding` — utf-8, utf-8-sig, cp949, euc-kr, utf-16, latin-1
- `X-File-Size` — bytes
- `Access-Control-Expose-Headers` — makes above readable from browser

### WebSocket

- `/ws/{session_id}` — Bidirectional streaming for long-running queries

## Web Interface Tabs

1. **Home** — Dashboard with quick-access Terminal + recent activity
2. **Terminal** — Chat interface with AI; image attachment (Gemma 4 vision); citation clicks navigate to Repository
3. **Repository** — File tree browser (`knowledge_base/`) + multi-renderer viewer with 12 format-specific renderers
4. **Skills** — Skill registry management + workflow action maps
5. **Admin** — System health, active workers, event logs, Learned Patterns panel (view/delete)

## Session Query Learning System

Research-backed system that learns from in-session query refinements. References: Intent-Aware Neural Query Reformulation (arXiv 2507.22213, 2025), RQ-RAG (arXiv 2404.00610), Springer Discover Computing 2010.

**Core Insight**: When a user refines a failed query within 5 minutes and the new query succeeds with strong evidence, store that pair as a learnable pattern. Inject entity hints into future similar queries.

### 4-Class Reformulation Taxonomy

| Type | Detection | Learned? |
|------|-----------|----------|
| **Specialization** | success has more entities than failure | ✓ |
| **Error Correction** | similarity ≥0.85, entities identical | ✓ |
| **Parallel Move** | same task, different entity values | ✓ |
| **Generalization** | success has fewer entities | ✗ (info loss) |

### Thresholds (Research-Grounded)

- Temporal window: **5 minutes**
- Pair similarity: **cosine ≥ 0.5**
- Match injection: **cosine ≥ 0.75**
- Pattern decay: 30 days unused

### Model-Independence

The learning layer uses BGE-M3 embeddings (not the generation LLM), so EXAONE → Gemma 4 → future model swaps don't invalidate learned patterns.

## Implementation Status

### Backend
- [x] Colligi2 collective intelligence analysis
- [x] Alliance-based code generation
- [x] LLM backend integration (MLX primary, llamacpp fallback)
- [x] **Gemma 4 vision backend** (GemmaVlmBackend via mlx-vlm)
- [x] Document parsers (PDF, DOCX, XLSX, PPTX, HWP, HWPX, code files)
- [x] FTS5 search + Kiwi morphological analysis
- [x] LanceDB vector search + BGE-M3 embeddings (22,692+ chunks indexed)
- [x] Cross-encoder reranker (multilingual)
- [x] Hybrid planner + per-task retrieval strategies
- [x] Answerability gate (pre-generation safety)
- [x] Governor (8 threshold rules: memory, swap, thermal, battery)
- [x] Token-based semantic chunking (table-row / code-function / paragraph)
- [x] Claim-level citation verification
- [x] **Session Query Learning System** (3-layer, 4-class classification)
- [x] FastAPI web API + WebSocket
- [x] 420+ tests passing

### Frontend
- [x] React 19 + TypeScript + Vite SPA
- [x] 5-tab workspace layout (Home, Terminal, Repository, Skills, Admin)
- [x] **Repository file tree browser** with lazy loading
- [x] **12 specialized viewers** (PDF, DOCX, PPTX, XLSX, HWP, code, markdown, text, HTML, image, video, web)
- [x] **Image attach in Terminal** for Gemma 4 vision Q&A
- [x] Syntax highlighting (react-syntax-highlighter)
- [x] GitHub Flavored Markdown (remark-gfm)
- [x] WRAP/NOWRAP toggle + encoding detection headers
- [x] Terminal citation → Repository navigation
- [x] **Learned Patterns admin UI** (view, delete)
- [x] Streaming response support

### Voice & Menu Bar
- [x] Voice interface (STT/TTS file mode, PTT, menu bar live loop)
- [x] macOS menu bar app (SwiftUI + Python bridge + approval panel + health status)
- [x] Wake word "Hey JARVIS" prototype

## Documentation

- [`docs/JARVIS_Authoritative_Decision.md`](alliance_20260317_130542/docs/JARVIS_Authoritative_Decision.md) — Single source of truth
- [`docs/superpowers/specs/`](ProjectHub-terminal-architect/docs/superpowers/specs/) — Design specifications
- [`docs/superpowers/plans/`](ProjectHub-terminal-architect/docs/superpowers/plans/) — Implementation plans

## Built With

- **[ProjectHub](https://projecthub.co.kr)** — AI-powered project management and build orchestration platform
- **[Colligi](https://colligi.ai)** — Collective intelligence analysis for architecture and technical decisions

## License

### JARVIS Source Code

JARVIS itself is released under the [MIT License](LICENSE).

### Third-Party Model Licenses

JARVIS integrates multiple open-weight LLMs. **Their licenses differ and may restrict how you use JARVIS in commercial products.**

| Model | License | Commercial Use |
|-------|---------|---------------|
| **Gemma 4 E2B / E4B** (Google) | Apache 2.0 | ✅ Free commercial use, redistribution allowed |
| **EXAONE 3.5 / 4.0 / Deep** (LG AI Research) | [EXAONE AI Model License](https://huggingface.co/LGAI-EXAONE/EXAONE-3.5-7.8B-Instruct/blob/main/LICENSE) | ⚠️ **Research only** — commercial use requires explicit permission from LG AI (contact_us@lgresearch.ai) |
| **Qwen3 / Qwen3.5** (Alibaba) | Apache 2.0 / Qwen License | ✅ Commercial use permitted (model-specific terms apply) |
| **BGE-M3** (BAAI) | MIT License | ✅ Free for any use |
| **whisper.cpp / Whisper models** (OpenAI) | MIT License | ✅ Free for any use |
| **Qwen3-TTS** (Alibaba) | Apache 2.0 / Qwen License | ✅ Commercial use permitted |

**What this means for you:**

- **Personal / research use**: All supported models are usable without restrictions.
- **Commercial product / SaaS**: Switch the default model chain to Apache-licensed alternatives:
  ```bash
  JARVIS_MENU_BAR_MODEL_CHAIN="gemma4:e4b,stub" ./scripts/start.sh
  ```
- **Model selection is user-controlled** via `JARVIS_MENU_BAR_MODEL_CHAIN` — each user chooses which models they can legally use in their context.

Gemma 4's April 2026 release moved from custom Gemma Terms of Use to **Apache 2.0**, removing previous commercial restrictions and "Prohibited Use" clauses. This makes Gemma 4 particularly well-suited for commercial deployments.

## Release Notes

- [2026-03-19 release notes](RELEASE_NOTES_2026-03-19.md)

---

### 🇰🇷 한국어

---

# JARVIS

**Just A Rather Very Intelligent System**

아이언맨의 자비스(JARVIS)에서 영감을 받은, Apple Silicon 전용 개인정보 보호 우선 로컬 AI 비서.

[![Built with Claude](https://img.shields.io/badge/Built_with-Claude-D97706?logo=anthropic&logoColor=white)](https://claude.com/claude-code)
[![Analyzed with Codex](https://img.shields.io/badge/Analyzed_with-OpenAI_Codex-412991?logo=openai&logoColor=white)](https://openai.com/codex)
[![Evaluated with Gemini](https://img.shields.io/badge/Evaluated_with-Gemini-4285F4?logo=google&logoColor=white)](https://deepmind.google/technologies/gemini/)
[![Orchestrated with Colligi²](https://img.shields.io/badge/Orchestrated_with-Colligi²-7C3AED)](https://colligi.ai)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Apple Silicon](https://img.shields.io/badge/Apple_Silicon-M1/M2/M3-000000?logo=apple&logoColor=white)](https://www.apple.com/mac/)

## 개요

JARVIS는 MacBook Pro M1 Max (64GB)에서 완전히 로컬로 동작하는 AI 비서입니다. 클라우드 의존 없이 **출처 기반 문서 Q&A**, **하이브리드 쿼리 플래닝**, **멀티모달 비전**, **세션 기반 학습**, **리치 웹 인터페이스**를 제공합니다.

### 핵심 기능

- **개인 RAG** — PDF, DOCX, XLSX, HWP, PPTX, 마크다운, 코드 파일 기반 출처 증거 포함 문서 Q&A
- **웹 인터페이스** — React/TypeScript SPA: Terminal(채팅), Repository(파일 브라우저+뷰어), Skills, Admin 워크스페이스
- **Repository 뷰어** — 12종 전용 렌더러 (PDF, DOCX, PPTX, XLSX, HWP, code, markdown, text, HTML, image, video) + syntax highlighting, GFM markdown, 인코딩 감지, WRAP/NOWRAP 토글
- **Vision Q&A** — Terminal에서 이미지 업로드 → Gemma 4 E4B 멀티모달 분석 (128K 컨텍스트)
- **Session Query Learning** — 실패→성공 쿼리 리포뮬레이션 캡처, entity hints 학습, 이후 유사 쿼리에 자동 주입 (생성 LLM과 독립)
- **하이브리드 검색** — SQLite FTS5 (한국어 형태소 확장) + LanceDB 벡터 검색 + RRF fusion + cross-encoder reranking
- **출처 기반 답변** — 사실 답변은 검색된 증거가 있을 때만 생성, relevance score 표시
- **Answerability Gate** — 증거가 약하거나 모호할 때 할루시네이션 방지
- **실시간 인덱싱** — 지식 베이스 파일 변경을 자동 인덱싱
- **리소스 Governor** — 메모리/스왑/발열/배터리 모니터링으로 자동 모델 티어 선택
- **음성 인터랙션** — 파일 모드, Push-to-talk, 메뉴바 live loop 포함 로컬 STT/TTS

### 기술 스택

| 계층 | 기술 |
|------|------|
| **생성 LLM (Fast/Balanced)** | EXAONE-3.5-7.8B-Instruct-4bit (MLX) — 1.5초, 기본값 |
| **생성 LLM (Deep)** | EXAONE-4.0-32B-4bit (128K 컨텍스트) |
| **Vision LLM** | Gemma 4 E4B (멀티모달, 128K 컨텍스트, mlx-vlm) |
| **대체 LLM** | Qwen3.5:9B, EXAONE-Deep (추론), Gemma 4 E2B (라우팅) |
| **임베딩** | BGE-M3 (다국어, CPU) |
| **Vector DB** | LanceDB (serverless, 파일 기반) |
| **Reranker** | cross-encoder/mmarco-mMiniLMv2-L12-H384-v1 |
| **FTS** | SQLite FTS5 + Kiwi 형태소 분석기 |
| **파서** | PyMuPDF, python-docx, openpyxl, python-pptx, python-hwpx, pyhwp |
| **STT / TTS** | whisper.cpp / Qwen3-TTS |
| **Backend** | Python 3.12 + FastAPI + uvicorn |
| **Frontend** | React 19 + TypeScript + Vite + Zustand + Tailwind CSS v4 |

### 대상 환경

- MacBook Pro 16" / Apple M1 Max / 통합 메모리 64GB
- macOS 15+ (Sequoia/Tahoe)
- Privacy-first, 완전 오프라인 동작 가능

## 빠른 시작

### 풀스택 (웹 인터페이스)

```bash
cd ProjectHub-terminal-architect
./scripts/start.sh
# 백엔드 :8000, 프론트엔드 :3000 동시 실행
```

http://localhost:3000 접속 → Terminal 탭에서 채팅 시작.

### 백엔드만 (CLI)

```bash
cd alliance_20260317_130542

python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pip install mlx-vlm                           # Gemma 4 vision 지원

python -m jarvis                              # 기본 모델 체인
python -m jarvis --model=gemma4:e4b           # Gemma 4 (비전 포함)
python -m jarvis --model=exaone3.5:7.8b       # EXAONE fast tier
python -m jarvis --model=exaone4.0:32b        # EXAONE deep tier

python -m pytest tests/ -v                    # 420+ 테스트
```

### 모델 체인 구성

```bash
# 기본: EXAONE + stub fallback (start.sh 기본값)
JARVIS_MENU_BAR_MODEL_CHAIN="exaone3.5:7.8b,stub" ./scripts/start.sh

# Gemma 4로 텍스트 + 비전
JARVIS_MENU_BAR_MODEL_CHAIN="gemma4:e4b,stub" ./scripts/start.sh

# 하이브리드: Gemma 우선, EXAONE fallback
JARVIS_MENU_BAR_MODEL_CHAIN="gemma4:e4b,exaone3.5:7.8b,stub" ./scripts/start.sh
```

## Session Query Learning System

사용자의 세션 내 쿼리 리포뮬레이션을 학습하는 시스템. 연구 근거: Intent-Aware Neural Query Reformulation (arXiv 2507.22213, 2025), RQ-RAG (arXiv 2404.00610), Springer 2010.

**핵심 아이디어**: 사용자가 실패한 쿼리를 5분 이내에 재표현하여 강한 증거와 함께 성공시키면, 그 쌍을 학습 가능한 패턴으로 저장하고 이후 유사 쿼리에 entity hints를 주입합니다.

### 4-클래스 리포뮬레이션 분류

| 타입 | 감지 조건 | 학습? |
|------|----------|-------|
| **Specialization** | 성공 쿼리의 entity가 실패보다 많음 | ✓ |
| **Error Correction** | 유사도 ≥0.85, entity 동일 | ✓ |
| **Parallel Move** | 같은 task, 다른 entity 값 | ✓ |
| **Generalization** | 성공 쿼리의 entity가 실패보다 적음 | ✗ (정보 손실) |

### 모델 독립성

학습 계층은 BGE-M3 임베딩만 사용 (생성 LLM과 분리)하므로, EXAONE → Gemma 4 → 미래 모델 교체 시에도 학습된 패턴이 유효합니다.

## 구현 현황

### 백엔드
- [x] MLX/GemmaVlm/llamacpp LLM 백엔드
- [x] **Gemma 4 vision backend** (mlx-vlm)
- [x] 문서 파서 (PDF, DOCX, XLSX, PPTX, HWP, HWPX, 코드)
- [x] FTS5 + Kiwi 형태소, LanceDB + BGE-M3, Cross-encoder reranker
- [x] 하이브리드 플래너 + 태스크별 검색 전략
- [x] Answerability gate + Governor
- [x] Claim-level citation verification
- [x] **Session Query Learning System**
- [x] FastAPI + WebSocket
- [x] 420+ 테스트

### 프론트엔드
- [x] React 19 + TypeScript + Vite SPA
- [x] 5탭 워크스페이스 (Home, Terminal, Repository, Skills, Admin)
- [x] **Repository 파일 트리** + lazy loading
- [x] **12종 전용 뷰어**
- [x] **이미지 첨부 Terminal** (Gemma 4 vision)
- [x] WRAP/NOWRAP 토글 + 인코딩 헤더
- [x] **학습 패턴 Admin UI**

## 사용 도구

- **[ProjectHub](https://projecthub.co.kr)** — AI 기반 프로젝트 관리 및 빌드 오케스트레이션 플랫폼
- **[Colligi](https://colligi.ai)** — 아키텍처 설계와 기술 의사결정 집단지성 분석 시스템

## 라이선스

### JARVIS 소스 코드

JARVIS 자체는 [MIT License](LICENSE) 하에 배포됩니다.

### 3rd-party 모델 라이선스

JARVIS는 여러 오픈 가중치 LLM을 사용합니다. **각 모델의 라이선스가 다르며 상업적 사용에 제한이 있을 수 있습니다.**

| 모델 | 라이선스 | 상업적 사용 |
|------|---------|-------------|
| **Gemma 4 E2B / E4B** (Google) | Apache 2.0 | ✅ 상업 사용 자유, 재배포 가능 |
| **EXAONE 3.5 / 4.0 / Deep** (LG AI Research) | [EXAONE AI Model License](https://huggingface.co/LGAI-EXAONE/EXAONE-3.5-7.8B-Instruct/blob/main/LICENSE) | ⚠️ **연구 전용** — 상업 사용 시 LG AI 허가 필요 (contact_us@lgresearch.ai) |
| **Qwen3 / Qwen3.5** (Alibaba) | Apache 2.0 / Qwen License | ✅ 상업 사용 가능 (모델별 조건 확인) |
| **BGE-M3** (BAAI) | MIT License | ✅ 자유 사용 |
| **whisper.cpp / Whisper** (OpenAI) | MIT License | ✅ 자유 사용 |
| **Qwen3-TTS** (Alibaba) | Apache 2.0 / Qwen License | ✅ 상업 사용 가능 |

**실무 가이드:**

- **개인/연구 용도**: 지원하는 모든 모델 제약 없이 사용 가능
- **상업 제품/SaaS**: 기본 모델 체인을 Apache 라이선스 모델로 전환
  ```bash
  JARVIS_MENU_BAR_MODEL_CHAIN="gemma4:e4b,stub" ./scripts/start.sh
  ```
- **모델 선택권은 사용자에게** — `JARVIS_MENU_BAR_MODEL_CHAIN` 환경변수로 각자 법적으로 사용 가능한 모델 선택

Gemma 4는 2026-04-02 릴리스에서 커스텀 Gemma Terms of Use에서 **Apache 2.0**로 전환되어, 이전의 상업 제한과 "Prohibited Use" 조항이 제거되었습니다. 이로 인해 Gemma 4는 상업 배포에 특히 적합합니다.
