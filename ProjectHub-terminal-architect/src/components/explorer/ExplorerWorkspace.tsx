import React, { useCallback, useEffect, useState } from 'react';
import { AnimatePresence } from 'motion/react';
import { apiClient } from '../../lib/api-client';
import { fileNodeToArtifact } from '../../lib/file-utils';
import { ExplorerTree } from './ExplorerTree';
import { ExplorerGrid } from './ExplorerGrid';
import { ExplorerViewer } from './ExplorerViewer';
import type { Artifact, FileNode } from '../../types';

interface OpenWindow {
  id: string;
  artifact: Artifact;
  originRect: DOMRect;
}

export function ExplorerWorkspace() {
  const [currentPath, setCurrentPath] = useState('');
  const [entries, setEntries] = useState<FileNode[]>([]);
  const [loading, setLoading] = useState(false);
  const [windows, setWindows] = useState<OpenWindow[]>([]);
  const [zStack, setZStack] = useState<string[]>([]); // ordered by z-index, last = top

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
    const artifact = fileNodeToArtifact(file);
    // If already open, just bring to front
    const existing = windows.find((w) => w.id === artifact.id);
    if (existing) {
      setZStack((prev) => [...prev.filter((id) => id !== artifact.id), artifact.id]);
      return;
    }
    const win: OpenWindow = { id: artifact.id, artifact, originRect: rect };
    setWindows((prev) => [...prev, win]);
    setZStack((prev) => [...prev, win.id]);
  }, [windows]);

  const handleCloseWindow = useCallback((id: string) => {
    setWindows((prev) => prev.filter((w) => w.id !== id));
    setZStack((prev) => prev.filter((wid) => wid !== id));
  }, []);

  const handleFocusWindow = useCallback((id: string) => {
    setZStack((prev) => {
      if (prev[prev.length - 1] === id) return prev; // already on top
      return [...prev.filter((wid) => wid !== id), id];
    });
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
        {windows.map((win) => (
          <ExplorerViewer
            key={win.id}
            artifact={win.artifact}
            originRect={win.originRect}
            zIndex={30 + zStack.indexOf(win.id)}
            onClose={() => handleCloseWindow(win.id)}
            onFocus={() => handleFocusWindow(win.id)}
          />
        ))}
      </AnimatePresence>
    </div>
  );
}
