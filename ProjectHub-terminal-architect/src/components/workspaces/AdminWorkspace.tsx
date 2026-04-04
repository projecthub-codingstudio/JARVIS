import React, { useMemo } from 'react';
import { Shield, ShieldAlert, ShieldCheck } from 'lucide-react';
import { cn } from '../../lib/utils';
import type { Artifact, Citation, Message, SystemLog } from '../../types';

interface AdminWorkspaceProps {
  assets: Artifact[];
  backendStatus: 'checking' | 'online' | 'offline';
  citations: Citation[];
  logs: SystemLog[];
  messages: Message[];
}

const DEFAULT_LOGS: SystemLog[] = [
  { id: 'default-1', timestamp: new Date().toISOString(), type: 'info', message: 'Worker ph-arch-01 registered at US-EAST-1a' },
  { id: 'default-2', timestamp: new Date().toISOString(), type: 'warning', message: 'Latency peak detected: 142ms in shard-04' },
  { id: 'default-3', timestamp: new Date().toISOString(), type: 'info', message: 'Auto-scaling group PH_CLUSTER initiated deployment: v1.0.4' },
];

export const AdminWorkspace: React.FC<AdminWorkspaceProps> = ({
  assets,
  backendStatus,
  citations,
  logs,
  messages,
}) => {
  const liveLogs = logs.length > 0 ? logs.slice(-8).reverse() : DEFAULT_LOGS;
  const securitySummary = useMemo(() => {
    const warningCount = liveLogs.filter((log) => log.type === 'warning').length;
    const errorCount = liveLogs.filter((log) => log.type === 'error').length;
    return { warningCount, errorCount };
  }, [liveLogs]);

  const activeWorkers = [
    { name: 'ph-arch-01', pid: '4412', cpu: '4.2%', state: 'Primary', tone: 'secondary' },
    { name: 'ph-arch-02', pid: '4413', cpu: '0.1%', state: 'Standby', tone: 'muted' },
    { name: 'ph-arch-03', pid: '4414', cpu: '0.1%', state: 'Standby', tone: 'muted' },
    { name: 'ph-arch-04', pid: '4415', cpu: '--', state: securitySummary.errorCount > 0 ? 'Error' : 'Standby', tone: securitySummary.errorCount > 0 ? 'error' : 'muted' },
  ];

  const runtimeLabel = backendStatus === 'online' ? 'ONLINE' : backendStatus === 'checking' ? 'CHECKING' : 'OFFLINE';

  return (
    <div className="flex h-full flex-col overflow-hidden bg-surface">
      <div className="flex h-14 shrink-0 items-center justify-between border-b border-white/5 bg-surface-container-low px-6">
        <div className="flex items-center gap-4">
          <h1 className="text-lg font-semibold tracking-tight text-on-surface">
            ProjectHub Runtime
            <span className={cn('ml-3 font-mono text-xs', backendStatus === 'online' ? 'text-secondary' : backendStatus === 'checking' ? 'text-primary' : 'text-[#ffb4ab]')}>
              {runtimeLabel}
            </span>
          </h1>
          <div className="hidden h-4 w-px bg-white/10 md:block" />
          <div className="hidden gap-4 font-mono text-[11px] text-on-surface-variant md:flex">
            <span>REGION: AP-NORTHEAST-2</span>
            <span>UPTIME: 342:12:04</span>
            <span>LOAD: 0.12 0.08 0.05</span>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button className="bg-surface-container-highest px-3 py-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-on-surface transition hover:ring-1 hover:ring-primary/20">
            Reboot Node
          </button>
          <button className="bg-secondary px-3 py-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-[#003909] transition hover:opacity-90">
            Export Dump
          </button>
        </div>
      </div>

      <div className="grid min-h-0 flex-1 grid-cols-1 gap-2 overflow-y-auto bg-surface p-4 custom-scrollbar xl:grid-cols-[280px_minmax(0,1fr)]">
        <section className="space-y-2">
          <div className="border border-white/5 bg-surface-container-low p-4">
            <div className="mb-4 flex items-center justify-between">
              <span className="text-[11px] font-semibold uppercase tracking-[0.12em] text-on-surface-variant">
                System Health
              </span>
              <ShieldCheck size={14} className={backendStatus === 'online' ? 'text-secondary' : 'text-primary'} />
            </div>
            <div className="space-y-4">
              <div className="border-l-2 border-primary bg-surface-container p-3">
                <div className="text-[10px] uppercase tracking-[0.12em] text-on-surface-variant">CPU Usage</div>
                <div className="mt-1 font-mono text-[28px] text-primary">12.4%</div>
              </div>
              <div className="border-l-2 border-tertiary bg-surface-container p-3">
                <div className="text-[10px] uppercase tracking-[0.12em] text-on-surface-variant">Memory</div>
                <div className="mt-1 font-mono text-[24px] text-tertiary">4.2GB <span className="text-xs text-on-surface-variant">/ 16GB</span></div>
              </div>
              <div className="border-l-2 border-secondary bg-surface-container p-3">
                <div className="text-[10px] uppercase tracking-[0.12em] text-on-surface-variant">Network IO</div>
                <div className="mt-1 font-mono text-[24px] text-secondary">842 KB/s</div>
              </div>
            </div>
          </div>

          <div className="border border-white/5 bg-surface-container p-4">
            <div className="mb-4 text-[11px] font-semibold uppercase tracking-[0.12em] text-on-surface-variant">
              Active Workers ({activeWorkers.length})
            </div>
            <div className="space-y-2">
              {activeWorkers.map((worker) => (
                <div
                  key={worker.name}
                  className={cn(
                    'border-l-2 bg-surface-container-low p-3',
                    worker.tone === 'secondary' ? 'border-secondary' : worker.tone === 'error' ? 'border-[#ffb4ab]' : 'border-white/10'
                  )}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="font-mono text-[11px] text-on-surface">{worker.name}</div>
                      <div className="mt-1 text-[10px] font-mono text-on-surface-variant">PID: {worker.pid}</div>
                    </div>
                    <span
                      className={cn(
                        'px-1.5 py-0.5 text-[10px] font-mono uppercase',
                        worker.tone === 'secondary'
                          ? 'bg-secondary-container/35 text-secondary'
                          : worker.tone === 'error'
                            ? 'bg-error-container/60 text-[#ffdad6]'
                            : 'bg-surface-container-highest text-on-surface-variant'
                      )}
                    >
                      {worker.state}
                    </span>
                  </div>
                  <div className="mt-2 text-right text-[10px] font-mono text-on-surface-variant">CPU: {worker.cpu}</div>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="grid min-h-0 grid-cols-1 gap-2 xl:grid-rows-[minmax(0,1fr)_210px]">
          <div className="flex min-h-0 flex-col border border-white/5 bg-surface-container-lowest">
            <div className="flex h-10 shrink-0 items-center justify-between bg-surface-container-high px-4">
              <div className="flex items-center gap-3">
                <span className="inline-flex h-2 w-2 rounded-full bg-secondary" />
                <span className="font-mono text-[12px] font-medium text-on-surface">SYSTEM_LIVE_STREAM</span>
              </div>
              <div className="flex gap-4 font-mono text-[11px] text-on-surface-variant">
                <button className="transition hover:text-on-surface">PAUSE</button>
                <button className="transition hover:text-on-surface">CLEAR</button>
              </div>
            </div>
            <div className="flex-1 space-y-1 overflow-y-auto bg-surface-container-lowest p-4 font-mono text-[12px] custom-scrollbar">
              {liveLogs.map((log) => (
                <div
                  key={log.id}
                  className={cn(
                    'flex gap-4',
                    log.type === 'warning' && 'text-[#ffb4ab]',
                    log.type === 'error' && 'text-[#ffdad6]'
                  )}
                >
                  <span className="text-on-surface-variant">
                    {new Date(log.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })}
                  </span>
                  <span className={cn(log.type === 'info' ? 'text-primary' : log.type === 'warning' ? 'text-[#ffb4ab]' : 'text-[#ffdad6]')}>
                    [{log.type === 'info' ? 'INFO' : log.type === 'warning' ? 'WARN' : 'ERROR'}]
                  </span>
                  <span className="text-on-surface">{log.message}</span>
                </div>
              ))}
            </div>
            <div className="border-t border-white/5 bg-surface-container px-4 py-3">
              <div className="flex items-center gap-3">
                <span className="font-mono text-secondary">▌</span>
                <input
                  className="w-full bg-transparent text-sm text-on-surface outline-none placeholder:text-outline"
                  placeholder="Execute PROJECT_HUB command..."
                />
              </div>
            </div>
          </div>

          <div className="grid grid-cols-1 gap-2 xl:grid-cols-2">
            <div className="border border-white/5 bg-surface-container-low p-4">
              <div className="mb-4 flex items-center justify-between">
                <span className="text-[11px] font-semibold uppercase tracking-[0.12em] text-on-surface-variant">
                  Security Audit Log
                </span>
                <Shield size={14} className="text-on-surface-variant" />
              </div>
              <div className="space-y-2 text-[11px] font-mono">
                {[
                  ['LOGIN: root_admin', 'SUCCESS'],
                  ['AUTH: API_KEY_882', 'SUCCESS'],
                  ['PORT: 22 SCAN DETECTED', securitySummary.warningCount > 0 ? 'BLOCKED' : 'CHECKED'],
                  ['CONFIG: WRITABLE_FS', securitySummary.errorCount > 0 ? 'LOCKED' : 'AUDITED'],
                ].map(([label, state]) => (
                  <div key={label} className="flex items-center justify-between border-b border-white/5 pb-2 last:border-b-0 last:pb-0">
                    <span className="text-on-surface">{label}</span>
                    <span className={cn(
                      state === 'SUCCESS' ? 'text-secondary' : state === 'BLOCKED' ? 'text-[#ffb4ab]' : 'text-primary'
                    )}>
                      {state}
                    </span>
                  </div>
                ))}
              </div>
            </div>

            <div className="border border-white/5 bg-surface-container-low p-4">
              <div className="mb-4 flex items-center justify-between">
                <span className="text-[11px] font-semibold uppercase tracking-[0.12em] text-on-surface-variant">
                  AI Security Audit Summary
                </span>
                <ShieldAlert size={14} className="text-tertiary" />
              </div>
              <p className="text-sm leading-relaxed text-on-surface-variant">
                Insight: System shows pattern of unauthorized port scanning from IP 192.0.2.14. AI has automatically blacklisted this CIDR range for 24 hours. No data leaks detected.
              </p>
              <div className="mt-4 flex flex-wrap gap-2">
                <button className="bg-surface-container-highest px-3 py-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-tertiary transition hover:text-on-surface">
                  Generate Full Report
                </button>
                <button className="px-3 py-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-on-surface-variant transition hover:text-on-surface">
                  Dismiss
                </button>
              </div>
              <div className="mt-6 border-t border-white/5 pt-4 text-[11px] font-mono text-on-surface-variant">
                Documents: {assets.length} · Citations: {citations.length} · Messages: {messages.length}
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
};

export default AdminWorkspace;
