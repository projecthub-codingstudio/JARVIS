# Dashboard Functional Items Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make all 8 non-functional dashboard UI elements fully operational — Command Palette (Global Search + Cmd+K), Notifications Bell, Settings Popover, Session Info, Help Popover, Activity shortcut, and live Footer data.

**Architecture:** Each feature is a self-contained React component mounted in App.tsx. Shared behavior (click-outside dismiss, keyboard shortcuts) is extracted into a single `useClickOutside` hook. All popovers follow the same pattern: `useState<boolean>` toggle + conditional render + fade animation via `motion/react`. No external UI library — matches existing codebase conventions.

**Tech Stack:** React 18, TypeScript, Tailwind CSS, Zustand (existing store), motion/react (existing), Lucide icons (existing), existing `/api/browse` and `/api/health` backend endpoints.

---

## File Structure

| Action | Path | Responsibility |
|--------|------|---------------|
| Create | `src/hooks/useClickOutside.ts` | Shared hook: close popover on outside click |
| Create | `src/components/shell/CommandPalette.tsx` | Cmd+K overlay: navigation + file search + query |
| Create | `src/components/shell/NotificationBell.tsx` | Bell icon + log popover with unread badge |
| Create | `src/components/shell/SettingsPopover.tsx` | Settings panel (API URL, health interval, data forget) |
| Create | `src/components/shell/SessionInfo.tsx` | User icon popover showing session details |
| Create | `src/components/shell/HelpPopover.tsx` | Help panel with shortcuts and version info |
| Modify | `src/App.tsx` | Wire all new components, add Cmd+K listener, fix footer, wire Activity button |
| Modify | `src/lib/api-client.ts` | Add `forgetData()` method for Settings |
| Modify | `src/store/app-store.ts` | Add `lastHealthLatency`, `clearLogs`, `lastLogReadCount` state |

---

### Task 1: useClickOutside Hook

**Files:**
- Create: `src/hooks/useClickOutside.ts`

- [ ] **Step 1: Create the hook**

```ts
import { useEffect, useRef, type RefObject } from 'react';

export function useClickOutside<T extends HTMLElement>(
  handler: () => void,
): RefObject<T | null> {
  const ref = useRef<T | null>(null);

  useEffect(() => {
    const listener = (event: MouseEvent | TouchEvent) => {
      if (!ref.current || ref.current.contains(event.target as Node)) return;
      handler();
    };
    document.addEventListener('mousedown', listener);
    document.addEventListener('touchstart', listener);
    return () => {
      document.removeEventListener('mousedown', listener);
      document.removeEventListener('touchstart', listener);
    };
  }, [handler]);

  return ref;
}
```

- [ ] **Step 2: Commit**

```bash
git add ProjectHub-terminal-architect/src/hooks/useClickOutside.ts
git commit -m "feat: add useClickOutside hook for popover dismiss"
```

---

### Task 2: Store Extensions (lastHealthLatency, clearLogs, notification tracking)

**Files:**
- Modify: `src/store/app-store.ts`

- [ ] **Step 1: Add new state and actions to the store interface and implementation**

Add these fields to the `AppState` interface after the existing `logs` field (line 8):

```ts
lastHealthLatency: number | null;
lastLogReadCount: number;
```

Add these actions after `addLog` (line 36):

```ts
setLastHealthLatency: (ms: number) => void;
clearLogs: () => void;
markLogsRead: () => void;
```

Add initial values after `logs: []` (line 50):

```ts
lastHealthLatency: null,
lastLogReadCount: 0,
```

Add action implementations after the `addLog` implementation (line 90):

```ts
setLastHealthLatency: (ms) => set({ lastHealthLatency: ms }),
clearLogs: () => set({ logs: [], lastLogReadCount: 0 }),
markLogsRead: () => set((state) => ({ lastLogReadCount: state.logs.length })),
```

- [ ] **Step 2: Commit**

```bash
git add ProjectHub-terminal-architect/src/store/app-store.ts
git commit -m "feat: add health latency, log clear, and notification tracking to store"
```

---

### Task 3: API Client — Add forgetData method

**Files:**
- Modify: `src/lib/api-client.ts`

- [ ] **Step 1: Add forgetData method to apiClient**

Add after the `getExtractedText` method (after line 258):

```ts
async forgetData(scope: 'all' | 'conversations' | 'session_events' | 'task_logs'): Promise<{ deleted: Record<string, number> }> {
  const res = await fetch(`${API_BASE_URL}/api/data/forget`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ scope }),
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Forget data failed: ${res.status} ${detail}`);
  }
  return res.json();
},
```

- [ ] **Step 2: Commit**

```bash
git add ProjectHub-terminal-architect/src/lib/api-client.ts
git commit -m "feat: add forgetData API method for data privacy"
```

---

### Task 4: CommandPalette (Global Search + Cmd+K)

**Files:**
- Create: `src/components/shell/CommandPalette.tsx`
- Modify: `src/App.tsx`

- [ ] **Step 1: Create CommandPalette component**

```tsx
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { motion } from 'motion/react';
import {
  ArrowRight,
  Command,
  FileText,
  FolderOpen,
  House,
  Search,
  TerminalSquare,
  Workflow,
  BarChart3,
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
  { key: 'home', label: 'Home', icon: House },
  { key: 'terminal', label: 'Terminal', icon: TerminalSquare },
  { key: 'repository', label: 'Repository', icon: FolderOpen },
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
    ...filteredNav.map((nav) => ({ type: 'nav' as const, ...nav })),
    ...files.map((file) => ({ type: 'file' as const, ...file })),
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
          if (item.type === 'nav') {
            onNavigate(item.key);
            onClose();
          } else if (item.type === 'file') {
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
```

- [ ] **Step 2: Commit CommandPalette component**

```bash
git add ProjectHub-terminal-architect/src/components/shell/CommandPalette.tsx
git commit -m "feat: add CommandPalette component for global search and navigation"
```

---

### Task 5: NotificationBell

**Files:**
- Create: `src/components/shell/NotificationBell.tsx`

- [ ] **Step 1: Create NotificationBell component**

```tsx
import React, { useCallback, useState } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { Bell, X } from 'lucide-react';
import { cn } from '../../lib/utils';
import { useClickOutside } from '../../hooks/useClickOutside';
import type { SystemLog } from '../../types';

interface NotificationBellProps {
  logs: SystemLog[];
  unreadCount: number;
  onMarkRead: () => void;
  onClearAll: () => void;
}

function getLogDot(type: SystemLog['type']) {
  switch (type) {
    case 'error': return 'bg-[#ffb4ab]';
    case 'warning': return 'bg-tertiary';
    default: return 'bg-secondary';
  }
}

export function NotificationBell({ logs, unreadCount, onMarkRead, onClearAll }: NotificationBellProps) {
  const [open, setOpen] = useState(false);

  const toggle = useCallback(() => {
    setOpen((prev) => {
      if (!prev) onMarkRead();
      return !prev;
    });
  }, [onMarkRead]);

  const ref = useClickOutside<HTMLDivElement>(() => setOpen(false));

  const recent = logs.slice(-20).reverse();

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={toggle}
        className="relative text-primary transition hover:bg-surface-container-high hover:text-on-surface"
      >
        <Bell size={16} />
        {unreadCount > 0 && (
          <span className="absolute -right-1 -top-1 flex h-3.5 w-3.5 items-center justify-center rounded-full bg-[#ffb4ab] text-[8px] font-bold text-black">
            {unreadCount > 9 ? '9+' : unreadCount}
          </span>
        )}
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            transition={{ duration: 0.12 }}
            className="absolute right-0 top-full mt-2 w-80 border border-white/10 bg-surface-container-low shadow-xl"
          >
            <div className="flex items-center justify-between border-b border-white/5 px-3 py-2">
              <span className="text-[11px] font-semibold uppercase tracking-[0.12em] text-on-surface-variant">
                Notifications
              </span>
              {recent.length > 0 && (
                <button
                  onClick={onClearAll}
                  className="text-[10px] text-outline transition hover:text-on-surface"
                >
                  Clear All
                </button>
              )}
            </div>
            <div className="max-h-64 overflow-y-auto custom-scrollbar">
              {recent.length === 0 ? (
                <div className="px-3 py-4 text-center text-xs text-outline">
                  No notifications
                </div>
              ) : (
                recent.map((log) => (
                  <div key={log.id} className="border-b border-white/5 px-3 py-2 last:border-0">
                    <div className="flex items-center gap-2">
                      <span className={cn('inline-flex h-1.5 w-1.5 rounded-full', getLogDot(log.type))} />
                      <span className="text-[10px] font-mono text-outline">
                        {new Date(log.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })}
                      </span>
                      <span className="text-[10px] font-semibold uppercase text-on-surface-variant">{log.type}</span>
                    </div>
                    <p className="mt-1 text-xs leading-relaxed text-on-surface-variant">{log.message}</p>
                  </div>
                ))
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add ProjectHub-terminal-architect/src/components/shell/NotificationBell.tsx
git commit -m "feat: add NotificationBell with unread badge and log popover"
```

---

### Task 6: SettingsPopover

**Files:**
- Create: `src/components/shell/SettingsPopover.tsx`

- [ ] **Step 1: Create SettingsPopover component**

```tsx
import React, { useCallback, useState } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { Settings, Trash2 } from 'lucide-react';
import { cn } from '../../lib/utils';
import { useClickOutside } from '../../hooks/useClickOutside';
import { apiClient } from '../../lib/api-client';

interface SettingsPopoverProps {
  onClearMessages: () => void;
  addLog: (log: { id: string; timestamp: string; type: 'info' | 'warning' | 'error'; message: string }) => void;
}

export function SettingsPopover({ onClearMessages, addLog }: SettingsPopoverProps) {
  const [open, setOpen] = useState(false);
  const [forgetting, setForgetting] = useState(false);
  const ref = useClickOutside<HTMLDivElement>(() => setOpen(false));

  const apiUrl = import.meta.env.VITE_JARVIS_API_URL || 'http://localhost:8000';

  const handleForgetConversations = useCallback(async () => {
    if (forgetting) return;
    setForgetting(true);
    try {
      const result = await apiClient.forgetData('conversations');
      onClearMessages();
      addLog({
        id: `${Date.now()}-forget`,
        timestamp: new Date().toISOString(),
        type: 'info',
        message: `Conversations cleared: ${JSON.stringify(result.deleted)}`,
      });
    } catch (error) {
      addLog({
        id: `${Date.now()}-forget-err`,
        timestamp: new Date().toISOString(),
        type: 'error',
        message: `Failed to clear conversations: ${error instanceof Error ? error.message : 'Unknown error'}`,
      });
    } finally {
      setForgetting(false);
    }
  }, [forgetting, onClearMessages, addLog]);

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((prev) => !prev)}
        className="text-primary transition hover:bg-surface-container-high hover:text-on-surface"
      >
        <Settings size={16} />
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            transition={{ duration: 0.12 }}
            className="absolute right-0 top-full mt-2 w-72 border border-white/10 bg-surface-container-low shadow-xl"
          >
            <div className="border-b border-white/5 px-3 py-2">
              <span className="text-[11px] font-semibold uppercase tracking-[0.12em] text-on-surface-variant">
                Settings
              </span>
            </div>

            <div className="space-y-3 p-3">
              <div>
                <div className="mb-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-outline">
                  API Endpoint
                </div>
                <div className="rounded-sm bg-surface-container-lowest/40 px-2 py-1.5 font-mono text-[11px] text-on-surface-variant">
                  {apiUrl}
                </div>
              </div>

              <div>
                <div className="mb-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-outline">
                  Theme
                </div>
                <div className="text-[11px] text-on-surface-variant">Dark (default)</div>
              </div>

              <div className="border-t border-white/5 pt-3">
                <div className="mb-2 text-[10px] font-semibold uppercase tracking-[0.12em] text-[#ffb4ab]">
                  Data Privacy
                </div>
                <button
                  onClick={handleForgetConversations}
                  disabled={forgetting}
                  className={cn(
                    'flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-[11px] transition',
                    forgetting
                      ? 'cursor-not-allowed text-outline'
                      : 'text-[#ffb4ab] hover:bg-surface-container',
                  )}
                >
                  <Trash2 size={12} />
                  {forgetting ? 'Clearing...' : 'Clear Conversation History'}
                </button>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add ProjectHub-terminal-architect/src/components/shell/SettingsPopover.tsx
git commit -m "feat: add SettingsPopover with API info and data privacy controls"
```

---

### Task 7: SessionInfo (User Icon)

**Files:**
- Create: `src/components/shell/SessionInfo.tsx`

- [ ] **Step 1: Create SessionInfo component**

```tsx
import React, { useState } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { UserRound } from 'lucide-react';
import { cn } from '../../lib/utils';
import { useClickOutside } from '../../hooks/useClickOutside';

interface SessionInfoProps {
  sessionId: string;
  backendStatus: 'checking' | 'online' | 'offline';
  artifactCount: number;
  citationCount: number;
  messageCount: number;
}

export function SessionInfo({ sessionId, backendStatus, artifactCount, citationCount, messageCount }: SessionInfoProps) {
  const [open, setOpen] = useState(false);
  const ref = useClickOutside<HTMLDivElement>(() => setOpen(false));

  const statusColor = backendStatus === 'online' ? 'text-secondary' : backendStatus === 'checking' ? 'text-primary' : 'text-[#ffb4ab]';

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((prev) => !prev)}
        className="flex h-7 w-7 items-center justify-center rounded-sm border border-white/10 bg-surface-container-highest text-outline transition hover:border-primary/30 hover:text-on-surface"
      >
        <UserRound size={14} />
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            transition={{ duration: 0.12 }}
            className="absolute right-0 top-full mt-2 w-64 border border-white/10 bg-surface-container-low shadow-xl"
          >
            <div className="border-b border-white/5 px-3 py-2">
              <span className="text-[11px] font-semibold uppercase tracking-[0.12em] text-on-surface-variant">
                Session
              </span>
            </div>

            <div className="space-y-2 p-3">
              <div className="flex items-center justify-between text-[11px]">
                <span className="text-outline">Session ID</span>
                <span className="font-mono text-on-surface-variant">{sessionId.slice(0, 8)}</span>
              </div>
              <div className="flex items-center justify-between text-[11px]">
                <span className="text-outline">Backend</span>
                <span className={statusColor}>{backendStatus}</span>
              </div>
              <div className="flex items-center justify-between text-[11px]">
                <span className="text-outline">Messages</span>
                <span className="text-primary">{messageCount}</span>
              </div>
              <div className="flex items-center justify-between text-[11px]">
                <span className="text-outline">Artifacts</span>
                <span className="text-primary">{artifactCount}</span>
              </div>
              <div className="flex items-center justify-between text-[11px]">
                <span className="text-outline">Citations</span>
                <span className="text-secondary">{citationCount}</span>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add ProjectHub-terminal-architect/src/components/shell/SessionInfo.tsx
git commit -m "feat: add SessionInfo popover for user icon"
```

---

### Task 8: HelpPopover

**Files:**
- Create: `src/components/shell/HelpPopover.tsx`

- [ ] **Step 1: Create HelpPopover component**

```tsx
import React, { useState } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { HelpCircle, Command } from 'lucide-react';
import { useClickOutside } from '../../hooks/useClickOutside';

interface HelpPopoverProps {
  backendStatus: 'checking' | 'online' | 'offline';
}

const SHORTCUTS = [
  { keys: ['Cmd', 'K'], description: 'Command Palette' },
  { keys: ['Enter'], description: 'Send message' },
  { keys: ['Esc'], description: 'Close palette / popover' },
  { keys: ['\u2191', '\u2193'], description: 'Navigate palette results' },
];

export function HelpPopover({ backendStatus }: HelpPopoverProps) {
  const [open, setOpen] = useState(false);
  const ref = useClickOutside<HTMLDivElement>(() => setOpen(false));

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((prev) => !prev)}
        className="text-outline transition hover:text-on-surface"
      >
        <HelpCircle size={18} />
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, x: -4 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -4 }}
            transition={{ duration: 0.12 }}
            className="absolute bottom-0 left-full ml-3 w-64 border border-white/10 bg-surface-container-low shadow-xl"
          >
            <div className="border-b border-white/5 px-3 py-2">
              <span className="text-[11px] font-semibold uppercase tracking-[0.12em] text-on-surface-variant">
                Help
              </span>
            </div>

            <div className="space-y-3 p-3">
              <div>
                <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-[0.12em] text-outline">
                  Keyboard Shortcuts
                </div>
                <div className="space-y-1.5">
                  {SHORTCUTS.map((shortcut) => (
                    <div key={shortcut.description} className="flex items-center justify-between">
                      <span className="text-[11px] text-on-surface-variant">{shortcut.description}</span>
                      <div className="flex gap-1">
                        {shortcut.keys.map((key) => (
                          <kbd key={key} className="rounded border border-white/10 px-1.5 py-0.5 text-[9px] font-mono text-outline">
                            {key}
                          </kbd>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="border-t border-white/5 pt-3">
                <div className="mb-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-outline">
                  Quick Guide
                </div>
                <ul className="space-y-1 text-[11px] text-on-surface-variant">
                  <li>Type a question in the input to ask JARVIS</li>
                  <li>Use Repository to browse knowledge base files</li>
                  <li>Skills manages automation profiles</li>
                  <li>Admin shows system activity and statistics</li>
                </ul>
              </div>

              <div className="border-t border-white/5 pt-3">
                <div className="flex items-center justify-between text-[10px]">
                  <span className="text-outline">Version</span>
                  <span className="text-on-surface-variant">ProjectHub-JARVIS v1.0</span>
                </div>
                <div className="mt-1 flex items-center justify-between text-[10px]">
                  <span className="text-outline">Backend</span>
                  <span className={backendStatus === 'online' ? 'text-secondary' : 'text-[#ffb4ab]'}>{backendStatus}</span>
                </div>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add ProjectHub-terminal-architect/src/components/shell/HelpPopover.tsx
git commit -m "feat: add HelpPopover with shortcuts and quick guide"
```

---

### Task 9: Wire Everything in App.tsx

This is the main integration task. All new components get mounted and connected here.

**Files:**
- Modify: `src/App.tsx`

- [ ] **Step 1: Add imports at top of App.tsx**

Add after existing imports (after line 27):

```ts
import { CommandPalette } from './components/shell/CommandPalette';
import { NotificationBell } from './components/shell/NotificationBell';
import { SettingsPopover } from './components/shell/SettingsPopover';
import { SessionInfo } from './components/shell/SessionInfo';
import { HelpPopover } from './components/shell/HelpPopover';
```

- [ ] **Step 2: Add state for CommandPalette and health latency**

Add after `const [repositoryInitialPath, setRepositoryInitialPath] = useState<string | null>(null);` (line 101):

```ts
const [commandPaletteOpen, setCommandPaletteOpen] = useState(false);
```

Extract additional store fields. Change the existing `useAppStore()` destructure (lines 103-114) to also include:

```ts
const {
  messages,
  assets,
  citations,
  guide,
  presentation,
  isLoading,
  error,
  logs,
  sessionId,
  addLog,
  lastHealthLatency,
  lastLogReadCount,
  setLastHealthLatency,
  clearLogs,
  clearMessages,
  markLogsRead,
} = useAppStore();
```

- [ ] **Step 3: Add Cmd+K global keyboard listener**

Add after the `useEffect` for viewport sync (after line 130):

```ts
useEffect(() => {
  const handleGlobalKeyDown = (event: KeyboardEvent) => {
    if ((event.metaKey || event.ctrlKey) && event.key === 'k') {
      event.preventDefault();
      setCommandPaletteOpen((prev) => !prev);
    }
  };
  window.addEventListener('keydown', handleGlobalKeyDown);
  return () => window.removeEventListener('keydown', handleGlobalKeyDown);
}, []);
```

- [ ] **Step 4: Update health check to measure latency**

In the existing `checkBackend` function (around line 179-201), replace the health check `useEffect` with:

```ts
useEffect(() => {
  const checkBackend = async () => {
    const start = performance.now();
    try {
      const response = await fetch(`${import.meta.env.VITE_JARVIS_API_URL || 'http://localhost:8000'}/api/health`);
      const elapsed = Math.round(performance.now() - start);
      setLastHealthLatency(elapsed);
      if (!response.ok) {
        setBackendStatus('offline');
        return;
      }
      setBackendStatus('online');
      addLog({
        id: `${Date.now()}-health`,
        timestamp: new Date().toISOString(),
        type: 'info',
        message: 'JARVIS backend is connected.',
      });
    } catch {
      setLastHealthLatency(null);
      setBackendStatus('offline');
    }
  };

  void checkBackend();
  const interval = window.setInterval(checkBackend, 30000);
  return () => window.clearInterval(interval);
}, [addLog, setLastHealthLatency]);
```

- [ ] **Step 5: Add handleCommandPaletteSend helper**

Add after `handleNavigate` (after line 335):

```ts
const handleCommandPaletteSend = useCallback(async (text: string) => {
  setInputValue(text);
  setView('terminal');
  setTerminalFocusNonce((current) => current + 1);
  await sendMessage(text);
  setInputValue('');
}, [sendMessage]);
```

- [ ] **Step 6: Replace header right-side controls**

Replace the entire `<div className="flex items-center gap-4">` block (lines 371-388) with:

```tsx
<div className="flex items-center gap-4">
  <button
    onClick={() => setCommandPaletteOpen(true)}
    className="hidden items-center gap-2 rounded-sm bg-surface-container-lowest px-3 py-1 md:flex"
  >
    <Search size={14} className="text-outline" />
    <span className="w-44 text-left text-[12px] text-outline">Global Search...</span>
    <kbd className="rounded border border-white/10 px-1 py-0.5 text-[9px] font-mono text-outline">
      Cmd+K
    </kbd>
  </button>
  <NotificationBell
    logs={logs}
    unreadCount={Math.max(0, logs.length - lastLogReadCount)}
    onMarkRead={markLogsRead}
    onClearAll={clearLogs}
  />
  <SettingsPopover
    onClearMessages={clearMessages}
    addLog={addLog}
  />
  <SessionInfo
    sessionId={sessionId}
    backendStatus={backendStatus}
    artifactCount={assets.length}
    citationCount={citations.length}
    messageCount={messages.length}
  />
</div>
```

- [ ] **Step 7: Replace sidebar bottom buttons (HelpCircle + Activity)**

Replace the sidebar bottom `<div className="mt-auto ...">` block (lines 412-419) with:

```tsx
<div className="mt-auto flex w-full flex-col items-center gap-4 pb-8">
  <HelpPopover backendStatus={backendStatus} />
  <button
    onClick={() => handleNavigate('admin')}
    className="text-outline transition hover:text-on-surface"
    title="System Activity"
  >
    <Activity size={18} />
  </button>
</div>
```

- [ ] **Step 8: Fix footer — replace hardcoded values with live data**

Replace the footer content (lines 545-558) with:

```tsx
<footer className="fixed inset-x-0 bottom-0 z-50 flex h-6 items-center border-t border-white/5 bg-surface-container-lowest px-4 font-mono text-[11px]">
  <span className={cn('mr-6', backendStatus === 'online' ? 'text-secondary' : backendStatus === 'checking' ? 'text-primary' : 'text-[#ffb4ab]')}>
    {backendStatus === 'online' ? 'SYSTEM READY' : backendStatus === 'checking' ? 'SYSTEM CHECKING' : 'SYSTEM OFFLINE'}
  </span>
  <div className="flex flex-1 items-center gap-6 text-outline">
    <span>backend:{backendStatus}</span>
    <span>latency:{lastHealthLatency !== null ? `${lastHealthLatency}ms` : '--'}</span>
    <span>session:{sessionId.slice(0, 8)}</span>
    {selectedArtifact && <span>{selectedArtifact.title}</span>}
  </div>
  <div className="hidden gap-4 text-outline md:flex">
    <span>docs:{assets.length}</span>
    <span>refs:{citations.length}</span>
  </div>
</footer>
```

- [ ] **Step 9: Add CommandPalette overlay before closing `</div>`**

Add right before the closing `</div>` of the root element (before line 560):

```tsx
<AnimatePresence>
  {commandPaletteOpen && (
    <CommandPalette
      open={commandPaletteOpen}
      onClose={() => setCommandPaletteOpen(false)}
      onNavigate={(target) => { handleNavigate(target); setCommandPaletteOpen(false); }}
      onSendMessage={handleCommandPaletteSend}
      onNavigateToFile={(path) => { navigateToFile(path); setCommandPaletteOpen(false); }}
    />
  )}
</AnimatePresence>
```

- [ ] **Step 10: Commit all App.tsx changes**

```bash
git add ProjectHub-terminal-architect/src/App.tsx
git commit -m "feat: wire all shell components — command palette, notifications, settings, session, help, footer"
```

---

### Task 10: Visual Verification

- [ ] **Step 1: Start dev server and open http://localhost:3000**

```bash
cd ProjectHub-terminal-architect && npm run dev
```

- [ ] **Step 2: Verify all 8 items**

| # | Item | Test |
|---|------|------|
| 1 | Global Search bar | Click — CommandPalette opens |
| 2 | Cmd+K | Press Cmd+K — CommandPalette opens, ESC closes |
| 3 | Bell | Click — log popover shows, badge counts unread |
| 4 | Settings | Click — popover shows API URL, "Clear Conversations" works |
| 5 | User icon | Click — session info popover shows |
| 6 | HelpCircle | Click — help popover shows shortcuts |
| 7 | Activity | Click — navigates to Admin view |
| 8 | Footer | Shows `backend:online`, real `latency:XXms` |

- [ ] **Step 3: Verify palette navigation**

Type "repo" in CommandPalette — should filter to Repository. Press Enter — navigates there.

- [ ] **Step 4: Verify palette file search**

Type a filename — should list matching files from `/api/browse`. Click one — opens in Repository.

- [ ] **Step 5: Verify palette ask**

Type a question — click "Ask JARVIS" — navigates to terminal and sends message.

- [ ] **Step 6: Final commit if any fixes needed**

```bash
git add -A && git commit -m "fix: visual verification adjustments"
```
