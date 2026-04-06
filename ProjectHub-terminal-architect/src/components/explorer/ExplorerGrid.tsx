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
