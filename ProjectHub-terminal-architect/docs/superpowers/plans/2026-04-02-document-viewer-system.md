# Document Viewer System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace hardcoded detail views with a modular viewer system supporting 7 viewer_kinds (11 renderers), fix sidebar navigation active states, and add a backend file-serving API.

**Architecture:** ViewerShell (common frame) + ViewerRouter (kind→renderer mapping) + independent renderer files per format. Backend adds `/api/file` endpoint reusing `ReadFileTool` path validation. App.tsx shrinks by ~360 lines as 3 detail views collapse into one `<ViewerShell>` call.

**Tech Stack:** React 19, TypeScript, react-pdf, docx-preview, @jvmr/pptx-to-html, xlsx, react-syntax-highlighter, DOMPurify (HTML sanitization), FastAPI FileResponse

**Security Note:** All renderers that inject HTML (PptxRenderer, XlsxRenderer, HtmlRenderer) MUST sanitize content with DOMPurify before rendering to prevent XSS attacks.

---

## File Structure

### New Files (Frontend)

| File | Responsibility |
|---|---|
| `src/components/viewer/ViewerShell.tsx` | Common frame: breadcrumb, toolbar, metadata sidebar, wraps renderer |
| `src/components/viewer/ViewerRouter.tsx` | Maps `viewer_kind` + file extension → lazy-loaded renderer component |
| `src/components/viewer/renderers/TextRenderer.tsx` | `<pre>` with line numbers (fallback) |
| `src/components/viewer/renderers/CodeRenderer.tsx` | react-syntax-highlighter with language detection |
| `src/components/viewer/renderers/ImageRenderer.tsx` | `<img>` with zoom/pan controls |
| `src/components/viewer/renderers/VideoRenderer.tsx` | `<video controls>` with MIME type |
| `src/components/viewer/renderers/HtmlRenderer.tsx` | `<iframe srcDoc sandbox>` with DOMPurify |
| `src/components/viewer/renderers/WebRenderer.tsx` | `<iframe src sandbox>` |
| `src/components/viewer/renderers/PdfRenderer.tsx` | react-pdf page navigation |
| `src/components/viewer/renderers/DocxRenderer.tsx` | docx-preview container |
| `src/components/viewer/renderers/PptxRenderer.tsx` | @jvmr/pptx-to-html slide rendering with DOMPurify |
| `src/components/viewer/renderers/XlsxRenderer.tsx` | SheetJS → HTML table with sheet tabs, DOMPurify |
| `src/components/viewer/renderers/HwpRenderer.tsx` | Text preview + "원본 파일 열기" button |

### Modified Files (Frontend)

| File | Change |
|---|---|
| `src/types.ts` | `ViewState` → replace 3 detail states with `detail_viewer` + add `repository` |
| `src/App.tsx` | Remove ~360 lines of detail views, add `<ViewerShell>`, fix sidebar buttons |
| `src/lib/api-client.ts` | Add `getFileUrl()` helper |

### Modified Files (Backend)

| File | Change |
|---|---|
| `alliance_20260317_130542/src/jarvis/web_api.py` | Add `GET /api/file` endpoint |

---

## Task 1: Install npm dependencies

**Files:**
- Modify: `package.json`

- [ ] **Step 1: Install viewer libraries**

```bash
cd /Users/codingstudio/__PROJECTHUB__/JARVIS/ProjectHub-terminal-architect
npm install react-pdf react-syntax-highlighter docx-preview xlsx dompurify
npm install -D @types/react-syntax-highlighter @types/dompurify
```

Note: `@jvmr/pptx-to-html` will be installed in the PPTX renderer task after verifying it works.

- [ ] **Step 2: Verify build**

Run: `npm run build`
Expected: Build succeeds with no errors

- [ ] **Step 3: Commit**

```bash
git add package.json package-lock.json
git commit -m "chore: add document viewer dependencies (react-pdf, docx-preview, xlsx, react-syntax-highlighter, dompurify)"
```

---

## Task 2: Update ViewState type and api-client helper

**Files:**
- Modify: `src/types.ts:148`
- Modify: `src/lib/api-client.ts`

- [ ] **Step 1: Update ViewState type**

In `src/types.ts`, replace line 148:

```typescript
// Before
export type ViewState = 'dashboard' | 'detail_report' | 'detail_image' | 'detail_code' | 'admin';

// After
export type ViewState = 'dashboard' | 'detail_viewer' | 'repository' | 'admin';
```

- [ ] **Step 2: Add getFileUrl helper to api-client.ts**

Add at the end of `src/lib/api-client.ts`, before the closing of the `apiClient` object:

```typescript
  getFileUrl(fullPath: string): string {
    return `${API_BASE_URL}/api/file?path=${encodeURIComponent(fullPath)}`;
  },
```

- [ ] **Step 3: Fix TypeScript errors from ViewState change**

In `src/App.tsx`, update `openAsset` function to use `'detail_viewer'`:

```typescript
const openAsset = (artifact: Artifact) => {
  setSelectedArtifact(artifact);
  setSelectedAsset({
    id: artifact.id,
    type: artifact.type.includes('code') ? 'html' :
          artifact.type.includes('image') ? 'image' :
          artifact.type.includes('pdf') ? 'pdf' : 'docx',
    name: artifact.title,
    description: artifact.preview,
    status: artifact.source_type,
    content: artifact.preview,
  });
  setView('detail_viewer');
};
```

- [ ] **Step 4: Verify TypeScript compiles**

Run: `npm run lint`
Expected: No type errors (there may be unused view references to fix in Task 6)

- [ ] **Step 5: Commit**

```bash
git add src/types.ts src/lib/api-client.ts src/App.tsx
git commit -m "refactor: unify ViewState to detail_viewer and add getFileUrl helper"
```

---

## Task 3: Fix sidebar navigation active states

**Files:**
- Modify: `src/App.tsx:234-294`

- [ ] **Step 1: Update desktop sidebar buttons**

Replace lines 245-256 (the 저장소, 자산, 네트워크 buttons) with:

```tsx
<button
  onClick={() => setView('repository')}
  className={cn(
    "flex flex-col items-center gap-1 w-full py-4 transition-all",
    view === 'repository' ? "text-primary border-l-2 border-primary bg-surface-highest/20" : "text-on-surface-variant opacity-80 hover:text-white hover:bg-surface-highest"
  )}
>
  <FolderOpen size={20} />
  <span className="text-[10px] font-medium">저장소</span>
</button>
<button
  onClick={() => selectedArtifact ? setView('detail_viewer') : null}
  className={cn(
    "flex flex-col items-center gap-1 w-full py-4 transition-all",
    view === 'detail_viewer' ? "text-primary border-l-2 border-primary bg-surface-highest/20" : "text-on-surface-variant opacity-80 hover:text-white hover:bg-surface-highest"
  )}
>
  <FileText size={20} />
  <span className="text-[10px] font-medium">자산</span>
</button>
<button className="flex flex-col items-center gap-1 text-on-surface-variant opacity-80 hover:text-on-surface hover:bg-surface-highest w-full py-4 transition-all">
  <Network size={20} />
  <span className="text-[10px] font-medium">네트워크</span>
</button>
```

- [ ] **Step 2: Update mobile navigation**

Replace the mobile nav buttons (lines ~278-294) to match:

```tsx
<nav className="md:hidden flex items-center justify-around bg-surface-low border-t border-outline/10 py-3 shrink-0 z-50 order-last">
  <button onClick={() => setView('dashboard')} className={cn("p-2", view === 'dashboard' ? "text-primary" : "text-on-surface-variant")}>
    <LayoutDashboard size={20} />
  </button>
  <button
    onClick={() => setIsMobileCmdOpen(!isMobileCmdOpen)}
    className={cn("p-2", isMobileCmdOpen ? "text-primary" : "text-on-surface-variant")}
  >
    <Terminal size={20} />
  </button>
  <button onClick={() => setView('repository')} className={cn("p-2", view === 'repository' ? "text-primary" : "text-on-surface-variant")}>
    <FolderOpen size={20} />
  </button>
  <button onClick={() => setView('admin')} className={cn("p-2", view === 'admin' ? "text-primary" : "text-on-surface-variant")}>
    <BarChart3 size={20} />
  </button>
</nav>
```

- [ ] **Step 3: Verify build**

Run: `npm run build`
Expected: Build succeeds

- [ ] **Step 4: Commit**

```bash
git add src/App.tsx
git commit -m "fix: add active states and click handlers to sidebar navigation buttons"
```

---

## Task 4: Create RendererProps interface and TextRenderer (fallback)

**Files:**
- Create: `src/components/viewer/renderers/TextRenderer.tsx`

- [ ] **Step 1: Create directory structure**

```bash
mkdir -p /Users/codingstudio/__PROJECTHUB__/JARVIS/ProjectHub-terminal-architect/src/components/viewer/renderers
```

- [ ] **Step 2: Create TextRenderer.tsx**

```tsx
import React from 'react';
import type { Artifact } from '../../../types';

export interface RendererProps {
  artifact: Artifact;
  fileUrl?: string;
  content?: string;
}

const TextRenderer: React.FC<RendererProps> = ({ artifact, content }) => {
  const text = content || artifact.preview || '내용 없음';
  const lines = text.split('\n');

  return (
    <div className="h-full overflow-auto custom-scrollbar bg-surface-low p-6 font-mono text-sm">
      <table className="w-full border-collapse">
        <tbody>
          {lines.map((line, i) => (
            <tr key={i} className="hover:bg-surface-highest/30">
              <td className="pr-4 text-right text-outline select-none w-12 align-top text-xs">
                {i + 1}
              </td>
              <td className="text-on-surface-variant whitespace-pre-wrap break-all">
                {line || '\u00A0'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

export default TextRenderer;
```

- [ ] **Step 3: Verify build**

Run: `npm run build`
Expected: Build succeeds

- [ ] **Step 4: Commit**

```bash
git add src/components/viewer/renderers/TextRenderer.tsx
git commit -m "feat: add TextRenderer with RendererProps interface"
```

---

## Task 5: Create CodeRenderer

**Files:**
- Create: `src/components/viewer/renderers/CodeRenderer.tsx`

- [ ] **Step 1: Create CodeRenderer.tsx**

```tsx
import React from 'react';
import { Light as SyntaxHighlighter } from 'react-syntax-highlighter';
import { atomOneDark } from 'react-syntax-highlighter/dist/esm/styles/hljs';
import type { RendererProps } from './TextRenderer';

const EXT_TO_LANG: Record<string, string> = {
  py: 'python', js: 'javascript', ts: 'typescript', tsx: 'typescript',
  jsx: 'javascript', rs: 'rust', go: 'go', java: 'java', swift: 'swift',
  kt: 'kotlin', rb: 'ruby', sh: 'bash', zsh: 'bash', bash: 'bash',
  yml: 'yaml', yaml: 'yaml', json: 'json', md: 'markdown', html: 'xml',
  css: 'css', sql: 'sql', toml: 'ini', cfg: 'ini', xml: 'xml',
};

function detectLanguage(path: string): string {
  const ext = path.split('.').pop()?.toLowerCase() || '';
  return EXT_TO_LANG[ext] || 'plaintext';
}

const CodeRenderer: React.FC<RendererProps> = ({ artifact, content }) => {
  const code = content || artifact.preview || '';
  const language = detectLanguage(artifact.path || artifact.full_path || '');

  return (
    <div className="h-full overflow-auto custom-scrollbar">
      <SyntaxHighlighter
        language={language}
        style={atomOneDark}
        showLineNumbers
        wrapLongLines
        customStyle={{
          margin: 0,
          padding: '1.5rem',
          background: 'transparent',
          minHeight: '100%',
          fontSize: '0.8125rem',
        }}
      >
        {code}
      </SyntaxHighlighter>
    </div>
  );
};

export default CodeRenderer;
```

- [ ] **Step 2: Verify build**

Run: `npm run build`
Expected: Build succeeds

- [ ] **Step 3: Commit**

```bash
git add src/components/viewer/renderers/CodeRenderer.tsx
git commit -m "feat: add CodeRenderer with syntax highlighting and language detection"
```

---

## Task 6: Create ImageRenderer, VideoRenderer, HtmlRenderer, WebRenderer

**Files:**
- Create: `src/components/viewer/renderers/ImageRenderer.tsx`
- Create: `src/components/viewer/renderers/VideoRenderer.tsx`
- Create: `src/components/viewer/renderers/HtmlRenderer.tsx`
- Create: `src/components/viewer/renderers/WebRenderer.tsx`

- [ ] **Step 1: Create ImageRenderer.tsx**

```tsx
import React, { useState } from 'react';
import { ZoomIn, ZoomOut, RotateCcw } from 'lucide-react';
import type { RendererProps } from './TextRenderer';

const ZOOM_STEPS = [0.25, 0.5, 0.75, 1, 1.25, 1.5, 2, 3];

const ImageRenderer: React.FC<RendererProps> = ({ artifact, fileUrl }) => {
  const [zoomIndex, setZoomIndex] = useState(3); // 1x default
  const [error, setError] = useState(false);
  const zoom = ZOOM_STEPS[zoomIndex];

  if (error || !fileUrl) {
    return (
      <div className="h-full flex items-center justify-center text-on-surface-variant">
        <p>{artifact.preview || '이미지를 불러올 수 없습니다.'}</p>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col">
      <div className="flex-1 overflow-auto flex items-center justify-center bg-black/20 custom-scrollbar">
        <img
          src={fileUrl}
          alt={artifact.title}
          style={{ transform: `scale(${zoom})`, transformOrigin: 'center', transition: 'transform 0.2s' }}
          onError={() => setError(true)}
          className="max-w-none"
          referrerPolicy="no-referrer"
        />
      </div>
      <div className="flex items-center justify-center gap-1 p-2 bg-surface-highest/50 border-t border-outline/10">
        <button
          onClick={() => setZoomIndex(Math.max(0, zoomIndex - 1))}
          className="p-2 hover:bg-surface-highest transition-colors"
        >
          <ZoomOut size={16} />
        </button>
        <span className="px-3 font-mono text-xs text-on-surface-variant min-w-[4rem] text-center">
          {Math.round(zoom * 100)}%
        </span>
        <button
          onClick={() => setZoomIndex(Math.min(ZOOM_STEPS.length - 1, zoomIndex + 1))}
          className="p-2 hover:bg-surface-highest transition-colors"
        >
          <ZoomIn size={16} />
        </button>
        <button
          onClick={() => setZoomIndex(3)}
          className="p-2 hover:bg-surface-highest transition-colors ml-2"
        >
          <RotateCcw size={16} />
        </button>
      </div>
    </div>
  );
};

export default ImageRenderer;
```

- [ ] **Step 2: Create VideoRenderer.tsx**

```tsx
import React from 'react';
import type { RendererProps } from './TextRenderer';

const EXT_TO_MIME: Record<string, string> = {
  mp4: 'video/mp4', webm: 'video/webm', mov: 'video/quicktime',
  m4v: 'video/mp4', ogg: 'video/ogg',
};

const VideoRenderer: React.FC<RendererProps> = ({ artifact, fileUrl }) => {
  if (!fileUrl) {
    return (
      <div className="h-full flex items-center justify-center text-on-surface-variant">
        <p>동영상 파일 경로가 없습니다.</p>
      </div>
    );
  }

  const ext = (artifact.path || artifact.full_path || '').split('.').pop()?.toLowerCase() || 'mp4';
  const mime = EXT_TO_MIME[ext] || 'video/mp4';

  return (
    <div className="h-full flex items-center justify-center bg-black p-4">
      <video
        controls
        className="max-w-full max-h-full"
        style={{ outline: 'none' }}
      >
        <source src={fileUrl} type={mime} />
        이 브라우저에서 동영상을 재생할 수 없습니다.
      </video>
    </div>
  );
};

export default VideoRenderer;
```

- [ ] **Step 3: Create HtmlRenderer.tsx**

```tsx
import React, { useMemo } from 'react';
import DOMPurify from 'dompurify';
import type { RendererProps } from './TextRenderer';

const HtmlRenderer: React.FC<RendererProps> = ({ artifact, content }) => {
  const html = content || artifact.preview || '';
  const sanitizedHtml = useMemo(() => DOMPurify.sanitize(html), [html]);

  return (
    <div className="h-full flex flex-col">
      <iframe
        srcDoc={sanitizedHtml}
        sandbox="allow-same-origin"
        title={artifact.title}
        className="flex-1 w-full border-0 bg-white"
      />
    </div>
  );
};

export default HtmlRenderer;
```

- [ ] **Step 4: Create WebRenderer.tsx**

```tsx
import React from 'react';
import { ExternalLink } from 'lucide-react';
import type { RendererProps } from './TextRenderer';

const WebRenderer: React.FC<RendererProps> = ({ artifact }) => {
  const url = artifact.full_path || artifact.path || '';

  if (!url.startsWith('http')) {
    return (
      <div className="h-full flex items-center justify-center text-on-surface-variant">
        <p>유효하지 않은 URL입니다: {url}</p>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col">
      <div className="flex items-center gap-2 px-4 py-2 bg-surface-highest border-b border-outline/10">
        <span className="text-xs font-mono text-on-surface-variant truncate flex-1">{url}</span>
        <a
          href={url}
          target="_blank"
          rel="noopener noreferrer"
          className="p-1 hover:text-primary transition-colors"
        >
          <ExternalLink size={14} />
        </a>
      </div>
      <iframe
        src={url}
        sandbox="allow-same-origin allow-scripts allow-popups"
        title={artifact.title}
        className="flex-1 w-full border-0"
      />
    </div>
  );
};

export default WebRenderer;
```

- [ ] **Step 5: Verify build**

Run: `npm run build`
Expected: Build succeeds

- [ ] **Step 6: Commit**

```bash
git add src/components/viewer/renderers/ImageRenderer.tsx \
        src/components/viewer/renderers/VideoRenderer.tsx \
        src/components/viewer/renderers/HtmlRenderer.tsx \
        src/components/viewer/renderers/WebRenderer.tsx
git commit -m "feat: add Image, Video, Html, Web renderers (native browser APIs + DOMPurify)"
```

---

## Task 7: Create PdfRenderer

**Files:**
- Create: `src/components/viewer/renderers/PdfRenderer.tsx`

- [ ] **Step 1: Create PdfRenderer.tsx**

```tsx
import React, { useState } from 'react';
import { Document, Page, pdfjs } from 'react-pdf';
import 'react-pdf/dist/Page/AnnotationLayer.css';
import 'react-pdf/dist/Page/TextLayer.css';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import type { RendererProps } from './TextRenderer';

pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  'pdfjs-dist/build/pdf.worker.min.mjs',
  import.meta.url,
).toString();

const PdfRenderer: React.FC<RendererProps> = ({ artifact, fileUrl }) => {
  const [numPages, setNumPages] = useState<number>(0);
  const [pageNumber, setPageNumber] = useState(1);
  const [error, setError] = useState(false);

  if (error || !fileUrl) {
    return (
      <div className="h-full overflow-auto p-6 custom-scrollbar">
        <pre className="text-on-surface-variant text-sm whitespace-pre-wrap">
          {artifact.preview || 'PDF를 불러올 수 없습니다.'}
        </pre>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col">
      <div className="flex-1 overflow-auto flex justify-center bg-surface-low custom-scrollbar p-4">
        <Document
          file={fileUrl}
          onLoadSuccess={({ numPages: n }) => setNumPages(n)}
          onLoadError={() => setError(true)}
          loading={
            <div className="flex items-center justify-center h-64">
              <div className="w-6 h-6 border-2 border-primary border-t-transparent rounded-full animate-spin" />
            </div>
          }
        >
          <Page
            pageNumber={pageNumber}
            renderTextLayer
            renderAnnotationLayer
            className="shadow-lg"
          />
        </Document>
      </div>
      {numPages > 0 && (
        <div className="flex items-center justify-center gap-4 p-3 bg-surface-highest/50 border-t border-outline/10">
          <button
            onClick={() => setPageNumber(Math.max(1, pageNumber - 1))}
            disabled={pageNumber <= 1}
            className="p-1 hover:bg-surface-highest disabled:opacity-30 transition-colors"
          >
            <ChevronLeft size={18} />
          </button>
          <span className="font-mono text-xs text-on-surface-variant">
            {pageNumber} / {numPages}
          </span>
          <button
            onClick={() => setPageNumber(Math.min(numPages, pageNumber + 1))}
            disabled={pageNumber >= numPages}
            className="p-1 hover:bg-surface-highest disabled:opacity-30 transition-colors"
          >
            <ChevronRight size={18} />
          </button>
        </div>
      )}
    </div>
  );
};

export default PdfRenderer;
```

- [ ] **Step 2: Verify build**

Run: `npm run build`
Expected: Build succeeds (PDF worker may need Vite config — see step 3)

- [ ] **Step 3: If worker fails, add Vite config for pdf.js worker**

In `vite.config.ts` (or create if needed), ensure the worker is included:

```typescript
// Add to vite config optimizeDeps if needed
optimizeDeps: {
  include: ['react-pdf'],
},
```

- [ ] **Step 4: Commit**

```bash
git add src/components/viewer/renderers/PdfRenderer.tsx
git commit -m "feat: add PdfRenderer with page navigation using react-pdf"
```

---

## Task 8: Create DocxRenderer, HwpRenderer

**Files:**
- Create: `src/components/viewer/renderers/DocxRenderer.tsx`
- Create: `src/components/viewer/renderers/HwpRenderer.tsx`

- [ ] **Step 1: Create DocxRenderer.tsx**

```tsx
import React, { useEffect, useRef, useState } from 'react';
import { renderAsync } from 'docx-preview';
import type { RendererProps } from './TextRenderer';

const DocxRenderer: React.FC<RendererProps> = ({ artifact, fileUrl }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!fileUrl || !containerRef.current) return;

    setLoading(true);
    fetch(fileUrl)
      .then(res => {
        if (!res.ok) throw new Error('Failed to fetch');
        return res.arrayBuffer();
      })
      .then(buffer => {
        if (!containerRef.current) return;
        return renderAsync(buffer, containerRef.current, undefined, {
          className: 'docx-preview',
          inWrapper: true,
        });
      })
      .then(() => setLoading(false))
      .catch(() => {
        setError(true);
        setLoading(false);
      });
  }, [fileUrl]);

  if (error || !fileUrl) {
    return (
      <div className="h-full overflow-auto p-6 custom-scrollbar">
        <pre className="text-on-surface-variant text-sm whitespace-pre-wrap">
          {artifact.preview || 'DOCX를 불러올 수 없습니다.'}
        </pre>
      </div>
    );
  }

  return (
    <div className="h-full overflow-auto custom-scrollbar bg-white">
      {loading && (
        <div className="flex items-center justify-center h-64">
          <div className="w-6 h-6 border-2 border-primary border-t-transparent rounded-full animate-spin" />
        </div>
      )}
      <div ref={containerRef} className={loading ? 'hidden' : ''} />
    </div>
  );
};

export default DocxRenderer;
```

- [ ] **Step 2: Create HwpRenderer.tsx**

```tsx
import React from 'react';
import { ExternalLink, FileText } from 'lucide-react';
import { apiClient } from '../../../lib/api-client';
import type { RendererProps } from './TextRenderer';

const HwpRenderer: React.FC<RendererProps> = ({ artifact }) => {
  const text = artifact.preview || '미리보기 내용이 없습니다.';
  const fileUrl = artifact.full_path ? apiClient.getFileUrl(artifact.full_path) : '';

  return (
    <div className="h-full flex flex-col">
      <div className="flex-1 overflow-auto p-6 md:p-10 custom-scrollbar">
        <div className="max-w-3xl mx-auto">
          <div className="flex items-center gap-3 mb-6 pb-4 border-b border-outline/10">
            <FileText size={20} className="text-primary" />
            <div>
              <h3 className="text-sm font-bold">{artifact.title}</h3>
              <p className="text-[10px] font-mono text-on-surface-variant uppercase">
                HWP 문서 — 텍스트 미리보기
              </p>
            </div>
          </div>
          <pre className="text-on-surface-variant text-sm leading-relaxed whitespace-pre-wrap font-sans">
            {text}
          </pre>
        </div>
      </div>
      {fileUrl && (
        <div className="flex items-center justify-center p-4 bg-surface-highest/30 border-t border-outline/10">
          <a
            href={fileUrl}
            download
            className="flex items-center gap-2 px-6 py-2 bg-primary text-on-primary font-bold text-xs hover:opacity-80 transition-all"
          >
            <ExternalLink size={14} />
            원본 파일 열기
          </a>
        </div>
      )}
    </div>
  );
};

export default HwpRenderer;
```

- [ ] **Step 3: Verify build**

Run: `npm run build`
Expected: Build succeeds

- [ ] **Step 4: Commit**

```bash
git add src/components/viewer/renderers/DocxRenderer.tsx \
        src/components/viewer/renderers/HwpRenderer.tsx
git commit -m "feat: add DocxRenderer (docx-preview) and HwpRenderer (text + download)"
```

---

## Task 9: Create PptxRenderer and XlsxRenderer

**Files:**
- Create: `src/components/viewer/renderers/PptxRenderer.tsx`
- Create: `src/components/viewer/renderers/XlsxRenderer.tsx`

- [ ] **Step 1: Install pptx-to-html**

```bash
cd /Users/codingstudio/__PROJECTHUB__/JARVIS/ProjectHub-terminal-architect
npm install @jvmr/pptx-to-html
```

- [ ] **Step 2: Create PptxRenderer.tsx**

```tsx
import React, { useEffect, useRef, useState } from 'react';
import DOMPurify from 'dompurify';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import type { RendererProps } from './TextRenderer';

const PptxRenderer: React.FC<RendererProps> = ({ artifact, fileUrl }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [slides, setSlides] = useState<string[]>([]);
  const [slideIndex, setSlideIndex] = useState(0);
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!fileUrl) return;

    setLoading(true);
    (async () => {
      try {
        const { default: pptxToHtml } = await import('@jvmr/pptx-to-html');
        const res = await fetch(fileUrl);
        if (!res.ok) throw new Error('Failed to fetch');
        const buffer = await res.arrayBuffer();
        const result = await pptxToHtml(new Uint8Array(buffer));
        // result may be a single HTML string or array of slide HTML strings
        const slideArray = Array.isArray(result) ? result : [result];
        // Sanitize each slide's HTML to prevent XSS
        const sanitizedSlides = slideArray.map(s => DOMPurify.sanitize(String(s)));
        setSlides(sanitizedSlides);
        setLoading(false);
      } catch {
        setError(true);
        setLoading(false);
      }
    })();
  }, [fileUrl]);

  if (error || !fileUrl) {
    return (
      <div className="h-full overflow-auto p-6 custom-scrollbar">
        <pre className="text-on-surface-variant text-sm whitespace-pre-wrap">
          {artifact.preview || 'PPTX를 불러올 수 없습니다.'}
        </pre>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col">
      <div className="flex-1 overflow-auto flex items-center justify-center bg-surface-low custom-scrollbar p-4">
        {loading ? (
          <div className="w-6 h-6 border-2 border-primary border-t-transparent rounded-full animate-spin" />
        ) : (
          <div
            ref={containerRef}
            className="bg-white shadow-lg max-w-4xl w-full p-8"
            dangerouslySetInnerHTML={{ __html: slides[slideIndex] || '' }}
          />
        )}
      </div>
      {slides.length > 1 && (
        <div className="flex items-center justify-center gap-4 p-3 bg-surface-highest/50 border-t border-outline/10">
          <button
            onClick={() => setSlideIndex(Math.max(0, slideIndex - 1))}
            disabled={slideIndex <= 0}
            className="p-1 hover:bg-surface-highest disabled:opacity-30 transition-colors"
          >
            <ChevronLeft size={18} />
          </button>
          <span className="font-mono text-xs text-on-surface-variant">
            슬라이드 {slideIndex + 1} / {slides.length}
          </span>
          <button
            onClick={() => setSlideIndex(Math.min(slides.length - 1, slideIndex + 1))}
            disabled={slideIndex >= slides.length - 1}
            className="p-1 hover:bg-surface-highest disabled:opacity-30 transition-colors"
          >
            <ChevronRight size={18} />
          </button>
        </div>
      )}
    </div>
  );
};

export default PptxRenderer;
```

- [ ] **Step 3: Create XlsxRenderer.tsx**

```tsx
import React, { useEffect, useState, useMemo } from 'react';
import * as XLSX from 'xlsx';
import DOMPurify from 'dompurify';
import type { RendererProps } from './TextRenderer';

interface SheetData {
  name: string;
  html: string;
}

const XlsxRenderer: React.FC<RendererProps> = ({ artifact, fileUrl }) => {
  const [sheets, setSheets] = useState<SheetData[]>([]);
  const [activeSheet, setActiveSheet] = useState(0);
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!fileUrl) return;

    setLoading(true);
    fetch(fileUrl)
      .then(res => {
        if (!res.ok) throw new Error('Failed to fetch');
        return res.arrayBuffer();
      })
      .then(buffer => {
        const wb = XLSX.read(buffer, { type: 'array' });
        const parsed: SheetData[] = wb.SheetNames.map(name => {
          const rawHtml = XLSX.utils.sheet_to_html(wb.Sheets[name]);
          return { name, html: DOMPurify.sanitize(rawHtml) };
        });
        setSheets(parsed);
        setLoading(false);
      })
      .catch(() => {
        setError(true);
        setLoading(false);
      });
  }, [fileUrl]);

  const currentHtml = useMemo(() => sheets[activeSheet]?.html || '', [sheets, activeSheet]);

  if (error || !fileUrl) {
    return (
      <div className="h-full overflow-auto p-6 custom-scrollbar">
        <pre className="text-on-surface-variant text-sm whitespace-pre-wrap">
          {artifact.preview || 'XLSX를 불러올 수 없습니다.'}
        </pre>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col">
      {sheets.length > 1 && (
        <div className="flex gap-0 bg-surface-highest border-b border-outline/10 overflow-x-auto">
          {sheets.map((s, i) => (
            <button
              key={s.name}
              onClick={() => setActiveSheet(i)}
              className={`px-4 py-2 text-xs font-mono border-b-2 transition-colors whitespace-nowrap ${
                i === activeSheet
                  ? 'border-primary text-primary'
                  : 'border-transparent text-on-surface-variant hover:text-on-surface'
              }`}
            >
              {s.name}
            </button>
          ))}
        </div>
      )}
      <div className="flex-1 overflow-auto custom-scrollbar bg-white text-black p-4">
        {loading ? (
          <div className="flex items-center justify-center h-64">
            <div className="w-6 h-6 border-2 border-primary border-t-transparent rounded-full animate-spin" />
          </div>
        ) : (
          <div
            className="xlsx-preview text-sm"
            dangerouslySetInnerHTML={{ __html: currentHtml }}
          />
        )}
      </div>
    </div>
  );
};

export default XlsxRenderer;
```

- [ ] **Step 4: Verify build**

Run: `npm run build`
Expected: Build succeeds

- [ ] **Step 5: Commit**

```bash
git add src/components/viewer/renderers/PptxRenderer.tsx \
        src/components/viewer/renderers/XlsxRenderer.tsx
git commit -m "feat: add PptxRenderer (@jvmr/pptx-to-html) and XlsxRenderer (SheetJS) with DOMPurify"
```

---

## Task 10: Create ViewerRouter

**Files:**
- Create: `src/components/viewer/ViewerRouter.tsx`

- [ ] **Step 1: Create ViewerRouter.tsx**

```tsx
import React, { Suspense } from 'react';
import type { Artifact } from '../../types';

export interface ViewerRouterProps {
  artifact: Artifact;
  fileUrl?: string;
  content?: string;
}

const TextRenderer = React.lazy(() => import('./renderers/TextRenderer'));
const CodeRenderer = React.lazy(() => import('./renderers/CodeRenderer'));
const ImageRenderer = React.lazy(() => import('./renderers/ImageRenderer'));
const VideoRenderer = React.lazy(() => import('./renderers/VideoRenderer'));
const HtmlRenderer = React.lazy(() => import('./renderers/HtmlRenderer'));
const WebRenderer = React.lazy(() => import('./renderers/WebRenderer'));
const PdfRenderer = React.lazy(() => import('./renderers/PdfRenderer'));
const DocxRenderer = React.lazy(() => import('./renderers/DocxRenderer'));
const PptxRenderer = React.lazy(() => import('./renderers/PptxRenderer'));
const XlsxRenderer = React.lazy(() => import('./renderers/XlsxRenderer'));
const HwpRenderer = React.lazy(() => import('./renderers/HwpRenderer'));

function getExtension(path: string): string {
  return (path.split('.').pop() || '').toLowerCase();
}

function selectRenderer(viewerKind: string, path: string) {
  switch (viewerKind) {
    case 'image':
      return ImageRenderer;
    case 'video':
      return VideoRenderer;
    case 'code':
      return CodeRenderer;
    case 'html':
      return HtmlRenderer;
    case 'web':
      return WebRenderer;
    case 'document': {
      const ext = getExtension(path);
      if (ext === 'pdf') return PdfRenderer;
      if (ext === 'docx') return DocxRenderer;
      if (ext === 'pptx') return PptxRenderer;
      if (ext === 'xlsx' || ext === 'xls') return XlsxRenderer;
      if (ext === 'hwp' || ext === 'hwpx') return HwpRenderer;
      return TextRenderer;
    }
    case 'text':
    default:
      return TextRenderer;
  }
}

const LoadingSpinner = () => (
  <div className="h-full flex items-center justify-center">
    <div className="w-6 h-6 border-2 border-primary border-t-transparent rounded-full animate-spin" />
  </div>
);

export const ViewerRouter: React.FC<ViewerRouterProps> = ({ artifact, fileUrl, content }) => {
  const Renderer = selectRenderer(
    artifact.viewer_kind || 'text',
    artifact.path || artifact.full_path || '',
  );

  return (
    <Suspense fallback={<LoadingSpinner />}>
      <Renderer artifact={artifact} fileUrl={fileUrl} content={content} />
    </Suspense>
  );
};
```

- [ ] **Step 2: Verify build**

Run: `npm run build`
Expected: Build succeeds

- [ ] **Step 3: Commit**

```bash
git add src/components/viewer/ViewerRouter.tsx
git commit -m "feat: add ViewerRouter with lazy-loaded renderer selection"
```

---

## Task 11: Create ViewerShell

**Files:**
- Create: `src/components/viewer/ViewerShell.tsx`

- [ ] **Step 1: Create ViewerShell.tsx**

```tsx
import React, { useState } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { Download, Share2, Printer, Info } from 'lucide-react';
import { cn } from '../../lib/utils';
import { apiClient } from '../../lib/api-client';
import { ViewerRouter } from './ViewerRouter';
import type { Artifact, Citation } from '../../types';

interface ViewerShellProps {
  artifact: Artifact;
  citations: Citation[];
  onBack: () => void;
  isMobile: boolean;
}

export const ViewerShell: React.FC<ViewerShellProps> = ({
  artifact,
  citations,
  onBack,
  isMobile,
}) => {
  const [isSidebarOpen, setIsSidebarOpen] = useState(!isMobile);

  const fileUrl = artifact.full_path
    ? apiClient.getFileUrl(artifact.full_path)
    : undefined;

  return (
    <motion.div
      key="viewer"
      initial={{ opacity: 0, x: 20 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: -20 }}
      className="h-full flex flex-col overflow-hidden"
    >
      {/* Header */}
      <div className="px-4 md:px-10 pt-6 bg-surface-low shrink-0">
        <nav className="flex items-center gap-2 text-[10px] font-mono uppercase tracking-widest text-on-surface-variant mb-4">
          <button onClick={onBack} className="hover:text-primary transition-colors">
            대시보드
          </button>
          <span>/</span>
          <button onClick={onBack} className="hover:text-primary transition-colors">
            자산
          </button>
          <span>/</span>
          <span className="text-primary-dim">{artifact.title}</span>
        </nav>
        <div className="flex flex-col md:flex-row md:justify-between md:items-center pb-6 gap-4">
          <div>
            <h1 className="text-lg md:text-xl font-bold tracking-tight text-primary-dim font-headline">
              {artifact.title}
            </h1>
            <p className="text-on-surface-variant text-[10px] font-mono uppercase tracking-widest mt-1">
              {artifact.path || artifact.source_type || ''}
            </p>
          </div>
          <div className="flex flex-wrap gap-2 md:gap-3">
            <button
              onClick={() => setIsSidebarOpen(!isSidebarOpen)}
              className={cn(
                "flex-1 md:flex-none px-3 md:px-5 py-2 border border-outline transition-all text-[10px] md:text-xs flex items-center justify-center gap-2",
                isSidebarOpen
                  ? "bg-primary/10 text-primary border-primary"
                  : "text-on-surface-variant hover:text-white hover:bg-surface-highest"
              )}
            >
              <Info size={14} /> {isSidebarOpen ? '정보_숨기기' : '정보_보기'}
            </button>
            <button className="flex-1 md:flex-none px-3 md:px-5 py-2 border border-outline text-on-surface-variant hover:text-white hover:bg-surface-highest transition-all text-[10px] md:text-xs flex items-center justify-center gap-2">
              <Share2 size={14} /> 공유
            </button>
            <button className="flex-1 md:flex-none px-3 md:px-5 py-2 border border-outline text-on-surface-variant hover:text-white hover:bg-surface-highest transition-all text-[10px] md:text-xs flex items-center justify-center gap-2">
              <Printer size={14} /> 인쇄
            </button>
            {fileUrl && (
              <a
                href={fileUrl}
                download
                className="w-full md:w-auto px-4 md:px-6 py-2 bg-primary text-on-primary font-bold hover:opacity-80 transition-all text-[10px] md:text-xs flex items-center justify-center gap-2"
              >
                <Download size={14} /> 다운로드
              </a>
            )}
          </div>
        </div>
      </div>

      {/* Content + Sidebar */}
      <div className="flex-1 flex flex-col md:flex-row overflow-hidden">
        <section className="flex-1 overflow-hidden">
          <ViewerRouter
            artifact={artifact}
            fileUrl={fileUrl}
            content={artifact.preview}
          />
        </section>

        <AnimatePresence>
          {isSidebarOpen && (
            <motion.aside
              initial={isMobile ? { height: 0, opacity: 0 } : { width: 0, opacity: 0 }}
              animate={isMobile ? { height: 'auto', opacity: 1 } : { width: 320, opacity: 1 }}
              exit={isMobile ? { height: 0, opacity: 0 } : { width: 0, opacity: 0 }}
              className="w-full md:w-80 bg-surface-low border-t md:border-t-0 md:border-l border-outline/10 shrink-0 overflow-hidden"
            >
              <div className="p-6 md:p-8 h-full overflow-y-auto custom-scrollbar">
                <h4 className="text-primary text-xs font-mono mb-6 uppercase tracking-widest">
                  문서 정보
                </h4>
                <div className="space-y-6 mb-10">
                  <div>
                    <p className="text-xs text-on-surface-variant uppercase mb-1">문서 유형</p>
                    <p className="text-sm font-mono text-on-surface uppercase">
                      {artifact.source_type || '-'}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs text-on-surface-variant uppercase mb-1">뷰어 종류</p>
                    <p className="text-sm font-mono text-on-surface uppercase">
                      {artifact.viewer_kind || '-'}
                    </p>
                  </div>
                  {artifact.path && (
                    <div>
                      <p className="text-xs text-on-surface-variant uppercase mb-1">경로</p>
                      <p className="text-xs font-mono text-on-surface break-all">
                        {artifact.path}
                      </p>
                    </div>
                  )}
                  {artifact.subtitle && (
                    <div>
                      <p className="text-xs text-on-surface-variant uppercase mb-1">설명</p>
                      <p className="text-xs text-on-surface">{artifact.subtitle}</p>
                    </div>
                  )}
                </div>

                {citations.length > 0 && (
                  <div>
                    <h4 className="text-primary text-xs font-mono mb-4 uppercase tracking-widest">
                      관련 근거
                    </h4>
                    <div className="space-y-3">
                      {citations.slice(0, 5).map((c, i) => (
                        <div
                          key={i}
                          className="bg-surface-high/50 border border-outline/10 p-3"
                        >
                          <p className="text-[10px] font-mono text-primary mb-1">[{c.label}]</p>
                          <p className="text-xs text-on-surface-variant line-clamp-3">
                            {c.quote}
                          </p>
                          <p className="text-[10px] font-mono text-outline mt-1">
                            {c.source_path}
                          </p>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </motion.aside>
          )}
        </AnimatePresence>
      </div>
    </motion.div>
  );
};
```

- [ ] **Step 2: Verify build**

Run: `npm run build`
Expected: Build succeeds

- [ ] **Step 3: Commit**

```bash
git add src/components/viewer/ViewerShell.tsx
git commit -m "feat: add ViewerShell with toolbar, metadata sidebar, and ViewerRouter integration"
```

---

## Task 12: Refactor App.tsx — replace detail views with ViewerShell

**Files:**
- Modify: `src/App.tsx`

- [ ] **Step 1: Add ViewerShell import**

At the top of `App.tsx`, add:

```typescript
import { ViewerShell } from './components/viewer/ViewerShell';
```

Remove unused imports that were only used by detail views: `Sparkles`, `CheckCircle2`, `Smartphone`, `Monitor`, `ShieldCheck`, `ZoomIn`, `ZoomOut`, `Maximize2`, `Code`, `ArrowLeft`. Keep any that are still used elsewhere in the file — check before removing.

- [ ] **Step 2: Replace the three detail views with ViewerShell**

Find the section starting with `) : view === 'detail_report' ? (` and ending before `) : view === 'admin' ? (`. This includes `detail_report`, `detail_image`, and `detail_code` views (~360 lines). Replace all of it with:

```tsx
) : view === 'detail_viewer' ? (
  selectedArtifact ? (
    <ViewerShell
      artifact={selectedArtifact}
      citations={citations}
      onBack={() => setView('dashboard')}
      isMobile={isMobile}
    />
  ) : (
    <div className="h-full flex items-center justify-center text-on-surface-variant">
      <p>선택된 문서가 없습니다.</p>
    </div>
  )
) : view === 'repository' ? (
  <motion.div
    key="repository"
    initial={{ opacity: 0 }}
    animate={{ opacity: 1 }}
    exit={{ opacity: 0 }}
    className="h-full flex items-center justify-center text-on-surface-variant"
  >
    <div className="text-center space-y-4">
      <FolderOpen size={48} className="mx-auto opacity-30" />
      <p className="text-sm">저장소 탐색기 (준비 중)</p>
    </div>
  </motion.div>
```

- [ ] **Step 3: Remove isContextSummaryOpen state if no longer used**

Check if `isContextSummaryOpen` is still used anywhere after removing the detail views. If only used in deleted code, remove the state declaration:

```typescript
// Remove this line if unused:
const [isContextSummaryOpen, setIsContextSummaryOpen] = useState(true);
```

- [ ] **Step 4: Verify build**

Run: `npm run build`
Expected: Build succeeds with no errors

- [ ] **Step 5: Verify the app loads in browser**

Run: `npm run dev`
Open: http://localhost:3000
Expected:
- Dashboard loads normally
- Sidebar buttons show correct active states
- 저장소 button shows placeholder view
- 자산 button activates when a document was previously selected

- [ ] **Step 6: Commit**

```bash
git add src/App.tsx
git commit -m "refactor: replace 3 hardcoded detail views with unified ViewerShell component"
```

---

## Task 13: Add backend /api/file endpoint

**Files:**
- Modify: `alliance_20260317_130542/src/jarvis/web_api.py`

- [ ] **Step 1: Add file serving endpoint to web_api.py**

Add imports at the top of the file:

```python
import mimetypes
from pathlib import Path

from fastapi.responses import FileResponse
```

Add the endpoint after the `/api/runtime-state` endpoint (before the WebSocket endpoint):

```python
@app.get("/api/file")
async def serve_file(path: str):
    """Serve a file from allowed directories.

    Uses the same path validation as ReadFileTool to prevent
    unauthorized file access.
    """
    file_path = Path(path).expanduser().resolve()

    # Security: reject path traversal
    if ".." in str(path):
        raise HTTPException(status_code=403, detail="Path traversal not allowed")

    # Security: validate against allowed roots (watched_folders from config)
    allowed_roots = []
    if hasattr(service, '_ctx') and service._ctx and service._ctx.knowledge_base_path:
        allowed_roots.append(service._ctx.knowledge_base_path)
    else:
        # Fallback: try to resolve knowledge base path
        from jarvis.app.runtime_context import resolve_knowledge_base_path
        try:
            kb_path = resolve_knowledge_base_path()
            allowed_roots.append(kb_path)
        except Exception:
            pass

    if not allowed_roots:
        raise HTTPException(status_code=403, detail="No allowed directories configured")

    # Check that resolved path is within an allowed root
    is_allowed = False
    for root in allowed_roots:
        try:
            resolved_root = root.expanduser().resolve()
            file_path.relative_to(resolved_root)
            is_allowed = True
            break
        except ValueError:
            continue

    if not is_allowed:
        raise HTTPException(status_code=403, detail="Path outside allowed scope")

    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    # Determine content type
    content_type, _ = mimetypes.guess_type(str(file_path))
    if content_type is None:
        content_type = "application/octet-stream"

    return FileResponse(
        path=str(file_path),
        media_type=content_type,
        filename=file_path.name,
    )
```

- [ ] **Step 2: Add Vite dev server port to CORS origins**

In the CORS middleware config, ensure port 3000 is listed (already present — verify):

```python
allow_origins=[
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://0.0.0.0:3000",
],
```

- [ ] **Step 3: Commit**

```bash
cd /Users/codingstudio/__PROJECTHUB__/JARVIS/alliance_20260317_130542
git add src/jarvis/web_api.py
git commit -m "feat: add /api/file endpoint for serving files to web viewer"
```

---

## Task 14: End-to-end verification

- [ ] **Step 1: Start JARVIS backend**

Ensure the JARVIS backend is running on port 8000.

- [ ] **Step 2: Start frontend dev server**

```bash
cd /Users/codingstudio/__PROJECTHUB__/JARVIS/ProjectHub-terminal-architect
npm run dev
```

- [ ] **Step 3: Test search → viewer flow**

1. Open http://localhost:3000
2. Enter a search query in the chat
3. Click on a document in the results
4. Verify:
   - Sidebar "자산" button is highlighted
   - ViewerShell shows with correct title, breadcrumb, toolbar
   - Appropriate renderer loads based on file type
   - Metadata sidebar shows artifact info and citations
   - Download button works

- [ ] **Step 4: Test sidebar navigation**

1. Click "터미널" → dashboard view, button highlighted
2. Click "저장소" → placeholder view, button highlighted
3. Click "자산" → last viewed document, button highlighted
4. Click "관리자" → admin view, button highlighted

- [ ] **Step 5: Test fallback behavior**

1. If backend is offline, viewers should show preview text fallback
2. Unknown file types should show TextRenderer

- [ ] **Step 6: Final commit if any fixes needed**

```bash
git add -A
git commit -m "fix: end-to-end viewer integration fixes"
```
