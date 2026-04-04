# Repository vs Documents Separation Design

**Date**: 2026-04-05
**Status**: Approved
**Approach**: Cursor/GitHub Model — File Tree + AI Search Separation

## Problem

The current web interface conflates Repository (file browsing) and Documents (document viewing). Both views use the same `Artifact[]` data model from AI search results. There is no way to browse the actual file system — all file discovery is query-driven via `/api/ask`. The `Documents` tab is just a flat list view of the same data the `Repository` tab shows as a tree.

## Solution

Adopt the Cursor/GitHub pattern: a real file tree for browsing + AI search in Terminal, both converging on the same Viewer.

### Core Changes

1. **Remove Documents tab** — Repository handles file browsing + viewing
2. **New API `GET /api/browse`** — returns actual directory structure from knowledge_base
3. **Separate data models** — `FileNode` (real files) vs `Artifact`/`Citation` (AI responses only)

## Architecture

### ViewState

```typescript
// Before: 6 states
type ViewState = 'home' | 'terminal' | 'repository' | 'detail_viewer' | 'skills' | 'admin';

// After: 5 states (detail_viewer removed)
type ViewState = 'home' | 'terminal' | 'repository' | 'skills' | 'admin';
```

### Repository Tab Layout

```
┌───────────┬──────────────────────────────────────────┐
│ File Tree │  Viewer (file content)                    │
│           │                                          │
│ 📁 coding │  breadcrumb: coding / pipeline.py        │
│   📄 pipe…│  ┌──────────────────────────────────┐    │
│   📄 Proj…│  │ import os                        │    │
│ 📁 HTML   │  │ import sys                       │    │
│ 📁 shell  │  │                                  │    │
│ 📁 sql    │  │ def run_pipeline():              │    │
│ 📄 14day… │  │     ...                          │    │
│ 📄 씨샵.… │  └──────────────────────────────────┘    │
│ 📄 한글…  │                                          │
└───────────┴──────────────────────────────────────────┘
```

- **Left panel**: Directory tree with lazy-loaded folders
- **Right panel**: Selected file rendered via existing ViewerShell/ViewerRouter
- File not selected: empty state message

### Two Entry Paths to Viewer

| Entry | Flow | Result |
|-------|------|--------|
| **Repository file tree** | Click file | File highlighted in tree, Viewer opens |
| **Terminal AI answer** | Click citation | Switch to Repository tab, auto-expand tree to file, Viewer opens |

## Data Models

### New: FileNode (real file system)

```typescript
interface FileNode {
  name: string;           // "pipeline.py"
  path: string;           // "coding/pipeline.py" (relative to knowledge_base)
  type: 'file' | 'directory';
  extension?: string;     // ".py"
  size?: number;
  children?: FileNode[];  // directory only
}
```

### Existing: Artifact & Citation (unchanged, Terminal-only)

`Artifact` and `Citation` remain as-is, used exclusively by Terminal workspace for AI responses.

## API

### New: GET /api/browse

```
GET /api/browse?path=         → root directory listing
GET /api/browse?path=coding   → subdirectory listing
```

Response:
```json
{
  "path": "coding",
  "entries": [
    { "name": "pipeline.py", "path": "coding/pipeline.py", "type": "file", "extension": ".py", "size": 2048 },
    { "name": "ProjectHubApp.swift", "path": "coding/ProjectHubApp.swift", "type": "file", "extension": ".swift", "size": 4096 }
  ]
}
```

Security: validate resolved path is within knowledge_base root (same pattern as `/api/file`).

### Existing: GET /api/file (unchanged)

Serves file content. Used by Viewer to load selected files.

## Component Structure

```
App.tsx
├── Sidebar (5 tabs: home, terminal, repository, skills, admin)
├── TerminalWorkspace
│   └── citation click → navigateToFile(path)
└── RepositoryWorkspace (replaces RepositoryExplorer)
    ├── FileTreePanel
    │   ├── SearchBar (local filename filter, not AI)
    │   └── TreeView (recursive folder/file rendering)
    └── FileViewerPanel
        ├── Breadcrumb (clickable path segments)
        └── ViewerShell (existing viewer reused)
```

### RepositoryWorkspace

- Props: `initialPath?: string` (for Terminal → Repository navigation)
- On mount: loads root directory via `GET /api/browse`
- On `initialPath` change: auto-expands tree to that file and selects it

### FileTreePanel

- Lazy loading: folders load children on first expand
- Cache: loaded directories stored in `fileTreeCache`, no re-fetching
- Icons: extension-based file type icons
- Highlight: current selected file visually marked
- SearchBar: filters already-loaded tree nodes by filename substring

### FileViewerPanel

- Breadcrumb: `knowledge_base / coding / pipeline.py` with clickable segments
- Converts `FileNode` → `Artifact` for ViewerShell compatibility
- Reuses all existing renderers (HwpRenderer, PptxRenderer, TextRenderer, etc.)

### Terminal → Repository Navigation

```typescript
// In App.tsx
function navigateToFile(path: string) {
  setRepositoryInitialPath(path);
  setCurrentView('repository');
}

// TerminalWorkspace passes this via prop
<CitationItem onClick={() => navigateToFile(citation.source_path)} />
```

## Store Changes

```typescript
interface AppState {
  // Existing (Terminal - unchanged)
  messages: Message[];
  assets: Artifact[];
  citations: Citation[];

  // New (Repository)
  fileTree: FileNode[];
  fileTreeCache: Record<string, FileNode[]>;
  selectedFilePath: string | null;
  expandedDirs: string[];
}
```

## Error Handling

| Scenario | Handling |
|----------|----------|
| `/api/browse` fails | "디렉토리를 불러올 수 없습니다" + retry button |
| `/api/file` fails | "파일을 열 수 없습니다" in viewer area |
| Empty directory | "빈 폴더" in tree |
| No knowledge_base | "Knowledge Base가 설정되지 않았습니다" fullscreen message |
| Terminal nav to missing file | Show tree, toast "파일을 찾을 수 없습니다" |

## Test Strategy

### Backend (`/api/browse`)
- Root directory listing returns entries
- Subdirectory listing returns correct children
- Non-existent path → 404
- Path traversal attempt (`../etc/passwd`) → 403
- Empty directory → empty entries array

### Frontend
- FileTreePanel: folder expand/collapse
- File click → ViewerPanel shows content
- Terminal citation click → Repository tab switch + file selected
- SearchBar filtering within loaded tree

## Files to Change

| File | Change |
|------|--------|
| `web_api.py` | Add `/api/browse` endpoint |
| `types.ts` | Add `FileNode`, remove `detail_viewer` from ViewState |
| `api-client.ts` | Add `browse(path)` method |
| `app-store.ts` | Add repository state fields |
| `App.tsx` | Remove Documents tab, add `navigateToFile()`, wire RepositoryWorkspace |
| `RepositoryExplorer.tsx` → `RepositoryWorkspace.tsx` | Full rewrite |
| `TerminalWorkspace.tsx` | Citation click calls `navigateToFile()` |
| `ViewerShell.tsx` | Clean up props for Repository context usage |
| New: `FileTreePanel.tsx` | Directory tree component |

## Not Changing

- Existing viewer renderers (Hwp, Pptx, Text, etc.)
- Terminal workspace AI conversation logic
- Skills, Admin workspaces
- `/api/ask`, `/api/file` endpoints
