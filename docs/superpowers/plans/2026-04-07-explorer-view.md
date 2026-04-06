# Explorer View Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a visual file browser ("Explorer") view with compact directory tree, icon grid, and zoom-expand animation to ViewerShell.

**Architecture:** New `ExplorerWorkspace` component with 4 sub-components: `ExplorerTree` (directory-only tree), `ExplorerGrid` (breadcrumb + file icon cards), `FileIconCard` (individual file/folder card with extension-based icon/color), `ExplorerViewer` (zoom animation wrapper around existing ViewerShell). A shared utility `fileNodeToArtifact` is extracted from RepositoryWorkspace for reuse.

**Tech Stack:** React 18, TypeScript, Tailwind CSS, motion/react (existing), Lucide icons (existing), existing `/api/browse` API, existing ViewerShell component.

---

## File Structure

| Action | Path | Responsibility |
|--------|------|---------------|
| Create | `src/lib/file-utils.ts` | Shared `fileNodeToArtifact()` + `formatFileSize()` + icon/color mapping |
| Create | `src/components/explorer/FileIconCard.tsx` | Single file/folder icon card with extension color |
| Create | `src/components/explorer/ExplorerTree.tsx` | Directory-only tree (140px sidebar) |
| Create | `src/components/explorer/ExplorerGrid.tsx` | Breadcrumb + responsive file icon grid |
| Create | `src/components/explorer/ExplorerViewer.tsx` | Zoom expand/shrink animation wrapper |
| Create | `src/components/explorer/ExplorerWorkspace.tsx` | Top-level container, state management |
| Modify | `src/types.ts:310` | Add `'explorer'` to `ViewState` |
| Modify | `src/App.tsx:42-47` | Add Explorer to `SHELL_NAV` and render `ExplorerWorkspace` |
| Modify | `src/components/shell/CommandPalette.tsx:25-31` | Add Explorer to `NAV_ITEMS` |
| Modify | `src/components/repository/RepositoryWorkspace.tsx:15-52` | Extract shared utils to `file-utils.ts`, import from there |

---

### Task 1: Shared File Utilities

**Files:**
- Create: `src/lib/file-utils.ts`
- Modify: `src/components/repository/RepositoryWorkspace.tsx`

- [ ] **Step 1: Create file-utils.ts with shared functions**

```ts
import type { Artifact, FileNode } from '../types';

/* ── Extension sets ── */

const CODE_EXTENSIONS = new Set([
  '.py', '.ts', '.tsx', '.js', '.jsx', '.mjs', '.cjs',
  '.swift', '.java', '.go', '.rs', '.kt', '.rb', '.scala', '.dart',
  '.c', '.cc', '.cpp', '.h', '.hpp', '.cs', '.php', '.lua', '.r',
  '.sh', '.bash', '.zsh', '.fish', '.ps1',
  '.yml', '.yaml', '.json', '.jsonc', '.toml', '.ini', '.cfg', '.conf', '.env',
  '.css', '.scss', '.sass', '.less',
  '.sql', '.graphql', '.proto', '.xml', '.ex', '.exs',
]);

const IMAGE_EXTENSIONS = new Set(['.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.bmp', '.heic']);
const VIDEO_EXTENSIONS = new Set(['.mp4', '.mov', '.webm', '.m4v']);
const TEXT_EXTENSIONS = new Set(['.txt', '.log', '.csv', '.tsv', '.env', '.nfo']);
const MARKDOWN_EXTENSIONS = new Set(['.md', '.markdown']);
const WEB_EXTENSIONS = new Set(['.html', '.htm']);

/* ── FileNode → Artifact ── */

export function fileNodeToArtifact(node: FileNode): Artifact {
  const ext = (node.extension ?? '').toLowerCase();
  let viewerKind = 'document';
  if (CODE_EXTENSIONS.has(ext)) viewerKind = 'code';
  else if (MARKDOWN_EXTENSIONS.has(ext)) viewerKind = 'markdown';
  else if (TEXT_EXTENSIONS.has(ext)) viewerKind = 'text';
  else if (IMAGE_EXTENSIONS.has(ext)) viewerKind = 'image';
  else if (VIDEO_EXTENSIONS.has(ext)) viewerKind = 'video';
  else if (WEB_EXTENSIONS.has(ext)) viewerKind = 'html';

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

/* ── File size formatter ── */

export function formatFileSize(bytes: number | null | undefined): string {
  if (bytes == null || bytes === 0) return '';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/* ── Icon color by extension ── */

export function getFileColor(ext: string | null | undefined): string {
  const e = (ext ?? '').toLowerCase();
  if (e === '.pdf') return '#ef4444';
  if (['.xlsx', '.xls', '.csv'].includes(e)) return '#22c55e';
  if (['.pptx', '.ppt'].includes(e)) return '#f97316';
  if (['.docx', '.doc'].includes(e)) return '#3b82f6';
  if (['.md', '.txt', '.log'].includes(e)) return '#94a3b8';
  if (CODE_EXTENSIONS.has(e)) return '#a855f7';
  if (IMAGE_EXTENSIONS.has(e)) return '#ec4899';
  if (['.hwp', '.hwpx'].includes(e)) return '#06b6d4';
  if (['.json', '.yaml', '.yml', '.toml', '.xml'].includes(e)) return '#f59e0b';
  return '#64748b';
}
```

- [ ] **Step 2: Update RepositoryWorkspace to import from file-utils**

In `src/components/repository/RepositoryWorkspace.tsx`, remove the `CODE_EXTENSIONS`, `IMAGE_EXTENSIONS`, `VIDEO_EXTENSIONS`, `TEXT_EXTENSIONS`, `MARKDOWN_EXTENSIONS`, `WEB_EXTENSIONS` constants and the `fileNodeToArtifact` function (lines 15-52). Replace with:

```ts
import { fileNodeToArtifact } from '../../lib/file-utils';
```

- [ ] **Step 3: Verify TypeScript compiles and commit**

```bash
npx tsc --noEmit
git add ProjectHub-terminal-architect/src/lib/file-utils.ts ProjectHub-terminal-architect/src/components/repository/RepositoryWorkspace.tsx
git commit -m "refactor: extract shared file utilities from RepositoryWorkspace"
```

---

### Task 2: FileIconCard Component

**Files:**
- Create: `src/components/explorer/FileIconCard.tsx`

- [ ] **Step 1: Create FileIconCard component**

```tsx
import React from 'react';
import {
  Braces,
  Code2,
  File,
  FileText,
  Folder,
  Image,
  Presentation,
  Sheet,
} from 'lucide-react';
import { cn } from '../../lib/utils';
import { formatFileSize, getFileColor } from '../../lib/file-utils';
import type { FileNode } from '../../types';

function getFileIcon(node: FileNode) {
  if (node.type === 'directory') return Folder;
  const ext = (node.extension ?? '').toLowerCase();
  if (['.xlsx', '.xls', '.csv'].includes(ext)) return Sheet;
  if (['.pptx', '.ppt'].includes(ext)) return Presentation;
  if (['.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.bmp', '.heic'].includes(ext)) return Image;
  if (['.json', '.yaml', '.yml', '.toml', '.xml'].includes(ext)) return Braces;
  if (['.py', '.ts', '.tsx', '.js', '.jsx', '.mjs', '.cjs', '.swift', '.java', '.go', '.rs',
       '.c', '.cpp', '.h', '.sh', '.sql', '.css', '.scss'].includes(ext)) return Code2;
  if (['.pdf', '.md', '.txt', '.docx', '.doc', '.hwp', '.hwpx', '.pptx', '.log'].includes(ext)) return FileText;
  return File;
}

interface FileIconCardProps {
  node: FileNode;
  onClick: (node: FileNode, rect: DOMRect) => void;
}

export function FileIconCard({ node, onClick }: FileIconCardProps) {
  const Icon = getFileIcon(node);
  const color = node.type === 'directory' ? '#eab308' : getFileColor(node.extension);
  const size = formatFileSize(node.size);

  const handleClick = (e: React.MouseEvent<HTMLButtonElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    onClick(node, rect);
  };

  return (
    <button
      onClick={handleClick}
      className="group flex flex-col items-center gap-2 rounded-lg border border-white/5 bg-surface-container-low p-4 text-center transition hover:border-primary/30 hover:bg-surface-container hover:scale-[1.02]"
    >
      <Icon size={36} style={{ color }} />
      <span className="w-full truncate text-[11px] text-on-surface">{node.name}</span>
      {size && <span className="text-[9px] text-outline">{size}</span>}
    </button>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add ProjectHub-terminal-architect/src/components/explorer/FileIconCard.tsx
git commit -m "feat: add FileIconCard component for Explorer view"
```

---

### Task 3: ExplorerTree Component

**Files:**
- Create: `src/components/explorer/ExplorerTree.tsx`

- [ ] **Step 1: Create ExplorerTree component**

```tsx
import React, { useCallback, useEffect, useState } from 'react';
import { ChevronDown, ChevronRight, Folder, FolderOpen } from 'lucide-react';
import { cn } from '../../lib/utils';
import { apiClient } from '../../lib/api-client';
import type { FileNode } from '../../types';

interface ExplorerTreeProps {
  currentPath: string;
  onSelectDirectory: (path: string) => void;
}

interface DirNode {
  name: string;
  path: string;
  children: DirNode[] | null; // null = not loaded
  expanded: boolean;
}

export function ExplorerTree({ currentPath, onSelectDirectory }: ExplorerTreeProps) {
  const [roots, setRoots] = useState<DirNode[]>([]);

  const loadChildren = useCallback(async (path: string): Promise<DirNode[]> => {
    try {
      const response = await apiClient.browse(path);
      return response.entries
        .filter((e) => e.type === 'directory')
        .map((e) => ({ name: e.name, path: e.path, children: null, expanded: false }));
    } catch {
      return [];
    }
  }, []);

  useEffect(() => {
    loadChildren('').then(setRoots);
  }, [loadChildren]);

  const toggleDir = useCallback(async (targetPath: string) => {
    const toggle = async (nodes: DirNode[]): Promise<DirNode[]> => {
      const result: DirNode[] = [];
      for (const node of nodes) {
        if (node.path === targetPath) {
          if (!node.expanded && node.children === null) {
            const children = await loadChildren(node.path);
            result.push({ ...node, expanded: true, children });
          } else {
            result.push({ ...node, expanded: !node.expanded });
          }
        } else {
          const updatedChildren = node.children ? await toggle(node.children) : null;
          result.push({ ...node, children: updatedChildren });
        }
      }
      return result;
    };
    setRoots(await toggle(roots));
  }, [roots, loadChildren]);

  const renderNode = (node: DirNode, depth: number) => {
    const isSelected = node.path === currentPath;
    const Icon = node.expanded ? FolderOpen : Folder;
    const Chevron = node.expanded ? ChevronDown : ChevronRight;

    return (
      <div key={node.path}>
        <button
          onClick={() => {
            onSelectDirectory(node.path);
            if (!node.expanded) toggleDir(node.path);
          }}
          className={cn(
            'flex w-full items-center gap-1 rounded-sm px-1 py-1 text-left text-[11px] transition',
            isSelected
              ? 'bg-surface-container text-primary'
              : 'text-on-surface-variant hover:bg-surface-container-high',
          )}
          style={{ paddingLeft: `${depth * 12 + 4}px` }}
        >
          <Chevron
            size={12}
            className="shrink-0 text-outline cursor-pointer"
            onClick={(e) => { e.stopPropagation(); toggleDir(node.path); }}
          />
          <Icon size={14} className="shrink-0 text-[#eab308]" />
          <span className="truncate">{node.name}</span>
        </button>
        {node.expanded && node.children && node.children.map((child) => renderNode(child, depth + 1))}
      </div>
    );
  };

  return (
    <div className="w-[140px] shrink-0 overflow-y-auto border-r border-white/5 bg-surface-container-high custom-scrollbar">
      <div className="px-3 py-3 text-[10px] font-semibold uppercase tracking-[0.12em] text-outline">
        Folders
      </div>
      <div className="px-1 pb-4">
        <button
          onClick={() => onSelectDirectory('')}
          className={cn(
            'flex w-full items-center gap-1 rounded-sm px-1 py-1 text-left text-[11px] transition',
            currentPath === ''
              ? 'bg-surface-container text-primary'
              : 'text-on-surface-variant hover:bg-surface-container-high',
          )}
        >
          <Folder size={14} className="shrink-0 text-[#eab308]" />
          <span>Root</span>
        </button>
        {roots.map((node) => renderNode(node, 1))}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add ProjectHub-terminal-architect/src/components/explorer/ExplorerTree.tsx
git commit -m "feat: add ExplorerTree directory-only tree component"
```

---

### Task 4: ExplorerGrid Component

**Files:**
- Create: `src/components/explorer/ExplorerGrid.tsx`

- [ ] **Step 1: Create ExplorerGrid component**

```tsx
import React from 'react';
import { ChevronRight, Home } from 'lucide-react';
import { cn } from '../../lib/utils';
import { FileIconCard } from './FileIconCard';
import type { FileNode } from '../../types';

interface ExplorerGridProps {
  currentPath: string;
  entries: FileNode[];
  loading: boolean;
  onNavigate: (path: string) => void;
  onOpenFile: (file: FileNode, rect: DOMRect) => void;
}

function Breadcrumb({ path, onNavigate }: { path: string; onNavigate: (path: string) => void }) {
  const segments = path ? path.split('/').filter(Boolean) : [];

  return (
    <div className="flex items-center gap-1 px-4 py-2 text-[12px] border-b border-white/5">
      <button
        onClick={() => onNavigate('')}
        className="text-outline transition hover:text-primary"
      >
        <Home size={14} />
      </button>
      {segments.map((segment, i) => {
        const segmentPath = segments.slice(0, i + 1).join('/');
        const isLast = i === segments.length - 1;
        return (
          <React.Fragment key={segmentPath}>
            <ChevronRight size={12} className="text-outline/50" />
            <button
              onClick={() => onNavigate(segmentPath)}
              className={cn(
                'transition',
                isLast ? 'text-on-surface font-medium' : 'text-outline hover:text-primary',
              )}
            >
              {segment}
            </button>
          </React.Fragment>
        );
      })}
    </div>
  );
}

export function ExplorerGrid({ currentPath, entries, loading, onNavigate, onOpenFile }: ExplorerGridProps) {
  const handleCardClick = (node: FileNode, rect: DOMRect) => {
    if (node.type === 'directory') {
      onNavigate(node.path);
    } else {
      onOpenFile(node, rect);
    }
  };

  return (
    <div className="flex flex-1 flex-col min-h-0 overflow-hidden">
      <Breadcrumb path={currentPath} onNavigate={onNavigate} />
      <div className="flex-1 overflow-y-auto p-4 custom-scrollbar">
        {loading ? (
          <div className="flex items-center justify-center h-40">
            <div className="w-6 h-6 border-2 border-primary border-t-transparent rounded-full animate-spin" />
          </div>
        ) : entries.length === 0 ? (
          <div className="flex items-center justify-center h-40 text-sm text-outline">
            이 디렉토리는 비어 있습니다.
          </div>
        ) : (
          <div className="grid grid-cols-3 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6">
            {entries.map((entry) => (
              <FileIconCard key={entry.path} node={entry} onClick={handleCardClick} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add ProjectHub-terminal-architect/src/components/explorer/ExplorerGrid.tsx
git commit -m "feat: add ExplorerGrid with breadcrumb and responsive icon grid"
```

---

### Task 5: ExplorerViewer Component

**Files:**
- Create: `src/components/explorer/ExplorerViewer.tsx`

- [ ] **Step 1: Create ExplorerViewer with zoom animation**

```tsx
import React from 'react';
import { motion } from 'motion/react';
import { X } from 'lucide-react';
import { ViewerShell } from '../viewer/ViewerShell';
import type { Artifact } from '../../types';

interface ExplorerViewerProps {
  artifact: Artifact;
  originRect: DOMRect;
  onClose: () => void;
}

export function ExplorerViewer({ artifact, originRect, onClose }: ExplorerViewerProps) {
  return (
    <motion.div
      className="absolute inset-0 z-30 flex flex-col bg-surface"
      initial={{
        x: originRect.left,
        y: originRect.top,
        width: originRect.width,
        height: originRect.height,
        opacity: 0.5,
        borderRadius: 12,
      }}
      animate={{
        x: 0,
        y: 0,
        width: '100%',
        height: '100%',
        opacity: 1,
        borderRadius: 0,
      }}
      exit={{
        x: originRect.left,
        y: originRect.top,
        width: originRect.width,
        height: originRect.height,
        opacity: 0,
        borderRadius: 12,
      }}
      transition={{ duration: 0.3, ease: 'easeInOut' }}
    >
      <button
        onClick={onClose}
        className="absolute right-3 top-3 z-40 rounded-full bg-surface-container-highest p-1.5 text-outline transition hover:bg-surface-container hover:text-on-surface"
      >
        <X size={16} />
      </button>
      <ViewerShell
        artifact={artifact}
        artifacts={[]}
        citations={[]}
        isMobile={false}
        hideLibrary
      />
    </motion.div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add ProjectHub-terminal-architect/src/components/explorer/ExplorerViewer.tsx
git commit -m "feat: add ExplorerViewer with zoom expand/shrink animation"
```

---

### Task 6: ExplorerWorkspace Component

**Files:**
- Create: `src/components/explorer/ExplorerWorkspace.tsx`

- [ ] **Step 1: Create ExplorerWorkspace**

```tsx
import React, { useCallback, useEffect, useState } from 'react';
import { AnimatePresence } from 'motion/react';
import { apiClient } from '../../lib/api-client';
import { fileNodeToArtifact } from '../../lib/file-utils';
import { ExplorerTree } from './ExplorerTree';
import { ExplorerGrid } from './ExplorerGrid';
import { ExplorerViewer } from './ExplorerViewer';
import type { Artifact, FileNode } from '../../types';

export function ExplorerWorkspace() {
  const [currentPath, setCurrentPath] = useState('');
  const [entries, setEntries] = useState<FileNode[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedArtifact, setSelectedArtifact] = useState<Artifact | null>(null);
  const [originRect, setOriginRect] = useState<DOMRect | null>(null);

  const loadDirectory = useCallback(async (path: string) => {
    setLoading(true);
    try {
      const response = await apiClient.browse(path);
      // Sort: directories first, then files alphabetically
      const sorted = [...response.entries].sort((a, b) => {
        if (a.type !== b.type) return a.type === 'directory' ? -1 : 1;
        return a.name.localeCompare(b.name);
      });
      setEntries(sorted);
    } catch {
      setEntries([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadDirectory(currentPath);
  }, [currentPath, loadDirectory]);

  const handleNavigate = useCallback((path: string) => {
    setCurrentPath(path);
  }, []);

  const handleOpenFile = useCallback((file: FileNode, rect: DOMRect) => {
    setSelectedArtifact(fileNodeToArtifact(file));
    setOriginRect(rect);
  }, []);

  const handleClose = useCallback(() => {
    setSelectedArtifact(null);
    setOriginRect(null);
  }, []);

  return (
    <div className="relative flex h-full overflow-hidden bg-surface">
      <ExplorerTree currentPath={currentPath} onSelectDirectory={handleNavigate} />
      <ExplorerGrid
        currentPath={currentPath}
        entries={entries}
        loading={loading}
        onNavigate={handleNavigate}
        onOpenFile={handleOpenFile}
      />
      <AnimatePresence>
        {selectedArtifact && originRect && (
          <ExplorerViewer
            key={selectedArtifact.id}
            artifact={selectedArtifact}
            originRect={originRect}
            onClose={handleClose}
          />
        )}
      </AnimatePresence>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add ProjectHub-terminal-architect/src/components/explorer/ExplorerWorkspace.tsx
git commit -m "feat: add ExplorerWorkspace container with state management"
```

---

### Task 7: Wire Explorer into App

**Files:**
- Modify: `src/types.ts:310`
- Modify: `src/App.tsx`
- Modify: `src/components/shell/CommandPalette.tsx`

- [ ] **Step 1: Add 'explorer' to ViewState**

In `src/types.ts`, change line 310:

```ts
export type ViewState = 'home' | 'terminal' | 'repository' | 'explorer' | 'skills' | 'admin';
```

- [ ] **Step 2: Add Explorer to App.tsx SHELL_NAV and imports**

Add import at top of `src/App.tsx`:

```ts
import { ExplorerWorkspace } from './components/explorer/ExplorerWorkspace';
```

Add `FolderSearch` to the lucide-react import.

Add to `SHELL_NAV` after repository:

```ts
{ key: 'explorer' as ViewState, label: 'Explorer', icon: FolderSearch },
```

Add view rendering inside `<AnimatePresence>` after the repository block:

```tsx
{view === 'explorer' ? (
  <motion.div
    key="explorer"
    initial={{ opacity: 0, x: 12 }}
    animate={{ opacity: 1, x: 0 }}
    exit={{ opacity: 0, x: -12 }}
    className="h-full"
  >
    <ExplorerWorkspace />
  </motion.div>
) : null}
```

- [ ] **Step 3: Add Explorer to CommandPalette NAV_ITEMS**

In `src/components/shell/CommandPalette.tsx`, add `FolderSearch` to the lucide-react import and add to `NAV_ITEMS` after repository:

```ts
{ key: 'explorer', label: 'Explorer', icon: FolderSearch },
```

- [ ] **Step 4: Verify and commit**

```bash
npx tsc --noEmit
git add ProjectHub-terminal-architect/src/types.ts ProjectHub-terminal-architect/src/App.tsx ProjectHub-terminal-architect/src/components/shell/CommandPalette.tsx
git commit -m "feat: wire Explorer view into app navigation"
```

---

### Task 8: Visual Verification

- [ ] **Step 1: Open http://localhost:3000 and click Explorer icon in sidebar**

Verify: New icon appears between Repository and Skills. Click shows Explorer view.

- [ ] **Step 2: Verify directory tree**

Click directories in left tree — grid updates with folder contents.

- [ ] **Step 3: Verify breadcrumb navigation**

Click breadcrumb segments — navigates to parent directories.

- [ ] **Step 4: Verify file icon cards**

Check: extension-based icons and colors, file sizes shown, hover effects work.

- [ ] **Step 5: Verify zoom animation**

Click a file — viewer opens with zoom expand from card position. Click X — zoom shrink back to grid.

- [ ] **Step 6: Verify Cmd+K palette**

Open Command Palette — Explorer appears in navigation list.

- [ ] **Step 7: Fix any issues and commit**

```bash
git add -A && git commit -m "fix: explorer visual verification adjustments"
```
