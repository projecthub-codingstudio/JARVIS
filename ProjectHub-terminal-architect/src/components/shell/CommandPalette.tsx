import React, { useCallback, useEffect, useRef, useState } from 'react';
import { motion } from 'motion/react';
import {
  ArrowRight,
  BarChart3,
  FileSearch2,
  FileText,
  FolderSearch,
  LayoutDashboard,
  Search,
  TerminalSquare,
  Workflow,
} from 'lucide-react';
import { cn } from '../../lib/utils';
import { apiClient } from '../../lib/api-client';
import type { FileNode, ViewState } from '../../types';

interface CommandPaletteProps {
  open: boolean;
  onClose: () => void;
  onNavigate: (view: ViewState) => void;
  onSendMessage: (text: string) => void;
  onNavigateToFile: (path: string) => void;
}

const NAV_ITEMS: { key: ViewState; label: string; icon: React.ElementType }[] = [
  { key: 'home', label: 'Dashboard', icon: LayoutDashboard },
  { key: 'terminal', label: 'Terminal', icon: TerminalSquare },
  { key: 'explorer', label: 'Explorer', icon: FolderSearch },
  { key: 'documents', label: 'Documents', icon: FileSearch2 },
  { key: 'skills', label: 'Skills', icon: Workflow },
  { key: 'admin', label: 'Admin', icon: BarChart3 },
];

export function CommandPalette({ open, onClose, onNavigate, onSendMessage, onNavigateToFile }: CommandPaletteProps) {
  const [query, setQuery] = useState('');
  const [files, setFiles] = useState<FileNode[]>([]);
  const [searching, setSearching] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open) {
      setQuery('');
      setFiles([]);
      setSelectedIndex(0);
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [open]);

  useEffect(() => {
    if (!query.trim()) {
      setFiles([]);
      return;
    }
    const timer = setTimeout(async () => {
      setSearching(true);
      try {
        const response = await apiClient.browse('');
        const flatFiles = response.entries.filter(
          (entry) =>
            entry.type === 'file' &&
            entry.name.toLowerCase().includes(query.toLowerCase()),
        );
        setFiles(flatFiles.slice(0, 8));
      } catch {
        setFiles([]);
      } finally {
        setSearching(false);
      }
    }, 200);
    return () => clearTimeout(timer);
  }, [query]);

  const filteredNav = query.trim()
    ? NAV_ITEMS.filter((item) =>
        item.label.toLowerCase().includes(query.toLowerCase()),
      )
    : NAV_ITEMS;

  const allItems = [
    ...filteredNav.map((nav) => ({ kind: 'nav' as const, ...nav })),
    ...files.map((file) => ({ kind: 'file' as const, ...file })),
  ];

  useEffect(() => {
    setSelectedIndex(0);
  }, [query]);

  const handleKeyDown = useCallback(
    (event: React.KeyboardEvent) => {
      if (event.key === 'Escape') {
        onClose();
        return;
      }
      if (event.key === 'ArrowDown') {
        event.preventDefault();
        setSelectedIndex((i) => Math.min(i + 1, allItems.length - 1));
        return;
      }
      if (event.key === 'ArrowUp') {
        event.preventDefault();
        setSelectedIndex((i) => Math.max(i - 1, 0));
        return;
      }
      if (event.key === 'Enter') {
        event.preventDefault();
        const item = allItems[selectedIndex];
        if (item) {
          if (item.kind === 'nav') {
            onNavigate(item.key);
            onClose();
          } else if (item.kind === 'file') {
            onNavigateToFile(item.path);
            onClose();
          }
        } else if (query.trim()) {
          onSendMessage(query.trim());
          onClose();
        }
        return;
      }
    },
    [allItems, selectedIndex, query, onClose, onNavigate, onSendMessage, onNavigateToFile],
  );

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[100] flex items-start justify-center pt-[15vh]" onClick={onClose}>
      <div className="absolute inset-0 bg-black/60" />
      <motion.div
        initial={{ opacity: 0, scale: 0.96, y: -8 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.96, y: -8 }}
        transition={{ duration: 0.15 }}
        className="relative w-full max-w-lg overflow-hidden border border-white/10 bg-surface-container-low shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-3 border-b border-white/5 px-4 py-3">
          <Search size={16} className="text-outline" />
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Navigate, search files, or ask a question..."
            className="w-full bg-transparent text-sm text-on-surface outline-none placeholder:text-outline"
          />
          <kbd className="rounded border border-white/10 px-1.5 py-0.5 text-[10px] font-mono text-outline">ESC</kbd>
        </div>

        <div className="max-h-72 overflow-y-auto py-2">
          {filteredNav.length > 0 && (
            <div className="px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-outline">
              Navigate
            </div>
          )}
          {filteredNav.map((nav, index) => {
            const Icon = nav.icon;
            return (
              <button
                key={nav.key}
                onClick={() => { onNavigate(nav.key); onClose(); }}
                className={cn(
                  'flex w-full items-center gap-3 px-4 py-2 text-sm transition',
                  selectedIndex === index
                    ? 'bg-surface-container text-primary'
                    : 'text-on-surface-variant hover:bg-surface-container-high',
                )}
              >
                <Icon size={14} />
                <span>{nav.label}</span>
              </button>
            );
          })}

          {files.length > 0 && (
            <>
              <div className="mt-2 px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-outline">
                Files
              </div>
              {files.map((file, i) => {
                const globalIndex = filteredNav.length + i;
                return (
                  <button
                    key={file.path}
                    onClick={() => { onNavigateToFile(file.path); onClose(); }}
                    className={cn(
                      'flex w-full items-center gap-3 px-4 py-2 text-sm transition',
                      selectedIndex === globalIndex
                        ? 'bg-surface-container text-primary'
                        : 'text-on-surface-variant hover:bg-surface-container-high',
                    )}
                  >
                    <FileText size={14} />
                    <span className="truncate">{file.name}</span>
                    <span className="ml-auto truncate text-[11px] text-outline">{file.path}</span>
                  </button>
                );
              })}
            </>
          )}

          {query.trim() && (
            <div className="mt-2 border-t border-white/5 px-3 pt-2">
              <button
                onClick={() => { onSendMessage(query.trim()); onClose(); }}
                className={cn(
                  'flex w-full items-center gap-3 px-4 py-2 text-sm transition',
                  selectedIndex === allItems.length
                    ? 'bg-surface-container text-primary'
                    : 'text-on-surface-variant hover:bg-surface-container-high',
                )}
              >
                <ArrowRight size={14} />
                <span>Ask JARVIS: &ldquo;{query}&rdquo;</span>
              </button>
            </div>
          )}

          {searching && (
            <div className="px-4 py-2 text-xs text-outline">Searching...</div>
          )}
        </div>
      </motion.div>
    </div>
  );
}
