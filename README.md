# JARVIS

**Just A Rather Very Intelligent System**

MacBook M1 Max 로컬 환경에서 구동되는 개인 AI 비서 시스템.

## Overview

아이언맨의 자비스처럼 음성으로 대화하고, 개인 문서를 이해하며, 맥북을 제어하는 AI 비서.

### Core Features

- **Voice Interaction** - "자비스" 호출어로 활성화, 한국어/영어 양방향 음성 대화
- **Personal RAG** - 로컬 문서(PDF, MD, 코드, Office, HWP 등) 기반 지식 검색 및 답변
- **System Control** - macOS 앱 실행, 파일 관리, 개발 워크플로우 자동화
- **Plugin Architecture** - 확장 가능한 플러그인 시스템

### Tech Stack

- **LLM**: Qwen3-30B-A3B (primary, Ollama) / MLX (Apple Silicon native)
- **TTS**: Qwen3-TTS (로컬, 검증 완료)
- **STT**: whisper.cpp (Phase 2)
- **Retrieval**: SQLite FTS5 + Kiwi 형태소 분석
- **Language**: Python 3.12

## Target Environment

- MacBook Pro 16 / Apple M1 Max / 64GB RAM
- macOS Tahoe 26.3

## Project Structure

```
JARVIS/
├── alliance_20260317_130542/   # 메인 소스 코드 (아래 상세 설명)
├── colligi2_20260316_021200/   # Colligi2 1차 분석 결과 (아키텍처 설계)
├── colligi2_20260316_133406/   # Colligi2 2차 분석 결과 (실행 설계)
├── knowledge_base/             # 지식 베이스 문서 (로컬 전용, git 제외)
└── .gitignore
```

### alliance_20260317_130542/ — 메인 소스

Alliance 빌드 시스템으로 생성된 JARVIS 구현체입니다. 모든 실행 가능한 코드가 이 디렉토리에 있습니다.

```
alliance_20260317_130542/
├── pyproject.toml              # 패키지 설정 및 의존성
├── sql/schema.sql              # SQLite 스키마 (FTS5 포함)
├── src/jarvis/
│   ├── __main__.py             # 엔트리 포인트 (python -m jarvis)
│   ├── app/                    # 부트스트랩, 설정
│   ├── cli/repl.py             # CLI REPL 인터페이스
│   ├── contracts/              # Protocol 인터페이스, 데이터 모델
│   ├── core/
│   │   ├── orchestrator.py     # 파이프라인 오케스트레이터
│   │   ├── governor.py         # 시스템 리소스 모니터링/임계값
│   │   └── planner.py          # AI 기반 Intent 분류/쿼리 정규화
│   ├── indexing/               # 문서 파싱, 청킹, 인덱싱 파이프라인
│   ├── retrieval/              # FTS5 검색, 하이브리드 검색, 형태소 분석
│   ├── runtime/                # LLM 백엔드 (MLX, Ollama)
│   └── memory/                 # 대화 기록, 태스크 로그
├── tests/                      # 249개 테스트
└── docs/                       # 설계 스펙 문서
```

### colligi2 디렉토리 — 분석 결과

Colligi2 집단지성 분석 시스템으로 생성된 JARVIS 프로젝트 분석 보고서입니다.

- **colligi2_20260316_021200/** — 1차 분석: 아키텍처 설계, 기술 스택 결정, 메모리 예산 분석
- **colligi2_20260316_133406/** — 2차 분석: 실행 설계, 충돌 해결, Phase 0/1 구현 명세

각 디렉토리에는 `.md` (마크다운 보고서), `.docx` (Word 문서), `.json` (구조화된 분석 데이터)이 포함됩니다.

## Quick Start

```bash
cd alliance_20260317_130542

# 환경 설정
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# 실행 (Ollama 필요)
python -m jarvis

# 다른 모델로 실행
python -m jarvis --model=exaone3.5:7.8b

# 테스트
python -m pytest tests/ -v
```

### 지식 베이스

`knowledge_base/` 디렉토리에 파일을 넣으면 시작 시 자동 인덱싱됩니다.
실행 중에도 파일 추가/수정/삭제가 실시간으로 반영됩니다.

지원 형식: `.pdf`, `.docx`, `.xlsx`, `.hwpx`, `.hwp`, `.md`, `.txt`, `.py`, `.json`, `.yaml`

## Status

- [x] Colligi2 집단지성 분석 완료
- [x] Alliance 기반 코드 생성
- [x] LLM 백엔드 연결 (MLX + Ollama)
- [x] 문서 파서 구현 (PDF, DOCX, XLSX, HWPX, HWP)
- [x] FTS5 검색 + Kiwi 형태소 분석
- [x] AI Planner (Intent 분류 + 한→영 키워드 번역)
- [x] Governor (시스템 리소스 모니터링)
- [x] 출처 표시 (Citation)
- [x] 실시간 파일 감시 (File Watcher)
- [ ] 벡터 검색 (LanceDB 임베딩)
- [ ] 음성 인터페이스 (STT/TTS)
- [ ] macOS 메뉴바 앱 (SwiftUI)

## License

[MIT License](LICENSE)
