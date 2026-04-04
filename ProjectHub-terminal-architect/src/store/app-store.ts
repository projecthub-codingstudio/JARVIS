import { create } from 'zustand';
import { Message, SystemLog, Citation, Artifact, GuideDirective, Presentation } from '../types';

interface AppState {
  // State
  messages: Message[];
  assets: Artifact[];
  logs: SystemLog[];
  isLoading: boolean;
  error: string | null;
  sessionId: string;
  
  // JARVIS specific state
  citations: Citation[];
  guide: GuideDirective | null;
  presentation: Presentation | null;
  hasEvidence: boolean;
  
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
}

export const useAppStore = create<AppState>((set) => ({
  // Initial state
  messages: [],
  assets: [],
  logs: [],
  isLoading: false,
  error: null,
  sessionId: typeof crypto !== 'undefined' ? crypto.randomUUID() : 'default-session',
  
  // JARVIS state
  citations: [],
  guide: null,
  presentation: null,
  hasEvidence: false,
  
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
}));
