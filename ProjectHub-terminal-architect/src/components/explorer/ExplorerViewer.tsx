import React, { useCallback, useEffect, useRef, useState } from 'react';
import { motion } from 'motion/react';
import { GripHorizontal, Maximize2, Minimize2, X } from 'lucide-react';
import { cn } from '../../lib/utils';
import { ViewerShell } from '../viewer/ViewerShell';
import type { Artifact } from '../../types';

/* ── Window size by document type ── */

function getWindowSize(artifact: Artifact): { width: number; height: number } {
  const ext = (artifact.path || artifact.full_path || '').split('.').pop()?.toLowerCase() || '';
  const kind = artifact.viewer_kind?.toLowerCase() || '';

  // PPTX: landscape 16:9
  if (ext === 'pptx' || ext === 'ppt') return { width: 800, height: 500 };
  // XLSX: wide landscape
  if (ext === 'xlsx' || ext === 'xls' || ext === 'csv') return { width: 850, height: 550 };
  // Image: square-ish
  if (kind === 'image') return { width: 700, height: 600 };
  // Code/text: tall
  if (kind === 'code' || kind === 'text') return { width: 650, height: 750 };
  // PDF/DOCX/HWP/MD: A4 portrait
  return { width: 600, height: 850 };
}

interface ExplorerViewerProps {
  artifact: Artifact;
  originRect: DOMRect;
  zIndex: number;
  onClose: () => void;
  onFocus: () => void;
}

export function ExplorerViewer({ artifact, originRect, zIndex, onClose, onFocus }: ExplorerViewerProps) {
  const windowSize = getWindowSize(artifact);
  const containerRef = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState<{ x: number; y: number } | null>(null);
  const [maximized, setMaximized] = useState(false);
  const dragging = useRef(false);
  const dragOffset = useRef({ x: 0, y: 0 });

  // Center the window initially, offset slightly based on z-index for cascade
  const cascade = (zIndex - 30) * 20;
  const initialX = typeof window !== 'undefined'
    ? Math.max(10, (window.innerWidth - windowSize.width) / 2 + cascade)
    : 100;
  const initialY = typeof window !== 'undefined'
    ? Math.max(10, (window.innerHeight - windowSize.height) / 2 + cascade - 40)
    : 60;

  const currentX = pos?.x ?? initialX;
  const currentY = pos?.y ?? initialY;

  const handlePointerDown = useCallback((e: React.PointerEvent) => {
    if (maximized) return;
    dragging.current = true;
    dragOffset.current = { x: e.clientX - currentX, y: e.clientY - currentY };
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
    onFocus();
  }, [currentX, currentY, onFocus]);

  const handlePointerMove = useCallback((e: React.PointerEvent) => {
    if (!dragging.current) return;
    setPos({
      x: e.clientX - dragOffset.current.x,
      y: e.clientY - dragOffset.current.y,
    });
  }, []);

  const handlePointerUp = useCallback(() => {
    dragging.current = false;
  }, []);

  return (
    <motion.div
      ref={containerRef}
      className="absolute flex flex-col overflow-hidden border border-white/10 bg-surface shadow-2xl"
      style={{ zIndex, borderRadius: 8 }}
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
        width: maximized ? '100%' : windowSize.width,
        height: maximized ? '100%' : windowSize.height,
        opacity: 1,
        borderRadius: maximized ? 0 : 8,
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
      {/* Title bar — draggable */}
      <div
        className={cn('flex h-8 shrink-0 items-center justify-between bg-surface-container-high px-2 select-none', maximized ? 'cursor-default' : 'cursor-move')}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
      >
        <div className="flex items-center gap-2">
          <GripHorizontal size={12} className="text-outline/50" />
          <span className="truncate text-[11px] text-on-surface-variant">{artifact.title}</span>
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={(e) => { e.stopPropagation(); setMaximized((v) => !v); }}
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
        />
      </div>
    </motion.div>
  );
}
