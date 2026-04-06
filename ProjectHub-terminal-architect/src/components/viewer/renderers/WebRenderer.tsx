import React from 'react';
import { ExternalLink } from 'lucide-react';
import type { RendererProps } from './TextRenderer';

const WebRenderer: React.FC<RendererProps> = ({ artifact }) => {
  const url = artifact.full_path || artifact.path || '';

  if (!url.startsWith('http')) {
    return (
      <div className="h-full flex items-center justify-center text-on-surface-variant">
        <p>유효하지 않은 URL입니다: {url}</p>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col">
      <div className="flex items-center gap-2 px-4 py-2 bg-surface-highest border-b border-outline/10">
        <span className="text-xs font-mono text-on-surface-variant truncate flex-1">{url}</span>
        <a href={url} target="_blank" rel="noopener noreferrer" className="p-1 hover:text-primary transition-colors">
          <ExternalLink size={14} />
        </a>
      </div>
      <iframe
        src={url}
        sandbox="allow-scripts allow-forms"
        referrerPolicy="no-referrer"
        title={artifact.title}
        className="flex-1 w-full border-0"
      />
    </div>
  );
};

export default WebRenderer;
