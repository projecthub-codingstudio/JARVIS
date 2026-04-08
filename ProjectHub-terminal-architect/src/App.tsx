/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useCallback, useEffect, useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import {
  Activity,
  BarChart3,
  FileSearch2,
  FolderSearch,
  LayoutDashboard,
  Search,
  Settings,
  TerminalSquare,
  Workflow,
} from 'lucide-react';
import { cn } from './lib/utils';
import { useAppStore } from './store/app-store';
import { useJarvis } from './hooks/useJarvis';
import { apiClient, type IndexingState } from './lib/api-client';
import { DocumentsWorkspace } from './components/documents/DocumentsWorkspace';
import { ExplorerWorkspace } from './components/explorer/ExplorerWorkspace';
import { TerminalWorkspace } from './components/workspaces/TerminalWorkspace';
import { AdminWorkspace } from './components/workspaces/AdminWorkspace';
import { SkillsWorkspace } from './components/workspaces/SkillsWorkspace';
import { SettingsWorkspace } from './components/workspaces/SettingsWorkspace';
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
  { key: 'documents' as ViewState, label: 'Documents', icon: FileSearch2 },
  { key: 'skills' as ViewState, label: 'Skills', icon: Workflow },
  { key: 'admin' as ViewState, label: 'Admin', icon: BarChart3 },
  { key: 'settings' as ViewState, label: 'Settings', icon: Settings },
];

const DOCUMENT_REFERENCE_PATTERN = /(이\s*(문서|파일|코드|슬라이드|페이지|시트|클래스|함수|메서드|모듈|스크립트)|해당\s*(문서|파일|코드|클래스|함수|모듈)|현재\s*(문서|파일|코드|클래스)|여기|this\s+(document|file|code|class|function|method|module)|current\s+(document|file|code|class|module)|here)/i;
const EXPLICIT_TARGET_PATTERN = /^\s*(.+?)\s*(?:에서|에\s*대해|관련(?:해서)?|기준으로)\b/i;
const GENERIC_DOCUMENT_TARGETS = new Set([
  '이 문서',
  '이 파일',
  '이 코드',
  '이 클래스',
  '이 함수',
  '이 메서드',
  '이 모듈',
  '이 스크립트',
  '해당 문서',
  '해당 파일',
  '해당 코드',
  '해당 클래스',
  '해당 함수',
  '해당 모듈',
  '현재 문서',
  '현재 파일',
  '현재 코드',
  '현재 클래스',
  '여기',
  'this document',
  'this file',
  'this code',
  'this class',
  'this function',
  'this method',
  'this module',
  'current document',
  'current file',
  'current code',
  'current class',
  'current module',
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
  const [kbStats, setKbStats] = useState<{ chunks: number; docs: number; failed: number; failedPaths: string[]; sizeBytes: number; embeddings: number } | null>(null);
  const [indexingState, setIndexingState] = useState<IndexingState>({ status: 'idle', processed: 0, total: 0, last_completed: null, error: null });
  const [terminalFocusNonce, setTerminalFocusNonce] = useState(0);
  const [documentContextPaths, setDocumentContextPaths] = useState<string[]>([]);
  const [skillCatalog, setSkillCatalog] = useState<SkillCatalog | null>(null);
  const [skillCatalogLoading, setSkillCatalogLoading] = useState(false);
  const [skillCatalogError, setSkillCatalogError] = useState<string | null>(null);
  const [actionMaps, setActionMaps] = useState<ActionMap[]>([]);
  const [actionMapsLoading, setActionMapsLoading] = useState(false);
  const [actionMapsError, setActionMapsError] = useState<string | null>(null);
  const [repositoryInitialPath, setRepositoryInitialPath] = useState<string | null>(null);
  const [activeProfileName, setActiveProfileName] = useState<string | null>(null);
  const [profileSwitching, setProfileSwitching] = useState<string | null>(null); // target profile name while switching
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
      return;
    }

    if (preferredView === 'documents') {
      if (assets.length > 0) {
        // Stay in terminal — set document context for follow-up Q&A
        // User can navigate to Documents view via nav if they want the cascade view
        const paths = assets.map((a) => a.full_path || a.path).filter(Boolean);
        if (paths.length > 0) setDocumentContextPaths(paths);
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
        const data = await response.json().catch(() => null);
        const isStarting = data?.health?.status_level === 'starting';
        setBackendStatus(isStarting ? 'checking' : 'online');
        setLastHealthLatency(elapsed);
        setLastHealthError(isStarting ? 'Backend is loading models...' : null);
        if (data?.health?.chunk_count != null) {
          setKbStats({
            chunks: data.health.chunk_count ?? 0,
            docs: data.health.doc_count ?? 0,
            failed: data.health.failed_doc_count ?? 0,
            failedPaths: data.health.failed_doc_paths ?? [],
            sizeBytes: data.health.total_size_bytes ?? 0,
            embeddings: data.health.embedding_count ?? 0,
          });
        }
        if (data?.health?.indexing) {
          setIndexingState(data.health.indexing);
        }
        if (data?.health?.profile_name) {
          setActiveProfileName((prev) => {
            const next = data.health.profile_name as string;
            if (prev !== next) {
              // Profile actually changed on backend — clear switching overlay
              setProfileSwitching(null);
            }
            return next;
          });
        }
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
    // Poll faster during restart/checking or indexing
    const isPollingFast = backendStatus === 'checking' || indexingState.status === 'scanning' || indexingState.status === 'indexing';
    const intervalMs = isPollingFast ? 2000 : 30000;
    const interval = window.setInterval(checkBackend, intervalMs);
    return () => window.clearInterval(interval);
  }, [addLog, setLastHealthLatency, indexingState.status, backendStatus]);

  const handleReindex = useCallback(async () => {
    try {
      const result = await apiClient.reindex();
      if (result.indexing) setIndexingState(result.indexing);
      addLog({ id: `${Date.now()}-reindex`, timestamp: new Date().toISOString(), type: 'info', message: result.started ? 'Reindex started.' : 'Reindex already in progress.' });
    } catch (err) {
      addLog({ id: `${Date.now()}-reindex-err`, timestamp: new Date().toISOString(), type: 'error', message: `Reindex failed: ${err instanceof Error ? err.message : 'unknown'}` });
    }
  }, [addLog]);

  const handleRestart = useCallback(async () => {
    if (!window.confirm('백엔드를 재시작하시겠습니까?\n재시작 중에는 질의가 불가능합니다.')) return;
    addLog({ id: `${Date.now()}-restart`, timestamp: new Date().toISOString(), type: 'info', message: 'Backend restart requested...' });
    setBackendStatus('checking');
    setLastHealthError('Backend is restarting...');
    setKbStats(null);
    await apiClient.restart();
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
    const filePath = artifact.full_path || artifact.path;
    // Web artifacts → open in new tab
    if (filePath?.startsWith('http://') || filePath?.startsWith('https://')) {
      window.open(filePath, '_blank', 'noopener,noreferrer');
      return;
    }
    setSelectedArtifact((current) => {
      if (!current) return artifact;
      const currentPath = current.full_path || current.path;
      const nextPath = artifact.full_path || artifact.path;
      return currentPath === nextPath ? current : artifact;
    });
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
    await sendMessage(inputValue, documentContextPaths.length > 0 ? { contextDocumentPaths: documentContextPaths } : undefined);
    setInputValue('');
  };

  const handleAskArtifact = useCallback(async (artifact: Artifact, prompt: string) => {
    const normalizedPrompt = prompt.trim();
    if (!normalizedPrompt) return;
    const artifactLabel = artifact.title || artifact.path || artifact.full_path || '문서';
    const contextualQuery = shouldScopeArtifactPrompt(normalizedPrompt)
      ? `${artifactLabel}에서 ${normalizedPrompt}`
      : normalizedPrompt;
    const docPath = artifact.full_path || artifact.path || '';
    if (docPath) setDocumentContextPaths([docPath]);
    setView('terminal');
    setTerminalFocusNonce((current) => current + 1);
    await sendMessage(contextualQuery, docPath ? { contextDocumentPaths: [docPath] } : undefined);
  }, [sendMessage]);

  const handleNavigate = (target: ViewState) => {
    if (target === 'terminal') {
      setView('terminal');
      setTerminalFocusNonce((current) => current + 1);
      return;
    }
    // Clear document context when navigating away from terminal/documents
    if (target !== 'documents' && target !== 'terminal') {
      setDocumentContextPaths([]);
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
                kbStats={kbStats}
                indexingState={indexingState}
                onReindex={handleReindex}
                onRestart={handleRestart}
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
                documentContext={documentContextPaths}
                onClearDocumentContext={() => setDocumentContextPaths([])}
                onNavigateToDocuments={() => setView('documents')}
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

          {view === 'documents' ? (
            <motion.div
              key="documents"
              initial={{ opacity: 0, x: 12 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -12 }}
              className="h-full"
            >
              <DocumentsWorkspace
                assets={assets}
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
          {view === 'settings' ? (
            <motion.div
              key="settings"
              initial={{ opacity: 0, x: 12 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -12 }}
              className="h-full"
            >
              <SettingsWorkspace
                backendStatus={backendStatus}
                indexingState={indexingState}
                onIndexingStateChange={setIndexingState}
                addLog={addLog}
                onProfileSwitch={setProfileSwitching}
                profileSwitching={profileSwitching}
              />
            </motion.div>
          ) : null}
        </AnimatePresence>
      </main>

      {/* Offline banner with retry */}
      {backendStatus === 'offline' && (
        <div className="fixed inset-x-0 top-12 z-50 flex items-center justify-between border-b border-[#ffb4ab]/30 bg-[#93000a] px-4 py-2 lg:left-16">
          <div className="flex items-center gap-3">
            <span className="inline-flex h-2 w-2 rounded-full bg-[#ffb4ab] animate-pulse" />
            <span className="text-[12px] font-medium text-[#ffdad6]">
              Backend Offline{lastHealthError ? ` — ${lastHealthError}` : ''}
            </span>
          </div>
          <button
            onClick={async () => {
              setBackendStatus('checking');
              setLastHealthError(null);
              try {
                const res = await fetch(`${import.meta.env.VITE_JARVIS_API_URL || 'http://localhost:8000'}/api/health`);
                if (res.ok) {
                  setBackendStatus('online');
                  setLastHealthError(null);
                  setLastHealthLatency(null);
                  addLog({ id: `${Date.now()}-retry`, timestamp: new Date().toISOString(), type: 'info', message: 'Backend reconnected via manual retry.' });
                } else {
                  const detail = await res.text().catch(() => '');
                  setBackendStatus('offline');
                  setLastHealthError(`HTTP ${res.status}${detail ? `: ${detail}` : ''}`);
                }
              } catch (err) {
                const msg = err instanceof Error && err.message.includes('Failed to fetch')
                  ? 'Connection refused — backend process not running'
                  : (err instanceof Error ? err.message : 'Connection failed');
                setBackendStatus('offline');
                setLastHealthError(msg);
              }
            }}
            className="shrink-0 rounded-sm bg-[#ffdad6]/20 px-3 py-1 text-[11px] font-semibold text-[#ffdad6] transition hover:bg-[#ffdad6]/30"
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
          {activeProfileName && <span className="text-primary">profile:{activeProfileName}</span>}
          <span>latency:{lastHealthLatency !== null ? `${lastHealthLatency}ms` : '--'}</span>
          <span>session:{sessionId.slice(0, 8)}</span>
          {selectedArtifact && <span>{selectedArtifact.title}</span>}
        </div>
        <div className="hidden gap-4 text-outline md:flex">
          {(indexingState.status === 'scanning' || indexingState.status === 'indexing') && (
            <span className="text-primary animate-pulse">
              indexing:{indexingState.processed}/{indexingState.total}
            </span>
          )}
          {kbStats && <span>kb:{kbStats.docs.toLocaleString()} docs</span>}
          {kbStats && <span>chunks:{kbStats.chunks.toLocaleString()}</span>}
          {kbStats && kbStats.embeddings > 0 && <span>vectors:{kbStats.embeddings.toLocaleString()}</span>}
          {assets.length > 0 && <span>loaded:{assets.length}</span>}
          {citations.length > 0 && <span>refs:{citations.length}</span>}
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

      {/* Profile switching overlay — blocks all interaction */}
      <AnimatePresence>
        {profileSwitching && (
          <motion.div
            className="fixed inset-0 z-[200] flex flex-col items-center justify-center bg-surface/95"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
          >
            <div className="flex flex-col items-center gap-6">
              <div className="relative flex h-16 w-16 items-center justify-center">
                <div className="absolute inset-0 animate-spin rounded-full border-2 border-primary/20 border-t-primary" />
                <img src="/projecthub-icon.png" alt="" className="h-8 w-8 rounded" />
              </div>
              <div className="text-center">
                <div className="text-sm font-semibold text-on-surface">Switching Profile</div>
                <div className="mt-1 text-[12px] text-outline">
                  {profileSwitching}
                </div>
                <div className="mt-3 text-[11px] text-on-surface-variant animate-pulse">
                  Backend restarting...
                </div>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
