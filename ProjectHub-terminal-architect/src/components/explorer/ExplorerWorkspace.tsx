import React, { useCallback, useEffect, useState } from 'react';
import { AnimatePresence } from 'motion/react';
import { apiClient } from '../../lib/api-client';
import { fileNodeToArtifact } from '../../lib/file-utils';
import { ExplorerTree } from './ExplorerTree';
import { ExplorerGrid } from './ExplorerGrid';
import { ExplorerViewer } from './ExplorerViewer';
import type { Artifact, FileNode } from '../../types';

export function ExplorerWorkspace() {
  const [currentPath, setCurrentPath] = useState('');
  const [entries, setEntries] = useState<FileNode[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedArtifact, setSelectedArtifact] = useState<Artifact | null>(null);
  const [originRect, setOriginRect] = useState<DOMRect | null>(null);

  const loadDirectory = useCallback(async (path: string) => {
    setLoading(true);
    try {
      const response = await apiClient.browse(path);
      const sorted = [...response.entries].sort((a, b) => {
        if (a.type !== b.type) return a.type === 'directory' ? -1 : 1;
        return a.name.localeCompare(b.name);
      });
      setEntries(sorted);
    } catch {
      setEntries([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadDirectory(currentPath);
  }, [currentPath, loadDirectory]);

  const handleNavigate = useCallback((path: string) => {
    setCurrentPath(path);
  }, []);

  const handleOpenFile = useCallback((file: FileNode, rect: DOMRect) => {
    setSelectedArtifact(fileNodeToArtifact(file));
    setOriginRect(rect);
  }, []);

  const handleClose = useCallback(() => {
    setSelectedArtifact(null);
    setOriginRect(null);
  }, []);

  return (
    <div className="relative flex h-full overflow-hidden bg-surface">
      <ExplorerTree currentPath={currentPath} onSelectDirectory={handleNavigate} />
      <ExplorerGrid
        currentPath={currentPath}
        entries={entries}
        loading={loading}
        onNavigate={handleNavigate}
        onOpenFile={handleOpenFile}
      />
      <AnimatePresence>
        {selectedArtifact && originRect && (
          <ExplorerViewer
            key={selectedArtifact.id}
            artifact={selectedArtifact}
            originRect={originRect}
            onClose={handleClose}
          />
        )}
      </AnimatePresence>
    </div>
  );
}
