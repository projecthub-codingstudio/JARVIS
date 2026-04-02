/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useState, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import {
  Terminal,
  Settings,
  LayoutDashboard,
  FolderOpen,
  FileText,
  Network,
  MicOff,
  SlidersHorizontal,
  Sparkles,
  Sun,
  Moon,
  BarChart3,
  AlertCircle,
  Info,
  AlertTriangle,
  X,
  Menu
} from 'lucide-react';
import { cn } from './lib/utils';
import { VoiceWaveform } from './components/VoiceWaveform';
import { AssetCard } from './components/AssetCard';
import { CitationList } from './components/CitationList';
import { ClarificationPrompt } from './components/ClarificationPrompt';
import { useAppStore } from './store/app-store';
import { useJarvis } from './hooks/useJarvis';
import { ViewerShell } from './components/viewer/ViewerShell';
import { Message, Asset, ViewState, SystemLog, Artifact, Citation } from './types';

export default function App() {
  const [view, setView] = useState<ViewState>('dashboard');
  const [inputValue, setInputValue] = useState('');
  const [selectedAsset, setSelectedAsset] = useState<Asset | null>(null);
  const [selectedArtifact, setSelectedArtifact] = useState<Artifact | null>(null);
  const [theme, setTheme] = useState<'dark' | 'light'>('dark');
  const [isMobileCmdOpen, setIsMobileCmdOpen] = useState(false);
  const [isMobile, setIsMobile] = useState(false);
  const [isSidebarVisible, setIsSidebarVisible] = useState(true);
  const chatEndRef = useRef<HTMLDivElement>(null);

  const [backendStatus, setBackendStatus] = useState<'checking' | 'online' | 'offline'>('checking');

  // Use Zustand store
  const {
    messages,
    assets,
    citations,
    guide,
    presentation,
    isLoading,
    error,
    logs,
    addMessage,
    setAssets,
    addLog
  } = useAppStore();

  // Use JARVIS hook
  const { sendMessage, handleSuggestedReply } = useJarvis();

  // Backend health check on mount
  useEffect(() => {
    const checkBackend = async () => {
      try {
        const res = await fetch(
          `${import.meta.env.VITE_JARVIS_API_URL || 'http://localhost:8000'}/api/health`
        );
        if (res.ok) {
          setBackendStatus('online');
          addLog({ id: Date.now().toString(), timestamp: new Date().toISOString(), type: 'info', message: 'JARVIS 백엔드 연결됨' });
        } else {
          setBackendStatus('offline');
        }
      } catch {
        setBackendStatus('offline');
      }
    };
    checkBackend();
    const interval = setInterval(checkBackend, 30_000);
    return () => clearInterval(interval);
  }, [addLog]);

  useEffect(() => {
    const checkMobile = () => {
      const mobile = window.innerWidth < 768;
      setIsMobile(mobile);
    };
    checkMobile();
    window.addEventListener('resize', checkMobile);
    return () => window.removeEventListener('resize', checkMobile);
  }, []);

  useEffect(() => {
    const root = window.document.documentElement;
    if (theme === 'dark') {
      root.classList.add('dark');
    } else {
      root.classList.remove('dark');
    }
  }, [theme]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSendMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputValue.trim()) return;
    
    await sendMessage(inputValue);
    setInputValue('');
  };

  const openAsset = (artifact: Artifact) => {
    setSelectedArtifact(artifact);
    setSelectedAsset({
      id: artifact.id,
      type: artifact.type.includes('code') ? 'html' :
            artifact.type.includes('image') ? 'image' :
            artifact.type.includes('pdf') ? 'pdf' : 'docx',
      name: artifact.title,
      description: artifact.preview,
      status: artifact.source_type,
      content: artifact.preview,
    });
    setView('detail_viewer');
  };

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'b') {
        e.preventDefault();
        setIsSidebarVisible(prev => !prev);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  return (
    <div className="h-screen flex flex-col bg-surface overflow-hidden selection:bg-primary/30">
      {/* Top Navigation */}
      <header className="h-16 border-b border-outline/10 flex items-center justify-between px-4 md:px-6 shrink-0 z-50 bg-surface">
        <div className="flex items-center gap-4 md:gap-8">
          <button 
            onClick={() => setIsSidebarVisible(!isSidebarVisible)}
            className="hidden md:flex p-2 text-on-surface-variant hover:bg-surface-highest hover:text-primary transition-all"
            title="사이드바 토글 (Ctrl+B)"
          >
            <Menu size={20} />
          </button>
          <span className="text-sm md:text-lg font-bold tracking-[0.2em] text-primary font-headline whitespace-nowrap">TERMINAL ARCHITECT</span>
          <nav className="hidden md:flex gap-6">
            <div className="flex items-center gap-2">
              <span className={cn(
                "w-1.5 h-1.5 rounded-full",
                backendStatus === 'online' ? "bg-primary animate-pulse" :
                backendStatus === 'checking' ? "bg-yellow-500 animate-pulse" : "bg-red-500"
              )} />
              <span className="text-xs font-bold uppercase tracking-wider">
                시스템: {backendStatus === 'online' ? '온라인' : backendStatus === 'checking' ? '확인중' : '오프라인'}
              </span>
            </div>
            <span className={cn(
              "text-xs uppercase tracking-wider",
              backendStatus === 'online' ? "text-primary" : "text-on-surface-variant"
            )}>
              AI: {backendStatus === 'online' ? '활성화' : '대기'}
            </span>
          </nav>
        </div>
        <div className="flex items-center gap-2 md:gap-4">
          <button 
            onClick={() => setTheme(prev => prev === 'dark' ? 'light' : 'dark')}
            className="p-2 text-on-surface-variant hover:bg-surface-highest hover:text-on-surface transition-all"
          >
            {theme === 'dark' ? <Sun size={18} /> : <Moon size={18} />}
          </button>
          <button className="hidden sm:block p-2 text-on-surface-variant hover:bg-surface-highest hover:text-on-surface transition-all">
            <Terminal size={18} />
          </button>
          <button className="hidden sm:block p-2 text-on-surface-variant hover:bg-surface-highest hover:text-on-surface transition-all">
            <Settings size={18} />
          </button>
          {view !== 'dashboard' && (
            <button 
              onClick={() => setView('dashboard')}
              className="bg-primary text-on-primary px-4 md:px-6 py-2 font-headline tracking-tighter uppercase text-xs md:text-sm font-bold hover:opacity-90 transition-all"
            >
              실행
            </button>
          )}
        </div>
      </header>

      <div className="flex flex-col md:flex-1 md:flex-row overflow-hidden">
        {/* Side Navigation - Hidden on mobile */}
        <AnimatePresence>
          {isSidebarVisible && (
            <motion.aside 
              initial={{ width: 0, opacity: 0 }}
              animate={{ width: 80, opacity: 1 }}
              exit={{ width: 0, opacity: 0 }}
              transition={{ type: 'spring', stiffness: 300, damping: 30 }}
              className="hidden md:flex bg-surface-low border-r border-outline/10 flex-col items-center py-8 shrink-0 overflow-hidden"
            >
              <div className="flex flex-col gap-8 flex-1 items-center w-full min-w-[80px]">
                <button 
                  onClick={() => setView('dashboard')}
                  className={cn(
                    "flex flex-col items-center gap-1 w-full py-4 transition-all",
                    view === 'dashboard' ? "text-primary border-l-2 border-primary bg-surface-highest/20" : "text-on-surface-variant opacity-80 hover:text-white hover:bg-surface-highest"
                  )}
                >
                  <LayoutDashboard size={20} />
                  <span className="text-[10px] font-medium">터미널</span>
                </button>
                <button
                  onClick={() => setView('repository')}
                  className={cn(
                    "flex flex-col items-center gap-1 w-full py-4 transition-all",
                    view === 'repository' ? "text-primary border-l-2 border-primary bg-surface-highest/20" : "text-on-surface-variant opacity-80 hover:text-white hover:bg-surface-highest"
                  )}
                >
                  <FolderOpen size={20} />
                  <span className="text-[10px] font-medium">저장소</span>
                </button>
                <button
                  onClick={() => selectedArtifact ? setView('detail_viewer') : null}
                  className={cn(
                    "flex flex-col items-center gap-1 w-full py-4 transition-all",
                    view === 'detail_viewer' ? "text-primary border-l-2 border-primary bg-surface-highest/20" : "text-on-surface-variant opacity-80 hover:text-white hover:bg-surface-highest"
                  )}
                >
                  <FileText size={20} />
                  <span className="text-[10px] font-medium">자산</span>
                </button>
                <button className="flex flex-col items-center gap-1 text-on-surface-variant opacity-80 hover:text-on-surface hover:bg-surface-highest w-full py-4 transition-all">
                  <Network size={20} />
                  <span className="text-[10px] font-medium">네트워크</span>
                </button>

                <button
                    onClick={() => setView('admin')}
                    className={cn(
                      "flex flex-col items-center gap-1 w-full py-4 transition-all",
                      view === 'admin' ? "text-primary border-l-2 border-primary bg-surface-highest/20" : "text-on-surface-variant opacity-80 hover:text-on-surface hover:bg-surface-highest"
                    )}
                  >
                    <BarChart3 size={20} />
                    <span className="text-[10px] font-medium">관리자</span>
                  </button>
              </div>
              <div className="flex flex-col gap-6 mb-4 items-center w-full min-w-[80px]">
                <button className="text-on-surface-variant opacity-80 hover:text-on-surface"><MicOff size={18} /></button>
                <button className="text-on-surface-variant opacity-80 hover:text-on-surface"><SlidersHorizontal size={18} /></button>
              </div>
            </motion.aside>
          )}
        </AnimatePresence>

        {/* Mobile Navigation - Shown only on mobile */}
        <nav className="md:hidden flex items-center justify-around bg-surface-low border-t border-outline/10 py-3 shrink-0 z-50 order-last">
          <button onClick={() => setView('dashboard')} className={cn("p-2", view === 'dashboard' ? "text-primary" : "text-on-surface-variant")}>
            <LayoutDashboard size={20} />
          </button>
          <button
            onClick={() => setIsMobileCmdOpen(!isMobileCmdOpen)}
            className={cn("p-2", isMobileCmdOpen ? "text-primary" : "text-on-surface-variant")}
          >
            <Terminal size={20} />
          </button>
          <button onClick={() => setView('repository')} className={cn("p-2", view === 'repository' ? "text-primary" : "text-on-surface-variant")}>
            <FolderOpen size={20} />
          </button>
          <button onClick={() => setView('admin')} className={cn("p-2", view === 'admin' ? "text-primary" : "text-on-surface-variant")}>
            <BarChart3 size={20} />
          </button>
        </nav>

        {/* Main Content Area */}
        <div className="flex-1 overflow-hidden relative">
          <AnimatePresence mode="wait">
            {view === 'dashboard' ? (
              <motion.div 
                key="dashboard"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="h-full flex flex-col md:flex-row overflow-hidden"
              >
                {/* Left Panel: Chat */}
                <section className="w-full md:w-1/3 border-b md:border-b-0 md:border-r border-outline/10 flex flex-col bg-surface-low/50 h-[50vh] md:h-full relative overflow-hidden">
                  <div className="p-4 md:p-6 flex-1 overflow-y-auto custom-scrollbar space-y-6 md:space-y-8 pb-40 md:pb-48">
                    <div className="flex items-center justify-between mb-4 md:mb-8">
                      <div>
                        <h2 className="text-primary font-headline font-bold text-sm uppercase tracking-widest">세션_활성화</h2>
                        <p className="text-on-surface-variant text-[10px] font-mono">ID: {useAppStore.getState().sessionId.slice(0, 8)}</p>
                      </div>
                      <span className={cn(
                        "text-[10px] px-2 py-1",
                        backendStatus === 'online' ? "text-primary bg-primary/10" :
                        backendStatus === 'checking' ? "text-yellow-500 bg-yellow-500/10" : "text-red-500 bg-red-500/10"
                      )}>
                        {backendStatus === 'online' ? 'JARVIS 연결됨' : backendStatus === 'checking' ? '연결 확인중...' : 'JARVIS 오프라인'}
                      </span>
                    </div>

                    {messages.map((msg) => (
                      <div key={msg.id} className="flex gap-4 group">
                        <div className={cn(
                          "w-[2px] shrink-0",
                          msg.role === 'architect' ? "bg-primary shadow-[0_0_8px_rgba(16,185,129,0.5)]" : "bg-on-surface-variant/50"
                        )} />
                        <div className="space-y-2">
                          <span className={cn(
                            "text-[10px] font-mono uppercase",
                            msg.role === 'architect' ? "text-primary" : "text-on-surface-variant"
                          )}>
                            {msg.role === 'operator' ? '오퍼레이터_입력' : '아키텍트_출력'} [{msg.timestamp}]
                          </span>
                          <p className={cn(
                            "text-sm leading-relaxed font-sans",
                            msg.role === 'architect' ? "opacity-90 italic" : ""
                          )}>
                            {msg.content}
                          </p>
                        </div>
                      </div>
                    ))}
                    
                    {isLoading && (
                      <div className="flex gap-4 group animate-pulse">
                        <div className="w-[2px] shrink-0 bg-primary/50" />
                        <div className="space-y-2">
                          <span className="text-[10px] font-mono uppercase text-primary">
                            아키텍트_처리중...
                          </span>
                          <p className="text-sm text-on-surface-variant italic">
                            JARVIS 가 응답을 생성하고 있습니다...
                          </p>
                        </div>
                      </div>
                    )}
                    
                    {error && (
                      <div className="flex gap-4 group">
                        <div className="w-[2px] shrink-0 bg-red-500" />
                        <div className="space-y-2">
                          <span className="text-[10px] font-mono uppercase text-red-500">
                            오류_감지
                          </span>
                          <p className="text-sm text-red-400">
                            {error}
                          </p>
                        </div>
                      </div>
                    )}
                    
                    <div ref={chatEndRef} />
                  </div>

                  {/* Input Area */}
                  <div className={cn(
                    "absolute left-0 w-full p-4 md:p-6 bg-gradient-to-t from-surface to-transparent z-20 transition-all duration-300",
                    isMobile 
                      ? (isMobileCmdOpen ? "bottom-0 opacity-100 translate-y-0" : "bottom-0 opacity-0 translate-y-full pointer-events-none")
                      : "bottom-0 opacity-100 translate-y-0"
                  )}>
                    <form 
                      onSubmit={handleSendMessage} 
                      className="flex flex-col bg-surface-high p-3 md:p-4 ring-1 ring-outline/20 gap-2 shadow-2xl"
                    >
                      <div className="flex items-center justify-between md:hidden mb-1">
                        <span className="text-[8px] font-mono text-primary uppercase tracking-widest">CMD_프롬프트_모드</span>
                        <button 
                          type="button" 
                          onClick={() => setIsMobileCmdOpen(false)}
                          className="text-on-surface-variant hover:text-primary"
                        >
                          <X size={14} />
                        </button>
                      </div>
                      <textarea 
                        className="w-full bg-transparent border-none focus:ring-0 text-sm font-sans text-on-surface placeholder:text-outline/80 uppercase tracking-tighter resize-none custom-scrollbar"
                        placeholder="명령어를 입력하세요..."
                        rows={isMobile ? 1 : 3}
                        value={inputValue}
                        onChange={(e) => setInputValue(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' && !e.shiftKey) {
                            e.preventDefault();
                            handleSendMessage(e as any);
                            if (isMobile) setIsMobileCmdOpen(false);
                          }
                        }}
                      />
                      <div className="flex items-center justify-between border-t border-outline/10 pt-2">
                        <div className="flex items-center gap-3">
                          <button type="button" className="text-on-surface-variant hover:text-red-500 transition-colors">
                            <MicOff size={18} />
                          </button>
                          <VoiceWaveform />
                        </div>
                        <button 
                          type="submit"
                          className="text-[10px] font-mono text-primary uppercase tracking-widest hover:underline"
                        >
                          [SEND_COMMAND]
                        </button>
                      </div>
                    </form>
                  </div>
                </section>

                {/* Right Panel: Assets & Results */}
                <section className="flex-1 overflow-y-auto p-4 md:p-8 space-y-6 md:space-y-10 custom-scrollbar h-[50vh] md:h-full">
                  <div className="flex flex-col md:flex-row md:items-center justify-between border-b border-outline/10 pb-4 gap-2">
                    <h3 className="text-primary-dim font-headline text-xl md:text-2xl font-light tracking-tight terminal-glow">
                      {assets.length > 0 ? 'JARVIS 검색 결과' : '워크스페이스'}
                    </h3>
                    {(assets.length > 0 || citations.length > 0) && (
                      <div className="flex gap-4 text-[10px] md:text-[11px] font-mono text-on-surface-variant">
                        <span>자산: {assets.length}개</span>
                        <span>근거: {citations.length}개</span>
                      </div>
                    )}
                  </div>

                  {/* Clarification Prompt */}
                  {guide?.has_clarification && guide.clarification_prompt && (
                    <ClarificationPrompt
                      prompt={guide.clarification_prompt}
                      suggestedReplies={guide.suggested_replies || []}
                      onReplySelect={handleSuggestedReply}
                    />
                  )}

                  {/* Assets Grid or Empty State */}
                  {assets.length > 0 ? (
                    <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
                      {assets.map((artifact) => (
                        <AssetCard
                          key={artifact.id}
                          artifact={artifact}
                          onClick={() => openAsset(artifact)}
                        />
                      ))}
                    </div>
                  ) : (
                    <div className="flex flex-col items-center justify-center py-20 text-center space-y-6">
                      <div className="w-16 h-16 rounded-full border-2 border-outline/20 flex items-center justify-center">
                        <Terminal size={28} className="text-outline/40" />
                      </div>
                      <div className="space-y-2">
                        <p className="text-sm font-headline text-on-surface-variant">대기 상태</p>
                        <p className="text-xs text-outline max-w-xs">
                          좌측 터미널에서 명령을 입력하면 검색 결과와 관련 자산이 여기에 표시됩니다.
                        </p>
                      </div>
                      {backendStatus === 'offline' && (
                        <div className="px-4 py-2 bg-red-500/10 border border-red-500/20 text-red-500 text-xs font-mono">
                          JARVIS 백엔드가 오프라인입니다. 서버를 시작해 주세요.
                        </div>
                      )}
                    </div>
                  )}

                  {/* Citations */}
                  {citations.length > 0 && (
                    <div className="bg-surface-low/50 p-6 border border-outline/10">
                      <CitationList
                        citations={citations}
                        onCitationClick={(citation: Citation) => {
                          console.log('Citation clicked:', citation);
                        }}
                      />
                    </div>
                  )}

                  {/* Status Bar */}
                  <div className="bg-surface-low p-6 flex flex-wrap items-center gap-8 border border-outline/10">
                    <div className="flex items-center gap-3">
                      <div className={cn(
                        "w-3 h-3",
                        backendStatus === 'online' ? "bg-primary animate-pulse" : "bg-outline/30"
                      )} />
                      <span className="text-[10px] font-mono text-on-surface uppercase">
                        {backendStatus === 'online' ? '실시간_분석_피드' : '대기중'}
                      </span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-[10px] font-mono text-outline">백엔드:</span>
                      <span className={cn(
                        "text-[10px] font-mono font-bold",
                        backendStatus === 'online' ? "text-primary" : "text-red-500"
                      )}>
                        {backendStatus === 'online' ? '연결됨' : '미연결'}
                      </span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-[10px] font-mono text-outline">메시지:</span>
                      <span className="text-[10px] font-mono text-primary font-bold">{messages.length}</span>
                    </div>
                  </div>
                </section>
              </motion.div>
            ) : view === 'detail_viewer' ? (
              selectedArtifact ? (
                <ViewerShell
                  artifact={selectedArtifact}
                  citations={citations}
                  onBack={() => setView('dashboard')}
                  isMobile={isMobile}
                />
              ) : (
                <div className="h-full flex items-center justify-center text-on-surface-variant">
                  <p>선택된 문서가 없습니다.</p>
                </div>
              )
            ) : view === 'repository' ? (
              <motion.div
                key="repository"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="h-full flex items-center justify-center text-on-surface-variant"
              >
                <div className="text-center space-y-4">
                  <FolderOpen size={48} className="mx-auto opacity-30" />
                  <p className="text-sm">저장소 탐색기 (준비 중)</p>
                </div>
              </motion.div>
            ) : view === 'admin' ? (
              <motion.div 
                key="admin"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="h-full flex flex-col p-10 overflow-hidden"
              >
                <div className="flex items-center justify-between mb-10 shrink-0">
                  <div className="flex items-center gap-4">
                    <div className="p-3 bg-primary/10 rounded-lg">
                      <BarChart3 size={24} className="text-primary" />
                    </div>
                    <h1 className="text-3xl font-headline font-bold tracking-tight">관리자 대시보드</h1>
                  </div>
                  <div className="flex gap-4">
                    <div className="px-4 py-2 bg-surface-low border border-outline/20 flex flex-col">
                      <span className="text-[8px] uppercase text-outline">시스템 상태</span>
                      <span className="text-xs font-bold text-primary">정상 작동 중</span>
                    </div>
                    <div className="px-4 py-2 bg-surface-low border border-outline/20 flex flex-col">
                      <span className="text-[8px] uppercase text-outline">활성 세션</span>
                      <span className="text-xs font-bold">128</span>
                    </div>
                  </div>
                </div>

                <div className="grid grid-cols-1 lg:grid-cols-3 gap-8 flex-1 overflow-hidden">
                  <div className="lg:col-span-2 flex flex-col gap-8 overflow-hidden">
                    <div className="bg-surface-low border border-outline/10 p-6 flex-1 flex flex-col overflow-hidden">
                      <div className="flex items-center justify-between mb-6">
                        <h2 className="text-sm font-headline font-bold uppercase tracking-widest text-primary">시스템 로그 피드</h2>
                        <button className="text-[10px] text-outline hover:text-primary uppercase tracking-widest">전체 보기</button>
                      </div>
                      <div className="flex-1 overflow-y-auto custom-scrollbar space-y-4">
                        {logs.length > 0 ? (
                          logs.map((log) => (
                            <div key={log.id} className="flex gap-4 p-3 bg-surface-high/50 border-l-2 border-outline/30 hover:border-primary transition-all">
                              <div className="shrink-0 pt-1">
                                {log.type === 'error' ? <AlertCircle size={14} className="text-red-500" /> :
                                 log.type === 'warning' ? <AlertTriangle size={14} className="text-yellow-500" /> :
                                 <Info size={14} className="text-blue-400" />}
                              </div>
                              <div className="flex-1 space-y-1">
                                <div className="flex justify-between items-center">
                                  <span className="text-[10px] font-mono text-outline">{new Date(log.timestamp).toLocaleString()}</span>
                                  <span className="text-[8px] font-mono px-1 bg-surface-highest text-on-surface-variant uppercase">{log.type}</span>
                                </div>
                                <p className="text-xs leading-relaxed">{log.message}</p>
                              </div>
                            </div>
                          ))
                        ) : (
                          <div className="text-center py-10 text-on-surface-variant text-xs">
                            표시할 로그가 없습니다.
                          </div>
                        )}
                      </div>
                    </div>
                  </div>

                  <div className="space-y-8 overflow-y-auto custom-scrollbar">
                    <div className="bg-surface-low border border-outline/10 p-6 space-y-6">
                      <h2 className="text-sm font-headline font-bold uppercase tracking-widest text-primary">리소스 할당</h2>
                      <div className="space-y-4">
                        {['네트워크 대역폭', '스토리지 사용량', 'AI 연산량'].map((label, i) => (
                          <div key={label} className="space-y-2">
                            <div className="flex justify-between text-[10px] uppercase font-bold">
                              <span>{label}</span>
                              <span className={i === 0 ? "text-primary" : ""}>{i === 0 ? '82%' : i === 1 ? '45%' : '12%'}</span>
                            </div>
                            <div className="h-1 bg-surface-highest w-full">
                              <div className={cn(
                                "h-full transition-all duration-1000",
                                i === 0 ? "bg-primary w-[82%]" : i === 1 ? "bg-blue-400 w-[45%]" : "bg-yellow-500 w-[12%]"
                              )} />
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>

                    <div className="bg-primary/5 border border-primary/20 p-6 space-y-4">
                      <div className="flex items-center gap-3">
                        <Sparkles size={18} className="text-primary" />
                        <h2 className="text-sm font-headline font-bold uppercase tracking-widest text-primary">AI 엔진 상태</h2>
                      </div>
                      <p className="text-xs text-on-surface-variant leading-relaxed">
                        현재 Architect_OS v4.2 엔진이 최적의 상태로 가동 중입니다. 신경망 링크 안정도는 99.9%를 유지하고 있습니다.
                      </p>
                      <button className="w-full py-2 bg-primary text-on-primary text-[10px] font-bold uppercase tracking-[0.2em] hover:opacity-90 transition-all">
                        엔진 재보정 실행
                      </button>
                    </div>
                  </div>
                </div>
              </motion.div>
            ) : null}
          </AnimatePresence>
        </div>
      </div>
      {/* Floating Action Element */}
      <div className="fixed bottom-8 right-8 flex flex-col gap-4 z-50">
        <div className="bg-surface-high/60 backdrop-blur-xl p-4 flex flex-col items-center gap-4 border border-outline/20">
          <div className="relative">
            <div className="w-12 h-12 rounded-full border-2 border-primary/30 flex items-center justify-center">
              <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center animate-pulse">
                <span className="text-primary text-sm font-bold">⚡</span>
              </div>
            </div>
            <div className="absolute -top-1 -right-1 w-3 h-3 bg-primary rounded-full shadow-[0_0_10px_#10B981]" />
          </div>
          <p className="text-[10px] font-mono text-primary uppercase [writing-mode:vertical-lr] tracking-widest h-16 text-center">
            Architect_OS Active
          </p>
        </div>
      </div>
    </div>
  );
}
