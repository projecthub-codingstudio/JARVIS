import React, { useCallback, useEffect, useRef, useState } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import {
  AlertTriangle,
  CheckCircle2,
  Database,
  FolderOpen,
  HardDrive,
  LoaderCircle,
  RefreshCw,
  XCircle,
} from 'lucide-react';
import { cn } from '../../lib/utils';
import { apiClient, type IndexingState, type KbStatusResponse, type KbValidateResponse } from '../../lib/api-client';
import type { SystemLog } from '../../types';

interface SettingsWorkspaceProps {
  backendStatus: 'checking' | 'online' | 'offline';
  indexingState: IndexingState;
  onIndexingStateChange: (state: IndexingState) => void;
  addLog: (log: SystemLog) => void;
}

export const SettingsWorkspace: React.FC<SettingsWorkspaceProps> = ({
  backendStatus,
  indexingState,
  onIndexingStateChange,
  addLog,
}) => {
  const [kbStatus, setKbStatus] = useState<KbStatusResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [newPath, setNewPath] = useState('');
  const [validation, setValidation] = useState<KbValidateResponse | null>(null);
  const [validating, setValidating] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [changing, setChanging] = useState(false);
  const [changeError, setChangeError] = useState<string | null>(null);
  const [changeSuccess, setChangeSuccess] = useState(false);
  const validateTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Load current KB status
  const loadStatus = useCallback(async () => {
    try {
      setLoading(true);
      const status = await apiClient.kbStatus();
      setKbStatus(status);
    } catch {
      // ignore — backend may be offline
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (backendStatus === 'online') void loadStatus();
  }, [backendStatus, loadStatus]);

  // Debounced validation on path input
  useEffect(() => {
    if (!newPath.trim()) {
      setValidation(null);
      return;
    }
    if (validateTimer.current) clearTimeout(validateTimer.current);
    validateTimer.current = setTimeout(async () => {
      setValidating(true);
      try {
        const result = await apiClient.kbValidate(newPath);
        setValidation(result);
      } catch {
        setValidation(null);
      } finally {
        setValidating(false);
      }
    }, 500);
    return () => {
      if (validateTimer.current) clearTimeout(validateTimer.current);
    };
  }, [newPath]);

  // Refresh status when indexing completes
  useEffect(() => {
    if (changeSuccess && (indexingState.status === 'done' || indexingState.status === 'idle')) {
      void loadStatus();
    }
  }, [indexingState.status, changeSuccess, loadStatus]);

  const handleChangeConfirm = async () => {
    setChanging(true);
    setChangeError(null);
    try {
      const result = await apiClient.kbChange(newPath);
      onIndexingStateChange(result.indexing);
      setShowConfirm(false);
      setChangeSuccess(true);
      setNewPath('');
      setValidation(null);
      addLog({
        id: `${Date.now()}-kb-change`,
        timestamp: new Date().toISOString(),
        type: 'info',
        message: `KB directory changed: ${result.previous_path} → ${result.new_path}`,
      });
    } catch (err) {
      setChangeError(err instanceof Error ? err.message : 'Failed to change KB directory');
    } finally {
      setChanging(false);
    }
  };

  const isIndexing = indexingState.status === 'scanning' || indexingState.status === 'indexing';
  const canSubmit = validation && validation.exists && validation.is_directory && validation.readable && !isIndexing;
  const progressPercent = indexingState.total > 0
    ? Math.round((indexingState.processed / indexingState.total) * 100)
    : 0;

  const formatBytes = (bytes: number) => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
  };

  return (
    <div className="flex h-full flex-col overflow-hidden bg-surface">
      {/* Header */}
      <div className="flex h-14 shrink-0 items-center justify-between border-b border-white/5 bg-surface-container-low px-6">
        <div className="flex items-center gap-4">
          <h1 className="text-lg font-semibold tracking-tight text-on-surface">Settings</h1>
          <div className="hidden h-4 w-px bg-white/10 md:block" />
          <span className="hidden font-mono text-[11px] text-on-surface-variant md:inline">
            Knowledge Base Configuration
          </span>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto custom-scrollbar p-6">
        <div className="mx-auto max-w-2xl space-y-8">

          {/* ── Current KB Status ── */}
          <section className="rounded-lg border border-white/5 bg-surface-container-low p-6">
            <div className="mb-4 flex items-center gap-3">
              <Database size={18} className="text-primary" />
              <h2 className="text-sm font-semibold uppercase tracking-widest text-on-surface">
                Current Knowledge Base
              </h2>
            </div>

            {loading ? (
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
              <div className="text-[12px] text-[#ffb4ab]">
                Backend offline — unable to load KB status.
              </div>
            )}
          </section>

          {/* ── Change KB Directory ── */}
          <section className="rounded-lg border border-white/5 bg-surface-container-low p-6">
            <div className="mb-4 flex items-center gap-3">
              <HardDrive size={18} className="text-primary" />
              <h2 className="text-sm font-semibold uppercase tracking-widest text-on-surface">
                Change Directory
              </h2>
            </div>

            <div className="space-y-4">
              {/* Path input */}
              <div>
                <label className="mb-1.5 block text-[11px] uppercase tracking-widest text-outline">
                  New Directory Path
                </label>
                <div className="relative">
                  <input
                    type="text"
                    value={newPath}
                    onChange={(e) => {
                      setNewPath(e.target.value);
                      setChangeSuccess(false);
                      setChangeError(null);
                    }}
                    placeholder="/Users/username/Documents/my-knowledge-base"
                    disabled={isIndexing}
                    className={cn(
                      'w-full rounded border bg-surface-container px-3 py-2 font-mono text-[12px] text-on-surface placeholder:text-outline/50 focus:outline-none focus:ring-1',
                      validation?.error
                        ? 'border-[#ffb4ab]/50 focus:ring-[#ffb4ab]'
                        : validation && !validation.error
                          ? 'border-secondary/50 focus:ring-secondary'
                          : 'border-white/10 focus:ring-primary',
                      isIndexing && 'cursor-not-allowed opacity-50',
                    )}
                  />
                  {validating && (
                    <LoaderCircle size={14} className="absolute right-3 top-1/2 -translate-y-1/2 animate-spin text-primary" />
                  )}
                </div>
              </div>

              {/* Validation result */}
              <AnimatePresence mode="wait">
                {validation && (
                  <motion.div
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: 'auto' }}
                    exit={{ opacity: 0, height: 0 }}
                  >
                    {validation.error ? (
                      <div className="flex items-center gap-2 rounded bg-[#93000a]/20 px-3 py-2 text-[12px] text-[#ffb4ab]">
                        <XCircle size={14} className="shrink-0" />
                        {validation.error}
                      </div>
                    ) : (
                      <div className="flex items-center gap-2 rounded bg-secondary/10 px-3 py-2 text-[12px] text-secondary">
                        <CheckCircle2 size={14} className="shrink-0" />
                        Valid directory — {validation.file_count.toLocaleString()} indexable files found
                      </div>
                    )}
                  </motion.div>
                )}
              </AnimatePresence>

              {/* Change button */}
              <button
                onClick={() => setShowConfirm(true)}
                disabled={!canSubmit || backendStatus !== 'online'}
                className={cn(
                  'rounded px-4 py-2 text-[12px] font-semibold uppercase tracking-widest transition',
                  canSubmit && backendStatus === 'online'
                    ? 'bg-primary text-surface hover:bg-primary/80'
                    : 'cursor-not-allowed bg-white/5 text-outline',
                )}
              >
                Change Directory
              </button>

              {/* Errors */}
              {changeError && (
                <div className="flex items-center gap-2 rounded bg-[#93000a]/20 px-3 py-2 text-[12px] text-[#ffb4ab]">
                  <XCircle size={14} className="shrink-0" />
                  {changeError}
                </div>
              )}

              {/* Success + Progress */}
              {changeSuccess && (
                <div className="space-y-3">
                  <div className="flex items-center gap-2 rounded bg-secondary/10 px-3 py-2 text-[12px] text-secondary">
                    <CheckCircle2 size={14} className="shrink-0" />
                    Directory changed successfully. Re-indexing in progress...
                  </div>

                  {isIndexing && (
                    <div className="space-y-2">
                      <div className="flex items-center justify-between text-[11px]">
                        <span className="flex items-center gap-2 text-primary">
                          <RefreshCw size={12} className="animate-spin" />
                          {indexingState.status === 'scanning' ? 'Scanning files...' : 'Indexing documents...'}
                        </span>
                        <span className="font-mono text-outline">
                          {indexingState.processed}/{indexingState.total} ({progressPercent}%)
                        </span>
                      </div>
                      <div className="h-1.5 overflow-hidden rounded-full bg-white/5">
                        <motion.div
                          className="h-full rounded-full bg-primary"
                          initial={{ width: 0 }}
                          animate={{ width: `${progressPercent}%` }}
                          transition={{ duration: 0.3 }}
                        />
                      </div>
                    </div>
                  )}

                  {indexingState.status === 'done' && (
                    <div className="flex items-center gap-2 text-[11px] text-secondary">
                      <CheckCircle2 size={12} />
                      Re-indexing complete — {indexingState.total} files processed.
                    </div>
                  )}

                  {indexingState.status === 'error' && (
                    <div className="flex items-center gap-2 text-[11px] text-[#ffb4ab]">
                      <XCircle size={12} />
                      Re-indexing failed: {indexingState.error}
                    </div>
                  )}
                </div>
              )}
            </div>
          </section>
        </div>
      </div>

      {/* ── Confirmation Modal ── */}
      <AnimatePresence>
        {showConfirm && (
          <motion.div
            className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => !changing && setShowConfirm(false)}
          >
            <motion.div
              className="mx-4 w-full max-w-lg rounded-lg border border-white/10 bg-surface-container-high p-6 shadow-2xl"
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              onClick={(e) => e.stopPropagation()}
            >
              <div className="mb-4 flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-full bg-[#ffb4ab]/20">
                  <AlertTriangle size={20} className="text-[#ffb4ab]" />
                </div>
                <h3 className="text-base font-semibold text-on-surface">
                  Knowledge Base Directory Change
                </h3>
              </div>

              <div className="mb-6 space-y-3 text-[12px] leading-relaxed text-on-surface-variant">
                <p>
                  <strong className="text-on-surface">New path:</strong>{' '}
                  <code className="rounded bg-surface-container px-1.5 py-0.5 font-mono text-[11px] text-primary">
                    {validation?.path || newPath}
                  </code>
                </p>

                <div className="rounded border border-[#ffb4ab]/20 bg-[#93000a]/10 p-3">
                  <p className="mb-2 font-semibold text-[#ffb4ab]">Warning: The following actions will occur</p>
                  <ul className="ml-4 list-disc space-y-1 text-[#ffdad6]">
                    <li>Existing indexed data will be <strong>purged</strong> (documents, chunks, vectors)</li>
                    <li>New directory's files ({validation?.file_count.toLocaleString() ?? '?'} files) will be <strong>fully re-indexed</strong></li>
                    <li>Embedding generation will run in background (may take several minutes)</li>
                    <li>Search functionality will be <strong>limited</strong> during re-indexing</li>
                  </ul>
                </div>

                <p className="text-outline">
                  This process is irreversible. The previous index data will be permanently removed.
                </p>
              </div>

              <div className="flex justify-end gap-3">
                <button
                  onClick={() => setShowConfirm(false)}
                  disabled={changing}
                  className="rounded px-4 py-2 text-[12px] font-semibold text-outline transition hover:bg-white/5 hover:text-on-surface"
                >
                  Cancel
                </button>
                <button
                  onClick={handleChangeConfirm}
                  disabled={changing}
                  className={cn(
                    'flex items-center gap-2 rounded px-4 py-2 text-[12px] font-semibold transition',
                    changing
                      ? 'cursor-not-allowed bg-[#ffb4ab]/30 text-[#ffdad6]'
                      : 'bg-[#ffb4ab] text-[#690005] hover:bg-[#ffb4ab]/80',
                  )}
                >
                  {changing && <LoaderCircle size={14} className="animate-spin" />}
                  {changing ? 'Processing...' : 'Confirm Change'}
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};
