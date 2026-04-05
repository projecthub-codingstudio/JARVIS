import React, { useState } from 'react';
import { ZoomIn, ZoomOut, RotateCcw } from 'lucide-react';
import type { RendererProps } from './TextRenderer';

const ZOOM_STEPS = [0.25, 0.5, 0.75, 1, 1.25, 1.5, 2, 3];

const ImageRenderer: React.FC<RendererProps> = ({ artifact, fileUrl }) => {
  const [zoomIndex, setZoomIndex] = useState(3);
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
        <button onClick={() => setZoomIndex(Math.max(0, zoomIndex - 1))} className="p-2 hover:bg-surface-highest transition-colors">
          <ZoomOut size={16} />
        </button>
        <span className="px-3 font-mono text-xs text-on-surface-variant min-w-[4rem] text-center">
          {Math.round(zoom * 100)}%
        </span>
        <button onClick={() => setZoomIndex(Math.min(ZOOM_STEPS.length - 1, zoomIndex + 1))} className="p-2 hover:bg-surface-highest transition-colors">
          <ZoomIn size={16} />
        </button>
        <button onClick={() => setZoomIndex(3)} className="p-2 hover:bg-surface-highest transition-colors ml-2">
          <RotateCcw size={16} />
        </button>
      </div>
    </div>
  );
};

export default ImageRenderer;
