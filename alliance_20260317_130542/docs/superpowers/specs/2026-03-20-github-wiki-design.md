# GitHub Wiki Design Spec — JARVIS Project

**Date**: 2026-03-20
**Purpose**: Create a comprehensive GitHub Wiki for the JARVIS project, targeting external developers and serving as a portfolio/showcase.
**Language**: English primary + Korean (한국어) section per page
**Structure**: Journey-based (Understand → Install → Use → Deep Dive → Contribute)

---

## Page Structure (12 Pages)

### Navigation Flow

```
Home → Getting Started → Architecture Overview → Tech Stack → Configuration
  → Retrieval Pipeline → Voice Pipeline → Menu Bar App → Security Model
  → Design Decisions → Contributing → FAQ & Troubleshooting
```

### Sidebar (`_Sidebar.md`)

Persistent navigation with grouped sections:
- **Intro**: Home, Getting Started
- **Deep Dive**: Architecture, Tech Stack, Configuration
- **Pipelines**: Retrieval, Voice, Menu Bar App, Security
- **Meta**: Design Decisions, Contributing, FAQ

### Footer (`_Footer.md`)

- "← Previous | Next →" page navigation
- MIT License link
- "Built with ProjectHub + Colligi" attribution

---

## Page Specifications

### 1. Home

**File**: `Home.md`
**Purpose**: First impression — project identity, core value proposition, quick orientation

**Content**:
- Hero: Project name, tagline ("Privacy-first local AI assistant for Apple Silicon")
- Core values: Privacy-first, Local-only, Korean-first
- Feature highlights (6 items): Personal RAG, Citation-backed Answers, AI Query Planner, Real-time Indexing, Resource Governor, Voice Interaction
- Tech stack summary table (7 rows)
- Current status: Beta 1, 335 tests, Python 93.5% / Swift 6.5%
- Quick links to all wiki pages
- 🇰🇷 한국어 section (same structure)

### 2. Getting Started

**File**: `Getting-Started.md`
**Purpose**: Zero-to-running in minimal steps

**Content**:
- Prerequisites: macOS (Apple Silicon), Python 3.12, Ollama, Xcode CLI Tools
- Step-by-step installation (clone → venv → pip install → knowledge_base setup)
- First run: `python -m jarvis`, model selection (`--model`)
- Voice modes: `--voice file`, `--voice ptt`, `--voice live`
- Menu bar app build instructions (Xcode)
- "Hello World" scenario: add a PDF to knowledge_base/, ask a question, see citations
- 🇰🇷 한국어 section

### 3. Architecture Overview

**File**: `Architecture-Overview.md`
**Purpose**: System-level understanding of how JARVIS works

**Content**:
- High-level Mermaid diagram: 7-step orchestrator pipeline
  - User Input → Governor Check → AI Planner → Hybrid Search → Evidence Builder → LLM Generation → Response with Citations
- Module layer diagram: contracts → core → retrieval/indexing/runtime → cli/menu bar
- Protocol-first design: 12 Protocol interfaces (frozen Day 0)
- Data flow: Document → Parse → Chunk → FTS5 + LanceDB → Search → Response
- Database schema summary (5 tables + FTS5 virtual table)
- Directory structure with purpose annotations
- 🇰🇷 한국어 section

### 4. Tech Stack

**File**: `Tech-Stack.md`
**Purpose**: Showcase technology choices with rationale (portfolio value)

**Content**:
- Component table with "Technology" and "Why?" columns:
  | Component | Technology | Why? |
  |-----------|-----------|------|
  | LLM | Qwen3-14B | Best KO/EN balance at 14B class |
  | Query Planner | EXAONE-3.5-7.8B | Fast intent, good Korean |
  | Retrieval | FTS5 + LanceDB + RRF | Hybrid beats single-method |
  | Embeddings | BGE-M3 (sentence-transformers) | Best multilingual, MLX unavailable |
  | STT | whisper.cpp | Native Metal acceleration |
  | TTS | Qwen3-TTS | Locally validated Korean quality |
  | Korean NLP | Kiwi | Best accuracy, active maintenance |
- Target hardware: M1 Max 64GB
- Memory budget: 15-20GB available, 16GB worst-case peak
- Sequential loading strategy: STT → LLM → TTS (never concurrent)
- Dependencies list (core / parsing / system / dev)
- 🇰🇷 한국어 section

### 5. Configuration

**File**: `Configuration.md`
**Purpose**: Reference for all configurable options

**Content**:
- `JarvisConfig` fields table (type, default, description)
- Environment variables reference:
  - `JARVIS_LOG_FORMAT` — json logging
  - `JARVIS_STT_MODEL` — whisper model path
  - `JARVIS_TTS_VOICE` — TTS voice (default: Sora)
  - `JARVIS_PTT_SECONDS` — recording duration (default: 8)
  - `JARVIS_PTT_DEVICE` — microphone device
- Directory structure: `~/.jarvis/`, `knowledge_base/`
- Model selection: `--model` flag, defaults
- Search tuning: fts_top_k, vector_top_k, rrf_k explained
- 🇰🇷 한국어 section

### 6. Retrieval Pipeline

**File**: `Retrieval-Pipeline.md`
**Purpose**: Deep dive into the hybrid search architecture

**Content**:
- Architecture diagram (Mermaid): Query → Planner → [FTS5 branch + Vector branch] → RRF Fusion → Evidence
- **FTS5 Search**: SQLite FTS5, Kiwi morphological tokenization, Korean-specific
- **Vector Search**: BGE-M3 embeddings, LanceDB ANN, sentence-transformers + MPS
- **RRF Fusion**: Reciprocal Rank Fusion with k=60, formula explanation
- **Freshness**: SHA-256 hash staleness detection, time-based score boost
- **Indexing Pipeline**: Parse → Chunk (500 tokens / 80 overlap, heading-aware) → FTS immediate + vector backfill daemon
- **AI Planner**: Intent classification, KO→EN keyword translation via EXAONE
- Supported formats: 100+ extensions, CP949/UTF-16 LE encoding support
- 🇰🇷 한국어 section

### 7. Voice Pipeline

**File**: `Voice-Pipeline.md`
**Purpose**: Explain voice interaction architecture and modes

**Content**:
- State diagram (Mermaid): DORMANT → LISTENING → PROCESSING → SPEAKING → DORMANT
- Three modes comparison table:
  | Mode | Command | Behavior |
  |------|---------|----------|
  | File | `--voice file` | Process pre-recorded audio file |
  | PTT Once | `--voice ptt` | Record once → transcribe → respond → exit |
  | Live Loop | `--voice live` | Continuous conversation loop |
- STT: whisper.cpp integration, model selection, TCC microphone permission
- TTS: Qwen3-TTS, voice selection, audio playback
- Audio Recording: afrecord wrapper, device selection, permission preflight
- Menu bar integration: live voice loop through SwiftUI bridge
- 🇰🇷 한국어 section

### 8. Menu Bar App

**File**: `Menu-Bar-App.md`
**Purpose**: Explain the macOS native UI layer

**Content**:
- SwiftUI architecture: StatusBarExtra, state management
- Python bridge JSON protocol:
  - Input: `--query "..." --model "..."`
  - Output: `{ response, citations[], status { safe_mode, degraded_mode, write_blocked } }`
- One-shot subprocess mode (not long-running daemon)
- Features: text query, PTT once, live voice loop, approval panel, health status
- RuntimeContext: shared factory for CLI and menu bar modes
- Build & run instructions (Xcode project)
- 🇰🇷 한국어 section

### 9. Security Model

**File**: `Security-Model.md`
**Purpose**: Document the safety architecture (important for trust)

**Content**:
- 5-level safety model diagram:
  - Level 0: Text-only conversation (no KB access)
  - Level 1: Selective folder read (`knowledge_base/` only)
  - Level 2: Approval-gated write (`draft_export` tool)
  - Level 3: Auto-execution — **intentionally excluded**
  - Level 4: Full autonomy — **intentionally excluded**
- Tool whitelist: read_file, search_files, draft_export (3 tools only)
- Approval gate flow: tool request → user confirmation → execution
- macOS TCC permissions: microphone access, file system scope
- Governor safety: thermal/battery pause for indexing
- Error monitor: failure tracking, degraded/safe mode triggers
- 🇰🇷 한국어 section

### 10. Design Decisions

**File**: `Design-Decisions.md`
**Purpose**: Portfolio centerpiece — demonstrate engineering judgment

**Content**:
- Introduction: How decisions were made (Colligi2 collective intelligence + manual validation)
- Decision format per item: Context → Options Considered → Decision → Rationale
- **6 key decisions**:
  1. **Local-only architecture** — Privacy vs performance tradeoff, no cloud dependency
  2. **Monolith with Protocol interfaces** — Why not microservices, Protocol-first for future extraction
  3. **Hybrid FTS5 + Vector retrieval** — Single-method limitations, RRF fusion benefits
  4. **MLX primary, Ollama fallback** — Metal acceleration priority, stability safety net
  5. **Memory budget 16GB worst-case** — Real measurement over optimistic estimates, sequential loading
  6. **Kiwi morphological analyzer** — Korean NLP comparison (Kiwi vs MeCab-ko vs Komoran)
- **Pivots & failures** (shows honest engineering):
  - Kokoro-82M TTS eliminated (no Korean support)
  - BGE-M3 cannot run on MLX (discovered during implementation)
  - EXAONE model name correction (EXAONE-3.5-7.8B, not "Exaone-4.0-7.8B")
  - Kanana-2-30B-A3B considered but needs 30min conversion
- Colligi2 analysis process summary (2 rounds of collective intelligence)
- 🇰🇷 한국어 section

### 11. Contributing

**File**: `Contributing.md`
**Purpose**: Enable external contributions

**Content**:
- Development environment setup (Python 3.12, venv, dev dependencies)
- Code style: ruff linter, mypy type checking
- Test strategy: 335 tests across unit/integration/e2e
- Running tests: `python -m pytest tests/ -v`
- Project structure guide (where to find what)
- Protocol interface rules: contracts/ is frozen, changes need discussion
- PR process, branch naming
- Known areas needing help (from KNOWN_ISSUES_BETA_1.md)
- 🇰🇷 한국어 section

### 12. FAQ & Troubleshooting

**File**: `FAQ-&-Troubleshooting.md`
**Purpose**: Self-service problem resolution

**Content**:
- **FAQ**:
  - "Can I run without Ollama?" → Yes, MLX backend is primary
  - "What if MLX isn't available?" → Ollama fallback activates
  - "How much memory does it need?" → 16GB worst-case, sequential loading
  - "Can I use my own documents?" → Drop into knowledge_base/, auto-indexed
  - "Does it work offline?" → Yes, fully local
  - "Korean-only or English too?" → Korean-first, English supported
- **Troubleshooting**:
  - Memory pressure / Governor degraded mode
  - Parser dependency missing (graceful degradation)
  - Microphone permission (TCC)
  - Slow morphological analysis
  - Model download / Ollama connection
- Known issues (from KNOWN_ISSUES_BETA_1.md)
- 🇰🇷 한국어 section

---

## Cross-Cutting Concerns

### Bilingual Strategy
- English is the primary language for each section
- Korean section appears at the bottom of each page under `---` separator and `## 🇰🇷 한국어` heading
- Korean content mirrors the English structure but is not a literal translation — natural Korean phrasing

### Navigation
- `_Sidebar.md`: Persistent left navigation with emoji prefixes and section dividers
- `_Footer.md`: "← Previous | Next →" links for sequential reading
- Each page links to related pages within content where relevant

### Diagrams
- Use Mermaid syntax (GitHub Wiki renders Mermaid natively)
- Key diagrams: orchestrator pipeline, retrieval architecture, voice state machine, security levels, module layers

### Tone
- Professional but approachable
- Technical depth with clear explanations
- Portfolio-conscious: highlight engineering decisions, not just features
- Code examples where helpful (config, CLI commands)
