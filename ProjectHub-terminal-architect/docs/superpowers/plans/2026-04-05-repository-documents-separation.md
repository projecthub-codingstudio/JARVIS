# Repository vs Documents Separation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the conflated Repository/Documents tabs with a real file-tree browser backed by a new `/api/browse` endpoint, and connect Terminal citations to navigate into the file tree.

**Architecture:** New `GET /api/browse` returns directory listings from knowledge_base. Frontend replaces `RepositoryExplorer` + `ViewerShell` (detail_viewer) with a unified `RepositoryWorkspace` containing `FileTreePanel` + embedded `ViewerShell`. Terminal citations link into Repository via `navigateToFile()`.

**Tech Stack:** FastAPI (backend), React + Zustand + Tailwind (frontend), existing ViewerShell/ViewerRouter renderers.

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `alliance_20260317_130542/src/jarvis/web_api.py` | Modify | Add `GET /api/browse` endpoint |
| `src/types.ts` | Modify | Add `FileNode`, `BrowseResponse`; remove `detail_viewer` from `ViewState` |
| `src/lib/api-client.ts` | Modify | Add `browse(path)` method |
| `src/store/app-store.ts` | Modify | Add repository state fields |
| `src/components/repository/FileTreePanel.tsx` | Create | Directory tree component |
| `src/components/repository/RepositoryWorkspace.tsx` | Create | File tree + viewer layout |
| `src/components/repository/RepositoryExplorer.tsx` | Delete | Replaced by RepositoryWorkspace |
| `src/App.tsx` | Modify | Remove Documents tab, wire RepositoryWorkspace + navigateToFile |
| `src/components/workspaces/TerminalWorkspace.tsx` | Modify | Citation click calls navigateToFile |
| `src/components/viewer/ViewerShell.tsx` | Modify | Accept optional FileNode-based props |

---

## Task 1: Backend — `GET /api/browse` endpoint

**Files:**
- Modify: `alliance_20260317_130542/src/jarvis/web_api.py` (after line 228, before the `/api/file` endpoint)

- [ ] **Step 1: Add the browse endpoint**

Add this code after the `PUT /api/action-maps/{map_id}` endpoint (line 228) in `web_api.py`:

```python
class BrowseEntry(BaseModel):
    name: str
    path: str
    type: str  # "file" or "directory"
    extension: str | None = None
    size: int | None = None


class BrowseResponse(BaseModel):
    path: str
    entries: list[BrowseEntry]


@app.get("/api/browse", response_model=BrowseResponse)
async def browse_directory(path: str = ""):
    """List directory contents within the knowledge base."""
    kb_root = _resolve_kb_root()
    if kb_root is None:
        raise HTTPException(status_code=500, detail="Knowledge base path not configured")

    target = (kb_root / path).resolve()

    # Security: ensure path is within knowledge base
    try:
        target.relative_to(kb_root.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied: path outside knowledge base")

    if not target.exists():
        raise HTTPException(status_code=404, detail=f"Path not found: {path}")

    if not target.is_dir():
        raise HTTPException(status_code=400, detail=f"Not a directory: {path}")

    entries: list[BrowseEntry] = []
    for item in sorted(target.iterdir(), key=lambda p: (p.is_file(), p.name.lower())):
        if item.name.startswith("."):
            continue
        rel_path = str(item.relative_to(kb_root.resolve()))
        if item.is_dir():
            entries.append(BrowseEntry(name=item.name, path=rel_path, type="directory"))
        else:
            stat = item.stat()
            entries.append(BrowseEntry(
                name=item.name,
                path=rel_path,
                type="file",
                extension=item.suffix.lower() if item.suffix else None,
                size=stat.st_size,
            ))

    return BrowseResponse(path=path, entries=entries)
```

- [ ] **Step 2: Extract `_resolve_kb_root` helper**

The `/api/file` endpoint (line 231+) already resolves the knowledge base root. Extract that logic into a shared helper placed above both endpoints:

```python
def _resolve_kb_root() -> Path | None:
    """Resolve knowledge base root path."""
    kb_env = os.environ.get("JARVIS_KNOWLEDGE_BASE")
    if kb_env:
        p = Path(kb_env)
        if p.is_dir():
            return p
    from jarvis.app.runtime_context import resolve_knowledge_base_path
    return resolve_knowledge_base_path()
```

Update the existing `/api/file` endpoint to use `_resolve_kb_root()` instead of its inline resolution logic.

- [ ] **Step 3: Verify manually**

```bash
cd /Users/codingstudio/__PROJECTHUB__/JARVIS/alliance_20260317_130542
python -m jarvis.web_api &
# In another terminal:
curl -s "http://localhost:8000/api/browse" | python -m json.tool
curl -s "http://localhost:8000/api/browse?path=coding" | python -m json.tool
curl -s "http://localhost:8000/api/browse?path=../etc" -w "%{http_code}"  # expect 403
curl -s "http://localhost:8000/api/browse?path=nonexistent" -w "%{http_code}"  # expect 404
```

- [ ] **Step 4: Commit**

```bash
git add alliance_20260317_130542/src/jarvis/web_api.py
git commit -m "feat(api): add GET /api/browse endpoint for directory listing"
```

---

## Task 2: Frontend types — `FileNode`, `BrowseResponse`, `ViewState`

**Files:**
- Modify: `src/types.ts`

- [ ] **Step 1: Add FileNode and BrowseResponse types**

Add at the end of `src/types.ts` (after line 311):

```typescript
/* ── Repository file tree ── */

export interface FileNode {
  name: string;
  path: string;
  type: 'file' | 'directory';
  extension?: string | null;
  size?: number | null;
}

export interface BrowseResponse {
  path: string;
  entries: FileNode[];
}
```

- [ ] **Step 2: Update ViewState**

Replace the ViewState type (line 310):

```typescript
// Before:
export type ViewState = 'home' | 'terminal' | 'detail_viewer' | 'repository' | 'skills' | 'admin';

// After:
export type ViewState = 'home' | 'terminal' | 'repository' | 'skills' | 'admin';
```

- [ ] **Step 3: Commit**

```bash
git add src/types.ts
git commit -m "feat(types): add FileNode/BrowseResponse, remove detail_viewer from ViewState"
```

---

## Task 3: API client — `browse()` method

**Files:**
- Modify: `src/lib/api-client.ts`

- [ ] **Step 1: Add import for BrowseResponse**

Update the import at the top of `api-client.ts` (line 1-17) to include `BrowseResponse`:

```typescript
import type { BrowseResponse } from '../types';
```

(Add `BrowseResponse` to the existing import statement from `'../types'`.)

- [ ] **Step 2: Add browse method**

Add after the `getFileUrl` method (line 196):

```typescript
  async browse(path: string = ''): Promise<BrowseResponse> {
    const res = await fetch(`${API_BASE_URL}/api/browse?path=${encodeURIComponent(path)}`);
    if (!res.ok) {
      throw new Error(`Browse failed: ${res.status} ${res.statusText}`);
    }
    return res.json();
  },
```

- [ ] **Step 3: Commit**

```bash
git add src/lib/api-client.ts
git commit -m "feat(api-client): add browse() method for directory listing"
```

---

## Task 4: Store — repository state

**Files:**
- Modify: `src/store/app-store.ts`

- [ ] **Step 1: Add repository state and actions**

Add to the state interface (after `hasEvidence` at line 17):

```typescript
  // Repository
  fileTree: FileNode[];
  fileTreeCache: Record<string, FileNode[]>;
  selectedFilePath: string | null;
  expandedDirs: string[];
```

Add to the actions interface (after `addLog` at line 30):

```typescript
  // Repository
  setFileTree: (entries: FileNode[]) => void;
  cacheDirectory: (path: string, entries: FileNode[]) => void;
  setSelectedFilePath: (path: string | null) => void;
  toggleExpandedDir: (path: string) => void;
  expandToPath: (filePath: string) => void;
```

Add the import for `FileNode` at the top:

```typescript
import type { FileNode } from '../types';
```

Add initial state values in the create() call:

```typescript
  fileTree: [],
  fileTreeCache: {},
  selectedFilePath: null,
  expandedDirs: [],
```

Add action implementations:

```typescript
  setFileTree: (entries) => set({ fileTree: entries }),
  cacheDirectory: (path, entries) =>
    set((state) => ({
      fileTreeCache: { ...state.fileTreeCache, [path]: entries },
    })),
  setSelectedFilePath: (path) => set({ selectedFilePath: path }),
  toggleExpandedDir: (path) =>
    set((state) => {
      const dirs = state.expandedDirs.includes(path)
        ? state.expandedDirs.filter((d) => d !== path)
        : [...state.expandedDirs, path];
      return { expandedDirs: dirs };
    }),
  expandToPath: (filePath) =>
    set((state) => {
      const parts = filePath.split('/');
      const dirs: string[] = [];
      for (let i = 1; i < parts.length; i++) {
        dirs.push(parts.slice(0, i).join('/'));
      }
      const merged = [...new Set([...state.expandedDirs, ...dirs])];
      return { expandedDirs: merged, selectedFilePath: filePath };
    }),
```

- [ ] **Step 2: Commit**

```bash
git add src/store/app-store.ts
git commit -m "feat(store): add repository file tree state and actions"
```

---

## Task 5: FileTreePanel component

**Files:**
- Create: `src/components/repository/FileTreePanel.tsx`

- [ ] **Step 1: Create the component**

```tsx
/**
 * FileTreePanel — Directory tree for knowledge_base browsing
 */

import React, { useCallback, useEffect } from 'react';
import {
  ChevronRight,
  ChevronDown,
  Folder,
  FolderOpen,
  FileText,
  FileCode,
  FileSpreadsheet,
  FileImage,
  File,
} from 'lucide-react';
import { cn } from '../../lib/utils';
import { useAppStore } from '../../store/app-store';
import { apiClient } from '../../lib/api-client';
import type { FileNode } from '../../types';

/* ── Icon by extension ── */

function fileIcon(ext?: string | null) {
  switch (ext) {
    case '.py': case '.ts': case '.tsx': case '.js': case '.jsx':
    case '.swift': case '.java': case '.go': case '.rs':
    case '.c': case '.cpp': case '.h': case '.sql': case '.sh':
      return FileCode;
    case '.xlsx': case '.csv': case '.tsv':
      return FileSpreadsheet;
    case '.png': case '.jpg': case '.jpeg': case '.gif': case '.svg': case '.webp':
      return FileImage;
    case '.pdf': case '.md': case '.txt': case '.docx':
    case '.pptx': case '.hwp': case '.hwpx': case '.html':
      return FileText;
    default:
      return File;
  }
}

/* ── Single tree node ── */

interface TreeNodeProps {
  node: FileNode;
  depth: number;
  selectedPath: string | null;
  expandedDirs: string[];
  childrenMap: Record<string, FileNode[]>;
  onSelectFile: (node: FileNode) => void;
  onToggleDir: (path: string) => void;
}

function TreeNode({
  node,
  depth,
  selectedPath,
  expandedDirs,
  childrenMap,
  onSelectFile,
  onToggleDir,
}: TreeNodeProps) {
  const isDir = node.type === 'directory';
  const isExpanded = expandedDirs.includes(node.path);
  const isSelected = selectedPath === node.path;
  const children = childrenMap[node.path];
  const Icon = isDir ? (isExpanded ? FolderOpen : Folder) : fileIcon(node.extension);

  return (
    <div>
      <button
        className={cn(
          'flex w-full items-center gap-1.5 rounded-md px-2 py-1 text-left text-sm transition-colors',
          'hover:bg-white/5',
          isSelected && 'bg-white/10 text-white font-medium',
          !isSelected && 'text-white/70',
        )}
        style={{ paddingLeft: `${depth * 16 + 8}px` }}
        onClick={() => (isDir ? onToggleDir(node.path) : onSelectFile(node))}
      >
        {isDir ? (
          isExpanded ? (
            <ChevronDown className="h-3.5 w-3.5 shrink-0 text-white/40" />
          ) : (
            <ChevronRight className="h-3.5 w-3.5 shrink-0 text-white/40" />
          )
        ) : (
          <span className="w-3.5" />
        )}
        <Icon className="h-4 w-4 shrink-0 text-white/50" />
        <span className="truncate">{node.name}</span>
      </button>

      {isDir && isExpanded && children && (
        <div>
          {children.map((child) => (
            <TreeNode
              key={child.path}
              node={child}
              depth={depth + 1}
              selectedPath={selectedPath}
              expandedDirs={expandedDirs}
              childrenMap={childrenMap}
              onSelectFile={onSelectFile}
              onToggleDir={onToggleDir}
            />
          ))}
        </div>
      )}

      {isDir && isExpanded && !children && (
        <div
          className="text-xs text-white/30 italic"
          style={{ paddingLeft: `${(depth + 1) * 16 + 8}px` }}
        >
          불러오는 중...
        </div>
      )}
    </div>
  );
}

/* ── FileTreePanel ── */

interface FileTreePanelProps {
  onSelectFile: (node: FileNode) => void;
}

export function FileTreePanel({ onSelectFile }: FileTreePanelProps) {
  const fileTree = useAppStore((s) => s.fileTree);
  const fileTreeCache = useAppStore((s) => s.fileTreeCache);
  const selectedFilePath = useAppStore((s) => s.selectedFilePath);
  const expandedDirs = useAppStore((s) => s.expandedDirs);
  const setFileTree = useAppStore((s) => s.setFileTree);
  const cacheDirectory = useAppStore((s) => s.cacheDirectory);
  const toggleExpandedDir = useAppStore((s) => s.toggleExpandedDir);

  // Load root on mount
  useEffect(() => {
    if (fileTree.length > 0) return;
    apiClient.browse('').then((res) => {
      setFileTree(res.entries);
      cacheDirectory('', res.entries);
    });
  }, [fileTree.length, setFileTree, cacheDirectory]);

  const handleToggleDir = useCallback(
    async (path: string) => {
      toggleExpandedDir(path);
      // Lazy load children if not cached
      if (!fileTreeCache[path]) {
        const res = await apiClient.browse(path);
        cacheDirectory(path, res.entries);
      }
    },
    [toggleExpandedDir, fileTreeCache, cacheDirectory],
  );

  // Build childrenMap: root entries + all cached subdirectories
  const childrenMap: Record<string, FileNode[]> = { '': fileTree, ...fileTreeCache };

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <div className="border-b border-white/10 px-3 py-2">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-white/50">
          Knowledge Base
        </h3>
      </div>
      <div className="flex-1 overflow-y-auto p-1">
        {fileTree.length === 0 ? (
          <div className="p-4 text-center text-sm text-white/30">불러오는 중...</div>
        ) : (
          fileTree.map((node) => (
            <TreeNode
              key={node.path}
              node={node}
              depth={0}
              selectedPath={selectedFilePath}
              expandedDirs={expandedDirs}
              childrenMap={childrenMap}
              onSelectFile={onSelectFile}
              onToggleDir={handleToggleDir}
            />
          ))
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add src/components/repository/FileTreePanel.tsx
git commit -m "feat: add FileTreePanel component for directory tree browsing"
```

---

## Task 6: RepositoryWorkspace component

**Files:**
- Create: `src/components/repository/RepositoryWorkspace.tsx`

- [ ] **Step 1: Create the component**

```tsx
/**
 * RepositoryWorkspace — File tree + viewer layout
 */

import React, { useCallback, useEffect, useMemo } from 'react';
import { FolderOpen } from 'lucide-react';
import { useAppStore } from '../../store/app-store';
import { apiClient } from '../../lib/api-client';
import { FileTreePanel } from './FileTreePanel';
import { ViewerShell } from '../viewer/ViewerShell';
import type { Artifact, FileNode } from '../../types';

/* ── Convert FileNode to Artifact for ViewerShell ── */

function fileNodeToArtifact(node: FileNode): Artifact {
  const ext = node.extension ?? '';
  let viewerKind = 'document';
  if (['.py', '.ts', '.tsx', '.js', '.jsx', '.swift', '.java', '.go', '.rs', '.c', '.cpp', '.h', '.hpp', '.sql', '.sh'].includes(ext)) {
    viewerKind = 'code';
  } else if (['.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp'].includes(ext)) {
    viewerKind = 'image';
  } else if (['.html', '.htm'].includes(ext)) {
    viewerKind = 'web';
  }

  return {
    id: node.path,
    type: ext.replace('.', '') || 'unknown',
    title: node.name,
    subtitle: node.path,
    path: node.path,
    full_path: node.path,
    preview: '',
    source_type: 'file',
    viewer_kind: viewerKind,
  };
}

/* ── RepositoryWorkspace ── */

interface RepositoryWorkspaceProps {
  initialPath?: string | null;
  onClearInitialPath?: () => void;
}

export function RepositoryWorkspace({ initialPath, onClearInitialPath }: RepositoryWorkspaceProps) {
  const selectedFilePath = useAppStore((s) => s.selectedFilePath);
  const setSelectedFilePath = useAppStore((s) => s.setSelectedFilePath);
  const expandToPath = useAppStore((s) => s.expandToPath);
  const fileTreeCache = useAppStore((s) => s.fileTreeCache);
  const cacheDirectory = useAppStore((s) => s.cacheDirectory);

  // Handle initialPath from Terminal citation navigation
  useEffect(() => {
    if (!initialPath) return;

    // Expand tree to the target file
    expandToPath(initialPath);

    // Lazy-load all parent directories
    const parts = initialPath.split('/');
    for (let i = 1; i < parts.length; i++) {
      const dirPath = parts.slice(0, i).join('/');
      if (!fileTreeCache[dirPath]) {
        apiClient.browse(dirPath).then((res) => cacheDirectory(dirPath, res.entries));
      }
    }

    onClearInitialPath?.();
  }, [initialPath, expandToPath, fileTreeCache, cacheDirectory, onClearInitialPath]);

  const handleSelectFile = useCallback(
    (node: FileNode) => {
      setSelectedFilePath(node.path);
    },
    [setSelectedFilePath],
  );

  const selectedArtifact = useMemo(() => {
    if (!selectedFilePath) return null;
    const ext = selectedFilePath.includes('.')
      ? '.' + selectedFilePath.split('.').pop()!.toLowerCase()
      : null;
    return fileNodeToArtifact({
      name: selectedFilePath.split('/').pop() || selectedFilePath,
      path: selectedFilePath,
      type: 'file',
      extension: ext,
    });
  }, [selectedFilePath]);

  return (
    <div className="flex h-full">
      {/* Left: File tree */}
      <div className="w-64 shrink-0 border-r border-white/10 bg-black/20">
        <FileTreePanel onSelectFile={handleSelectFile} />
      </div>

      {/* Right: Viewer */}
      <div className="flex-1 overflow-hidden">
        {selectedArtifact ? (
          <ViewerShell
            artifact={selectedArtifact}
            artifacts={[]}
            citations={[]}
            isMobile={false}
            isLoading={false}
          />
        ) : (
          <div className="flex h-full flex-col items-center justify-center gap-3 text-white/30">
            <FolderOpen className="h-12 w-12" />
            <p className="text-sm">파일을 선택하세요</p>
          </div>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add src/components/repository/RepositoryWorkspace.tsx
git commit -m "feat: add RepositoryWorkspace with file tree + viewer layout"
```

---

## Task 7: Wire up App.tsx

**Files:**
- Modify: `src/App.tsx`

- [ ] **Step 1: Update imports**

Replace the RepositoryExplorer import (line 26):

```typescript
// Before:
import { RepositoryExplorer } from './components/repository/RepositoryExplorer';

// After:
import { RepositoryWorkspace } from './components/repository/RepositoryWorkspace';
```

- [ ] **Step 2: Remove Documents from sidebar nav**

Replace the `SHELL_NAV` array (lines 42-49):

```typescript
// Before:
const SHELL_NAV = [
  { key: 'home' as ViewState, label: 'Home', icon: House },
  { key: 'terminal' as ViewState, label: 'Terminal', icon: TerminalSquare },
  { key: 'repository' as ViewState, label: 'Repository', icon: FolderOpen },
  { key: 'detail_viewer' as ViewState, label: 'Documents', icon: FileText },
  { key: 'skills' as ViewState, label: 'Skills', icon: Workflow },
  { key: 'admin' as ViewState, label: 'Admin', icon: BarChart3 },
];

// After:
const SHELL_NAV = [
  { key: 'home' as ViewState, label: 'Home', icon: House },
  { key: 'terminal' as ViewState, label: 'Terminal', icon: TerminalSquare },
  { key: 'repository' as ViewState, label: 'Repository', icon: FolderOpen },
  { key: 'skills' as ViewState, label: 'Skills', icon: Workflow },
  { key: 'admin' as ViewState, label: 'Admin', icon: BarChart3 },
];
```

- [ ] **Step 3: Add navigateToFile state and handler**

Add state near the other state declarations (around line 92):

```typescript
const [repositoryInitialPath, setRepositoryInitialPath] = useState<string | null>(null);
```

Add the navigation function (near `openArtifact` around line 214):

```typescript
const navigateToFile = useCallback((path: string) => {
  setRepositoryInitialPath(path);
  setView('repository');
}, []);
```

- [ ] **Step 4: Replace RepositoryExplorer with RepositoryWorkspace**

Find the conditional rendering block for `view === 'repository'` (around lines 484-491) and replace:

```tsx
// Before:
{view === 'repository' && (
  <RepositoryExplorer
    assets={assets}
    citations={citations}
    onOpenArtifact={openArtifact}
    onSelectArtifact={selectArtifact}
    selectedArtifact={selectedArtifact}
  />
)}

// After:
{view === 'repository' && (
  <RepositoryWorkspace
    initialPath={repositoryInitialPath}
    onClearInitialPath={() => setRepositoryInitialPath(null)}
  />
)}
```

- [ ] **Step 5: Remove the detail_viewer rendering block**

Find and remove the conditional rendering for `view === 'detail_viewer'` (around lines 503-511):

```tsx
// DELETE this entire block:
{view === 'detail_viewer' && selectedArtifact && (
  <ViewerShell
    artifact={selectedArtifact}
    artifacts={assets}
    citations={citations}
    isMobile={isMobile}
    isLoading={isLoading}
    onAskArtifact={handleAskArtifact}
    onSelectArtifact={selectArtifact}
  />
)}
```

- [ ] **Step 6: Pass navigateToFile to TerminalWorkspace**

Find the TerminalWorkspace rendering (around lines 460-480) and add the prop:

```tsx
<TerminalWorkspace
  // ... existing props ...
  onNavigateToFile={navigateToFile}
/>
```

- [ ] **Step 7: Remove unused FileText import if no longer needed**

Check if `FileText` from lucide-react is still used elsewhere in App.tsx. If only used for the Documents nav item, remove it from the import.

- [ ] **Step 8: Commit**

```bash
git add src/App.tsx
git commit -m "feat(app): replace Documents tab with unified RepositoryWorkspace"
```

---

## Task 8: Terminal citation → Repository navigation

**Files:**
- Modify: `src/components/workspaces/TerminalWorkspace.tsx`

- [ ] **Step 1: Add onNavigateToFile prop**

Find the component's props interface and add:

```typescript
interface TerminalWorkspaceProps {
  // ... existing props ...
  onNavigateToFile?: (path: string) => void;
}
```

- [ ] **Step 2: Wire citation clicks**

Find where citations are rendered in TerminalWorkspace. Where a citation's source_path is displayed or clickable, add an onClick handler:

```tsx
// On citation items, add/update the click handler:
onClick={() => onNavigateToFile?.(citation.source_path)}
```

The exact location depends on how citations are currently rendered — look for `citation.source_path` or `citation.full_source_path` usage and add the click handler there. If citations are rendered as a list of `<button>` or `<div>` elements, wrap the existing click with `onNavigateToFile`.

- [ ] **Step 3: Commit**

```bash
git add src/components/workspaces/TerminalWorkspace.tsx
git commit -m "feat(terminal): citation click navigates to Repository file tree"
```

---

## Task 9: Delete old RepositoryExplorer

**Files:**
- Delete: `src/components/repository/RepositoryExplorer.tsx`

- [ ] **Step 1: Remove the file**

```bash
git rm src/components/repository/RepositoryExplorer.tsx
```

- [ ] **Step 2: Verify no remaining imports**

```bash
grep -r "RepositoryExplorer" src/
```

Should return no results. If any remain, update those imports.

- [ ] **Step 3: Commit**

```bash
git commit -m "refactor: remove old RepositoryExplorer, replaced by RepositoryWorkspace"
```

---

## Task 10: Smoke test & final verification

- [ ] **Step 1: Start the backend**

```bash
cd /Users/codingstudio/__PROJECTHUB__/JARVIS
./ProjectHub-terminal-architect/scripts/start.sh
```

- [ ] **Step 2: Verify /api/browse works**

```bash
curl -s "http://localhost:8000/api/browse" | python -m json.tool
curl -s "http://localhost:8000/api/browse?path=coding" | python -m json.tool
```

- [ ] **Step 3: Start the frontend**

```bash
cd /Users/codingstudio/__PROJECTHUB__/JARVIS/ProjectHub-terminal-architect
npm run dev
```

- [ ] **Step 4: Verify in browser**

1. Open http://localhost:5173
2. Click "Repository" tab → file tree should show knowledge_base contents
3. Click a folder → should expand and show children
4. Click a file → right panel should show file content via Viewer
5. Go to Terminal, ask a question that returns citations
6. Click a citation → should switch to Repository tab with that file selected
7. Verify Documents tab no longer exists in sidebar

- [ ] **Step 5: Final commit if any fixes needed**

```bash
git add -A
git commit -m "fix: address smoke test issues in repository workspace"
```
