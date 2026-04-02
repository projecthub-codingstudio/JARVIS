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
  Mic,
  SlidersHorizontal,
  FileIcon,
  ExternalLink,
  Download,
  Share2,
  Printer,
  ArrowLeft,
  Search,
  Maximize2,
  ZoomIn,
  ZoomOut,
  CheckCircle2,
  Database,
  Sparkles,
  Code,
  Smartphone,
  Monitor,
  ShieldCheck,
  Sun,
  Moon,
  User as UserIcon,
  LogOut,
  LogIn,
  BarChart3,
  Camera,
  AlertCircle,
  Info,
  AlertTriangle,
  X,
  Menu
} from 'lucide-react';
import { cn } from './lib/utils';
import { VoiceWaveform } from './components/VoiceWaveform';
import { Message, Asset, ViewState, UserProfile, SystemLog } from './types';
import { INITIAL_MESSAGES, ASSETS } from './constants';
import { 
  auth, 
  db, 
  googleProvider, 
  signInWithPopup, 
  signOut, 
  onAuthStateChanged, 
  doc, 
  getDoc, 
  setDoc, 
  updateDoc, 
  collection, 
  query, 
  orderBy, 
  limit, 
  onSnapshot, 
  Timestamp,
  User,
  OperationType,
  handleFirestoreError
} from './firebase';

export default function App() {
  const [view, setView] = useState<ViewState>('dashboard');
  const [messages, setMessages] = useState<Message[]>(INITIAL_MESSAGES);
  const [inputValue, setInputValue] = useState('');
  const [selectedAsset, setSelectedAsset] = useState<Asset | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [theme, setTheme] = useState<'dark' | 'light'>('dark');
  const [adminLogs, setAdminLogs] = useState<SystemLog[]>([]);
  const [isAuthReady, setIsAuthReady] = useState(false);
  const [isLoggingIn, setIsLoggingIn] = useState(false);
  const [loginError, setLoginError] = useState<string | null>(null);
  const [isMobileCmdOpen, setIsMobileCmdOpen] = useState(false);
  const [isMobile, setIsMobile] = useState(false);
  const [isContextSummaryOpen, setIsContextSummaryOpen] = useState(true);
  const [isSidebarVisible, setIsSidebarVisible] = useState(true);
  const chatEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const checkMobile = () => {
      const mobile = window.innerWidth < 768;
      setIsMobile(mobile);
      if (mobile) setIsContextSummaryOpen(false);
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
    const unsubscribe = onAuthStateChanged(auth, async (currentUser) => {
      setUser(currentUser);
      if (currentUser) {
        try {
          const profileDoc = await getDoc(doc(db, 'users', currentUser.uid));
          if (profileDoc.exists()) {
            setProfile(profileDoc.data() as UserProfile);
          } else {
            // Create initial profile
            const newProfile: UserProfile = {
              uid: currentUser.uid,
              displayName: currentUser.displayName || 'Anonymous',
              email: currentUser.email || '',
              photoURL: currentUser.photoURL || '',
              role: currentUser.email === 'codingstudio.projecthub@gmail.com' ? 'admin' : 'user',
              createdAt: new Date().toISOString(),
              updatedAt: new Date().toISOString()
            };
            await setDoc(doc(db, 'users', currentUser.uid), newProfile);
            setProfile(newProfile);
            
            // Log creation
            await addSystemLog('info', `New user registered: ${newProfile.email}`, currentUser.uid);
          }
        } catch (error) {
          handleFirestoreError(error, OperationType.GET, `users/${currentUser.uid}`);
        }
      } else {
        setProfile(null);
      }
      setIsAuthReady(true);
    });
    return () => unsubscribe();
  }, []);

  useEffect(() => {
    if (profile?.role === 'admin') {
      const q = query(collection(db, 'system_logs'), orderBy('timestamp', 'desc'), limit(50));
      const unsubscribe = onSnapshot(q, (snapshot) => {
        const logs = snapshot.docs.map(doc => ({ id: doc.id, ...doc.data() } as SystemLog));
        setAdminLogs(logs);
      }, (error) => {
        handleFirestoreError(error, OperationType.LIST, 'system_logs');
      });
      return () => unsubscribe();
    }
  }, [profile]);

  const addSystemLog = async (type: 'info' | 'warning' | 'error', message: string, userId?: string) => {
    try {
      await setDoc(doc(collection(db, 'system_logs')), {
        timestamp: new Date().toISOString(),
        type,
        message,
        userId: userId || user?.uid
      });
    } catch (error) {
      console.error('Failed to add system log:', error);
    }
  };

  const handleLogin = async () => {
    setIsLoggingIn(true);
    setLoginError(null);
    try {
      await signInWithPopup(auth, googleProvider);
      setView('dashboard');
    } catch (error: any) {
      if (error.code === 'auth/popup-closed-by-user') {
        setLoginError('로그인 창이 닫혔습니다. 다시 시도해 주세요.');
      } else if (error.code === 'auth/cancelled-popup-request') {
        // Ignore this error as it's usually a duplicate request
      } else {
        console.error('Login failed:', error);
        setLoginError('로그인 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.');
      }
    } finally {
      setIsLoggingIn(false);
    }
  };

  const handleLogout = async () => {
    try {
      await signOut(auth);
      setView('dashboard');
    } catch (error) {
      console.error('Logout failed:', error);
    }
  };

  const updateProfile = async (data: Partial<UserProfile>) => {
    if (!user) return;
    try {
      const updatedData = { ...data, updatedAt: new Date().toISOString() };
      await updateDoc(doc(db, 'users', user.uid), updatedData);
      setProfile(prev => prev ? { ...prev, ...updatedData } : null);
      await addSystemLog('info', 'User profile updated', user.uid);
    } catch (error) {
      handleFirestoreError(error, OperationType.UPDATE, `users/${user.uid}`);
    }
  };

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSendMessage = (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputValue.trim()) return;

    const newMessage: Message = {
      id: Date.now().toString(),
      role: 'operator',
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }),
      content: inputValue
    };

    setMessages(prev => [...prev, newMessage]);
    setInputValue('');

    // Simulate AI response
    setTimeout(() => {
      const aiResponse: Message = {
        id: (Date.now() + 1).toString(),
        role: 'architect',
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }),
        content: 'Analyzing request... Cross-referencing with system architecture. Processing complete.'
      };
      setMessages(prev => [...prev, aiResponse]);
    }, 1000);
  };

  const openAsset = (asset: Asset) => {
    setSelectedAsset(asset);
    if (asset.type === 'image') setView('detail_image');
    else if (asset.type === 'pdf' || asset.type === 'docx' || asset.type === 'hwp') setView('detail_report');
    else setView('detail_code');
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
              <span className="w-1.5 h-1.5 rounded-full bg-primary animate-pulse" />
              <span className="text-xs font-bold uppercase tracking-wider">시스템: 온라인</span>
            </div>
            <span className="text-on-surface-variant text-xs uppercase tracking-wider">AI: 활성화</span>
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
                <button className="flex flex-col items-center gap-1 text-on-surface-variant opacity-80 hover:text-white hover:bg-surface-highest w-full py-4 transition-all">
                  <FolderOpen size={20} />
                  <span className="text-[10px] font-medium">저장소</span>
                </button>
                <button className="flex flex-col items-center gap-1 text-on-surface-variant opacity-80 hover:text-white hover:bg-surface-highest w-full py-4 transition-all">
                  <FileText size={20} />
                  <span className="text-[10px] font-medium">자산</span>
                </button>
                <button className="flex flex-col items-center gap-1 text-on-surface-variant opacity-80 hover:text-on-surface hover:bg-surface-highest w-full py-4 transition-all">
                  <Network size={20} />
                  <span className="text-[10px] font-medium">네트워크</span>
                </button>

                {profile?.role === 'admin' && (
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
                )}
              </div>
              <div className="flex flex-col gap-6 mb-4 items-center w-full min-w-[80px]">
                {user ? (
                  <button 
                    onClick={() => setView('profile')}
                    className={cn(
                      "p-2 rounded-full transition-all",
                      view === 'profile' ? "ring-2 ring-primary" : "text-on-surface-variant opacity-80 hover:text-on-surface"
                    )}
                  >
                    {profile?.photoURL ? (
                      <img src={profile.photoURL} alt="Profile" className="w-6 h-6 rounded-full object-cover" />
                    ) : (
                      <UserIcon size={18} />
                    )}
                  </button>
                ) : (
                  <button 
                    onClick={() => setView('login')}
                    className="text-on-surface-variant opacity-80 hover:text-on-surface"
                  >
                    <LogIn size={18} />
                  </button>
                )}
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
          <button onClick={() => setView('dashboard')} className="p-2 text-on-surface-variant">
            <FolderOpen size={20} />
          </button>
          {profile?.role === 'admin' && (
            <button onClick={() => setView('admin')} className={cn("p-2", view === 'admin' ? "text-primary" : "text-on-surface-variant")}>
              <BarChart3 size={20} />
            </button>
          )}
          {user ? (
            <button onClick={() => setView('profile')} className={cn("p-2 rounded-full", view === 'profile' ? "ring-2 ring-primary" : "text-on-surface-variant")}>
              {profile?.photoURL ? <img src={profile.photoURL} className="w-5 h-5 rounded-full" /> : <UserIcon size={20} />}
            </button>
          ) : (
            <button onClick={() => setView('login')} className={cn("p-2", view === 'login' ? "text-primary" : "text-on-surface-variant")}>
              <LogIn size={20} />
            </button>
          )}
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
                        <p className="text-on-surface-variant text-[10px] font-mono">ID: 0x4F92-ARCHITECT</p>
                      </div>
                      <span className="text-[10px] text-outline px-2 py-1 bg-surface-high">v4.0.2-phosphor</span>
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

                {/* Right Panel: Assets */}
                <section className="flex-1 overflow-y-auto p-4 md:p-8 space-y-6 md:space-y-10 custom-scrollbar h-[50vh] md:h-full">
                  <div className="flex flex-col md:flex-row md:items-center justify-between border-b border-outline/10 pb-4 gap-2">
                    <h3 className="text-primary-dim font-headline text-xl md:text-2xl font-light tracking-tight terminal-glow">자산_합성_뷰</h3>
                    <div className="flex gap-4 text-[10px] md:text-[11px] font-mono text-on-surface-variant">
                      <span>일치_정밀도: 98.4%</span>
                      <span>리소스: 04</span>
                    </div>
                  </div>

                  <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
                    {ASSETS.map((asset) => (
                      <div 
                        key={asset.id}
                        onClick={() => openAsset(asset)}
                        className={cn(
                          "bg-surface-high group hover:bg-surface-highest transition-colors flex flex-col cursor-pointer border border-outline/10",
                          asset.type === 'image' && "xl:row-span-2"
                        )}
                      >
                        <div className="p-4 border-b border-outline/10 flex justify-between items-center">
                          <div className="flex items-center gap-3">
                            <FileIcon size={16} className={cn(
                              asset.type === 'pdf' ? "text-red-500" : 
                              asset.type === 'image' ? "text-blue-400" : 
                              asset.type === 'docx' ? "text-primary" : "text-yellow-500"
                            )} />
                            <span className="text-xs font-mono text-on-surface uppercase tracking-widest">{asset.name}</span>
                          </div>
                          {asset.size && <span className="text-[10px] text-outline">{asset.size}</span>}
                        </div>

                        {asset.type === 'image' ? (
                          <div className="flex-1 relative overflow-hidden bg-black min-h-[300px]">
                            <img 
                              src={asset.imageUrl} 
                              alt={asset.name}
                              className="w-full h-full object-cover opacity-60 grayscale group-hover:grayscale-0 group-hover:opacity-100 transition-all duration-700"
                            />
                            <div className="absolute inset-0 bg-gradient-to-t from-black/80 to-transparent flex flex-col justify-end p-6">
                              <p className="text-[10px] font-mono text-primary mb-1">데이터_오버레이: 활성화</p>
                              <p className="text-sm font-headline text-on-surface">{asset.description}</p>
                            </div>
                          </div>
                        ) : (
                          <div className="p-6 flex-1 flex flex-col justify-center gap-4">
                            {asset.status && (
                              <div className="flex items-center gap-4">
                                <div className={cn(
                                  "px-2 py-1 text-[8px] font-black",
                                  asset.status === 'LEGACY_FORMAT' ? "bg-red-500/20 text-red-500" : "bg-primary/20 text-primary"
                                )}>
                                  {asset.status.toUpperCase()}
                                </div>
                              </div>
                            )}
                            {asset.type === 'docx' ? (
                              <div className="space-y-3">
                                <div className="h-2 w-full bg-outline/20" />
                                <div className="h-2 w-3/4 bg-outline/20" />
                                <div className="h-2 w-full bg-outline/20" />
                                <div className="h-2 w-1/2 bg-primary/20" />
                              </div>
                            ) : (
                              <p className="text-xs text-on-surface-variant font-headline leading-relaxed">
                                {asset.description || "System analysis pending. Encryption protocols active for this segment."}
                              </p>
                            )}
                          </div>
                        )}

                        <div className="p-4 flex justify-between items-center bg-surface-low/30">
                          <button className="text-[10px] uppercase font-bold text-primary tracking-tighter hover:underline">
                            {asset.type === 'hwp' ? '지금_변환' : asset.type === 'pdf' ? '데이터_추출' : '요약하기'}
                          </button>
                          <ExternalLink size={14} className="text-outline" />
                        </div>
                      </div>
                    ))}
                  </div>

                  <div className="bg-surface-low p-6 flex flex-wrap items-center gap-8 border border-outline/10">
                    <div className="flex items-center gap-3">
                      <div className="w-3 h-3 bg-primary animate-pulse" />
                      <span className="text-[10px] font-mono text-on-surface uppercase">실시간_분석_피드</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-[10px] font-mono text-outline">CPU:</span>
                      <div className="w-24 h-1 bg-surface-highest">
                        <div className="w-1/3 h-full bg-primary" />
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-[10px] font-mono text-outline">신경망_링크:</span>
                      <span className="text-[10px] font-mono text-primary font-bold">안정적</span>
                    </div>
                  </div>
                </section>
              </motion.div>
            ) : view === 'detail_report' ? (
              <motion.div 
                key="report"
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -20 }}
                className="h-full flex flex-col overflow-hidden"
              >
                <div className="px-4 md:px-10 pt-6 bg-surface-low shrink-0">
                  <nav className="flex items-center gap-2 text-[10px] font-mono uppercase tracking-widest text-on-surface-variant mb-4">
                    <button onClick={() => setView('dashboard')} className="hover:text-primary transition-colors">대시보드</button>
                    <span>/</span>
                    <button onClick={() => setView('dashboard')} className="hover:text-primary transition-colors">자산</button>
                    <span>/</span>
                    <span className="text-primary-dim">{selectedAsset?.name || '보고서'}</span>
                  </nav>
                  <div className="flex flex-col md:flex-row md:justify-between md:items-center pb-6 gap-4">
                    <div>
                      <h1 className="text-lg md:text-xl font-bold tracking-tight text-primary-dim font-headline">결과 상세 보기 (한글)</h1>
                      <p className="text-on-surface-variant text-[10px] font-mono uppercase tracking-widest mt-1">Report ID: ARCH-992-KOR-ALPHA</p>
                    </div>
                    <div className="flex flex-wrap gap-2 md:gap-3">
                      <button 
                        onClick={() => setIsContextSummaryOpen(!isContextSummaryOpen)}
                        className={cn(
                          "flex-1 md:flex-none px-3 md:px-5 py-2 border border-outline transition-all text-[10px] md:text-xs flex items-center justify-center gap-2",
                          isContextSummaryOpen ? "bg-primary/10 text-primary border-primary" : "text-on-surface-variant hover:text-white hover:bg-surface-highest"
                        )}
                      >
                        <Info size={14} /> {isContextSummaryOpen ? '요약_숨기기' : '요약_보기'}
                      </button>
                      <button className="flex-1 md:flex-none px-3 md:px-5 py-2 border border-outline text-on-surface-variant hover:text-white hover:bg-surface-highest transition-all text-[10px] md:text-xs flex items-center justify-center gap-2">
                        <Share2 size={14} /> 공유
                      </button>
                      <button className="flex-1 md:flex-none px-3 md:px-5 py-2 border border-outline text-on-surface-variant hover:text-white hover:bg-surface-highest transition-all text-[10px] md:text-xs flex items-center justify-center gap-2">
                        <Printer size={14} /> 인쇄
                      </button>
                      <button className="w-full md:w-auto px-4 md:px-6 py-2 bg-primary text-on-primary font-bold hover:opacity-80 transition-all text-[10px] md:text-xs flex items-center justify-center gap-2">
                        <Download size={14} /> 다운로드
                      </button>
                    </div>
                  </div>
                </div>

                <div className="flex-1 flex flex-col md:flex-row overflow-hidden">
                  <section className="flex-1 overflow-y-auto p-6 md:p-12 custom-scrollbar">
                    <div className="max-w-4xl mx-auto">
                      <div className="mb-12">
                        <div className="flex items-center gap-3 mb-4">
                          <span className="text-primary font-mono">&gt;</span>
                          <span className="text-primary font-mono text-xs">EXECUTE RAG_SYNTHESIS --target="KR_FIN_REPORT_2024"</span>
                          <span className="w-2 h-4 bg-primary animate-pulse" />
                        </div>
                        <h2 className="text-2xl font-black font-headline text-on-surface leading-tight uppercase">2024년 4분기 시장 분석 및 전략 보고서</h2>
                      </div>

                      <div className="space-y-10">
                        <div className="relative pl-8">
                          <div className="absolute left-0 top-0 bottom-0 w-[2px] bg-primary" />
                          <h3 className="text-primary-dim font-headline text-lg mb-4">I. 요약 (Executive Summary)</h3>
                          <p className="text-on-surface-variant leading-relaxed text-base">
                            본 보고서는 2024년 4분기 국내 시장의 주요 기술 트렌드와 경제 지표를 기반으로 한 RAG(Retrieval-Augmented Generation) 분석 결과입니다. 주요 지표에 따르면 클라우드 인프라 확장과 AI 도입 가속화가 시장 성장의 핵심 동인으로 나타났습니다.
                          </p>
                        </div>

                        <div className="grid grid-cols-1 md:grid-cols-2 gap-8 py-6">
                          <div className="bg-surface-low p-6 border-l-2 border-primary">
                            <h4 className="text-on-surface font-headline font-bold mb-2 text-sm">주요 성장률</h4>
                            <span className="text-2xl font-mono text-primary font-black">+14.2%</span>
                            <p className="text-on-surface-variant text-[10px] mt-2 uppercase font-mono">Core Tech Sector Growth</p>
                          </div>
                          <div className="bg-surface-low p-6 border-l-2 border-primary-dim">
                            <h4 className="text-on-surface font-headline font-bold mb-2 text-sm">위험 지수</h4>
                            <span className="text-2xl font-mono text-primary-dim font-black">LOW</span>
                            <p className="text-on-surface-variant text-[10px] mt-2 uppercase font-mono">Risk Assessment Level</p>
                          </div>
                        </div>

                        <div className="relative pl-8">
                          <div className="absolute left-0 top-0 bottom-0 w-[2px] bg-primary" />
                          <h3 className="text-primary-dim font-headline text-lg mb-4">II. 상세 분석 (Deep Dive)</h3>
                          <div className="space-y-6 text-on-surface-variant leading-relaxed text-sm">
                            <p>1. <strong className="text-on-surface">시장 환경 분석:</strong> 최근 통계청 및 산업통상자원부 데이터를 추출한 결과, 반도체 및 인공지능 관련 수출액이 전년 대비 18% 증가했습니다.</p>
                            <p>2. <strong className="text-on-surface">RAG 기반 통찰:</strong> 시스템은 1,200개 이상의 금융 보고서를 참조하여 현재의 금리 기조가 IT 투자 심리에 미치는 영향을 분석했습니다.</p>
                          </div>
                        </div>
                      </div>
                    </div>
                  </section>

                  <AnimatePresence>
                    {isContextSummaryOpen && (
                      <motion.aside 
                        initial={isMobile ? { height: 0, opacity: 0 } : { width: 0, opacity: 0 }}
                        animate={isMobile ? { height: 'auto', opacity: 1 } : { width: 320, opacity: 1 }}
                        exit={isMobile ? { height: 0, opacity: 0 } : { width: 0, opacity: 0 }}
                        className="w-full md:w-80 bg-surface-low border-t md:border-t-0 md:border-l border-outline/10 shrink-0 overflow-hidden"
                      >
                        <div className="p-6 md:p-8 h-full overflow-y-auto custom-scrollbar">
                          <h4 className="text-primary text-xs font-mono mb-6 uppercase tracking-widest">Context Summary</h4>
                          <div className="space-y-6 mb-10">
                            <div>
                              <p className="text-xs text-on-surface-variant uppercase mb-1">문서 신뢰도</p>
                              <div className="h-1 bg-surface-highest w-full">
                                <div className="h-full bg-primary w-[94%]" />
                              </div>
                              <p className="text-right text-[10px] font-mono mt-1 text-primary">94.2% 신뢰도</p>
                            </div>
                            <div>
                              <p className="text-xs text-on-surface-variant uppercase mb-1">처리 소요 시간</p>
                              <p className="text-lg font-mono text-on-surface">1.24s</p>
                            </div>
                          </div>
                          <div className="relative aspect-video w-full bg-surface-highest overflow-hidden mb-8">
                            <img 
                              src="https://images.unsplash.com/photo-1550751827-4bd374c3f58b?auto=format&fit=crop&q=80&w=500" 
                              alt="Visual"
                              className="w-full h-full object-cover opacity-50"
                              referrerPolicy="no-referrer"
                            />
                            <div className="absolute inset-0 bg-gradient-to-t from-surface-low to-transparent" />
                            <p className="absolute bottom-2 left-2 text-[10px] font-mono text-primary">데이터_비주얼_01</p>
                          </div>
                          <button className="w-full py-3 border border-primary text-primary font-mono text-xs hover:bg-primary/10 transition-all uppercase tracking-tighter">
                            원시 JSON 데이터 보기
                          </button>
                        </div>
                      </motion.aside>
                    )}
                  </AnimatePresence>
                </div>
              </motion.div>
            ) : view === 'detail_image' ? (
              <motion.div 
                key="image"
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 1.05 }}
                className="h-full flex flex-col md:flex-row overflow-hidden"
              >
                <div className="flex-1 flex flex-col items-center justify-center p-4 md:p-8 relative bg-black/40 overflow-hidden">
                  <div className="absolute top-4 md:top-6 left-4 md:left-6 flex flex-col gap-4">
                    <nav className="flex items-center gap-2 text-[10px] font-mono uppercase tracking-widest text-on-surface-variant">
                      <button onClick={() => setView('dashboard')} className="hover:text-primary transition-colors">대시보드</button>
                      <span>/</span>
                      <button onClick={() => setView('dashboard')} className="hover:text-primary transition-colors">자산</button>
                      <span>/</span>
                      <span className="text-primary-dim">{selectedAsset?.name || '이미지'}</span>
                    </nav>
                  </div>

                  <div className="absolute top-4 md:top-6 right-4 md:right-6">
                    <button 
                      onClick={() => setIsContextSummaryOpen(!isContextSummaryOpen)}
                      className={cn(
                        "p-2 md:px-4 md:py-2 border border-outline transition-all text-[10px] md:text-xs flex items-center gap-2 bg-surface-low/80 backdrop-blur-md",
                        isContextSummaryOpen ? "text-primary border-primary" : "text-on-surface-variant hover:text-white"
                      )}
                    >
                      <Info size={14} /> <span className="hidden md:inline">{isContextSummaryOpen ? '메타데이터_숨기기' : '메타데이터_보기'}</span>
                    </button>
                  </div>

                  <div className="relative max-w-full max-h-[70vh] md:max-h-[80%] border border-outline/20 shadow-2xl overflow-hidden bg-black group">
                    <img 
                      src={selectedAsset?.imageUrl} 
                      alt="Analysis"
                      className="opacity-90 group-hover:opacity-100 transition-opacity duration-500 object-contain max-h-[60vh] md:max-h-[70vh]"
                      referrerPolicy="no-referrer"
                    />
                    <div className="absolute inset-0 pointer-events-none border-t border-primary/20 bg-gradient-to-b from-primary/5 to-transparent h-1/4 animate-pulse" />
                    <div className="absolute top-0 left-0 w-8 h-8 border-t-2 border-l-2 border-primary/60" />
                    <div className="absolute top-0 right-0 w-8 h-8 border-t-2 border-r-2 border-primary/60" />
                    <div className="absolute bottom-0 left-0 w-8 h-8 border-b-2 border-l-2 border-primary/60" />
                    <div className="absolute bottom-0 right-0 w-8 h-8 border-b-2 border-r-2 border-primary/60" />
                  </div>

                  <div className="mt-6 md:absolute md:bottom-8 flex items-center gap-px bg-surface-highest/80 backdrop-blur-xl border border-outline/30 p-1">
                    <button className="p-2 md:p-3 hover:bg-primary hover:text-on-primary transition-all"><ZoomIn size={18} /></button>
                    <button className="p-2 md:p-3 hover:bg-primary hover:text-on-primary transition-all"><ZoomOut size={18} /></button>
                    <div className="w-px h-6 bg-outline/30 mx-2" />
                    <button className="p-2 md:p-3 hover:bg-primary hover:text-on-primary transition-all"><Maximize2 size={18} /></button>
                    <button className="p-2 md:p-3 hover:bg-primary hover:text-on-primary transition-all"><Download size={18} /></button>
                    <div className="w-px h-6 bg-outline/30 mx-2" />
                    <div className="px-4 font-mono text-xs text-primary/80">150%</div>
                  </div>
                </div>

                <AnimatePresence>
                  {isContextSummaryOpen && (
                    <motion.aside 
                      initial={isMobile ? { height: 0, opacity: 0 } : { width: 0, opacity: 0 }}
                      animate={isMobile ? { height: 'auto', opacity: 1 } : { width: 400, opacity: 1 }}
                      exit={isMobile ? { height: 0, opacity: 0 } : { width: 0, opacity: 0 }}
                      className="w-full md:w-[400px] bg-surface-low border-t md:border-t-0 md:border-l border-outline/10 shrink-0 overflow-hidden"
                    >
                      <div className="p-6 md:p-8 flex flex-col gap-6 md:gap-10 h-full overflow-y-auto custom-scrollbar">
                        <div className="space-y-6">
                          <h2 className="font-headline text-xs font-bold uppercase tracking-[0.2em] text-primary/90">Metadata // 파일 속성</h2>
                          <div className="grid grid-cols-2 gap-4">
                            <div className="space-y-1">
                              <p className="text-[10px] uppercase text-on-surface-variant tracking-wider">해상도</p>
                              <p className="font-mono text-sm">3840 x 2160</p>
                            </div>
                            <div className="space-y-1">
                              <p className="text-[10px] uppercase text-on-surface-variant tracking-wider">포맷</p>
                              <p className="font-mono text-sm">RAW / EXR</p>
                            </div>
                          </div>
                        </div>

                        <div className="space-y-6">
                          <div className="flex items-center justify-between">
                            <h2 className="font-headline text-xs font-bold uppercase tracking-[0.2em] text-primary/90">AI Analysis // 분석 리포트</h2>
                            <span className="flex h-2 w-2 rounded-full bg-primary animate-pulse" />
                          </div>
                          <div className="bg-surface p-6 space-y-4 border-l-2 border-primary relative overflow-hidden">
                            <Sparkles size={32} className="absolute top-2 right-2 opacity-10" />
                            <p className="font-mono text-xs text-on-surface-variant italic">[ARCHITECT_ENGINE_v4.2] :: 분석 완료</p>
                            <p className="text-sm leading-relaxed">
                              본 이미지는 복합적인 고밀도 데이터 네트워크 아키텍처를 시각화하고 있습니다. 중앙 집중식 노드 구조에서 파생되는 72개의 서브-프로세스 레이어가 감지되었습니다.
                            </p>
                            <ul className="space-y-2 pt-2">
                              <li className="flex items-start gap-2 text-xs text-on-surface-variant">
                                <CheckCircle2 size={14} className="text-primary shrink-0" /> 감지된 주요 패턴: 하이브리드 토폴로지 구조
                              </li>
                            </ul>
                          </div>
                        </div>

                        <div className="space-y-4">
                          <h2 className="font-headline text-xs font-bold uppercase tracking-[0.2em] text-primary/90">Tags // 키워드</h2>
                          <div className="flex flex-wrap gap-2">
                            {['NETWORK_ARCH', 'DATA_VISUAL', 'SYSTEM_FLOW', 'EMERALD_PROTO'].map(tag => (
                              <span key={tag} className="px-3 py-1 bg-surface-highest text-[10px] font-mono text-on-surface-variant border border-outline/20">{tag}</span>
                            ))}
                          </div>
                        </div>
                      </div>
                    </motion.aside>
                  )}
                </AnimatePresence>
              </motion.div>
            ) : view === 'detail_code' ? (
              <motion.div 
                key="code"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="h-full flex flex-col p-4 md:p-8 overflow-hidden"
              >
                <div className="flex flex-col md:flex-row md:justify-between md:items-end mb-6 md:mb-8 gap-4">
                  <div className="space-y-4">
                    <nav className="flex items-center gap-2 text-[10px] font-mono uppercase tracking-widest text-on-surface-variant">
                      <button onClick={() => setView('dashboard')} className="hover:text-primary transition-colors">대시보드</button>
                      <span>/</span>
                      <button onClick={() => setView('dashboard')} className="hover:text-primary transition-colors">자산</button>
                      <span>/</span>
                      <span className="text-primary-dim">{selectedAsset?.name || '소스'}</span>
                    </nav>
                    <h1 className="text-xl md:text-2xl font-headline font-bold tracking-tight uppercase">텍스트 & HTML 뷰어 상세</h1>
                  </div>
                  <div className="flex gap-2 md:gap-4">
                    <button className="flex-1 md:flex-none border border-outline px-4 md:px-6 py-2 flex items-center justify-center gap-2 text-[10px] md:text-xs uppercase tracking-widest hover:bg-surface-highest transition-all">
                      <FileText size={14} /> 복사
                    </button>
                    <button className="flex-1 md:flex-none border border-outline px-4 md:px-6 py-2 flex items-center justify-center gap-2 text-[10px] md:text-xs uppercase tracking-widest hover:bg-surface-highest transition-all">
                      <Download size={14} /> 다운로드
                    </button>
                  </div>
                </div>

                <div className="flex-1 flex flex-col lg:grid lg:grid-cols-2 gap-px bg-outline/20 border border-outline/30 overflow-hidden">
                  <div className="flex flex-col bg-surface-low h-1/2 lg:h-full">
                    <div className="flex items-center justify-between px-4 py-2 bg-surface-highest border-b border-outline/30">
                      <div className="flex items-center gap-2">
                        <Code size={14} className="text-primary" />
                        <span className="text-[10px] uppercase tracking-widest text-on-surface-variant">SOURCE_VIEW.HTML</span>
                      </div>
                      <span className="font-mono text-[10px] text-on-surface-variant">LN 1, COL 1</span>
                    </div>
                    <div className="flex-1 p-4 md:p-6 font-mono text-xs md:text-sm leading-relaxed text-primary-dim overflow-auto bg-black/20 custom-scrollbar">
                      <pre><code>{`<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <title>시스템 아키텍처 상세</title>
</head>
<body>
    <section class="container">
        <h1>디지털 아키텍트의 미래</h1>
        <p>본 시스템은 최첨단 터미널 인터페이스를 통해 
           데이터를 시각화하며, 사용자에게 직관적인 
           피드백을 제공합니다.</p>
        
        <div id="status-indicator">
            현재 상태: 최적화됨
        </div>
    </section>
</body>
</html>`}</code></pre>
                    </div>
                  </div>

                  <div className="flex flex-col bg-surface h-1/2 lg:h-full">
                    <div className="flex items-center justify-between px-4 py-2 bg-surface-highest border-b border-outline/30">
                      <div className="flex items-center gap-2">
                        <Monitor size={14} className="text-primary" />
                        <span className="text-[10px] uppercase tracking-widest text-on-surface-variant">RENDERED_PREVIEW</span>
                      </div>
                      <div className="flex gap-3">
                        <Smartphone size={14} className="text-on-surface-variant cursor-pointer" />
                        <Monitor size={14} className="text-primary cursor-pointer" />
                      </div>
                    </div>
                    <div className="flex-1 bg-white text-black p-6 md:p-12 overflow-auto custom-scrollbar">
                      <div className="max-w-2xl mx-auto space-y-6 md:space-y-8 font-sans">
                        <header className="border-l-4 border-black pl-4">
                          <h2 className="text-xl md:text-2xl font-bold tracking-tighter">디지털 아키텍트의 미래</h2>
                        </header>
                        <p className="text-sm md:text-base leading-relaxed text-gray-700">
                          본 시스템은 최첨단 터미널 인터페이스를 통해 데이터를 시각화하며, 사용자에게 직관적인 피드백을 제공합니다. 텍스트와 코드의 조화를 통해 새로운 디지털 경험을 설계하십시오.
                        </p>
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                          <div className="bg-gray-100 p-4 md:p-6">
                            <p className="text-[10px] font-bold uppercase tracking-widest text-gray-400 mb-2">현재 상태</p>
                            <p className="text-base md:text-lg font-bold">최적화됨</p>
                          </div>
                          <div className="bg-gray-100 p-4 md:p-6">
                            <p className="text-[10px] font-bold uppercase tracking-widest text-gray-400 mb-2">성능 지표</p>
                            <p className="text-base md:text-lg font-bold">99.9%</p>
                          </div>
                        </div>
                        <div className="h-32 md:h-48 bg-gray-900 flex items-center justify-center overflow-hidden">
                           <img 
                            src="https://images.unsplash.com/photo-1558494949-ef010cbdcc51?auto=format&fit=crop&q=80&w=1000" 
                            alt="Visual"
                            className="w-full h-full object-cover opacity-50 grayscale"
                            referrerPolicy="no-referrer"
                          />
                        </div>
                      </div>
                    </div>
                  </div>
                </div>

                <footer className="flex flex-col sm:flex-row sm:items-center justify-between py-4 border-t border-outline/20 mt-6 shrink-0 gap-4">
                  <div className="flex gap-8">
                    <div className="flex flex-col">
                      <span className="text-[10px] text-on-surface-variant uppercase tracking-widest">인코딩</span>
                      <span className="text-xs font-headline font-medium">UTF-8</span>
                    </div>
                    <div className="flex flex-col">
                      <span className="text-[10px] text-on-surface-variant uppercase tracking-widest">라인 수</span>
                      <span className="text-xs font-headline font-medium">1,402</span>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <ShieldCheck size={14} className="text-primary" />
                    <span className="text-[10px] text-primary uppercase tracking-widest">체크섬 확인됨</span>
                  </div>
                </footer>
              </motion.div>
            ) : view === 'login' ? (
              <motion.div 
                key="login"
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -20 }}
                className="h-full flex items-center justify-center p-8"
              >
                <div className="max-w-md w-full bg-surface-low border border-outline/20 p-10 space-y-8 shadow-2xl">
                  <div className="text-center space-y-4">
                    <div className="inline-flex p-4 bg-primary/10 rounded-full">
                      <Terminal size={48} className="text-primary" />
                    </div>
                    <h1 className="text-3xl font-headline font-bold tracking-tight">시스템 로그인</h1>
                    <p className="text-on-surface-variant text-sm">터미널 아키텍트 시스템에 접속하려면 인증이 필요합니다.</p>
                  </div>

                  {loginError && (
                    <div className="p-4 bg-red-500/10 border border-red-500/20 text-red-500 text-xs text-center font-medium animate-pulse">
                      {loginError}
                    </div>
                  )}

                  <button 
                    onClick={handleLogin}
                    disabled={isLoggingIn}
                    className={cn(
                      "w-full py-4 bg-primary text-on-primary font-headline font-bold flex items-center justify-center gap-3 hover:opacity-90 transition-all shadow-lg shadow-primary/20",
                      isLoggingIn && "opacity-50 cursor-not-allowed"
                    )}
                  >
                    {isLoggingIn ? (
                      <div className="w-5 h-5 border-2 border-on-primary/30 border-t-on-primary rounded-full animate-spin" />
                    ) : (
                      <LogIn size={20} />
                    )}
                    {isLoggingIn ? '인증 중...' : 'Google 계정으로 로그인'}
                  </button>
                </div>
              </motion.div>
            ) : view === 'profile' ? (
              <motion.div 
                key="profile"
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -20 }}
                className="h-full flex flex-col p-10 max-w-4xl mx-auto w-full"
              >
                <div className="flex items-center justify-between mb-12">
                  <h1 className="text-4xl font-headline font-bold tracking-tighter">개인 프로필 설정</h1>
                  <button 
                    onClick={handleLogout}
                    className="flex items-center gap-2 px-6 py-2 border border-red-500/50 text-red-500 hover:bg-red-500 hover:text-white transition-all text-sm font-bold uppercase tracking-widest"
                  >
                    <LogOut size={16} /> 로그아웃
                  </button>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-12">
                  <div className="flex flex-col items-center gap-6">
                    <div className="relative group">
                      <div className="w-48 h-48 rounded-full overflow-hidden border-4 border-primary/20 bg-surface-highest">
                        {profile?.photoURL ? (
                          <img src={profile.photoURL} alt="Profile" className="w-full h-full object-cover" />
                        ) : (
                          <div className="w-full h-full flex items-center justify-center text-outline">
                            <UserIcon size={64} />
                          </div>
                        )}
                      </div>
                      <label className="absolute bottom-2 right-2 p-3 bg-primary text-on-primary rounded-full shadow-xl hover:scale-110 transition-transform cursor-pointer">
                        <Camera size={20} />
                        <input 
                          type="file" 
                          className="hidden" 
                          accept="image/*"
                          onChange={(e) => {
                            const file = e.target.files?.[0];
                            if (file) {
                              const reader = new FileReader();
                              reader.onloadend = () => {
                                updateProfile({ photoURL: reader.result as string });
                              };
                              reader.readAsDataURL(file);
                            }
                          }}
                        />
                      </label>
                    </div>
                    <div className="text-center">
                      <p className="text-xs font-mono text-primary uppercase tracking-widest mb-1">{profile?.role}</p>
                      <p className="text-on-surface-variant text-[10px] font-mono">UID: {profile?.uid.slice(0, 12)}...</p>
                    </div>
                  </div>

                  <div className="md:col-span-2 space-y-8">
                    <div className="grid grid-cols-1 gap-6">
                      <div className="space-y-2">
                        <label className="text-[10px] uppercase font-bold text-outline tracking-widest">사용자 이름</label>
                        <input 
                          type="text" 
                          defaultValue={profile?.displayName}
                          onBlur={(e) => updateProfile({ displayName: e.target.value })}
                          className="w-full bg-surface-low border border-outline/20 p-4 focus:border-primary focus:ring-1 focus:ring-primary outline-none transition-all"
                        />
                      </div>
                      <div className="space-y-2 opacity-60">
                        <label className="text-[10px] uppercase font-bold text-outline tracking-widest">이메일 주소 (수정 불가)</label>
                        <input 
                          type="email" 
                          value={profile?.email}
                          disabled
                          className="w-full bg-surface-highest border border-outline/20 p-4 cursor-not-allowed"
                        />
                      </div>
                      <div className="space-y-2">
                        <label className="text-[10px] uppercase font-bold text-outline tracking-widest">프로필 사진 URL</label>
                        <input 
                          type="text" 
                          defaultValue={profile?.photoURL}
                          onBlur={(e) => updateProfile({ photoURL: e.target.value })}
                          className="w-full bg-surface-low border border-outline/20 p-4 focus:border-primary focus:ring-1 focus:ring-primary outline-none transition-all"
                          placeholder="https://example.com/photo.jpg"
                        />
                      </div>
                    </div>
                    <div className="pt-6 border-t border-outline/10">
                      <p className="text-[10px] text-outline uppercase tracking-widest mb-4">계정 정보</p>
                      <div className="flex gap-8">
                        <div>
                          <p className="text-[10px] text-on-surface-variant">생성일</p>
                          <p className="text-xs font-mono">{profile?.createdAt ? new Date(profile.createdAt).toLocaleDateString() : '-'}</p>
                        </div>
                        <div>
                          <p className="text-[10px] text-on-surface-variant">마지막 업데이트</p>
                          <p className="text-xs font-mono">{profile?.updatedAt ? new Date(profile.updatedAt).toLocaleDateString() : '-'}</p>
                        </div>
                      </div>
                    </div>
                  </div>
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
                        {adminLogs.map((log) => (
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
                              {log.userId && <p className="text-[9px] font-mono text-outline">USER_ID: {log.userId}</p>}
                            </div>
                          </div>
                        ))}
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
