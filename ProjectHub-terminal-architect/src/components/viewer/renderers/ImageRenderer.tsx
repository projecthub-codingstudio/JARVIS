import React, { useState } from 'react';
import type { RendererProps } from './TextRenderer';

const ImageRenderer: React.FC<RendererProps> = ({ artifact, fileUrl, scale }) => {
  const [error, setError] = useState(false);
  const zoom = scale || 1;

  if (error || !fileUrl) {
    return (
      <div className="h-full flex items-center justify-center text-on-surface-variant">
        <p>{artifact.preview || '이미지를 불러올 수 없습니다.'}</p>
      </div>
    );
  }

  return (
    <div className="h-full overflow-auto flex items-center justify-center bg-black/20 custom-scrollbar">
      <img
        src={fileUrl}
        alt={artifact.title}
        style={{ transform: `scale(${zoom})`, transformOrigin: 'center', transition: 'transform 0.2s' }}
        onError={() => setError(true)}
        className="max-w-none"
        referrerPolicy="no-referrer"
      />
    </div>
  );
};

export default ImageRenderer;
