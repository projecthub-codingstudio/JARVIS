# Explorer View Design Spec

## Goal

Knowledge Base에 시각적 파일 브라우저 뷰를 추가한다. 기존 Repository 뷰(개발자 친화적 트리+뷰어)는 그대로 유지하고, Explorer는 아이콘 그리드 기반의 직관적 파일 탐색 경험을 제공한다.

## Layout: Compact Tree + Grid (Hybrid)

```
┌─────────────────────────────────────────────────────────┐
│ [sidebar] │  — 100% +  Bookmark         원문보기        │
├───────┬───┴─────────────────────────────────────────────┤
│FOLDERS│ 🏠 › coding › documents                         │
│       │                                                  │
│📁coding│ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐           │
│ 📁py  │ │  📄  │ │  📊  │ │  📝  │ │  🎨  │           │
│ 📁sh  │ │report│ │ data │ │notes │ │slides│           │
│📁docs ◄│ │.pdf  │ │.xlsx │ │.md   │ │.pptx │           │
│📁media│ │2.4 MB│ │840 KB│ │12 KB │ │5.1 MB│           │
│       │ └──────┘ └──────┘ └──────┘ └──────┘           │
│       │ ┌──────┐ ┌──────┐                               │
│       │ │  📋  │ │  💻  │                               │
│       │ │ task │ │ main │                               │
│       │ │.docx │ │.py   │                               │
│       │ │320 KB│ │8 KB  │                               │
│       │ └──────┘ └──────┘                               │
├───────┴─────────────────────────────────────────────────┤
│ SYSTEM READY  backend:online  latency:5ms               │
└─────────────────────────────────────────────────────────┘
```

- **좌측 (140px)**: 디렉토리 전용 트리. 파일은 표시하지 않음.
- **우측**: 빵가루 경로 + 파일/폴더 아이콘 그리드.
- **파일 클릭**: Zoom Expand 애니메이션 → ViewerShell (기존 뷰어 재사용)
- **뷰어 닫기**: Zoom Shrink 애니메이션 → 그리드 복귀

## ViewState 확장

`ViewState`에 `'explorer'`를 추가한다:

```ts
type ViewState = 'home' | 'terminal' | 'repository' | 'explorer' | 'skills' | 'admin';
```

사이드바 메뉴에 `FolderSearch` 아이콘으로 추가. Repository(`FolderOpen`) 아래에 위치.

## 컴포넌트 구조

```
src/components/explorer/
├── ExplorerWorkspace.tsx    — 최상위 컨테이너, 상태 관리
├── ExplorerTree.tsx         — 좌측 디렉토리 전용 트리 (140px)
├── ExplorerGrid.tsx         — 빵가루 + 파일/폴더 아이콘 그리드
├── FileIconCard.tsx         — 개별 파일/폴더 아이콘 카드
└── ExplorerViewer.tsx       — Zoom 애니메이션 + ViewerShell 래퍼
```

### ExplorerWorkspace

최상위 상태 관리:
- `currentPath: string` — 현재 디렉토리 경로
- `entries: FileNode[]` — 현재 디렉토리의 파일/폴더 목록
- `selectedFile: FileNode | null` — 뷰어에 열린 파일
- `selectedRect: DOMRect | null` — Zoom 애니메이션 시작 위치

`/api/browse` API를 호출하여 디렉토리 내용을 로드한다.

### ExplorerTree

- 디렉토리만 표시 (파일 미표시)
- 클릭 시 `onSelectDirectory(path)` 콜백
- 현재 선택된 디렉토리 하이라이트
- 재귀적 확장/접기 (기존 FileTreePanel의 디렉토리 부분 로직 참조)

### ExplorerGrid

- 상단: 빵가루 경로 (홈 > coding > documents) — 각 세그먼트 클릭 시 해당 디렉토리로 이동
- 그리드: `grid-cols` 반응형 (sm:3, md:4, lg:5, xl:6)
- 폴더 아이콘 클릭: `onNavigate(path)` — 해당 디렉토리로 이동
- 파일 아이콘 클릭: `onOpenFile(file, rect)` — rect는 클릭한 카드의 위치

### FileIconCard

- 확장자별 아이콘 + 색상
- 파일명 (truncate)
- 파일 크기 (formatBytes)
- hover 시 배경 밝아짐 + scale(1.02)

아이콘/색상 매핑:

| 확장자 | 색상 | Lucide 아이콘 |
|--------|------|--------------|
| pdf | `#ef4444` | `FileText` |
| xlsx, xls, csv | `#22c55e` | `Sheet` |
| pptx, ppt | `#f97316` | `Presentation` |
| docx, doc | `#3b82f6` | `FileText` |
| md, txt, log | `#94a3b8` | `FileText` |
| py, js, ts, tsx, jsx, ... | `#a855f7` | `Code2` |
| png, jpg, jpeg, gif, webp, svg | `#ec4899` | `Image` |
| hwp | `#06b6d4` | `FileText` |
| json, yaml, toml, xml | `#f59e0b` | `Braces` |
| 폴더 | `#eab308` | `Folder` |
| 기타 | `#64748b` | `File` |

### ExplorerViewer

- `selectedFile`이 null이 아닌 경우 렌더링
- `motion/react`로 Zoom Expand/Shrink 애니메이션:
  - `initial`: `selectedRect` 위치/크기, opacity 0
  - `animate`: 전체 컨텐츠 영역, opacity 1
  - `exit`: `selectedRect` 위치/크기로 축소, opacity 0
  - `transition`: duration 0.3초, ease "easeInOut"
- 내부에 ViewerShell 렌더링 (`hideLibrary=true`)
- 좌상단 닫기 버튼 (X) → `onClose()` → selectedFile을 null로

## 데이터 흐름

1. Explorer 마운트 → `apiClient.browse('')` → 루트 디렉토리 로드
2. 트리/그리드에서 디렉토리 선택 → `apiClient.browse(path)` → 그리드 갱신
3. 그리드에서 파일 클릭 → `selectedFile` 설정 + 클릭 위치 캡처
4. ExplorerViewer 마운트 → Zoom Expand → ViewerShell 표시
5. 닫기 클릭 → Zoom Shrink → `selectedFile = null` → 그리드 복귀

## 파일 경로 NFC 정규화

`apiClient.browse()`와 `apiClient.getFileUrl()`은 이미 NFC 정규화가 적용되어 있으므로 추가 작업 불필요.

## App.tsx 수정

- `ViewState`에 `'explorer'` 추가
- `SHELL_NAV`에 `{ key: 'explorer', label: 'Explorer', icon: FolderSearch }` 추가 (Repository 다음)
- `CommandPalette`의 `NAV_ITEMS`에도 동일 추가
- `<main>` 내부에 `view === 'explorer'` 분기 추가 → `ExplorerWorkspace` 렌더링

## 제약 사항

- 기존 Repository 뷰는 변경하지 않음
- ViewerShell을 재사용하되 `hideLibrary=true`로 Document Library 숨김
- 뷰어 내 줌, 페이지 이동, 썸네일 등 기존 기능 모두 동작
