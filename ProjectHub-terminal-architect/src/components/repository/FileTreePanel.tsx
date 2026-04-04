/**
 * FileTreePanel — Directory tree for knowledge_base browsing
 */

import React, { useCallback, useEffect } from 'react';
import {
  ChevronRight,
  ChevronDown,
  Folder,
  FolderOpen,
  FileText,
  FileCode,
  FileSpreadsheet,
  FileImage,
  File,
} from 'lucide-react';
import { cn } from '../../lib/utils';
import { useAppStore } from '../../store/app-store';
import { apiClient } from '../../lib/api-client';
import type { FileNode } from '../../types';

/* ── Icon by extension ── */

function fileIcon(ext?: string | null) {
  switch (ext) {
    case '.py': case '.ts': case '.tsx': case '.js': case '.jsx':
    case '.swift': case '.java': case '.go': case '.rs':
    case '.c': case '.cpp': case '.h': case '.sql': case '.sh':
      return FileCode;
    case '.xlsx': case '.csv': case '.tsv':
      return FileSpreadsheet;
    case '.png': case '.jpg': case '.jpeg': case '.gif': case '.svg': case '.webp':
      return FileImage;
    case '.pdf': case '.md': case '.txt': case '.docx':
    case '.pptx': case '.hwp': case '.hwpx': case '.html':
      return FileText;
    default:
      return File;
  }
}

/* ── Single tree node ── */

interface TreeNodeProps {
  node: FileNode;
  depth: number;
  selectedPath: string | null;
  expandedDirs: string[];
  childrenMap: Record<string, FileNode[]>;
  onSelectFile: (node: FileNode) => void;
  onToggleDir: (path: string) => void;
}

function TreeNode({
  node,
  depth,
  selectedPath,
  expandedDirs,
  childrenMap,
  onSelectFile,
  onToggleDir,
}: TreeNodeProps) {
  const isDir = node.type === 'directory';
  const isExpanded = expandedDirs.includes(node.path);
  const isSelected = selectedPath === node.path;
  const children = childrenMap[node.path];
  const Icon = isDir ? (isExpanded ? FolderOpen : Folder) : fileIcon(node.extension);

  return (
    <div>
      <button
        className={cn(
          'flex w-full items-center gap-1.5 rounded-md px-2 py-1 text-left text-sm transition-colors',
          'hover:bg-white/5',
          isSelected && 'bg-white/10 text-white font-medium',
          !isSelected && 'text-white/70',
        )}
        style={{ paddingLeft: `${depth * 16 + 8}px` }}
        onClick={() => (isDir ? onToggleDir(node.path) : onSelectFile(node))}
      >
        {isDir ? (
          isExpanded ? (
            <ChevronDown className="h-3.5 w-3.5 shrink-0 text-white/40" />
          ) : (
            <ChevronRight className="h-3.5 w-3.5 shrink-0 text-white/40" />
          )
        ) : (
          <span className="w-3.5" />
        )}
        <Icon className="h-4 w-4 shrink-0 text-white/50" />
        <span className="truncate">{node.name}</span>
      </button>

      {isDir && isExpanded && children && (
        <div>
          {children.map((child) => (
            <TreeNode
              key={child.path}
              node={child}
              depth={depth + 1}
              selectedPath={selectedPath}
              expandedDirs={expandedDirs}
              childrenMap={childrenMap}
              onSelectFile={onSelectFile}
              onToggleDir={onToggleDir}
            />
          ))}
        </div>
      )}

      {isDir && isExpanded && !children && (
        <div
          className="text-xs text-white/30 italic"
          style={{ paddingLeft: `${(depth + 1) * 16 + 8}px` }}
        >
          불러오는 중...
        </div>
      )}
    </div>
  );
}

/* ── FileTreePanel ── */

interface FileTreePanelProps {
  onSelectFile: (node: FileNode) => void;
}

export function FileTreePanel({ onSelectFile }: FileTreePanelProps) {
  const fileTree = useAppStore((s) => s.fileTree);
  const fileTreeCache = useAppStore((s) => s.fileTreeCache);
  const selectedFilePath = useAppStore((s) => s.selectedFilePath);
  const expandedDirs = useAppStore((s) => s.expandedDirs);
  const setFileTree = useAppStore((s) => s.setFileTree);
  const cacheDirectory = useAppStore((s) => s.cacheDirectory);
  const toggleExpandedDir = useAppStore((s) => s.toggleExpandedDir);

  // Load root on mount
  useEffect(() => {
    if (fileTree.length > 0) return;
    apiClient.browse('').then((res) => {
      setFileTree(res.entries);
      cacheDirectory('', res.entries);
    });
  }, [fileTree.length, setFileTree, cacheDirectory]);

  const handleToggleDir = useCallback(
    async (path: string) => {
      toggleExpandedDir(path);
      // Lazy load children if not cached
      if (!fileTreeCache[path]) {
        const res = await apiClient.browse(path);
        cacheDirectory(path, res.entries);
      }
    },
    [toggleExpandedDir, fileTreeCache, cacheDirectory],
  );

  // Build childrenMap: root entries + all cached subdirectories
  const childrenMap: Record<string, FileNode[]> = { '': fileTree, ...fileTreeCache };

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <div className="border-b border-white/10 px-3 py-2">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-white/50">
          Knowledge Base
        </h3>
      </div>
      <div className="flex-1 overflow-y-auto p-1">
        {fileTree.length === 0 ? (
          <div className="p-4 text-center text-sm text-white/30">불러오는 중...</div>
        ) : (
          fileTree.map((node) => (
            <TreeNode
              key={node.path}
              node={node}
              depth={0}
              selectedPath={selectedFilePath}
              expandedDirs={expandedDirs}
              childrenMap={childrenMap}
              onSelectFile={onSelectFile}
              onToggleDir={handleToggleDir}
            />
          ))
        )}
      </div>
    </div>
  );
}
