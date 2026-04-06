import { create } from 'zustand';
import { Message, SystemLog, Citation, Artifact, GuideDirective, Presentation, FileNode } from '../types';

interface AppState {
  // State
  messages: Message[];
  assets: Artifact[];
  logs: SystemLog[];
  lastHealthLatency: number | null;
  lastLogReadCount: number;
  isLoading: boolean;
  error: string | null;
  sessionId: string;
  
  // JARVIS specific state
  citations: Citation[];
  guide: GuideDirective | null;
  presentation: Presentation | null;
  hasEvidence: boolean;

  // Repository
  fileTree: FileNode[];
  fileTreeCache: Record<string, FileNode[]>;
  selectedFilePath: string | null;
  expandedDirs: string[];

  // Actions
  addMessage: (message: Message) => void;
  setAssets: (assets: Artifact[]) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  clearMessages: () => void;
  setCitations: (citations: Citation[]) => void;
  setGuide: (guide: GuideDirective) => void;
  setPresentation: (presentation: Presentation | null) => void;
  setHasEvidence: (hasEvidence: boolean) => void;
  setSessionId: (sessionId: string) => void;
  addLog: (log: SystemLog) => void;
  setLastHealthLatency: (ms: number | null) => void;
  clearLogs: () => void;
  markLogsRead: () => void;

  // Repository
  setFileTree: (entries: FileNode[]) => void;
  cacheDirectory: (path: string, entries: FileNode[]) => void;
  setSelectedFilePath: (path: string | null) => void;
  toggleExpandedDir: (path: string) => void;
  expandToPath: (filePath: string) => void;
}

export const useAppStore = create<AppState>((set) => ({
  // Initial state
  messages: [],
  assets: [],
  logs: [],
  lastHealthLatency: null,
  lastLogReadCount: 0,
  isLoading: false,
  error: null,
  sessionId: typeof crypto !== 'undefined' ? crypto.randomUUID() : 'default-session',
  
  // JARVIS state
  citations: [],
  guide: null,
  presentation: null,
  hasEvidence: false,

  // Repository
  fileTree: [],
  fileTreeCache: {},
  selectedFilePath: null,
  expandedDirs: [],

  // Actions
  addMessage: (message) => 
    set((state) => ({ messages: [...state.messages, message] })),
  
  setAssets: (assets) => set({ assets }),
  
  setLoading: (loading) => set({ isLoading: loading }),
  
  setError: (error) => set({ error }),
  
  clearMessages: () => set({ messages: [] }),
  
  setCitations: (citations) => set({ citations }),
  
  setGuide: (guide) => set({ guide }),
  
  setPresentation: (presentation) => set({ presentation }),
  
  setHasEvidence: (hasEvidence) => set({ hasEvidence }),
  
  setSessionId: (sessionId) => set({ sessionId }),
  
  addLog: (log) =>
    set((state) => ({ logs: [...state.logs, log] })),

  setLastHealthLatency: (ms) => set({ lastHealthLatency: ms }),
  clearLogs: () => set({ logs: [], lastLogReadCount: 0 }),
  markLogsRead: () => set((state) => ({ lastLogReadCount: state.logs.length })),

  setFileTree: (entries) => set({ fileTree: entries }),
  cacheDirectory: (path, entries) =>
    set((state) => ({
      fileTreeCache: { ...state.fileTreeCache, [path]: entries },
    })),
  setSelectedFilePath: (path) => set({ selectedFilePath: path }),
  toggleExpandedDir: (path) =>
    set((state) => {
      const dirs = state.expandedDirs.includes(path)
        ? state.expandedDirs.filter((d) => d !== path)
        : [...state.expandedDirs, path];
      return { expandedDirs: dirs };
    }),
  expandToPath: (filePath) =>
    set((state) => {
      const parts = filePath.split('/');
      const dirs: string[] = [];
      for (let i = 1; i < parts.length; i++) {
        dirs.push(parts.slice(0, i).join('/'));
      }
      const merged = [...new Set([...state.expandedDirs, ...dirs])];
      return { expandedDirs: merged, selectedFilePath: filePath };
    }),
}));
