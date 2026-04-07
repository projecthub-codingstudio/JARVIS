import React, { useCallback, useEffect, useRef, useState } from 'react';
import { AnimatePresence } from 'motion/react';
import {
  FileText,
  FolderOpen,
  Layers,
  LayoutGrid,
  LayoutList,
  Maximize2,
  Minimize2,
  X,
} from 'lucide-react';
import { cn } from '../../lib/utils';
import { ExplorerViewer, getDefaultWindowSize, type WindowLayout } from '../explorer/ExplorerViewer';
import type { Artifact } from '../../types';

type LayoutMode = 'free' | 'cascade' | 'tile';

interface OpenWindow {
  id: string;
  artifact: Artifact;
  originRect: DOMRect;
}

interface DocumentsWorkspaceProps {
  assets: Artifact[];
  onAskArtifact?: (artifact: Artifact, prompt: string) => Promise<void> | void;
}

const SIDEBAR_WIDTH = 240;

function makeCenterRect(): DOMRect {
  const cx = typeof window !== 'undefined' ? window.innerWidth / 2 - 50 : 400;
  const cy = typeof window !== 'undefined' ? window.innerHeight / 2 - 50 : 300;
  return new DOMRect(cx, cy, 100, 100);
}

function getFileIcon(artifact: Artifact): string {
  const ext = (artifact.path || artifact.full_path || '').split('.').pop()?.toLowerCase() || '';
  if (['pdf'].includes(ext)) return '📄';
  if (['xlsx', 'xls', 'csv'].includes(ext)) return '📊';
  if (['pptx', 'ppt'].includes(ext)) return '📑';
  if (['docx', 'doc', 'hwp', 'hwpx'].includes(ext)) return '📝';
  if (['png', 'jpg', 'jpeg', 'gif', 'svg', 'webp'].includes(ext)) return '🖼️';
  if (['md', 'txt'].includes(ext)) return '📃';
  return '📁';
}

export function DocumentsWorkspace({ assets, onAskArtifact }: DocumentsWorkspaceProps) {
  const [windows, setWindows] = useState<OpenWindow[]>([]);
  const [zStack, setZStack] = useState<string[]>([]);
  const [layoutMode, setLayoutMode] = useState<LayoutMode>('cascade');
  const [layouts, setLayouts] = useState<Record<string, WindowLayout>>({});
  const containerRef = useRef<HTMLDivElement>(null);
  const prevAssetsRef = useRef<string>('');

  // ── Auto-open all windows when assets change ──
  useEffect(() => {
    const key = assets.map((a) => a.id).join(',');
    if (key === prevAssetsRef.current || assets.length === 0) return;
    prevAssetsRef.current = key;

    const newWindows = assets.map((artifact) => ({
      id: artifact.id,
      artifact,
      originRect: makeCenterRect(),
    }));
    const newIds = assets.map((a) => a.id);

    setWindows(newWindows);
    setZStack(newIds);
    setLayoutMode('cascade');

    // Apply cascade layout after state flush
    requestAnimationFrame(() => {
      const container = containerRef.current;
      const areaWidth = container ? container.clientWidth : 1000;
      const areaHeight = container ? container.clientHeight : 700;

      const newLayouts: Record<string, WindowLayout> = {};
      newWindows.forEach((win, i) => {
        const size = getDefaultWindowSize(win.artifact);
        newLayouts[win.id] = {
          x: 30 + i * 30,
          y: 30 + i * 30,
          width: Math.min(size.width, areaWidth - 60),
          height: Math.min(size.height, areaHeight - 60),
        };
      });
      setLayouts(newLayouts);
    });
  }, [assets]);

  // ── Window management ──
  const openWindow = useCallback((artifact: Artifact) => {
    setWindows((prev) => {
      const existing = prev.find((w) => w.id === artifact.id);
      if (existing) return prev;
      return [...prev, { id: artifact.id, artifact, originRect: makeCenterRect() }];
    });
    setZStack((prev) => {
      const filtered = prev.filter((id) => id !== artifact.id);
      return [...filtered, artifact.id];
    });
  }, []);

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

  const handleSidebarClick = useCallback((artifact: Artifact) => {
    const isOpen = windows.some((w) => w.id === artifact.id);
    if (isOpen) {
      handleFocusWindow(artifact.id);
    } else {
      openWindow(artifact);
    }
  }, [windows, handleFocusWindow, openWindow]);

  // ── Bulk actions ──
  const handleOpenAll = useCallback(() => {
    const newWindows: OpenWindow[] = assets.map((artifact) => ({
      id: artifact.id,
      artifact,
      originRect: makeCenterRect(),
    }));
    setWindows(newWindows);
    setZStack(assets.map((a) => a.id));
  }, [assets]);

  const handleCloseAll = useCallback(() => {
    setWindows([]);
    setZStack([]);
    setLayouts({});
  }, []);

  // ── Layout calculations ──
  const applyLayout = useCallback((mode: LayoutMode) => {
    setLayoutMode(mode);
    if (mode === 'free' || windows.length === 0) {
      setLayouts({});
      return;
    }

    const container = containerRef.current;
    const areaWidth = container ? container.clientWidth : 1000;
    const areaHeight = container ? container.clientHeight : 700;

    if (mode === 'cascade') {
      const newLayouts: Record<string, WindowLayout> = {};
      windows.forEach((win, i) => {
        const size = getDefaultWindowSize(win.artifact);
        newLayouts[win.id] = {
          x: 30 + i * 30,
          y: 30 + i * 30,
          width: Math.min(size.width, areaWidth - 60),
          height: Math.min(size.height, areaHeight - 60),
        };
      });
      setLayouts(newLayouts);
      setZStack(windows.map((w) => w.id));
    }

    if (mode === 'tile') {
      const count = windows.length;
      const newLayouts: Record<string, WindowLayout> = {};

      if (count === 1) {
        newLayouts[windows[0].id] = { x: 4, y: 4, width: areaWidth - 8, height: areaHeight - 8 };
      } else if (count === 2) {
        const halfW = Math.floor((areaWidth - 12) / 2);
        windows.forEach((win, i) => {
          newLayouts[win.id] = { x: 4 + i * (halfW + 4), y: 4, width: halfW, height: areaHeight - 8 };
        });
      } else {
        const cols = Math.ceil(Math.sqrt(count));
        const rows = Math.ceil(count / cols);
        const cellW = Math.floor((areaWidth - (cols + 1) * 4) / cols);
        const cellH = Math.floor((areaHeight - (rows + 1) * 4) / rows);
        windows.forEach((win, i) => {
          const col = i % cols;
          const row = Math.floor(i / cols);
          newLayouts[win.id] = {
            x: 4 + col * (cellW + 4),
            y: 4 + row * (cellH + 4),
            width: cellW,
            height: cellH,
          };
        });
      }
      setLayouts(newLayouts);
    }
  }, [windows]);

  const openIds = new Set(windows.map((w) => w.id));

  return (
    <div className="relative flex h-full overflow-hidden bg-surface">
      {/* ── Left sidebar: search result list ── */}
      <aside
        className="flex h-full shrink-0 flex-col border-r border-white/5 bg-surface-container-high"
        style={{ width: SIDEBAR_WIDTH }}
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-white/5 px-3 py-2.5">
          <div className="flex items-center gap-2">
            <FileText size={14} className="text-primary" />
            <span className="text-[11px] font-semibold uppercase tracking-[0.08em] text-on-surface-variant">
              검색 결과
            </span>
            <span className="rounded-full bg-primary/15 px-1.5 text-[10px] font-bold text-primary">
              {assets.length}
            </span>
          </div>
        </div>

        {/* Bulk actions */}
        <div className="flex items-center gap-1 border-b border-white/5 px-3 py-1.5">
          <button
            onClick={handleOpenAll}
            className="flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] text-outline transition hover:bg-surface-container hover:text-on-surface"
            title="모두 열기"
          >
            <Maximize2 size={10} />
            모두 열기
          </button>
          <button
            onClick={handleCloseAll}
            className="flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] text-outline transition hover:bg-surface-container hover:text-on-surface"
            title="모두 닫기"
          >
            <Minimize2 size={10} />
            모두 닫기
          </button>
        </div>

        {/* Document list */}
        <div className="flex-1 overflow-y-auto">
          {assets.map((artifact) => {
            const isOpen = openIds.has(artifact.id);
            const isFocused = isOpen && zStack[zStack.length - 1] === artifact.id;
            return (
              <div
                key={artifact.id}
                role="button"
                tabIndex={0}
                onClick={() => handleSidebarClick(artifact)}
                onKeyDown={(e) => e.key === 'Enter' && handleSidebarClick(artifact)}
                className={cn(
                  'flex w-full cursor-pointer items-start gap-2 border-b border-white/[0.03] px-3 py-2 text-left transition',
                  isFocused
                    ? 'bg-primary/10 text-on-surface'
                    : isOpen
                      ? 'bg-surface-container text-on-surface-variant'
                      : 'text-outline hover:bg-surface-container hover:text-on-surface',
                )}
              >
                <span className="mt-0.5 shrink-0 text-[13px]">{getFileIcon(artifact)}</span>
                <div className="min-w-0 flex-1">
                  <div className="truncate text-[12px] font-medium">{artifact.title}</div>
                  <div className="truncate text-[10px] text-outline">{artifact.subtitle || artifact.path}</div>
                </div>
                {isOpen && (
                  <button
                    onClick={(e) => { e.stopPropagation(); handleCloseWindow(artifact.id); }}
                    className="mt-0.5 shrink-0 rounded p-0.5 text-outline transition hover:bg-surface-container-high hover:text-on-surface"
                  >
                    <X size={10} />
                  </button>
                )}
              </div>
            );
          })}
        </div>
      </aside>

      {/* ── Main area: floating windows ── */}
      <div ref={containerRef} className="relative flex-1">
        {windows.length === 0 && (
          <div className="flex h-full flex-col items-center justify-center gap-3 text-outline">
            <FolderOpen size={48} className="opacity-30" />
            <div className="text-[13px]">좌측 목록에서 문서를 클릭하면 열립니다</div>
          </div>
        )}

        <AnimatePresence>
          {windows.map((win) => (
            <ExplorerViewer
              key={win.id}
              artifact={win.artifact}
              originRect={win.originRect}
              zIndex={30 + zStack.indexOf(win.id)}
              isFocused={zStack[zStack.length - 1] === win.id}
              layout={layouts[win.id] ?? null}
              onClose={() => handleCloseWindow(win.id)}
              onFocus={() => handleFocusWindow(win.id)}
              onAskArtifact={onAskArtifact}
            />
          ))}
        </AnimatePresence>

        {/* Layout toolbar */}
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
    </div>
  );
}
