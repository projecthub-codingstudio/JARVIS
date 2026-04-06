/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useCallback, useEffect, useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import {
  Activity,
  BarChart3,
  FolderSearch,
  LayoutDashboard,
  Search,
  TerminalSquare,
  Workflow,
} from 'lucide-react';
import { cn } from './lib/utils';
import { useAppStore } from './store/app-store';
import { useJarvis } from './hooks/useJarvis';
import { apiClient } from './lib/api-client';
import { ExplorerWorkspace } from './components/explorer/ExplorerWorkspace';
import { TerminalWorkspace } from './components/workspaces/TerminalWorkspace';
import { AdminWorkspace } from './components/workspaces/AdminWorkspace';
import { SkillsWorkspace } from './components/workspaces/SkillsWorkspace';
import { CommandPalette } from './components/shell/CommandPalette';
import { NotificationBell } from './components/shell/NotificationBell';
import { SettingsPopover } from './components/shell/SettingsPopover';
import { SessionInfo } from './components/shell/SessionInfo';
import { HelpPopover } from './components/shell/HelpPopover';
import type {
  ActionMap,
  ActionMapCreateInput,
  ActionMapInput,
  Artifact,
  SkillCatalog,
  SkillProfileCreateInput,
  SkillProfileInput,
  ViewState,
} from './types';

const SHELL_NAV = [
  { key: 'home' as ViewState, label: 'Dashboard', icon: LayoutDashboard },
  { key: 'terminal' as ViewState, label: 'Terminal', icon: TerminalSquare },
  { key: 'explorer' as ViewState, label: 'Explorer', icon: FolderSearch },
  { key: 'skills' as ViewState, label: 'Skills', icon: Workflow },
  { key: 'admin' as ViewState, label: 'Admin', icon: BarChart3 },
];

const DOCUMENT_REFERENCE_PATTERN = /(이\s*(문서|파일|코드|슬라이드|페이지|시트)|해당\s*(문서|파일|코드)|현재\s*(문서|파일|코드)|여기|this\s+(document|file|code)|current\s+(document|file|code)|here)/i;
const EXPLICIT_TARGET_PATTERN = /^\s*(.+?)\s*(?:에서|에\s*대해|관련(?:해서)?|기준으로)\b/i;
const GENERIC_DOCUMENT_TARGETS = new Set([
  '이 문서',
  '이 파일',
  '이 코드',
  '해당 문서',
  '해당 파일',
  '해당 코드',
  '현재 문서',
  '현재 파일',
  '현재 코드',
  '여기',
  'this document',
  'this file',
  'this code',
  'current document',
  'current file',
  'current code',
]);

function getActiveShellKey(view: ViewState): ViewState {
  return view;
}

function shouldScopeArtifactPrompt(prompt: string) {
  const normalized = prompt.trim();
  if (!normalized) return false;
  if (DOCUMENT_REFERENCE_PATTERN.test(normalized)) return true;
  if (/[\\/]/.test(normalized) || /\.[A-Za-z0-9]{2,5}\b/.test(normalized)) return false;
  const explicitTargetMatch = normalized.match(EXPLICIT_TARGET_PATTERN);
  if (explicitTargetMatch) {
    const target = explicitTargetMatch[1]?.trim().toLowerCase() || '';
    if (target && !GENERIC_DOCUMENT_TARGETS.has(target)) {
      return false;
    }
  }
  return true;
}

export default function App() {
  const [view, setView] = useState<ViewState>('home');
  const [inputValue, setInputValue] = useState('');
  const [isMobile, setIsMobile] = useState(false);
  const [selectedArtifact, setSelectedArtifact] = useState<Artifact | null>(null);
  const [backendStatus, setBackendStatus] = useState<'checking' | 'online' | 'offline'>('checking');
  const [terminalFocusNonce, setTerminalFocusNonce] = useState(0);
  const [skillCatalog, setSkillCatalog] = useState<SkillCatalog | null>(null);
  const [skillCatalogLoading, setSkillCatalogLoading] = useState(false);
  const [skillCatalogError, setSkillCatalogError] = useState<string | null>(null);
  const [actionMaps, setActionMaps] = useState<ActionMap[]>([]);
  const [actionMapsLoading, setActionMapsLoading] = useState(false);
  const [actionMapsError, setActionMapsError] = useState<string | null>(null);
  const [repositoryInitialPath, setRepositoryInitialPath] = useState<string | null>(null);
  const [commandPaletteOpen, setCommandPaletteOpen] = useState(false);

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
    lastHealthError,
    lastLogReadCount,
    setLastHealthLatency,
    setLastHealthError,
    clearLogs,
    clearMessages,
    markLogsRead,
  } = useAppStore();

  const { sendMessage, sendMessageWithImage } = useJarvis();

  useEffect(() => {
    document.documentElement.classList.add('dark');
    return () => document.documentElement.classList.remove('dark');
  }, []);

  useEffect(() => {
    const syncViewport = () => {
      setIsMobile(window.innerWidth < 1024);
    };
    syncViewport();
    window.addEventListener('resize', syncViewport);
    return () => window.removeEventListener('resize', syncViewport);
  }, []);

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

  useEffect(() => {
    const syncSelectedArtifact = () => {
      if (assets.length === 0) {
        setSelectedArtifact(null);
        return;
      }

      setSelectedArtifact((current) => {
        if (current && assets.some((artifact) => artifact.id === current.id)) {
          return current;
        }
        if (presentation?.selected_artifact_id) {
          const preferred = assets.find((artifact) => artifact.id === presentation.selected_artifact_id);
          if (preferred) return preferred;
        }
        return assets[0];
      });
    };

    syncSelectedArtifact();
  }, [assets, presentation]);

  useEffect(() => {
    const preferredView = guide?.ui_hints?.preferred_view;
    if (!preferredView) return;

    if (preferredView === 'dashboard') {
      setView('terminal');
      setTerminalFocusNonce((current) => current + 1);
      return;
    }

    if (preferredView === 'repository') {
      if (assets.length > 0 || citations.length > 0) {
        setView('explorer');
      }
      return;
    }

    if (preferredView === 'detail_viewer') {
      if (assets.length > 0) {
        setView('explorer');
      }
    }
  }, [assets.length, citations.length, guide?.ui_hints?.preferred_view]);

  useEffect(() => {
    const checkBackend = async () => {
      const start = performance.now();
      try {
        const response = await fetch(`${import.meta.env.VITE_JARVIS_API_URL || 'http://localhost:8000'}/api/health`);
        if (!response.ok) {
          const detail = await response.text().catch(() => '');
          const errorMsg = `HTTP ${response.status}: ${response.statusText}${detail ? ` — ${detail}` : ''}`;
          setBackendStatus('offline');
          setLastHealthLatency(null);
          setLastHealthError(errorMsg);
          addLog({ id: `${Date.now()}-health-err`, timestamp: new Date().toISOString(), type: 'error', message: errorMsg });
          return;
        }
        const elapsed = Math.round(performance.now() - start);
        setBackendStatus('online');
        setLastHealthLatency(elapsed);
        setLastHealthError(null);
        addLog({
          id: `${Date.now()}-health`,
          timestamp: new Date().toISOString(),
          type: 'info',
          message: 'JARVIS backend is connected.',
        });
      } catch (err) {
        const errorMsg = err instanceof Error
          ? (err.message.includes('Failed to fetch') ? 'Connection refused — backend process not running' : err.message)
          : 'Unknown connection error';
        setBackendStatus('offline');
        setLastHealthLatency(null);
        setLastHealthError(errorMsg);
        addLog({ id: `${Date.now()}-health-err`, timestamp: new Date().toISOString(), type: 'error', message: errorMsg });
      }
    };

    void checkBackend();
    const interval = window.setInterval(checkBackend, 30000);
    return () => window.clearInterval(interval);
  }, [addLog, setLastHealthLatency]);

  const selectArtifact = useCallback((artifact: Artifact) => {
    setSelectedArtifact((current) => {
      if (!current) return artifact;
      const currentPath = current.full_path || current.path;
      const nextPath = artifact.full_path || artifact.path;
      return currentPath === nextPath ? current : artifact;
    });
  }, []);

  const navigateToFile = useCallback((path: string) => {
    // Convert absolute path to knowledge_base-relative path
    // e.g. "/Users/.../knowledge_base/coding/pipeline.py" → "coding/pipeline.py"
    const kbMarker = 'knowledge_base/';
    const kbIndex = path.indexOf(kbMarker);
    const relativePath = kbIndex >= 0 ? path.slice(kbIndex + kbMarker.length) : path;
    setRepositoryInitialPath(relativePath);
    setView('explorer');
  }, []);

  const openArtifact = useCallback((artifact: Artifact) => {
    setSelectedArtifact((current) => {
      if (!current) return artifact;
      const currentPath = current.full_path || current.path;
      const nextPath = artifact.full_path || artifact.path;
      return currentPath === nextPath ? current : artifact;
    });
    const filePath = artifact.full_path || artifact.path;
    if (filePath) {
      navigateToFile(filePath);
    }
  }, [navigateToFile]);

  const loadSkillCatalog = useCallback(async () => {
    setSkillCatalogLoading(true);
    setSkillCatalogError(null);
    try {
      const response = await apiClient.fetchSkillCatalog();
      setSkillCatalog(response.catalog);
    } catch (error) {
      setSkillCatalogError(error instanceof Error ? error.message : 'Failed to load skills');
    } finally {
      setSkillCatalogLoading(false);
    }
  }, []);

  const loadActionMaps = useCallback(async () => {
    setActionMapsLoading(true);
    setActionMapsError(null);
    try {
      const response = await apiClient.fetchActionMaps();
      setActionMaps(response.maps || []);
    } catch (error) {
      setActionMapsError(error instanceof Error ? error.message : 'Failed to load action maps');
    } finally {
      setActionMapsLoading(false);
    }
  }, []);

  const handleSaveSkillProfile = useCallback(async (skillId: string, payload: SkillProfileInput) => {
    const response = await apiClient.updateSkillProfile(skillId, payload);
    setSkillCatalog(response.catalog);
    addLog({
      id: `${Date.now()}-skill-save`,
      timestamp: new Date().toISOString(),
      type: 'info',
      message: `Skill updated: ${skillId}`,
    });
  }, [addLog]);

  const handleCreateSkillProfile = useCallback(async (payload: SkillProfileCreateInput) => {
    const response = await apiClient.createSkillProfile(payload);
    setSkillCatalog(response.catalog);
    addLog({
      id: `${Date.now()}-skill-create`,
      timestamp: new Date().toISOString(),
      type: 'info',
      message: `Skill created: ${payload.skill_id}`,
    });
  }, [addLog]);

  const handleSaveActionMap = useCallback(async (mapId: string, payload: ActionMapInput) => {
    const response = await apiClient.updateActionMap(mapId, payload);
    setActionMaps(response.maps || []);
    addLog({
      id: `${Date.now()}-map-save`,
      timestamp: new Date().toISOString(),
      type: 'info',
      message: `Action map updated: ${mapId}`,
    });
  }, [addLog]);

  const handleCreateActionMap = useCallback(async (payload: ActionMapCreateInput) => {
    const response = await apiClient.createActionMap(payload);
    setActionMaps(response.maps || []);
    addLog({
      id: `${Date.now()}-map-create`,
      timestamp: new Date().toISOString(),
      type: 'info',
      message: `Action map created: ${payload.map_id}`,
    });
  }, [addLog]);

  const handleSendMessage = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!inputValue.trim()) return;
    if (view !== 'terminal') {
      setView('terminal');
      setTerminalFocusNonce((current) => current + 1);
    }
    await sendMessage(inputValue);
    setInputValue('');
  };

  const handleAskArtifact = useCallback(async (artifact: Artifact, prompt: string) => {
    const normalizedPrompt = prompt.trim();
    if (!normalizedPrompt) return;
    const artifactLabel = artifact.title || artifact.path || artifact.full_path || '문서';
    const contextualQuery = shouldScopeArtifactPrompt(normalizedPrompt)
      ? `${artifactLabel}에서 ${normalizedPrompt}`
      : normalizedPrompt;
    setView('terminal');
    setTerminalFocusNonce((current) => current + 1);
    await sendMessage(contextualQuery);
  }, [sendMessage]);

  const handleNavigate = (target: ViewState) => {
    if (target === 'terminal') {
      setView('terminal');
      setTerminalFocusNonce((current) => current + 1);
      return;
    }
    setView(target);
  };

  const handleCommandPaletteSend = useCallback(async (text: string) => {
    setInputValue(text);
    setView('terminal');
    setTerminalFocusNonce((current) => current + 1);
    await sendMessage(text);
    setInputValue('');
  }, [sendMessage]);

  useEffect(() => {
    if (view !== 'skills') return;
    void loadSkillCatalog();
    void loadActionMaps();
  }, [view, loadSkillCatalog, loadActionMaps]);

  const activeShellKey = getActiveShellKey(view);

  return (
    <div className="h-screen overflow-hidden bg-surface text-on-surface">
      <header className="fixed inset-x-0 top-0 z-50 flex h-12 items-center justify-between border-b border-white/5 bg-surface px-4">
        <div className="flex items-center gap-6">
          <div className="flex items-center gap-2">
            <img src="/projecthub-icon.png" alt="ProjectHub" className="h-6 w-6 rounded" />
            <div className="text-sm font-bold tracking-tight text-primary">ProjectHub-JARVIS</div>
          </div>
          <nav className="hidden items-center gap-4 md:flex lg:hidden">
            {SHELL_NAV.map(({ key, label }) => (
              <button
                key={key}
                onClick={() => handleNavigate(key)}
                className={cn(
                  'h-12 px-1 text-[12px] font-semibold uppercase tracking-[-0.011em] transition-colors',
                  activeShellKey === key
                    ? 'border-b-2 border-secondary text-primary'
                    : 'text-outline hover:bg-surface-container-high hover:text-on-surface'
                )}
              >
                {label}
              </button>
            ))}
          </nav>
        </div>

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
      </header>

      <aside className="fixed bottom-0 left-0 top-12 z-40 hidden w-16 flex-col items-center border-r border-white/5 bg-surface-container-high py-4 lg:flex">
        <div className="flex w-full flex-col items-center gap-4">
          {SHELL_NAV.map(({ key, icon: Icon }) => (
            <button
              key={key}
              onClick={() => handleNavigate(key)}
              className={cn(
                'w-full border-l-2 py-3 text-outline transition-all',
                activeShellKey === key
                  ? 'border-secondary bg-surface text-secondary'
                  : 'border-transparent hover:bg-surface hover:text-on-surface'
              )}
              title={key}
            >
              <div className="flex justify-center">
                <Icon size={18} />
              </div>
            </button>
          ))}
        </div>

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
      </aside>

      <main className="ml-0 mt-12 h-[calc(100vh-4.5rem)] overflow-hidden lg:ml-16">
        <AnimatePresence mode="wait">
          {view === 'home' ? (
            <motion.div
              key="home"
              initial={{ opacity: 0, x: 12 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -12 }}
              className="h-full"
            >
              <TerminalWorkspace
                assets={assets}
                backendStatus={backendStatus}
                citations={citations}
                error={error}
                guide={guide}
                inputValue={inputValue}
                isLoading={isLoading}
                logs={logs}
                messages={messages}
                mode="home"
                onInputChange={setInputValue}
                onNavigateToFile={navigateToFile}
                onOpenArtifact={openArtifact}
                sessionId={sessionId}
                onSubmit={handleSendMessage}
                onImageSubmit={sendMessageWithImage}
                focusInputNonce={terminalFocusNonce}
              />
            </motion.div>
          ) : null}

          {view === 'terminal' ? (
            <motion.div
              key="terminal"
              initial={{ opacity: 0, x: 12 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -12 }}
              className="h-full"
            >
              <TerminalWorkspace
                assets={assets}
                backendStatus={backendStatus}
                citations={citations}
                error={error}
                guide={guide}
                inputValue={inputValue}
                isLoading={isLoading}
                logs={logs}
                messages={messages}
                mode="terminal"
                onInputChange={setInputValue}
                onNavigateToFile={navigateToFile}
                onOpenArtifact={openArtifact}
                sessionId={sessionId}
                onSubmit={handleSendMessage}
                onImageSubmit={sendMessageWithImage}
                focusInputNonce={terminalFocusNonce}
              />
            </motion.div>
          ) : null}

          {view === 'explorer' ? (
            <motion.div
              key="explorer"
              initial={{ opacity: 0, x: 12 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -12 }}
              className="h-full"
            >
              <ExplorerWorkspace
                initialPath={repositoryInitialPath}
                onClearInitialPath={() => setRepositoryInitialPath(null)}
                onAskArtifact={handleAskArtifact}
              />
            </motion.div>
          ) : null}

          {view === 'admin' ? (
            <motion.div
              key="admin"
              initial={{ opacity: 0, x: 12 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -12 }}
              className="h-full"
            >
              <AdminWorkspace
                assets={assets}
                backendStatus={backendStatus}
                lastHealthError={lastHealthError}
                citations={citations}
                logs={logs}
                messages={messages}
              />
            </motion.div>
          ) : null}

          {view === 'skills' ? (
            <motion.div
              key="skills"
              initial={{ opacity: 0, x: 12 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -12 }}
              className="h-full"
            >
              <SkillsWorkspace
                actionMaps={actionMaps}
                actionMapsError={actionMapsError}
                actionMapsLoading={actionMapsLoading}
                backendStatus={backendStatus}
                catalog={skillCatalog}
                catalogError={skillCatalogError}
                catalogLoading={skillCatalogLoading}
                onCreateActionMap={handleCreateActionMap}
                onCreateSkill={handleCreateSkillProfile}
                onRefreshActionMaps={loadActionMaps}
                onRefreshSkills={loadSkillCatalog}
                onSaveActionMap={handleSaveActionMap}
                onSaveSkill={handleSaveSkillProfile}
              />
            </motion.div>
          ) : null}
        </AnimatePresence>
      </main>

      {/* Offline banner with restart */}
      {backendStatus === 'offline' && (
        <div className="fixed inset-x-0 top-12 z-50 flex items-center justify-between border-b border-[#ffb4ab]/20 bg-[#ffb4ab]/10 px-4 py-2 lg:left-16">
          <div className="flex items-center gap-3">
            <span className="inline-flex h-2 w-2 rounded-full bg-[#ffb4ab] animate-pulse" />
            <span className="text-[12px] text-[#ffb4ab]">
              Backend Offline{lastHealthError ? ` — ${lastHealthError}` : ''}
            </span>
          </div>
          <button
            onClick={async () => {
              setBackendStatus('checking');
              try {
                const res = await fetch(`${import.meta.env.VITE_JARVIS_API_URL || 'http://localhost:8000'}/api/health`);
                if (res.ok) {
                  setBackendStatus('online');
                  setLastHealthError(null);
                } else {
                  setBackendStatus('offline');
                }
              } catch {
                setBackendStatus('offline');
              }
            }}
            className="rounded-sm bg-[#ffb4ab]/20 px-3 py-1 text-[11px] font-semibold text-[#ffb4ab] transition hover:bg-[#ffb4ab]/30"
          >
            Retry Connection
          </button>
        </div>
      )}

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
    </div>
  );
}
