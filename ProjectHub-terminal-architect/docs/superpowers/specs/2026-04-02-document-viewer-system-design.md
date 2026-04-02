# Document Viewer System Design

**Date:** 2026-04-02
**Status:** Approved
**Scope:** 사이드바 네비게이션 수정 + 통합 뷰어 컴포넌트 시스템 + 백엔드 파일 서빙 API

---

## 1. 문제 정의

현재 웹 인터페이스의 문제:

1. **사이드바 선택 상태 미반영** — "터미널"과 "관리자"만 active 스타일이 있고, "저장소/자산"은 onClick 핸들러 없는 플레이스홀더
2. **뷰어 하드코딩** — `detail_report`, `detail_image`, `detail_code` 3개 뷰가 더미 콘텐츠로 채워져 있음
3. **파일 형식 미지원** — PPTX, HWP, XLSX, Video 등 JARVIS 백엔드가 반환하는 7가지 `viewer_kind` 중 일부만 대응
4. **파일 서빙 API 부재** — 바이너리 파일을 브라우저로 전송할 엔드포인트 없음

## 2. 사이드바 네비게이션

### ViewState 변경

```typescript
// Before
type ViewState = 'dashboard' | 'detail_report' | 'detail_image' | 'detail_code' | 'admin';

// After
type ViewState = 'dashboard' | 'detail_viewer' | 'repository' | 'admin';
```

- `detail_report`, `detail_image`, `detail_code` → `detail_viewer` 하나로 통합
- `repository` 추가 (파일 시스템 탐색기 — 뷰 전환만 구현, 실제 탐색기는 Phase 2)

### 사이드바 버튼 활성 상태

| 사이드바 버튼 | 활성 조건 |
|---|---|
| 터미널 (대시보드) | `view === 'dashboard'` |
| 저장소 | `view === 'repository'` |
| 자산 | `view === 'detail_viewer'` |
| 관리자 | `view === 'admin'` |

- 검색 결과에서 문서 클릭 → `detail_viewer` 진입 → 사이드바 "자산" 활성화
- "자산" 클릭 시: 마지막 선택된 artifact가 있으면 뷰어로 이동, 없으면 대시보드 유지
- "저장소" 클릭 시: `repository` 뷰로 전환

## 3. 통합 뷰어 컴포넌트 구조

### 파일 구조

```
src/components/viewer/
├── ViewerShell.tsx        — 공통 프레임 (브레드크럼, 툴바, 사이드바)
├── ViewerRouter.tsx       — viewer_kind → 렌더러 매핑
└── renderers/
    ├── PdfRenderer.tsx    — react-pdf (pdfjs-dist)
    ├── DocxRenderer.tsx   — docx-preview
    ├── PptxRenderer.tsx   — @jvmr/pptx-to-html
    ├── XlsxRenderer.tsx   — SheetJS (xlsx)
    ├── HwpRenderer.tsx    — 텍스트 미리보기 + 원본 파일 열기 버튼
    ├── ImageRenderer.tsx  — <img> + 줌/팬 컨트롤
    ├── VideoRenderer.tsx  — <video controls>
    ├── CodeRenderer.tsx   — react-syntax-highlighter (refractor)
    ├── HtmlRenderer.tsx   — <iframe srcDoc sandbox>
    ├── WebRenderer.tsx    — <iframe src sandbox>
    └── TextRenderer.tsx   — <pre> fallback (기본값)
```

### ViewerShell 구성

- **상단:** 브레드크럼 (`대시보드 / 자산 / {artifact.title}`)
- **상단 우측:** 툴바 (다운로드, 공유, 인쇄, 요약 보기/숨기기)
- **중앙:** `ViewerRouter`가 선택한 렌더러
- **우측 사이드바 (토글):** 문서 메타데이터 (유형, 뷰어, 경로) + 관련 citations

### ViewerRouter 매핑 로직

```
viewer_kind === 'document' → 파일 확장자로 분기
  .pdf       → PdfRenderer
  .docx      → DocxRenderer
  .pptx      → PptxRenderer
  .xlsx      → XlsxRenderer
  .hwp/.hwpx → HwpRenderer
viewer_kind === 'image'    → ImageRenderer
viewer_kind === 'video'    → VideoRenderer
viewer_kind === 'code'     → CodeRenderer
viewer_kind === 'html'     → HtmlRenderer
viewer_kind === 'web'      → WebRenderer
viewer_kind === 'text'     → TextRenderer (default fallback)
```

### 공통 렌더러 인터페이스

```typescript
interface RendererProps {
  artifact: Artifact;      // 전체 artifact 메타데이터
  fileUrl?: string;        // /api/file?path=... URL (바이너리 파일용)
  content?: string;        // 텍스트 기반 콘텐츠
}
```

### Lazy Loading

각 렌더러는 `React.lazy()`로 import하여 사용하지 않는 렌더러는 번들에 포함되지 않음:

```typescript
const PdfRenderer = React.lazy(() => import('./renderers/PdfRenderer'));
const DocxRenderer = React.lazy(() => import('./renderers/DocxRenderer'));
// ...
```

## 4. 렌더러별 상세 동작

| 렌더러 | 입력 | 렌더링 방식 | 폴백 |
|---|---|---|---|
| PdfRenderer | `fileUrl` | react-pdf 페이지별 렌더링 + 페이지 네비게이션 | preview 텍스트 표시 |
| DocxRenderer | `fileUrl` | docx-preview로 HTML 변환 후 컨테이너 렌더링 | preview 텍스트 |
| PptxRenderer | `fileUrl` | @jvmr/pptx-to-html 슬라이드별 HTML 변환 | preview 텍스트 |
| XlsxRenderer | `fileUrl` | SheetJS 파싱 → HTML 테이블 + 시트 탭 | preview 텍스트 |
| HwpRenderer | `artifact.preview` | 텍스트 미리보기 + "원본 파일 열기" 버튼 | - |
| ImageRenderer | `fileUrl` | `<img>` + 줌인/줌아웃/리셋 컨트롤 | 깨진 이미지 대체 UI |
| VideoRenderer | `fileUrl` | `<video controls>` + MIME 타입 자동 설정 | 지원 불가 메시지 |
| CodeRenderer | `artifact.preview` 또는 `content` | react-syntax-highlighter + 확장자 기반 언어 감지 | `<pre>` |
| HtmlRenderer | `content` | `<iframe srcDoc sandbox>` | 소스 코드 표시 |
| WebRenderer | `artifact.full_path` (URL) | `<iframe src sandbox>` | 클릭 가능한 링크 |
| TextRenderer | `artifact.preview` | `<pre>` + 줄번호 | - |

### 공통 패턴

- 모든 렌더러는 로딩 상태 표시 (Skeleton UI)
- 파일 로드 실패 시 → preview 텍스트 폴백 + 에러 메시지
- HwpRenderer의 "원본 파일 열기"는 `window.open(fileUrl)`로 브라우저 다운로드

## 5. 백엔드 파일 서빙 API

### 엔드포인트

`GET /api/file?path={full_path}`

### 동작

1. `full_path` 파라미터로 로컬 파일 경로를 받음
2. 기존 `ReadFileTool`의 `allowed_roots` 경로 검증 로직 재활용
3. 허용된 경로 내의 파일만 서빙, 그 외는 403 반환
4. `Content-Type`을 파일 확장자 기반으로 자동 설정 (Python `mimetypes` 모듈)
5. 바이너리 파일은 `FileResponse`로 직접 전송
6. CORS 헤더 추가

### 보안

- Path traversal 방지 (`..` 포함 경로 거부, `os.path.realpath()` 검증)
- `allowed_roots` 외부 접근 차단 → 403
- 파일 존재 여부 확인 → 404

### 프론트엔드 사용

```typescript
const fileUrl = `${API_BASE_URL}/api/file?path=${encodeURIComponent(artifact.full_path)}`;
```

### 수정 파일

`alliance_20260317_130542/src/jarvis/web_api.py`에 엔드포인트 추가

## 6. npm 패키지 추가

```
react-pdf                  — PDF 렌더링 (~1.5MB, MIT)
docx-preview               — DOCX 렌더링 (경량, MIT)
@jvmr/pptx-to-html         — PPTX 렌더링 (경량, MIT)
xlsx                       — XLSX 파싱 (~400KB, Apache 2.0)
react-syntax-highlighter   — 코드 구문 강조 (~17KB, MIT)
```

## 7. App.tsx 변경 요약

- `ViewState` 타입 변경: `detail_report | detail_image | detail_code` → `detail_viewer`에 `repository` 추가
- `selectedArtifact` 상태 활용 (이미 추가됨)
- 기존 3개 detail 뷰 코드 (~360줄) → `<ViewerShell>` 컴포넌트 호출 1개로 교체
- 사이드바 버튼에 onClick 핸들러 + active 스타일 조건 추가
- `openAsset()` 함수 간소화: viewer_kind별 분기 → `setView('detail_viewer')` 하나로 통합
