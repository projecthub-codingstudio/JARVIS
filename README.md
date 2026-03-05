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

- **TTS**: Qwen3-TTS (로컬, 검증 완료)
- **STT**: TBD (로컬 실행 가능한 솔루션)
- **Language**: Python (AI/ML) + Swift (macOS native)

## Target Environment

- MacBook Pro 16 / Apple M1 Max / 64GB RAM
- macOS Tahoe 26.3

## Project Structure

```
JARVIS/
├── docs/           # 설계 문서, 기획서
├── src/            # 소스 코드 (추후 구성)
├── tests/          # 테스트
└── 계획/           # Colligi 분석 프롬프트 및 기획 자료
```

## Status

- [x] 프로젝트 초기 설정
- [x] Colligi 분석 프롬프트 작성
- [ ] Colligi 집단지성 분석 실행
- [ ] 기획문서 검토 및 보완
- [ ] Alliance 기반 구현 시작

## License

[MIT License](LICENSE)
