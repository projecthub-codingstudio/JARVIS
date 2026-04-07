import React from 'react';
import {
  Bookmark,
  Braces,
  Code2,
  File,
  FileText,
  Folder,
  Image,
  Presentation,
  Sheet,
} from 'lucide-react';
import { cn } from '../../lib/utils';
import { formatFileSize, getFileColor } from '../../lib/file-utils';
import type { FileNode } from '../../types';

function getFileIcon(node: FileNode) {
  if (node.type === 'directory') return Folder;
  const ext = (node.extension ?? '').toLowerCase();
  if (['.xlsx', '.xls', '.csv'].includes(ext)) return Sheet;
  if (['.pptx', '.ppt'].includes(ext)) return Presentation;
  if (['.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.bmp', '.heic'].includes(ext)) return Image;
  if (['.json', '.yaml', '.yml', '.toml', '.xml'].includes(ext)) return Braces;
  if (['.py', '.ts', '.tsx', '.js', '.jsx', '.mjs', '.cjs', '.swift', '.java', '.go', '.rs',
       '.c', '.cpp', '.h', '.sh', '.sql', '.css', '.scss'].includes(ext)) return Code2;
  if (['.pdf', '.md', '.txt', '.docx', '.doc', '.hwp', '.hwpx', '.pptx', '.log'].includes(ext)) return FileText;
  return File;
}

interface FileIconCardProps {
  node: FileNode;
  onClick: (node: FileNode, rect: DOMRect) => void;
  bookmarked?: boolean;
}

export function FileIconCard({ node, onClick, bookmarked }: FileIconCardProps) {
  const Icon = getFileIcon(node);
  const color = node.type === 'directory' ? '#eab308' : getFileColor(node.extension);
  const size = formatFileSize(node.size);

  const handleClick = (e: React.MouseEvent<HTMLButtonElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    onClick(node, rect);
  };

  return (
    <button
      onClick={handleClick}
      className={cn(
        'group relative flex flex-col items-center gap-2 rounded-lg border p-4 text-center transition hover:scale-[1.02]',
        bookmarked
          ? 'border-primary/40 bg-primary/5 hover:border-primary/60 hover:bg-primary/10'
          : 'border-white/5 bg-surface-container-low hover:border-primary/30 hover:bg-surface-container',
      )}
    >
      {bookmarked && (
        <Bookmark size={10} className="absolute top-1.5 right-1.5 text-primary fill-primary" />
      )}
      <Icon size={36} style={{ color }} />
      <span className="w-full truncate text-[11px] text-on-surface">{node.name}</span>
      {size && <span className="text-[9px] text-outline">{size}</span>}
    </button>
  );
}
