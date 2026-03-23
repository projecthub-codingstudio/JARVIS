# JARVIS

> **Just A Rather Very Intelligent System**

A privacy-first, local AI assistant for Apple Silicon — inspired by Iron Man's JARVIS.

JARVIS runs entirely on your MacBook Pro with **zero cloud dependencies**. It provides document-grounded Q&A with citations, AI-powered query planning, and real-time knowledge base indexing — all processed locally on Apple Silicon.

## Core Values

| | Value | Description |
|---|---|---|
| :lock: | **Privacy-first** | All data stays on your device. No cloud APIs, no telemetry, no data leaving your machine. |
| :computer: | **Local-only** | Every model — LLM, STT, TTS, embeddings — runs on Apple Silicon with Metal acceleration. |
| :kr: | **Korean-first** | Native Korean morphological analysis (Kiwi), bilingual query planning, optimized for Korean documents. |

## Key Features

- **Personal RAG** — Document-grounded Q&A over PDF, DOCX, XLSX, HWP, Markdown, and code files
- **Citation-backed Answers** — Every factual response includes source file references with quoted text
- **AI Query Planner** — LLM-based intent classification with Korean-English bilingual keyword translation
- **Real-time Indexing** — File watcher auto-indexes new/modified documents as they change
- **Resource Governor** — System monitoring (memory, swap, thermal, battery) with automatic model tier selection
- **Voice Interaction** — Local STT/TTS with file mode, push-to-talk, and menu bar live loop

## Tech Stack

| Component | Technology |
|-----------|-----------|
| LLM | Qwen3-14B (default) / MLX primary + Ollama fallback |
| Query Planner | EXAONE-3.5-7.8B (fast intent analysis) |
| Retrieval | SQLite FTS5 + LanceDB vectors + RRF hybrid fusion |
| Embeddings | BGE-M3 via sentence-transformers (MPS accelerated) |
| STT | whisper.cpp (Metal acceleration) |
| TTS | Qwen3-TTS (locally validated) |
| Korean NLP | Kiwi morphological analyzer |

## Current Status

**Beta 1** (v0.1.0b1) — 357 passing tests | Python 93.5% / Swift 6.5% | MIT License

## Wiki Pages

| Section | Page | Description |
|---------|------|-------------|
| **Start Here** | [[Getting Started]] | Installation, first run, "Hello World" |
| **Understand** | [[Architecture Overview]] | System design, data flow, module layers |
| | [[Tech Stack]] | Technology choices with rationale |
| | [[Configuration]] | Settings, environment variables, tuning |
| **Deep Dive** | [[Retrieval Pipeline]] | FTS5 + Vector + RRF hybrid search |
| | [[Voice Pipeline]] | STT, TTS, three voice modes |
| | [[Menu Bar App]] | SwiftUI + Python JSON bridge |
| | [[Security Model]] | 5-level safety architecture |
| **Meta** | [[Design Decisions]] | Engineering judgment and trade-offs |
| | [[Contributing]] | Dev setup, code style, testing |
| | [[FAQ & Troubleshooting]] | Common questions, known issues |

## Built With

- **[ProjectHub](https://projecthub.co.kr)** — AI-powered project management and build orchestration
- **[Colligi](https://colligi.ai)** — Collective intelligence analysis for architecture design

---

## :kr: 한국어

# JARVIS

> **Just A Rather Very Intelligent System**

아이언맨의 자비스에서 영감을 받은, 애플 실리콘 전용 프라이버시 최우선 로컬 AI 비서.

JARVIS는 MacBook Pro 위에서 **완전히 로컬로** 동작합니다. 클라우드 의존 없이 문서 기반 Q&A(출처 표시 포함), AI 쿼리 플래닝, 실시간 지식 베이스 인덱싱을 제공합니다.

### 핵심 가치

| | 가치 | 설명 |
|---|---|---|
| :lock: | **프라이버시 우선** | 모든 데이터가 기기 내에 유지됩니다. 클라우드 API 없음, 텔레메트리 없음. |
| :computer: | **완전 로컬** | LLM, STT, TTS, 임베딩 — 모든 모델이 Metal 가속으로 애플 실리콘에서 동작합니다. |
| :kr: | **한국어 우선** | Kiwi 형태소 분석, 한영 이중 언어 쿼리 플래닝, 한국어 문서 최적화. |

### 주요 기능

- **개인 RAG** — PDF, DOCX, XLSX, HWP, Markdown, 코드 파일 기반 문서 Q&A
- **출처 기반 답변** — 모든 사실 답변에 소스 파일과 인용문 포함
- **AI 쿼리 플래너** — LLM 기반 의도 분류 + 한→영 키워드 번역
- **실시간 인덱싱** — 파일 감시기가 신규/수정 문서를 자동 인덱싱
- **리소스 거버너** — 시스템 모니터링(메모리, 스왑, 발열, 배터리)으로 자동 모델 티어 선택
- **음성 인터랙션** — 파일 모드, Push-to-talk, 메뉴바 live loop 포함 로컬 STT/TTS

### 현재 상태

**Beta 1** (v0.1.0b1) — 357개 테스트 통과 | Python 93.5% / Swift 6.5% | MIT License
