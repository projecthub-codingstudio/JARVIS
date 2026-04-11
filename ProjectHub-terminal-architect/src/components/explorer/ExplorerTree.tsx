import React, { useCallback, useEffect, useState } from 'react';
import { ChevronDown, ChevronRight, Folder, FolderOpen } from 'lucide-react';
import { cn } from '../../lib/utils';
import { apiClient } from '../../lib/api-client';
import type { FileNode } from '../../types';

interface ExplorerTreeProps {
  currentPath: string;
  onSelectDirectory: (path: string) => void;
}

interface DirNode {
  name: string;
  path: string;
  children: DirNode[] | null;
  expanded: boolean;
}

export function ExplorerTree({ currentPath, onSelectDirectory }: ExplorerTreeProps) {
  const [roots, setRoots] = useState<DirNode[]>([]);

  const loadChildren = useCallback(async (path: string): Promise<DirNode[]> => {
    try {
      const response = await apiClient.browse(path);
      return response.entries
        .filter((e) => e.type === 'directory')
        .map((e) => ({ name: e.name, path: e.path, children: null, expanded: false }));
    } catch {
      return [];
    }
  }, []);

  useEffect(() => {
    loadChildren('').then(setRoots);
  }, [loadChildren]);

  const toggleDir = useCallback(async (targetPath: string) => {
    const toggle = async (nodes: DirNode[]): Promise<DirNode[]> => {
      const result: DirNode[] = [];
      for (const node of nodes) {
        if (node.path === targetPath) {
          if (!node.expanded && node.children === null) {
            const children = await loadChildren(node.path);
            result.push({ ...node, expanded: true, children });
          } else {
            result.push({ ...node, expanded: !node.expanded });
          }
        } else {
          const updatedChildren = node.children ? await toggle(node.children) : null;
          result.push({ ...node, children: updatedChildren });
        }
      }
      return result;
    };
    setRoots(await toggle(roots));
  }, [roots, loadChildren]);

  const renderNode = (node: DirNode, depth: number) => {
    const isSelected = node.path === currentPath;
    const Icon = node.expanded ? FolderOpen : Folder;
    const Chevron = node.expanded ? ChevronDown : ChevronRight;

    return (
      <div key={node.path}>
        <button
          onClick={() => {
            onSelectDirectory(node.path);
            if (!node.expanded) toggleDir(node.path);
          }}
          className={cn(
            'flex w-full items-center gap-1 rounded-sm px-1 py-1 text-left text-[11px] transition',
            isSelected
              ? 'bg-surface-container text-primary'
              : 'text-on-surface-variant hover:bg-surface-container-high',
          )}
          style={{ paddingLeft: `${depth * 12 + 4}px` }}
        >
          <Chevron
            size={12}
            className="shrink-0 text-outline cursor-pointer"
            onClick={(e) => { e.stopPropagation(); toggleDir(node.path); }}
          />
          <Icon size={14} className="shrink-0 text-[#eab308]" />
          <span className="truncate">{node.name}</span>
        </button>
        {node.expanded && node.children && node.children.map((child) => renderNode(child, depth + 1))}
      </div>
    );
  };

  return (
    <div className="w-[140px] shrink-0 overflow-y-auto border-r border-white/5 bg-surface-container-high custom-scrollbar">
      <div className="px-3 py-3 text-[10px] font-semibold uppercase tracking-[0.12em] text-outline">
        Folders
      </div>
      <div className="px-1 pb-4">
        <button
          onClick={() => onSelectDirectory('')}
          className={cn(
            'flex w-full items-center gap-1 rounded-sm px-1 py-1 text-left text-[11px] transition',
            currentPath === ''
              ? 'bg-surface-container text-primary'
              : 'text-on-surface-variant hover:bg-surface-container-high',
          )}
        >
          <Folder size={14} className="shrink-0 text-[#eab308]" />
          <span>Root</span>
        </button>
        {roots.map((node) => renderNode(node, 1))}
      </div>
    </div>
  );
}
