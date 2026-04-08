# ProjectHub-JARVIS Web Interface

JARVIS의 웹 기반 프론트엔드 인터페이스입니다.

[![Built with ProjectHub](https://img.shields.io/badge/Built_with-ProjectHub-0EA5E9)](https://projecthub.co.kr)
[![Designed with Stitch](https://img.shields.io/badge/Designed_with-Google_Stitch-4285F4?logo=google&logoColor=white)](https://stitch.withgoogle.com/)
[![React 19](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=white)](https://react.dev)
[![TypeScript](https://img.shields.io/badge/TypeScript-5-3178C6?logo=typescript&logoColor=white)](https://www.typescriptlang.org)
[![Vite](https://img.shields.io/badge/Vite-6-646CFF?logo=vite&logoColor=white)](https://vite.dev)
[![Tailwind CSS v4](https://img.shields.io/badge/Tailwind_CSS-v4-06B6D4?logo=tailwindcss&logoColor=white)](https://tailwindcss.com)

---

## UI Design

이 프로젝트의 UI 디자인은 [Google Stitch](https://stitch.withgoogle.com/)를 사용하여 설계되었습니다.

- **디자인 방향**: Command OS — 터미널 + 저장소 + 문서 + 근거 + AI 조합의 작업 운영 표면
- **레퍼런스**: Raycast (키보드 중심), Linear (작업 밀도), Notion (문서 + 명령), Warp (터미널 현대화)
- **디자인 브리프**: [`docs/design/stitch-ui-brief.md`](docs/design/stitch-ui-brief.md)

### 디자인 특징
- 다크 모드 기반, 낮은 시각 소음
- 키보드 중심 진입 (Cmd+K 커맨드 팔레트)
- 6탭 워크스페이스 구조 (Home, Terminal, Documents, Explorer, Skills, Admin)
- 플로팅 윈도우 기반 문서 뷰어 (drag, resize, maximize, cascade/tile layout)
- Material Design 3 색상 체계 (primary, secondary, tertiary, surface variants)

---

## Tech Stack

| 기술 | 용도 |
|------|------|
| [React 19](https://react.dev) | UI 프레임워크 |
| [TypeScript 5](https://www.typescriptlang.org) | 타입 시스템 |
| [Vite 6](https://vite.dev) | 빌드 도구 |
| [Tailwind CSS v4](https://tailwindcss.com) | 스타일링 |
| [Zustand](https://zustand.docs.pmnd.rs) | 상태 관리 |
| [Framer Motion](https://motion.dev) | 애니메이션 |
| [Lucide React](https://lucide.dev) | 아이콘 |
| [React Markdown](https://remarkjs.github.io/react-markdown/) | 마크다운 렌더링 (GFM) |
| [react-pdf](https://react-pdf.org/) | PDF 뷰어 |
| [react-syntax-highlighter](https://github.com/react-syntax-highlighter/react-syntax-highlighter) | 코드 하이라이팅 |
| [docx-preview](https://github.com/nickenlow/docx-preview-ts) | DOCX 뷰어 |

---

## 워크스페이스 구조

| 탭 | 설명 |
|----|------|
| **Home** | 대시보드, KB 통계, 리인덱스, 서버 재시작 |
| **Terminal** | AI 채팅, 이미지 첨부 (Gemma 4 Vision), 문서 컨텍스트 뱃지, 👍/👎 피드백 |
| **Documents** | 검색 결과 cascade 윈도우, 좌측 목록, Free/Cascade/Tile 레이아웃 |
| **Explorer** | 파일 트리 브라우저, 12개 전문 뷰어, 플로팅 윈도우 |
| **Skills** | 스킬 프로필 관리, 워크플로우 액션 맵 |
| **Admin** | 시스템 로그, Source Map (radial), Token Usage, Learned Patterns |

---

## 설치 및 실행

**사전 조건**: Node.js 18+

```bash
# 의존성 설치
npm install

# 환경 설정
cp .env.example .env

# 개발 서버 실행 (포트 3000)
npm run dev

# 빌드
npm run build
```

> 백엔드(`localhost:8000`)가 실행 중이어야 합니다. 전체 설치는 [Installation Guide](../docs/JARVIS_Installation_Guide.md)를 참조하세요.

---

## 프로젝트 구조

```
src/
├── App.tsx                          # 메인 앱 (6탭 + 뷰 전환 + 문서 컨텍스트)
├── types.ts                         # TypeScript 타입 정의
├── store/app-store.ts               # Zustand 상태 관리
├── hooks/useJarvis.ts               # API 통신 훅
├── lib/
│   ├── api-client.ts                # HTTP 클라이언트 (ask, feedback, browse, file)
│   └── response-text.ts             # 응답 텍스트 정규화
├── components/
│   ├── documents/
│   │   └── DocumentsWorkspace.tsx   # 검색 결과 cascade 윈도우
│   ├── explorer/
│   │   ├── ExplorerWorkspace.tsx     # 파일 탐색기
│   │   ├── ExplorerViewer.tsx        # 플로팅 윈도우 (drag/resize/maximize)
│   │   ├── ExplorerTree.tsx          # 디렉토리 트리
│   │   └── ExplorerGrid.tsx          # 파일 그리드
│   ├── viewer/
│   │   ├── ViewerShell.tsx           # 문서 뷰어 셸 (zoom, bookmark, ask)
│   │   ├── ViewerRouter.tsx          # 확장자별 렌더러 라우팅
│   │   └── renderers/               # 12개 전문 렌더러
│   ├── workspaces/
│   │   ├── TerminalWorkspace.tsx     # 채팅 + 피드백 + 문서 뱃지
│   │   ├── AdminWorkspace.tsx        # 관리자 패널
│   │   └── SkillsWorkspace.tsx       # 스킬 관리
│   └── shell/
│       ├── CommandPalette.tsx        # Cmd+K 명령 팔레트
│       ├── NotificationBell.tsx      # 알림
│       └── SettingsPopover.tsx       # 설정
└── index.css                         # Tailwind + 타이포그래피
```

---

## Built With

- **[ProjectHub](https://projecthub.co.kr)** — AI 기반 프로젝트 관리 및 빌드 오케스트레이션 플랫폼
- **[Google Stitch](https://stitch.withgoogle.com/)** — UI 디자인 및 프로토타이핑
- **[Colligi](https://colligi.ai)** — 아키텍처 설계 집단지성 분석
