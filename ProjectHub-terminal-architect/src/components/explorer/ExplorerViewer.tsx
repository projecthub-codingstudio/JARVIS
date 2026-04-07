import React, { useCallback, useRef, useState } from 'react';
import { motion } from 'motion/react';
import { GripHorizontal, Maximize2, Minimize2, X } from 'lucide-react';
import { cn } from '../../lib/utils';
import { ViewerShell } from '../viewer/ViewerShell';
import type { Artifact } from '../../types';

/* ── Window size by document type ── */

export function getDefaultWindowSize(artifact: Artifact): { width: number; height: number } {
  const ext = (artifact.path || artifact.full_path || '').split('.').pop()?.toLowerCase() || '';
  const kind = artifact.viewer_kind?.toLowerCase() || '';

  // Available viewport (minus sidebar ~140px, some padding)
  const maxH = typeof window !== 'undefined' ? window.innerHeight - 80 : 900;
  const maxW = typeof window !== 'undefined' ? window.innerWidth - 200 : 1000;

  // PPT: 16:9 ratio, fill viewport width
  if (ext === 'pptx' || ext === 'ppt') {
    const w = Math.min(maxW, 1100);
    const h = Math.min(Math.round(w * 9 / 16) + 80, maxH); // +80 for toolbar/bottom bar
    return { width: w, height: h };
  }
  // Spreadsheet: wide landscape, fill viewport
  if (ext === 'xlsx' || ext === 'xls' || ext === 'csv') {
    const w = Math.min(maxW, 1200);
    const h = Math.min(Math.round(w * 0.6), maxH);
    return { width: w, height: h };
  }
  if (kind === 'image') return { width: Math.min(700, maxW), height: Math.min(600, maxH) };
  if (kind === 'code' || kind === 'text') return { width: Math.min(650, maxW), height: Math.min(750, maxH) };

  // PDF / documents: A4 ratio (1:1.414), fit one full page in viewport
  if (ext === 'pdf' || ext === 'docx' || ext === 'doc' || ext === 'hwp' || ext === 'hwpx') {
    const h = Math.min(maxH, 960);
    const w = Math.min(Math.round(h / 1.414) + 40, maxW); // +40 for scrollbar/padding
    return { width: w, height: h };
  }

  return { width: Math.min(650, maxW), height: Math.min(850, maxH) };
}

export interface WindowLayout {
  x: number;
  y: number;
  width: number;
  height: number;
}

interface ExplorerViewerProps {
  artifact: Artifact;
  originRect: DOMRect;
  zIndex: number;
  isFocused?: boolean;
  layout?: WindowLayout | null;
  onClose: () => void;
  onFocus: () => void;
  onAskArtifact?: (artifact: Artifact, prompt: string) => Promise<void> | void;
}

const MIN_WIDTH = 300;
const MIN_HEIGHT = 200;

export function ExplorerViewer({ artifact, originRect, zIndex, isFocused, layout, onClose, onFocus, onAskArtifact }: ExplorerViewerProps) {
  const defaultSize = getDefaultWindowSize(artifact);
  const [pos, setPos] = useState<{ x: number; y: number } | null>(null);
  const [size, setSize] = useState<{ width: number; height: number } | null>(null);
  const [maximized, setMaximized] = useState(false);
  const dragging = useRef(false);
  const resizing = useRef(false);
  const dragOffset = useRef({ x: 0, y: 0 });
  const resizeStart = useRef({ x: 0, y: 0, w: 0, h: 0 });

  // Effective values: layout prop > local state > defaults
  const effWidth = layout?.width ?? size?.width ?? defaultSize.width;
  const effHeight = layout?.height ?? size?.height ?? defaultSize.height;

  const cascade = (zIndex - 30) * 20;
  const defaultX = typeof window !== 'undefined'
    ? Math.max(10, (window.innerWidth - effWidth) / 2 + cascade)
    : 100;
  const defaultY = typeof window !== 'undefined'
    ? Math.max(10, (window.innerHeight - effHeight) / 2 + cascade - 40)
    : 60;

  const currentX = layout?.x ?? pos?.x ?? defaultX;
  const currentY = layout?.y ?? pos?.y ?? defaultY;

  // ── Drag ──
  const handleDragDown = useCallback((e: React.PointerEvent) => {
    if (maximized) return;
    dragging.current = true;
    dragOffset.current = { x: e.clientX - currentX, y: e.clientY - currentY };
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
    onFocus();
  }, [currentX, currentY, onFocus, maximized]);

  const handleDragMove = useCallback((e: React.PointerEvent) => {
    if (!dragging.current) return;
    setPos({ x: e.clientX - dragOffset.current.x, y: e.clientY - dragOffset.current.y });
  }, []);

  const handleDragUp = useCallback(() => { dragging.current = false; }, []);

  // ── Resize ──
  const handleResizeDown = useCallback((e: React.PointerEvent) => {
    if (maximized) return;
    e.stopPropagation();
    resizing.current = true;
    resizeStart.current = { x: e.clientX, y: e.clientY, w: effWidth, h: effHeight };
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
    onFocus();
  }, [effWidth, effHeight, onFocus, maximized]);

  const handleResizeMove = useCallback((e: React.PointerEvent) => {
    if (!resizing.current) return;
    const dx = e.clientX - resizeStart.current.x;
    const dy = e.clientY - resizeStart.current.y;
    setSize({
      width: Math.max(MIN_WIDTH, resizeStart.current.w + dx),
      height: Math.max(MIN_HEIGHT, resizeStart.current.h + dy),
    });
  }, []);

  const handleResizeUp = useCallback(() => { resizing.current = false; }, []);

  return (
    <motion.div
      className={cn(
        'absolute flex flex-col overflow-hidden bg-surface shadow-2xl transition-[border-color]',
        isFocused ? 'border border-primary/50' : 'border border-white/10',
      )}
      style={{ zIndex, borderRadius: maximized ? 0 : 8 }}
      initial={{
        x: originRect.left,
        y: originRect.top,
        width: originRect.width,
        height: originRect.height,
        opacity: 0,
      }}
      animate={{
        x: maximized ? 0 : currentX,
        y: maximized ? 0 : currentY,
        width: maximized ? '100%' : effWidth,
        height: maximized ? '100%' : effHeight,
        opacity: 1,
      }}
      exit={{
        x: originRect.left,
        y: originRect.top,
        width: originRect.width,
        height: originRect.height,
        opacity: 0,
      }}
      transition={{ duration: 0.3, ease: 'easeInOut' }}
      onPointerDown={onFocus}
    >
      {/* Title bar */}
      <div
        className={cn(
          'flex h-8 shrink-0 items-center justify-between px-2 select-none transition-colors',
          isFocused ? 'bg-primary/15' : 'bg-surface-container-high',
          maximized ? 'cursor-default' : 'cursor-move',
        )}
        onPointerDown={handleDragDown}
        onPointerMove={handleDragMove}
        onPointerUp={handleDragUp}
      >
        <div className="flex items-center gap-2 min-w-0">
          <GripHorizontal size={12} className="shrink-0 text-outline/50" />
          <span className={cn('truncate text-[11px]', isFocused ? 'text-on-surface' : 'text-on-surface-variant')}>{artifact.title}</span>
        </div>
        <div className="flex items-center gap-1 shrink-0">
          <button
            onClick={(e) => { e.stopPropagation(); setMaximized((v) => !v); onFocus(); }}
            onPointerDown={(e) => e.stopPropagation()}
            className="rounded-full p-0.5 text-outline transition hover:bg-surface-container hover:text-on-surface"
            title={maximized ? 'Restore' : 'Maximize'}
          >
            {maximized ? <Minimize2 size={12} /> : <Maximize2 size={12} />}
          </button>
          <button
            onClick={(e) => { e.stopPropagation(); onClose(); }}
            onPointerDown={(e) => e.stopPropagation()}
            className="rounded-full p-0.5 text-outline transition hover:bg-surface-container hover:text-on-surface"
          >
            <X size={14} />
          </button>
        </div>
      </div>

      {/* Viewer content */}
      <div className="flex-1 overflow-hidden">
        <ViewerShell
          artifact={artifact}
          artifacts={[]}
          citations={[]}
          isMobile={false}
          hideLibrary
          onAskArtifact={onAskArtifact}
        />
      </div>

      {/* Resize handle (bottom-right corner) */}
      {!maximized && (
        <div
          className="absolute bottom-0 right-0 h-4 w-4 cursor-nwse-resize"
          onPointerDown={handleResizeDown}
          onPointerMove={handleResizeMove}
          onPointerUp={handleResizeUp}
        >
          <svg width="16" height="16" viewBox="0 0 16 16" className="text-outline/30">
            <path d="M14 14L8 14M14 14L14 8M14 14L6 6" stroke="currentColor" strokeWidth="1.5" fill="none" />
          </svg>
        </div>
      )}
    </motion.div>
  );
}
