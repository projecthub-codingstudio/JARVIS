# JARVIS

**Just A Rather Very Intelligent System**

A privacy-first, local AI assistant for Apple Silicon — inspired by Iron Man's JARVIS.

## Overview

JARVIS is a fully local AI assistant that runs on MacBook Pro M1 Max (64GB). It provides voice interaction, document-grounded Q&A with citations, and macOS system control — all without cloud dependencies.

### Core Features

- **Personal RAG** — Document-grounded Q&A over PDF, DOCX, XLSX, HWP, Markdown, and code files
- **Citation-backed Answers** — Every factual response includes source file references
- **AI Query Planner** — LLM-based intent classification with Korean-English bilingual keyword translation
- **Real-time Indexing** — File watcher auto-indexes new/modified documents in the knowledge base
- **Resource Governor** — System monitoring (memory, swap, thermal, battery) with automatic model tier selection
- **Voice Interaction** — Push-to-talk with local STT/TTS (Phase 2)

### Tech Stack

| Component | Technology |
|-----------|-----------|
| LLM | Qwen3-30B-A3B (Ollama) / MLX (Apple Silicon native) |
| Query Planner | EXAONE-3.5-7.8B (fast intent analysis) |
| Retrieval | SQLite FTS5 + Kiwi morphological analyzer |
| Parsers | PyMuPDF, python-docx, openpyxl, python-hwpx, pyhwp |
| TTS | Qwen3-TTS (validated) |
| STT | whisper.cpp (Phase 2) |
| Language | Python 3.12 |

### Target Environment

- MacBook Pro 16" / Apple M1 Max / 64GB Unified Memory
- macOS Tahoe 26.3

## Project Structure

```
JARVIS/
├── alliance_20260317_130542/   # Main source code (see below)
├── colligi2_20260316_021200/   # Colligi2 analysis round 1
├── colligi2_20260316_133406/   # Colligi2 analysis round 2
├── knowledge_base/             # User documents (local only, git-ignored)
└── .gitignore
```

## Quick Start

```bash
cd alliance_20260317_130542

# Setup
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Run (requires Ollama)
python -m jarvis

# Run with a different model
python -m jarvis --model=exaone3.5:7.8b

# Tests (249 passing)
python -m pytest tests/ -v
```

## Built With

This project was designed and built using:

- **[ProjectHub](https://projecthub.co.kr)** — AI-powered project management and build orchestration platform
- **[Colligi](https://colligi.ai)** — Collective intelligence analysis system for architecture design and technical decision-making

## License

[MIT License](LICENSE)

---

## 상세 설명

### alliance_20260317_130542/ — 메인 소스 디렉토리

Alliance 빌드 시스템으로 생성된 JARVIS 구현체입니다. 모든 실행 가능한 코드가 이 디렉토리에 있습니다.

```
alliance_20260317_130542/
├── pyproject.toml              # 패키지 설정 및 의존성
├── sql/schema.sql              # SQLite 스키마 (FTS5, lexical_morphs 포함)
├── src/jarvis/
│   ├── __main__.py             # 엔트리 포인트 (python -m jarvis)
│   ├── app/                    # 부트스트랩, 설정
│   ├── cli/repl.py             # CLI REPL 인터페이스 (출처 표시 포함)
│   ├── contracts/              # Protocol 인터페이스, 데이터 모델
│   ├── core/
│   │   ├── orchestrator.py     # 파이프라인 오케스트레이터
│   │   ├── governor.py         # 시스템 리소스 모니터링 (psutil)
│   │   └── planner.py          # AI 기반 Intent 분류 + 한→영 키워드 번역
│   ├── indexing/               # 문서 파싱(PDF/DOCX/XLSX/HWP), 청킹, 인덱싱
│   ├── retrieval/              # FTS5 검색, Kiwi 형태소 분석, 하이브리드 검색
│   ├── runtime/                # LLM 백엔드 (MLX primary, Ollama fallback)
│   └── memory/                 # 대화 기록 (SQLite), 태스크 로그
├── tests/                      # 249개 테스트 (unit, integration, e2e)
└── docs/                       # 설계 스펙 문서
```

### colligi2 디렉토리 — 집단지성 분석 결과

Colligi2 집단지성 분석 시스템으로 생성된 JARVIS 프로젝트 분석 보고서입니다.

- **colligi2_20260316_021200/** — 1차 분석: 아키텍처 설계, 기술 스택 결정, 메모리 예산 분석
- **colligi2_20260316_133406/** — 2차 분석: 실행 설계, 충돌 해결, Phase 0/1 구현 명세

각 디렉토리에는 `.md` (마크다운 보고서), `.docx` (Word 문서), `.json` (구조화된 분석 데이터)이 포함됩니다. 이 분석 결과가 구현의 기술 문서로 사용되었습니다.

### 지식 베이스 (knowledge_base/)

`knowledge_base/` 디렉토리에 파일을 넣으면 JARVIS 시작 시 자동으로 인덱싱됩니다. 실행 중에도 파일 추가/수정/삭제가 실시간으로 반영됩니다.

지원 형식: `.pdf`, `.docx`, `.xlsx`, `.hwpx`, `.hwp`, `.md`, `.txt`, `.py`, `.json`, `.yaml`

### 구현 현황

- [x] Colligi2 집단지성 분석 완료
- [x] Alliance 기반 코드 생성
- [x] LLM 백엔드 연결 (MLX primary + Ollama fallback)
- [x] 문서 파서 구현 (PDF, DOCX, XLSX, HWPX, HWP)
- [x] FTS5 검색 + Kiwi 형태소 분석
- [x] AI Planner (Intent 분류 + 한→영 키워드 번역)
- [x] Governor (시스템 리소스 모니터링, 8개 임계값 규칙)
- [x] 출처 표시 (Citation) — 파일명, 유형, 인용문
- [x] 실시간 파일 감시 (File Watcher)
- [x] 토큰 기반 청킹 (500 토큰 / 80 오버랩, heading-aware)
- [x] 형태소 분석 비동기 배치 처리
- [ ] 벡터 검색 (LanceDB 임베딩)
- [ ] 음성 인터페이스 (STT/TTS)
- [ ] macOS 메뉴바 앱 (SwiftUI)
