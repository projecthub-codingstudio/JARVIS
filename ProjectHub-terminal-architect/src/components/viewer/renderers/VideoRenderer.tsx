import React from 'react';
import type { RendererProps } from './TextRenderer';

const EXT_TO_MIME: Record<string, string> = {
  mp4: 'video/mp4', webm: 'video/webm', mov: 'video/quicktime',
  m4v: 'video/mp4', ogg: 'video/ogg',
};

const VideoRenderer: React.FC<RendererProps> = ({ artifact, fileUrl }) => {
  if (!fileUrl) {
    return (
      <div className="h-full flex items-center justify-center text-on-surface-variant">
        <p>동영상 파일 경로가 없습니다.</p>
      </div>
    );
  }

  const ext = (artifact.path || artifact.full_path || '').split('.').pop()?.toLowerCase() || 'mp4';
  const mime = EXT_TO_MIME[ext] || 'video/mp4';

  return (
    <div className="h-full flex items-center justify-center bg-black p-4">
      <video controls className="max-w-full max-h-full" style={{ outline: 'none' }}>
        <source src={fileUrl} type={mime} />
        이 브라우저에서 동영상을 재생할 수 없습니다.
      </video>
    </div>
  );
};

export default VideoRenderer;
