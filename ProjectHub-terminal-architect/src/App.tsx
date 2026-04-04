/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useCallback, useEffect, useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import {
  Activity,
  BarChart3,
  Bell,
  FolderOpen,
  HelpCircle,
  House,
  Search,
  Settings,
  TerminalSquare,
  UserRound,
  Workflow,
} from 'lucide-react';
import { cn } from './lib/utils';
import { useAppStore } from './store/app-store';
import { useJarvis } from './hooks/useJarvis';
import { apiClient } from './lib/api-client';
import { RepositoryWorkspace } from './components/repository/RepositoryWorkspace';
import { TerminalWorkspace } from './components/workspaces/TerminalWorkspace';
import { AdminWorkspace } from './components/workspaces/AdminWorkspace';
import { SkillsWorkspace } from './components/workspaces/SkillsWorkspace';
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
  { key: 'home' as ViewState, label: 'Home', icon: House },
  { key: 'terminal' as ViewState, label: 'Terminal', icon: TerminalSquare },
  { key: 'repository' as ViewState, label: 'Repository', icon: FolderOpen },
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
  } = useAppStore();

  const { sendMessage } = useJarvis();

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
        setView('repository');
      }
      return;
    }

    if (preferredView === 'detail_viewer') {
      if (assets.length > 0) {
        setView('repository');
      }
    }
  }, [assets.length, citations.length, guide?.ui_hints?.preferred_view]);

  useEffect(() => {
    const checkBackend = async () => {
      try {
        const response = await fetch(`${import.meta.env.VITE_JARVIS_API_URL || 'http://localhost:8000'}/api/health`);
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
        setBackendStatus('offline');
      }
    };

    void checkBackend();
    const interval = window.setInterval(checkBackend, 30000);
    return () => window.clearInterval(interval);
  }, [addLog]);

  const selectArtifact = useCallback((artifact: Artifact) => {
    setSelectedArtifact((current) => {
      if (!current) return artifact;
      const currentPath = current.full_path || current.path;
      const nextPath = artifact.full_path || artifact.path;
      return currentPath === nextPath ? current : artifact;
    });
  }, []);

  const navigateToFile = useCallback((path: string) => {
    setRepositoryInitialPath(path);
    setView('repository');
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
          <div className="text-sm font-bold tracking-tight text-primary">ProjectHub</div>
          <nav className="hidden items-center gap-4 md:flex">
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
          <label className="hidden items-center gap-2 rounded-sm bg-surface-container-lowest px-3 py-1 md:flex">
            <Search size={14} className="text-outline" />
            <input
              className="w-44 bg-transparent text-[12px] text-on-surface outline-none placeholder:text-outline"
              placeholder="Global Search..."
            />
          </label>
          <button className="text-primary transition hover:bg-surface-container-high hover:text-on-surface">
            <Bell size={16} />
          </button>
          <button className="text-primary transition hover:bg-surface-container-high hover:text-on-surface">
            <Settings size={16} />
          </button>
          <div className="flex h-7 w-7 items-center justify-center rounded-sm border border-white/10 bg-surface-container-highest text-outline">
            <UserRound size={14} />
          </div>
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
          <button className="text-outline transition hover:text-on-surface">
            <HelpCircle size={18} />
          </button>
          <button className="text-outline transition hover:text-on-surface">
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
                focusInputNonce={terminalFocusNonce}
              />
            </motion.div>
          ) : null}

          {view === 'repository' ? (
            <motion.div
              key="repository"
              initial={{ opacity: 0, x: 12 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -12 }}
              className="h-full"
            >
              <RepositoryWorkspace
                initialPath={repositoryInitialPath}
                onClearInitialPath={() => setRepositoryInitialPath(null)}
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

      <footer className="fixed inset-x-0 bottom-0 z-50 flex h-6 items-center border-t border-white/5 bg-surface-container-lowest px-4 font-mono text-[11px]">
        <span className={cn('mr-6', backendStatus === 'online' ? 'text-secondary' : backendStatus === 'checking' ? 'text-primary' : 'text-[#ffb4ab]')}>
          {backendStatus === 'online' ? 'SYSTEM READY' : backendStatus === 'checking' ? 'SYSTEM CHECKING' : 'SYSTEM OFFLINE'}
        </span>
        <div className="flex flex-1 items-center gap-6 text-outline">
          <span>branch:main</span>
          <span>latency:14ms</span>
          <span>session:{sessionId.slice(0, 8)}</span>
          {selectedArtifact && <span>{selectedArtifact.title}</span>}
        </div>
        <div className="hidden gap-4 text-outline md:flex">
          <span>docs:{assets.length}</span>
          <span>refs:{citations.length}</span>
        </div>
      </footer>
    </div>
  );
}
