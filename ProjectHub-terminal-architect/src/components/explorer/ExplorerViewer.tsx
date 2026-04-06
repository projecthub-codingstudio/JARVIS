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
