/**
 * RepositoryWorkspace — File tree + viewer layout
 */

import React, { useCallback, useEffect, useMemo } from 'react';
import { FolderOpen } from 'lucide-react';
import { useAppStore } from '../../store/app-store';
import { apiClient } from '../../lib/api-client';
import { FileTreePanel } from './FileTreePanel';
import { ViewerShell } from '../viewer/ViewerShell';
import type { FileNode } from '../../types';
import { fileNodeToArtifact } from '../../lib/file-utils';

/* ── RepositoryWorkspace ── */

interface RepositoryWorkspaceProps {
  initialPath?: string | null;
  onClearInitialPath?: () => void;
}

export function RepositoryWorkspace({ initialPath, onClearInitialPath }: RepositoryWorkspaceProps) {
  const selectedFilePath = useAppStore((s) => s.selectedFilePath);
  const setSelectedFilePath = useAppStore((s) => s.setSelectedFilePath);
  const expandToPath = useAppStore((s) => s.expandToPath);
  const fileTreeCache = useAppStore((s) => s.fileTreeCache);
  const cacheDirectory = useAppStore((s) => s.cacheDirectory);

  // Handle initialPath from Terminal citation navigation
  useEffect(() => {
    if (!initialPath) return;

    // Expand tree to the target file
    expandToPath(initialPath);

    // Lazy-load all parent directories
    const parts = initialPath.split('/');
    for (let i = 1; i < parts.length; i++) {
      const dirPath = parts.slice(0, i).join('/');
      if (!fileTreeCache[dirPath]) {
        apiClient.browse(dirPath).then((res) => cacheDirectory(dirPath, res.entries));
      }
    }

    onClearInitialPath?.();
  }, [initialPath, expandToPath, fileTreeCache, cacheDirectory, onClearInitialPath]);

  const handleSelectFile = useCallback(
    (node: FileNode) => {
      setSelectedFilePath(node.path);
    },
    [setSelectedFilePath],
  );

  const selectedArtifact = useMemo(() => {
    if (!selectedFilePath) return null;
    const ext = selectedFilePath.includes('.')
      ? '.' + selectedFilePath.split('.').pop()!.toLowerCase()
      : null;
    return fileNodeToArtifact({
      name: selectedFilePath.split('/').pop() || selectedFilePath,
      path: selectedFilePath,
      type: 'file',
      extension: ext,
    });
  }, [selectedFilePath]);

  return (
    <div className="flex h-full">
      {/* Left: File tree */}
      <div className="w-96 shrink-0 border-r border-white/10 bg-black/20">
        <FileTreePanel onSelectFile={handleSelectFile} />
      </div>

      {/* Right: Viewer */}
      <div className="flex-1 overflow-hidden">
        {selectedArtifact ? (
          <ViewerShell
            artifact={selectedArtifact}
            artifacts={[]}
            citations={[]}
            isMobile={false}
            isLoading={false}
            hideLibrary
          />
        ) : (
          <div className="flex h-full flex-col items-center justify-center gap-3 text-white/30">
            <FolderOpen className="h-12 w-12" />
            <p className="text-sm">파일을 선택하세요</p>
          </div>
        )}
      </div>
    </div>
  );
}
