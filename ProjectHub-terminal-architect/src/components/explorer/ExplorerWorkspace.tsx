import React, { useCallback, useEffect, useRef, useState } from 'react';
import { AnimatePresence } from 'motion/react';
import { Layers, LayoutGrid, LayoutList } from 'lucide-react';
import { cn } from '../../lib/utils';
import { apiClient } from '../../lib/api-client';
import { fileNodeToArtifact } from '../../lib/file-utils';
import { ExplorerTree } from './ExplorerTree';
import { ExplorerGrid } from './ExplorerGrid';
import { ExplorerViewer, getDefaultWindowSize, type WindowLayout } from './ExplorerViewer';
import type { Artifact, FileNode } from '../../types';

type LayoutMode = 'free' | 'cascade' | 'tile';

interface OpenWindow {
  id: string;
  artifact: Artifact;
  originRect: DOMRect;
}

interface ExplorerWorkspaceProps {
  initialPath?: string | null;
  onClearInitialPath?: () => void;
  onAskArtifact?: (artifact: Artifact, prompt: string) => Promise<void> | void;
}

export function ExplorerWorkspace({ initialPath, onClearInitialPath, onAskArtifact }: ExplorerWorkspaceProps) {
  const [currentPath, setCurrentPath] = useState('');
  const [entries, setEntries] = useState<FileNode[]>([]);
  const [loading, setLoading] = useState(false);
  const [windows, setWindows] = useState<OpenWindow[]>([]);
  const [zStack, setZStack] = useState<string[]>([]);
  const [layoutMode, setLayoutMode] = useState<LayoutMode>('free');
  const [layouts, setLayouts] = useState<Record<string, WindowLayout>>({});
  const containerRef = useRef<HTMLDivElement>(null);

  const loadDirectory = useCallback(async (path: string) => {
    setLoading(true);
    try {
      const response = await apiClient.browse(path);
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

  // Handle initial path from external navigation (Terminal → Explorer)
  useEffect(() => {
    if (!initialPath) return;
    // Extract directory from file path to navigate there
    const lastSlash = initialPath.lastIndexOf('/');
    const dir = lastSlash > 0 ? initialPath.slice(0, lastSlash) : '';
    setCurrentPath(dir);

    // Open the file in a floating window after entries load
    const timer = setTimeout(async () => {
      try {
        const response = await apiClient.browse(dir);
        const file = response.entries.find((e) => e.path === initialPath || e.name === initialPath.split('/').pop());
        if (file && file.type === 'file') {
          const artifact = fileNodeToArtifact(file);
          const centerRect = new DOMRect(
            window.innerWidth / 2 - 50,
            window.innerHeight / 2 - 50,
            100, 100,
          );
          setWindows((prev) => [...prev, { id: artifact.id, artifact, originRect: centerRect }]);
          setZStack((prev) => [...prev, artifact.id]);
        }
      } catch { /* ignore */ }
      onClearInitialPath?.();
    }, 300);
    return () => clearTimeout(timer);
  }, [initialPath, onClearInitialPath]);

  const handleNavigate = useCallback((path: string) => {
    setCurrentPath(path);
  }, []);

  const handleOpenFile = useCallback((file: FileNode, rect: DOMRect) => {
    const artifact = fileNodeToArtifact(file);
    const existing = windows.find((w) => w.id === artifact.id);
    if (existing) {
      setZStack((prev) => [...prev.filter((id) => id !== artifact.id), artifact.id]);
      return;
    }
    const win: OpenWindow = { id: artifact.id, artifact, originRect: rect };
    setWindows((prev) => [...prev, win]);
    setZStack((prev) => [...prev, win.id]);
    // Clear auto-layout when opening new window in free mode
    if (layoutMode === 'free') {
      setLayouts((prev) => { const next = { ...prev }; delete next[win.id]; return next; });
    }
  }, [windows, layoutMode]);

  const handleCloseWindow = useCallback((id: string) => {
    setWindows((prev) => prev.filter((w) => w.id !== id));
    setZStack((prev) => prev.filter((wid) => wid !== id));
    setLayouts((prev) => { const next = { ...prev }; delete next[id]; return next; });
  }, []);

  const handleFocusWindow = useCallback((id: string) => {
    setZStack((prev) => {
      if (prev[prev.length - 1] === id) return prev;
      return [...prev.filter((wid) => wid !== id), id];
    });
  }, []);

  // ── Layout calculations ──

  const applyLayout = useCallback((mode: LayoutMode) => {
    setLayoutMode(mode);
    if (mode === 'free' || windows.length === 0) {
      setLayouts({});
      return;
    }

    // Get available area (excluding tree sidebar ~140px and some padding)
    const container = containerRef.current;
    const areaWidth = container ? container.clientWidth - 140 : 1000;
    const areaHeight = container ? container.clientHeight : 700;
    const offsetX = 140; // tree sidebar width

    if (mode === 'cascade') {
      const newLayouts: Record<string, WindowLayout> = {};
      windows.forEach((win, i) => {
        const size = getDefaultWindowSize(win.artifact);
        newLayouts[win.id] = {
          x: offsetX + 30 + i * 30,
          y: 30 + i * 30,
          width: Math.min(size.width, areaWidth - 60),
          height: Math.min(size.height, areaHeight - 60),
        };
      });
      setLayouts(newLayouts);
      // Reset z-stack to match order
      setZStack(windows.map((w) => w.id));
    }

    if (mode === 'tile') {
      const count = windows.length;
      const newLayouts: Record<string, WindowLayout> = {};

      if (count === 1) {
        newLayouts[windows[0].id] = { x: offsetX + 4, y: 4, width: areaWidth - 8, height: areaHeight - 8 };
      } else if (count === 2) {
        const halfW = Math.floor((areaWidth - 12) / 2);
        windows.forEach((win, i) => {
          newLayouts[win.id] = { x: offsetX + 4 + i * (halfW + 4), y: 4, width: halfW, height: areaHeight - 8 };
        });
      } else {
        // Grid layout: calculate cols/rows
        const cols = Math.ceil(Math.sqrt(count));
        const rows = Math.ceil(count / cols);
        const cellW = Math.floor((areaWidth - (cols + 1) * 4) / cols);
        const cellH = Math.floor((areaHeight - (rows + 1) * 4) / rows);
        windows.forEach((win, i) => {
          const col = i % cols;
          const row = Math.floor(i / cols);
          newLayouts[win.id] = {
            x: offsetX + 4 + col * (cellW + 4),
            y: 4 + row * (cellH + 4),
            width: cellW,
            height: cellH,
          };
        });
      }
      setLayouts(newLayouts);
    }
  }, [windows]);

  return (
    <div ref={containerRef} className="relative flex h-full overflow-hidden bg-surface">
      <ExplorerTree currentPath={currentPath} onSelectDirectory={handleNavigate} />
      <ExplorerGrid
        currentPath={currentPath}
        entries={entries}
        loading={loading}
        onNavigate={handleNavigate}
        onOpenFile={handleOpenFile}
      />
      <AnimatePresence>
        {windows.map((win) => (
          <ExplorerViewer
            key={win.id}
            artifact={win.artifact}
            originRect={win.originRect}
            zIndex={30 + zStack.indexOf(win.id)}
            layout={layouts[win.id] ?? null}
            onClose={() => handleCloseWindow(win.id)}
            onFocus={() => handleFocusWindow(win.id)}
            onAskArtifact={onAskArtifact}
          />
        ))}
      </AnimatePresence>

      {/* Layout toolbar — only show when windows are open */}
      {windows.length > 1 && (
        <div className="absolute bottom-3 right-3 z-50 flex items-center gap-1 rounded-lg border border-white/10 bg-surface-container-high/90 px-2 py-1 shadow-lg backdrop-blur-sm">
          <span className="mr-1 text-[9px] font-semibold uppercase tracking-[0.12em] text-outline">Layout</span>
          <button
            onClick={() => applyLayout('free')}
            className={cn(
              'rounded p-1 transition',
              layoutMode === 'free' ? 'bg-surface-container text-primary' : 'text-outline hover:text-on-surface',
            )}
            title="Free"
          >
            <LayoutList size={14} />
          </button>
          <button
            onClick={() => applyLayout('cascade')}
            className={cn(
              'rounded p-1 transition',
              layoutMode === 'cascade' ? 'bg-surface-container text-primary' : 'text-outline hover:text-on-surface',
            )}
            title="Cascade"
          >
            <Layers size={14} />
          </button>
          <button
            onClick={() => applyLayout('tile')}
            className={cn(
              'rounded p-1 transition',
              layoutMode === 'tile' ? 'bg-surface-container text-primary' : 'text-outline hover:text-on-surface',
            )}
            title="Tile"
          >
            <LayoutGrid size={14} />
          </button>
        </div>
      )}
    </div>
  );
}
