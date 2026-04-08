import React, { useCallback, useEffect, useRef, useState } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import {
  AlertTriangle,
  CheckCircle2,
  Database,
  FolderOpen,
  HardDrive,
  LoaderCircle,
  Plus,
  RefreshCw,
  Trash2,
  XCircle,
} from 'lucide-react';
import { cn } from '../../lib/utils';
import {
  apiClient,
  type IndexingState,
  type KbStatusResponse,
  type KbValidateResponse,
  type ProfileItem,
} from '../../lib/api-client';
import type { SystemLog } from '../../types';

interface SettingsWorkspaceProps {
  backendStatus: 'checking' | 'online' | 'offline';
  indexingState: IndexingState;
  onIndexingStateChange: (state: IndexingState) => void;
  addLog: (log: SystemLog) => void;
}

// ── Helpers ──────────────────────────────────────
function formatBytes(bytes: number) {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
}

// ── Modal Backdrop ───────────────────────────────
function ModalBackdrop({
  children,
  onClose,
  disabled,
}: {
  children: React.ReactNode;
  onClose: () => void;
  disabled?: boolean;
}) {
  return (
    <motion.div
      className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      onClick={() => !disabled && onClose()}
    >
      <motion.div
        className="mx-4 w-full max-w-lg rounded-lg border border-white/10 bg-surface-container-high p-6 shadow-2xl"
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.95 }}
        onClick={(e) => e.stopPropagation()}
      >
        {children}
      </motion.div>
    </motion.div>
  );
}

// ── Main Component ───────────────────────────────
export const SettingsWorkspace: React.FC<SettingsWorkspaceProps> = ({
  backendStatus,
  indexingState,
  onIndexingStateChange,
  addLog,
}) => {
  // Profile state
  const [profiles, setProfiles] = useState<ProfileItem[]>([]);
  const [activeProfileId, setActiveProfileId] = useState<string>('');
  const [profilesLoading, setProfilesLoading] = useState(true);

  // KB status state
  const [kbStatus, setKbStatus] = useState<KbStatusResponse | null>(null);
  const [statusLoading, setStatusLoading] = useState(true);

  // Add profile dialog
  const [showAddDialog, setShowAddDialog] = useState(false);
  const [addName, setAddName] = useState('');
  const [addPath, setAddPath] = useState('');
  const [addValidation, setAddValidation] = useState<KbValidateResponse | null>(null);
  const [addValidating, setAddValidating] = useState(false);
  const [addSubmitting, setAddSubmitting] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);
  const addValidateTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Switch dialog
  const [switchTarget, setSwitchTarget] = useState<ProfileItem | null>(null);
  const [switching, setSwitching] = useState(false);

  // Delete dialog
  const [deleteTarget, setDeleteTarget] = useState<ProfileItem | null>(null);
  const [deleting, setDeleting] = useState(false);

  // Change directory (existing feature for active profile)
  const [changePath, setChangePath] = useState('');
  const [changeValidation, setChangeValidation] = useState<KbValidateResponse | null>(null);
  const [changeValidating, setChangeValidating] = useState(false);
  const [showChangeConfirm, setShowChangeConfirm] = useState(false);
  const [changing, setChanging] = useState(false);
  const [changeError, setChangeError] = useState<string | null>(null);
  const [changeSuccess, setChangeSuccess] = useState(false);
  const changeValidateTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const isIndexing = indexingState.status === 'scanning' || indexingState.status === 'indexing';
  const progressPercent = indexingState.total > 0
    ? Math.round((indexingState.processed / indexingState.total) * 100)
    : 0;

  // ── Load Data ──
  const loadProfiles = useCallback(async () => {
    try {
      setProfilesLoading(true);
      const data = await apiClient.listProfiles();
      setProfiles(data.profiles);
      setActiveProfileId(data.active);
    } catch {
      // backend may be offline
    } finally {
      setProfilesLoading(false);
    }
  }, []);

  const loadStatus = useCallback(async () => {
    try {
      setStatusLoading(true);
      const status = await apiClient.kbStatus();
      setKbStatus(status);
    } catch {
      // ignore
    } finally {
      setStatusLoading(false);
    }
  }, []);

  useEffect(() => {
    if (backendStatus === 'online') {
      void loadProfiles();
      void loadStatus();
    }
  }, [backendStatus, loadProfiles, loadStatus]);

  // Refresh status when indexing completes
  useEffect(() => {
    if (changeSuccess && (indexingState.status === 'done' || indexingState.status === 'idle')) {
      void loadStatus();
      void loadProfiles();
    }
  }, [indexingState.status, changeSuccess, loadStatus, loadProfiles]);

  // ── Add Profile: debounced validation ──
  useEffect(() => {
    if (!addPath.trim()) {
      setAddValidation(null);
      return;
    }
    if (addValidateTimer.current) clearTimeout(addValidateTimer.current);
    addValidateTimer.current = setTimeout(async () => {
      setAddValidating(true);
      try {
        const result = await apiClient.kbValidate(addPath);
        setAddValidation(result);
      } catch {
        setAddValidation(null);
      } finally {
        setAddValidating(false);
      }
    }, 500);
    return () => {
      if (addValidateTimer.current) clearTimeout(addValidateTimer.current);
    };
  }, [addPath]);

  // ── Change Directory: debounced validation ──
  useEffect(() => {
    if (!changePath.trim()) {
      setChangeValidation(null);
      return;
    }
    if (changeValidateTimer.current) clearTimeout(changeValidateTimer.current);
    changeValidateTimer.current = setTimeout(async () => {
      setChangeValidating(true);
      try {
        const result = await apiClient.kbValidate(changePath);
        setChangeValidation(result);
      } catch {
        setChangeValidation(null);
      } finally {
        setChangeValidating(false);
      }
    }, 500);
    return () => {
      if (changeValidateTimer.current) clearTimeout(changeValidateTimer.current);
    };
  }, [changePath]);

  // ── Handlers ──
  const handleAddProfile = async () => {
    setAddSubmitting(true);
    setAddError(null);
    try {
      const result = await apiClient.createProfile(addName, addPath);
      setProfiles(result.profiles);
      setActiveProfileId(result.active);
      setShowAddDialog(false);
      setAddName('');
      setAddPath('');
      setAddValidation(null);
      addLog({
        id: `${Date.now()}-profile-add`,
        timestamp: new Date().toISOString(),
        type: 'info',
        message: `Profile created: ${result.profile.name}`,
      });
    } catch (err) {
      setAddError(err instanceof Error ? err.message : 'Failed to create profile');
    } finally {
      setAddSubmitting(false);
    }
  };

  const handleSwitchProfile = async () => {
    if (!switchTarget) return;
    setSwitching(true);
    try {
      await apiClient.activateProfile(switchTarget.id);
      addLog({
        id: `${Date.now()}-profile-switch`,
        timestamp: new Date().toISOString(),
        type: 'info',
        message: `Switching to profile: ${switchTarget.name}`,
      });
      setSwitchTarget(null);
      // Backend will restart — frontend auto-reconnects via health polling
    } catch (err) {
      addLog({
        id: `${Date.now()}-profile-switch-err`,
        timestamp: new Date().toISOString(),
        type: 'error',
        message: `Profile switch failed: ${err instanceof Error ? err.message : 'unknown'}`,
      });
    } finally {
      setSwitching(false);
    }
  };

  const handleDeleteProfile = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await apiClient.deleteProfile(deleteTarget.id);
      await loadProfiles();
      setDeleteTarget(null);
      addLog({
        id: `${Date.now()}-profile-delete`,
        timestamp: new Date().toISOString(),
        type: 'info',
        message: `Profile deleted: ${deleteTarget.name}`,
      });
    } catch (err) {
      addLog({
        id: `${Date.now()}-profile-delete-err`,
        timestamp: new Date().toISOString(),
        type: 'error',
        message: `Delete failed: ${err instanceof Error ? err.message : 'unknown'}`,
      });
    } finally {
      setDeleting(false);
    }
  };

  const handleChangeConfirm = async () => {
    setChanging(true);
    setChangeError(null);
    try {
      const result = await apiClient.kbChange(changePath);
      onIndexingStateChange(result.indexing);
      setShowChangeConfirm(false);
      setChangeSuccess(true);
      setChangePath('');
      setChangeValidation(null);
      addLog({
        id: `${Date.now()}-kb-change`,
        timestamp: new Date().toISOString(),
        type: 'info',
        message: `KB directory changed: ${result.previous_path} → ${result.new_path}`,
      });
    } catch (err) {
      setChangeError(err instanceof Error ? err.message : 'Failed to change directory');
    } finally {
      setChanging(false);
    }
  };

  const canAddProfile = addName.trim().length > 0 && addValidation && !addValidation.error && !addSubmitting;
  const canChangeDir = changeValidation && changeValidation.exists && changeValidation.is_directory && changeValidation.readable && !isIndexing;

  return (
    <div className="flex h-full flex-col overflow-hidden bg-surface">
      {/* Header */}
      <div className="flex h-14 shrink-0 items-center justify-between border-b border-white/5 bg-surface-container-low px-6">
        <div className="flex items-center gap-4">
          <h1 className="text-lg font-semibold tracking-tight text-on-surface">Settings</h1>
          <div className="hidden h-4 w-px bg-white/10 md:block" />
          <span className="hidden font-mono text-[11px] text-on-surface-variant md:inline">
            Knowledge Base Profiles
          </span>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto custom-scrollbar p-6">
        <div className="mx-auto max-w-2xl space-y-8">

          {/* ── Profile List ── */}
          <section className="rounded-lg border border-white/5 bg-surface-container-low p-6">
            <div className="mb-4 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <Database size={18} className="text-primary" />
                <h2 className="text-sm font-semibold uppercase tracking-widest text-on-surface">
                  Profiles
                </h2>
              </div>
              <button
                onClick={() => { setShowAddDialog(true); setAddError(null); }}
                disabled={backendStatus !== 'online'}
                className={cn(
                  'flex items-center gap-1.5 rounded px-3 py-1.5 text-[11px] font-semibold uppercase tracking-widest transition',
                  backendStatus === 'online'
                    ? 'bg-primary/10 text-primary hover:bg-primary/20'
                    : 'cursor-not-allowed text-outline',
                )}
              >
                <Plus size={14} />
                Add Profile
              </button>
            </div>

            {profilesLoading ? (
              <div className="flex items-center gap-2 text-outline">
                <LoaderCircle size={14} className="animate-spin" />
                <span className="text-[12px]">Loading profiles...</span>
              </div>
            ) : profiles.length === 0 ? (
              <div className="text-[12px] text-outline">No profiles configured.</div>
            ) : (
              <div className="space-y-2">
                {profiles.map((profile) => (
                  <div
                    key={profile.id}
                    className={cn(
                      'group flex items-center gap-3 rounded-lg border px-4 py-3 transition',
                      profile.is_active
                        ? 'border-secondary/30 bg-secondary/5'
                        : 'border-white/5 bg-surface-container hover:border-white/10 cursor-pointer',
                    )}
                    onClick={() => {
                      if (!profile.is_active && !isIndexing) setSwitchTarget(profile);
                    }}
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="text-[13px] font-semibold text-on-surface">{profile.name}</span>
                        {profile.is_active && (
                          <span className="rounded bg-secondary/20 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-widest text-secondary">
                            Active
                          </span>
                        )}
                      </div>
                      <code className="mt-0.5 block truncate text-[11px] text-outline">{profile.kb_path}</code>
                      <div className="mt-1 flex gap-3 text-[10px] text-on-surface-variant">
                        <span>{profile.doc_count} docs</span>
                        <span>{profile.chunk_count} chunks</span>
                        {!profile.has_index && <span className="text-[#ffb4ab]">not indexed</span>}
                      </div>
                    </div>
                    {!profile.is_active && (
                      <button
                        onClick={(e) => { e.stopPropagation(); setDeleteTarget(profile); }}
                        className="shrink-0 rounded p-1.5 text-outline opacity-0 transition hover:bg-[#93000a]/20 hover:text-[#ffb4ab] group-hover:opacity-100"
                        title="Delete profile"
                      >
                        <Trash2 size={14} />
                      </button>
                    )}
                  </div>
                ))}
              </div>
            )}
          </section>

          {/* ── Active Profile Details ── */}
          <section className="rounded-lg border border-white/5 bg-surface-container-low p-6">
            <div className="mb-4 flex items-center gap-3">
              <FolderOpen size={18} className="text-primary" />
              <h2 className="text-sm font-semibold uppercase tracking-widest text-on-surface">
                Active Knowledge Base
              </h2>
            </div>

            {statusLoading ? (
              <div className="flex items-center gap-2 text-outline">
                <LoaderCircle size={14} className="animate-spin" />
                <span className="text-[12px]">Loading...</span>
              </div>
            ) : kbStatus ? (
              <div className="space-y-3">
                <div className="flex items-center gap-2 rounded bg-surface-container px-3 py-2">
                  <FolderOpen size={14} className="shrink-0 text-secondary" />
                  <code className="break-all text-[12px] text-on-surface">{kbStatus.path}</code>
                  {kbStatus.exists ? (
                    <CheckCircle2 size={14} className="ml-auto shrink-0 text-secondary" />
                  ) : (
                    <XCircle size={14} className="ml-auto shrink-0 text-[#ffb4ab]" />
                  )}
                </div>
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                  {[
                    { label: 'Documents', value: kbStatus.doc_count.toLocaleString() },
                    { label: 'Chunks', value: kbStatus.chunk_count.toLocaleString() },
                    { label: 'Vectors', value: kbStatus.embedding_count.toLocaleString() },
                    { label: 'Size', value: formatBytes(kbStatus.total_size_bytes) },
                  ].map(({ label, value }) => (
                    <div key={label} className="rounded bg-surface-container px-3 py-2">
                      <div className="text-[10px] uppercase tracking-widest text-outline">{label}</div>
                      <div className="mt-0.5 font-mono text-[13px] font-semibold text-on-surface">{value}</div>
                    </div>
                  ))}
                </div>
                {kbStatus.last_indexed && (
                  <div className="text-[11px] text-outline">
                    Last indexed: {new Date(kbStatus.last_indexed).toLocaleString('ko-KR')}
                  </div>
                )}
              </div>
            ) : (
              <div className="text-[12px] text-[#ffb4ab]">Backend offline</div>
            )}
          </section>

          {/* ── Change Active Profile's Directory ── */}
          <section className="rounded-lg border border-white/5 bg-surface-container-low p-6">
            <div className="mb-4 flex items-center gap-3">
              <HardDrive size={18} className="text-primary" />
              <h2 className="text-sm font-semibold uppercase tracking-widest text-on-surface">
                Change Directory
              </h2>
            </div>
            <div className="space-y-4">
              <div>
                <label className="mb-1.5 block text-[11px] uppercase tracking-widest text-outline">
                  New Directory Path
                </label>
                <div className="relative">
                  <input
                    type="text"
                    value={changePath}
                    onChange={(e) => { setChangePath(e.target.value); setChangeSuccess(false); setChangeError(null); }}
                    placeholder="/Users/username/Documents/my-knowledge-base"
                    disabled={isIndexing}
                    className={cn(
                      'w-full rounded border bg-surface-container px-3 py-2 font-mono text-[12px] text-on-surface placeholder:text-outline/50 focus:outline-none focus:ring-1',
                      changeValidation?.error ? 'border-[#ffb4ab]/50 focus:ring-[#ffb4ab]'
                        : changeValidation && !changeValidation.error ? 'border-secondary/50 focus:ring-secondary'
                        : 'border-white/10 focus:ring-primary',
                      isIndexing && 'cursor-not-allowed opacity-50',
                    )}
                  />
                  {changeValidating && <LoaderCircle size={14} className="absolute right-3 top-1/2 -translate-y-1/2 animate-spin text-primary" />}
                </div>
              </div>
              <AnimatePresence mode="wait">
                {changeValidation && (
                  <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }}>
                    {changeValidation.error ? (
                      <div className="flex items-center gap-2 rounded bg-[#93000a]/20 px-3 py-2 text-[12px] text-[#ffb4ab]">
                        <XCircle size={14} className="shrink-0" />{changeValidation.error}
                      </div>
                    ) : (
                      <div className="flex items-center gap-2 rounded bg-secondary/10 px-3 py-2 text-[12px] text-secondary">
                        <CheckCircle2 size={14} className="shrink-0" />
                        Valid — {changeValidation.file_count.toLocaleString()} indexable files
                      </div>
                    )}
                  </motion.div>
                )}
              </AnimatePresence>
              <button
                onClick={() => setShowChangeConfirm(true)}
                disabled={!canChangeDir || backendStatus !== 'online'}
                className={cn(
                  'rounded px-4 py-2 text-[12px] font-semibold uppercase tracking-widest transition',
                  canChangeDir && backendStatus === 'online' ? 'bg-primary text-surface hover:bg-primary/80' : 'cursor-not-allowed bg-white/5 text-outline',
                )}
              >
                Change Directory
              </button>
              {changeError && (
                <div className="flex items-center gap-2 rounded bg-[#93000a]/20 px-3 py-2 text-[12px] text-[#ffb4ab]">
                  <XCircle size={14} className="shrink-0" />{changeError}
                </div>
              )}
              {changeSuccess && (
                <div className="space-y-3">
                  <div className="flex items-center gap-2 rounded bg-secondary/10 px-3 py-2 text-[12px] text-secondary">
                    <CheckCircle2 size={14} className="shrink-0" />Directory changed. Re-indexing...
                  </div>
                  {isIndexing && (
                    <div className="space-y-2">
                      <div className="flex items-center justify-between text-[11px]">
                        <span className="flex items-center gap-2 text-primary">
                          <RefreshCw size={12} className="animate-spin" />
                          {indexingState.status === 'scanning' ? 'Scanning...' : 'Indexing...'}
                        </span>
                        <span className="font-mono text-outline">{indexingState.processed}/{indexingState.total} ({progressPercent}%)</span>
                      </div>
                      <div className="h-1.5 overflow-hidden rounded-full bg-white/5">
                        <motion.div className="h-full rounded-full bg-primary" initial={{ width: 0 }} animate={{ width: `${progressPercent}%` }} transition={{ duration: 0.3 }} />
                      </div>
                    </div>
                  )}
                  {indexingState.status === 'done' && (
                    <div className="flex items-center gap-2 text-[11px] text-secondary">
                      <CheckCircle2 size={12} />Complete — {indexingState.total} files processed.
                    </div>
                  )}
                  {indexingState.status === 'error' && (
                    <div className="flex items-center gap-2 text-[11px] text-[#ffb4ab]">
                      <XCircle size={12} />Failed: {indexingState.error}
                    </div>
                  )}
                </div>
              )}
            </div>
          </section>
        </div>
      </div>

      {/* ── Add Profile Dialog ── */}
      <AnimatePresence>
        {showAddDialog && (
          <ModalBackdrop onClose={() => setShowAddDialog(false)} disabled={addSubmitting}>
            <h3 className="mb-4 text-base font-semibold text-on-surface">Add Profile</h3>
            <div className="space-y-4">
              <div>
                <label className="mb-1.5 block text-[11px] uppercase tracking-widest text-outline">Profile Name</label>
                <input
                  type="text"
                  value={addName}
                  onChange={(e) => setAddName(e.target.value)}
                  placeholder="e.g. Work Documents"
                  className="w-full rounded border border-white/10 bg-surface-container px-3 py-2 text-[12px] text-on-surface placeholder:text-outline/50 focus:outline-none focus:ring-1 focus:ring-primary"
                />
              </div>
              <div>
                <label className="mb-1.5 block text-[11px] uppercase tracking-widest text-outline">Knowledge Base Path</label>
                <div className="relative">
                  <input
                    type="text"
                    value={addPath}
                    onChange={(e) => setAddPath(e.target.value)}
                    placeholder="/Users/username/Documents/work-kb"
                    className={cn(
                      'w-full rounded border bg-surface-container px-3 py-2 font-mono text-[12px] text-on-surface placeholder:text-outline/50 focus:outline-none focus:ring-1',
                      addValidation?.error ? 'border-[#ffb4ab]/50 focus:ring-[#ffb4ab]'
                        : addValidation && !addValidation.error ? 'border-secondary/50 focus:ring-secondary'
                        : 'border-white/10 focus:ring-primary',
                    )}
                  />
                  {addValidating && <LoaderCircle size={14} className="absolute right-3 top-1/2 -translate-y-1/2 animate-spin text-primary" />}
                </div>
              </div>
              <AnimatePresence mode="wait">
                {addValidation && (
                  <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }}>
                    {addValidation.error ? (
                      <div className="flex items-center gap-2 rounded bg-[#93000a]/20 px-3 py-2 text-[12px] text-[#ffb4ab]">
                        <XCircle size={14} className="shrink-0" />{addValidation.error}
                      </div>
                    ) : (
                      <div className="flex items-center gap-2 rounded bg-secondary/10 px-3 py-2 text-[12px] text-secondary">
                        <CheckCircle2 size={14} className="shrink-0" />
                        Valid — {addValidation.file_count.toLocaleString()} indexable files
                      </div>
                    )}
                  </motion.div>
                )}
              </AnimatePresence>
              {addError && (
                <div className="flex items-center gap-2 rounded bg-[#93000a]/20 px-3 py-2 text-[12px] text-[#ffb4ab]">
                  <XCircle size={14} className="shrink-0" />{addError}
                </div>
              )}
              <div className="flex justify-end gap-3 pt-2">
                <button onClick={() => setShowAddDialog(false)} disabled={addSubmitting} className="rounded px-4 py-2 text-[12px] font-semibold text-outline hover:bg-white/5">Cancel</button>
                <button
                  onClick={handleAddProfile}
                  disabled={!canAddProfile}
                  className={cn(
                    'flex items-center gap-2 rounded px-4 py-2 text-[12px] font-semibold transition',
                    canAddProfile ? 'bg-primary text-surface hover:bg-primary/80' : 'cursor-not-allowed bg-white/5 text-outline',
                  )}
                >
                  {addSubmitting && <LoaderCircle size={14} className="animate-spin" />}
                  Create
                </button>
              </div>
            </div>
          </ModalBackdrop>
        )}
      </AnimatePresence>

      {/* ── Switch Profile Dialog ── */}
      <AnimatePresence>
        {switchTarget && (
          <ModalBackdrop onClose={() => setSwitchTarget(null)} disabled={switching}>
            <div className="mb-4 flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-full bg-primary/20">
                <RefreshCw size={20} className="text-primary" />
              </div>
              <h3 className="text-base font-semibold text-on-surface">Switch Profile</h3>
            </div>
            <div className="mb-6 space-y-3 text-[12px] leading-relaxed text-on-surface-variant">
              <p>
                <strong className="text-on-surface">Target:</strong>{' '}
                <span className="text-primary">{switchTarget.name}</span>
              </p>
              <div className="rounded border border-primary/20 bg-primary/5 p-3">
                <ul className="ml-4 list-disc space-y-1">
                  <li>Backend will <strong>restart</strong> (2-3 seconds)</li>
                  <li>Search will be temporarily <strong>unavailable</strong></li>
                  {!switchTarget.has_index && (
                    <li className="text-[#ffb4ab]">First switch — <strong>full indexing</strong> will start automatically</li>
                  )}
                  {switchTarget.has_index && (
                    <li className="text-secondary">Index exists — <strong>immediate</strong> availability</li>
                  )}
                </ul>
              </div>
            </div>
            <div className="flex justify-end gap-3">
              <button onClick={() => setSwitchTarget(null)} disabled={switching} className="rounded px-4 py-2 text-[12px] font-semibold text-outline hover:bg-white/5">Cancel</button>
              <button
                onClick={handleSwitchProfile}
                disabled={switching}
                className={cn(
                  'flex items-center gap-2 rounded px-4 py-2 text-[12px] font-semibold transition',
                  switching ? 'cursor-not-allowed bg-primary/30 text-primary' : 'bg-primary text-surface hover:bg-primary/80',
                )}
              >
                {switching && <LoaderCircle size={14} className="animate-spin" />}
                {switching ? 'Switching...' : 'Switch'}
              </button>
            </div>
          </ModalBackdrop>
        )}
      </AnimatePresence>

      {/* ── Delete Profile Dialog ── */}
      <AnimatePresence>
        {deleteTarget && (
          <ModalBackdrop onClose={() => setDeleteTarget(null)} disabled={deleting}>
            <div className="mb-4 flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-full bg-[#ffb4ab]/20">
                <AlertTriangle size={20} className="text-[#ffb4ab]" />
              </div>
              <h3 className="text-base font-semibold text-on-surface">Delete Profile</h3>
            </div>
            <div className="mb-6 text-[12px] leading-relaxed text-on-surface-variant">
              <p>
                Profile <strong className="text-on-surface">{deleteTarget.name}</strong> and all its index data
                ({deleteTarget.doc_count} docs, {deleteTarget.chunk_count} chunks) will be permanently deleted.
              </p>
              <p className="mt-2 text-outline">The original knowledge base directory will not be affected.</p>
            </div>
            <div className="flex justify-end gap-3">
              <button onClick={() => setDeleteTarget(null)} disabled={deleting} className="rounded px-4 py-2 text-[12px] font-semibold text-outline hover:bg-white/5">Cancel</button>
              <button
                onClick={handleDeleteProfile}
                disabled={deleting}
                className={cn(
                  'flex items-center gap-2 rounded px-4 py-2 text-[12px] font-semibold transition',
                  deleting ? 'cursor-not-allowed bg-[#ffb4ab]/30 text-[#ffdad6]' : 'bg-[#ffb4ab] text-[#690005] hover:bg-[#ffb4ab]/80',
                )}
              >
                {deleting && <LoaderCircle size={14} className="animate-spin" />}
                Delete
              </button>
            </div>
          </ModalBackdrop>
        )}
      </AnimatePresence>

      {/* ── Change Directory Confirm Dialog ── */}
      <AnimatePresence>
        {showChangeConfirm && (
          <ModalBackdrop onClose={() => setShowChangeConfirm(false)} disabled={changing}>
            <div className="mb-4 flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-full bg-[#ffb4ab]/20">
                <AlertTriangle size={20} className="text-[#ffb4ab]" />
              </div>
              <h3 className="text-base font-semibold text-on-surface">Change Directory</h3>
            </div>
            <div className="mb-6 space-y-3 text-[12px] leading-relaxed text-on-surface-variant">
              <p>
                <strong className="text-on-surface">New path:</strong>{' '}
                <code className="rounded bg-surface-container px-1.5 py-0.5 font-mono text-[11px] text-primary">{changeValidation?.path || changePath}</code>
              </p>
              <div className="rounded border border-[#ffb4ab]/20 bg-[#93000a]/10 p-3">
                <p className="mb-2 font-semibold text-[#ffb4ab]">Warning</p>
                <ul className="ml-4 list-disc space-y-1 text-[#ffdad6]">
                  <li>Existing index will be <strong>purged</strong></li>
                  <li>{changeValidation?.file_count.toLocaleString() ?? '?'} files will be <strong>re-indexed</strong></li>
                  <li>Search will be <strong>limited</strong> during indexing</li>
                </ul>
              </div>
            </div>
            <div className="flex justify-end gap-3">
              <button onClick={() => setShowChangeConfirm(false)} disabled={changing} className="rounded px-4 py-2 text-[12px] font-semibold text-outline hover:bg-white/5">Cancel</button>
              <button
                onClick={handleChangeConfirm}
                disabled={changing}
                className={cn(
                  'flex items-center gap-2 rounded px-4 py-2 text-[12px] font-semibold transition',
                  changing ? 'cursor-not-allowed bg-[#ffb4ab]/30 text-[#ffdad6]' : 'bg-[#ffb4ab] text-[#690005] hover:bg-[#ffb4ab]/80',
                )}
              >
                {changing && <LoaderCircle size={14} className="animate-spin" />}
                {changing ? 'Processing...' : 'Confirm'}
              </button>
            </div>
          </ModalBackdrop>
        )}
      </AnimatePresence>
    </div>
  );
};
