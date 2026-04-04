# ProjectHub Stitch UI Brief

## 목적
ProjectHub의 전체 인터페이스를 Google Stitch로 재설계하기 위한 기준 문서다.
이 앱은 채팅 앱이 아니라 개발자를 위한 작업 운영 표면이어야 한다.

## 추천 방향
우선 추천안은 `Direction 1: Command OS`다.
이유는 현재 제품이 `터미널 + 저장소 + 문서 + 근거 + AI` 조합이기 때문이다.

## 레퍼런스 보드

### 1. Raycast
- URL: https://www.raycast.com/
- 참고 포인트:
  - 키보드 중심 진입
  - 낮은 시각 소음
  - 빠른 반응과 얇은 크롬
  - 명령 중심 정보 구조

### 2. Linear
- URL: https://linear.app/
- 참고 포인트:
  - 리스트, 상세, 메타 패널 위계
  - 높은 정보 밀도
  - 차분한 톤과 선명한 상태 구분
  - 작업 중심 레이아웃

### 3. Cursor
- URL: https://cursor.com/en-US
- 참고 포인트:
  - AI를 작업 표면 안에 배치하는 방식
  - 코드베이스 중심 맥락 유지
  - 챗봇처럼 보이지 않는 AI 통합

### 4. Warp
- URL: https://www.warp.dev/terminal
- 참고 포인트:
  - 터미널 중심 워크플로우
  - 블록 기반 출력
  - 파일 트리와 명령 실행의 결합
  - IDE 같은 입력 경험

### 5. Obsidian
- URL: https://obsidian.md/
- 참고 포인트:
  - 로컬 파일 탐색 감각
  - 파일 트리와 문서 읽기 중심 구조
  - 문서 중심 앱의 안정감

## Direction 1: Command OS

### 성격
빠르고 조용한 AI 작업 운영체제.
`Raycast + Linear + Cursor` 성격이 강한 방향.

### 핵심 구조
- 상단: 전역 커맨드 바
- 좌측: Terminal, Repository, Documents, Admin
- 중앙: 현재 작업 표면
- 우측: citations, evidence, related files, metadata

### 설계 원칙
- 카드보다 패널
- 장식보다 위계
- AI는 보조 레이어
- 중앙 작업면이 항상 주인공

### Stitch Prompt
```text
Design a macOS desktop app called ProjectHub Terminal Architect.

Goal:
Create an AI-native workspace for developers, not a chatbot app and not a dashboard-heavy admin tool.
The product combines terminal workflow, repository navigation, evidence-based answers, and document viewing.

Primary inspiration:
Raycast for command entry and low visual noise
Linear for information hierarchy and list/detail structure
Cursor for AI integrated into the work surface
Warp for terminal-native workflows

Main layout:
- Top global command bar with keyboard-first interaction
- Left narrow navigation rail: Terminal, Repository, Documents, Admin
- Center main workspace showing the active task surface
- Right collapsible context panel for citations, evidence, related files, and AI reasoning context

Key screens:
1. Terminal workspace with command input, response stream, and related result documents
2. Repository explorer with file tree and quick preview
3. Document viewer for PDF, DOCX, PPTX, XLSX, code, and web artifacts
4. Admin overview for system logs and runtime status

Design direction:
- Calm, dense, professional
- Dark theme first but not neon cyberpunk
- macOS-native feeling
- High information clarity
- Minimal decorative chrome
- Crisp typography
- Strong spacing rhythm
- AI is embedded, not dominant

Visual rules:
- Avoid dashboard card clutter
- Avoid oversized hero sections
- Avoid generic purple gradients
- Use muted graphite, warm gray, off-white, deep green accents
- Use subtle borders, layered surfaces, and restrained glow
- Emphasize hierarchy through layout, not color overload

Please generate:
- one main app shell
- one terminal-focused screen
- one repository/document split screen
- one document viewer detail screen
```

## Direction 2: Repository Cockpit

### 성격
문서와 근거를 많이 보는 조사형 워크벤치.
`Obsidian + Linear + Warp` 성격이 강한 방향.

### 핵심 구조
- 좌측: 파일 트리와 최근 경로
- 중앙: 문서/코드/슬라이드 뷰어
- 하단: 명령 입력과 실행 로그
- 우측: 근거, citations, 관련 문서, 메타데이터

### 설계 원칙
- 저장소와 문서가 화면의 중심
- AI는 검사와 요약 보조
- 채팅보다 검증과 탐색

### Stitch Prompt
```text
Design a macOS investigation workspace called ProjectHub.

Goal:
Create a repository-first and document-first interface for developers who inspect code, search evidence, read source documents, and interact with AI assistance.

Primary inspiration:
Obsidian for file navigation and document focus
Linear for panel hierarchy and density
Warp for terminal workflow and output organization

Main layout:
- Left persistent repository tree with folders, files, and recent items
- Center content canvas for code, documents, slides, spreadsheets, and web previews
- Bottom docked command console with terminal-style interaction
- Right evidence inspector with citations, source snippets, related artifacts, and metadata

Priority experience:
- Reading and verifying source material
- Moving quickly between repository file and answer evidence
- Clear distinction between repository, documents, and chat
- AI as an assistant panel, not the center of the interface

Visual direction:
- macOS desktop software
- editorial and technical
- quiet, structured, trustworthy
- less flashy, more legible
- deep gray surfaces, bone white content panels, green accent, amber warning, steel blue metadata
- use real split panes and toolbars, not marketing sections

Do not design this like:
- a generic SaaS dashboard
- a messaging app
- a mobile-first card feed

Please generate:
- one repository explorer screen
- one evidence-driven answer review screen
- one document viewer screen
- one code + terminal + citations combined workflow screen
```

## Stitch 사용 순서
1. `Direction 1` 프롬프트로 먼저 생성한다.
2. 현재 앱 스크린샷을 함께 넣는다.
3. 이 저장소의 `DESIGN.md`를 같이 첨부하거나 복사해서 넣는다.
4. 아래 보정 프롬프트로 2~3회 다듬는다.

## 보정 프롬프트

### 정보 밀도 올리기
```text
Make the interface denser and more operational.
Reduce dashboard feeling.
Use more split panes and fewer large cards.
Keep the app readable but significantly more desktop-like.
```

### 저장소와 문서 분리 강화
```text
Make Repository and Documents clearly distinct.
Repository should feel path-oriented and source-oriented.
Documents should feel result-oriented and reading-oriented.
Use navigation, breadcrumbs, panel titles, and layout to reinforce this difference.
```

### AI 존재감 줄이기
```text
Reduce the visual dominance of AI.
Do not center the interface around chat.
Make AI feel embedded into the workflow as contextual assistance.
```

## 권장 산출물
- 앱 셸 1안
- 터미널 메인 화면 1안
- 저장소 탐색 화면 1안
- 문서 뷰어 상세 화면 1안
- 관리자 화면은 마지막에 추가

## 비고
- Google Stitch 관련 참고:
  - Google Labs Stitch: https://labs.google/
  - Stitch 소개 글: https://blog.google/innovation-and-ai/models-and-research/google-labs/stitch-ai-ui-design/
- 이 저장소의 전역 규칙 파일은 루트의 `DESIGN.md`다.
