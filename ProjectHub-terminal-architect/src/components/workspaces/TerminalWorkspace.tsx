import React, { useEffect, useMemo, useRef, useState } from 'react';
import ReactMarkdown, { type Components } from 'react-markdown';
import {
  ArrowRight,
  Clock3,
  Code2,
  Command,
  Database,
  FileText,
  ImagePlus,
  Link2,
  LoaderCircle,
  RefreshCw,
  ShieldAlert,
  Sparkles,
  X,
} from 'lucide-react';
import type { IndexingState } from '../../lib/api-client';
import { normalizeResponseText } from '../../lib/response-text';
import { cn } from '../../lib/utils';
import type { Artifact, Citation, GuideDirective, Message, SystemLog } from '../../types';

interface TerminalWorkspaceProps {
  assets: Artifact[];
  backendStatus: 'checking' | 'online' | 'offline';
  citations: Citation[];
  error: string | null;
  focusInputNonce: number;
  guide: GuideDirective | null;
  inputValue: string;
  isLoading: boolean;
  logs: SystemLog[];
  messages: Message[];
  mode: 'home' | 'terminal';
  onInputChange: (value: string) => void;
  onNavigateToFile?: (path: string) => void;
  onOpenArtifact: (artifact: Artifact) => void;
  sessionId: string;
  onSubmit: (event: React.FormEvent<HTMLFormElement>) => void;
  onImageSubmit?: (text: string, image: File) => void;
  kbStats?: { chunks: number; docs: number; failed: number; failedPaths: string[]; sizeBytes: number; embeddings: number } | null;
  indexingState?: IndexingState;
  onReindex?: () => void;
  onRestart?: () => void;
}

function RestartProgress() {
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    const t0 = Date.now();
    const id = window.setInterval(() => setElapsed(Math.floor((Date.now() - t0) / 1000)), 1000);
    return () => window.clearInterval(id);
  }, []);
  return (
    <div className="flex items-center gap-2 rounded bg-primary/10 px-3 py-2">
      <div className="h-3.5 w-3.5 shrink-0 animate-spin rounded-full border-2 border-primary border-t-transparent" />
      <span className="text-[11px] font-semibold uppercase tracking-[0.12em] text-primary">
        Restarting{elapsed > 0 ? ` · ${elapsed}s` : ''}
      </span>
    </div>
  );
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`;
}

function getArtifactIcon(artifact: Artifact) {
  const type = artifact.type.toLowerCase();
  const viewerKind = artifact.viewer_kind.toLowerCase();

  if (viewerKind === 'code' || type.includes('code')) {
    return <Code2 size={14} className="text-secondary" />;
  }
  if (type.includes('spreadsheet')) {
    return <Database size={14} className="text-primary" />;
  }
  return <FileText size={14} className="text-on-surface-variant" />;
}

function getLogTone(type: SystemLog['type']) {
  switch (type) {
    case 'error':
      return 'text-[#ffb4ab]';
    case 'warning':
      return 'text-[#c9bfff]';
    default:
      return 'text-primary';
  }
}

const ANSWER_KIND_LABELS: Record<NonNullable<Message['answer_kind']>, string> = {
  utility_result: 'Utility Result',
  action_result: 'Action Result',
  live_data_result: 'Live Data',
  retrieval_result: 'Document Answer',
  capability_gap: 'Capability Notice',
};

const TASK_TITLE_LABELS: Record<string, string> = {
  datetime_now: '현재 시각',
  timezone_now: '시간대 확인',
  math_eval: '수식 계산',
  relative_date: '날짜 계산',
  calendar_followup: '일정 후속 처리',
  calendar_create: '일정 생성',
  calendar_update: '일정 수정',
  calendar_today: '일정 조회',
  action_map_execute: '액션 맵 실행',
  capability_gap: '지원 범위 안내',
  unit_convert: '단위 변환',
  capability_help: '도움말',
  runtime_status: '런타임 상태',
  doc_summary: '문서 요약',
  doc_outline: '문서 개요',
  sheet_list: '시트 목록',
  doc_sheet: '시트 상세',
  doc_section: '문서 구간',
};

function formatMessageTimestamp(timestamp: string) {
  if (!timestamp) return '';
  const parsed = new Date(timestamp);
  if (Number.isNaN(parsed.getTime())) {
    return timestamp;
  }
  return parsed.toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });
}

function getArchitectPanelTitle(message: Message) {
  const payload = message.structured_payload;
  const titleCandidates = ['title', 'section_label', 'sheet_name', 'range_label'] as const;

  if (payload) {
    for (const key of titleCandidates) {
      const value = payload[key];
      if (typeof value === 'string' && value.trim()) {
        return value;
      }
    }
  }

  if (message.task_id && TASK_TITLE_LABELS[message.task_id]) {
    return TASK_TITLE_LABELS[message.task_id];
  }

  if (message.answer_kind) {
    return ANSWER_KIND_LABELS[message.answer_kind];
  }

  return message.has_evidence ? '근거 기반 응답' : 'PH_ARCH 응답';
}

function buildMessageBlocks(messages: Message[]) {
  return messages.map((message, index) => ({
    key: `${message.id}-${index}`,
    message,
  }));
}

function buildSourceMapEntries(citations: Citation[], assets: Artifact[]) {
  const entries: Array<{ id: string; label: string; kind: 'citation' | 'artifact'; score?: number }> = [];
  const seen = new Set<string>();

  for (const citation of citations) {
    const label = citation.source_path || citation.full_source_path;
    if (!label || seen.has(label)) continue;
    seen.add(label);
    entries.push({ id: `citation-${label}`, label, kind: 'citation', score: citation.relevance_score });
  }

  for (const artifact of assets) {
    const label = artifact.title || artifact.path || artifact.full_path;
    if (!label || seen.has(label)) continue;
    seen.add(label);
    entries.push({ id: `artifact-${label}`, label, kind: 'artifact' });
  }

  return entries;
}

const GRAPH_MAX = 8;

const markdownComponents: Components = {
  h1: ({ children }) => <h1 className="mb-3 text-[18px] font-semibold tracking-tight text-on-surface">{children}</h1>,
  h2: ({ children }) => <h2 className="mb-3 text-[17px] font-semibold tracking-tight text-on-surface">{children}</h2>,
  h3: ({ children }) => <h3 className="mb-2 text-[16px] font-semibold tracking-tight text-on-surface">{children}</h3>,
  p: ({ children }) => <p className="mb-3 last:mb-0">{children}</p>,
  ul: ({ children }) => <ul className="mb-3 list-disc space-y-1 pl-5 last:mb-0">{children}</ul>,
  ol: ({ children }) => <ol className="mb-3 list-decimal space-y-1 pl-5 last:mb-0">{children}</ol>,
  li: ({ children }) => <li className="pl-1">{children}</li>,
  strong: ({ children }) => <strong className="font-semibold text-on-surface">{children}</strong>,
  em: ({ children }) => <em className="italic text-on-surface">{children}</em>,
  blockquote: ({ children }) => (
    <blockquote className="mb-3 border-l-2 border-secondary/40 pl-4 text-on-surface-variant last:mb-0">
      {children}
    </blockquote>
  ),
  pre: ({ children }) => (
    <pre className="mb-3 overflow-x-auto rounded-lg border border-white/8 bg-surface px-3 py-3 font-mono text-[13px] leading-6 text-on-surface last:mb-0">
      {children}
    </pre>
  ),
  code: ({ children, className }) => {
    const isBlock = typeof className === 'string' && className.length > 0;
    if (isBlock) {
      return <code className={className}>{children}</code>;
    }
    return (
      <code className="rounded bg-surface px-1.5 py-0.5 font-mono text-[13px] text-primary">
        {children}
      </code>
    );
  },
  a: ({ href, children }) => (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="text-primary underline underline-offset-2 transition hover:text-secondary"
    >
      {children}
    </a>
  ),
};

function ArchitectResponseBody({ content }: { content: string }) {
  const normalizedContent = normalizeResponseText(content);

  return (
    <div className="text-[15px] leading-7 text-on-surface">
      <ReactMarkdown components={markdownComponents}>
        {normalizedContent}
      </ReactMarkdown>
    </div>
  );
}

function renderStructuredPayload(message: Message) {
  const payload = message.structured_payload;
  if (!payload) return null;

  if (message.task_id === 'datetime_now' || message.task_id === 'timezone_now') {
    const clocks = Array.isArray(payload.clocks) ? payload.clocks as Array<Record<string, unknown>> : [];
    if (clocks.length === 0) return null;
    return (
      <div className="grid gap-2 md:grid-cols-2">
        {clocks.map((clock, index) => (
          <div key={`${message.id}-clock-${index}`} className="border border-white/5 bg-surface-container p-3">
            <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-secondary">
              {String(clock.label || clock.timezone || `Clock ${index + 1}`)}
            </div>
            <div className="mt-2 text-sm font-medium text-on-surface">
              {String(clock.formatted || '')}
            </div>
            <div className="mt-1 text-[11px] font-mono text-on-surface-variant">
              {String(clock.timezone || '')}
            </div>
          </div>
        ))}
      </div>
    );
  }

  if (message.task_id === 'math_eval') {
    return (
      <div className="grid gap-2 md:grid-cols-2">
        <div className="border border-white/5 bg-surface-container p-3">
          <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-on-surface-variant">Expression</div>
          <div className="mt-2 font-mono text-sm text-on-surface">{String(payload.expression || '')}</div>
        </div>
        <div className="border border-white/5 bg-surface-container p-3">
          <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-on-surface-variant">Result</div>
          <div className="mt-2 font-mono text-sm text-secondary">{String(payload.result || '')}</div>
        </div>
      </div>
    );
  }

  if (message.task_id === 'relative_date') {
    return (
      <div className="grid gap-2 md:grid-cols-3">
        <div className="border border-white/5 bg-surface-container p-3">
          <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-on-surface-variant">Anchor</div>
          <div className="mt-2 text-sm font-medium text-on-surface">{String(payload.anchor_label || '오늘')}</div>
          <div className="mt-1 text-[11px] font-mono text-on-surface-variant">{String(payload.anchor_formatted || '')}</div>
        </div>
        <div className="border border-white/5 bg-surface-container p-3">
          <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-on-surface-variant">Offset</div>
          <div className="mt-2 font-mono text-sm text-on-surface">{String(payload.offset_days || 0)} days</div>
        </div>
        <div className="border border-white/5 bg-surface-container p-3">
          <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-on-surface-variant">Result</div>
          <div className="mt-2 text-sm font-medium text-secondary">{String(payload.target_formatted || '')}</div>
          <div className="mt-1 font-mono text-[11px] text-outline">{String(payload.target_date || '')}</div>
        </div>
      </div>
    );
  }

  if (message.task_id === 'calendar_followup') {
    return (
      <div className="grid gap-2 md:grid-cols-2">
        <div className="border border-white/5 bg-surface-container p-3">
          <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-on-surface-variant">Target Date</div>
          <div className="mt-2 text-sm font-medium text-on-surface">{String(payload.target_formatted || 'Unknown')}</div>
          <div className="mt-1 font-mono text-[11px] text-outline">{String(payload.target_date || '')}</div>
        </div>
        <div className="border border-white/5 bg-surface-container p-3">
          <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-on-surface-variant">Status</div>
          <div className="mt-2 text-sm font-medium text-secondary">
            {String(payload.status || 'calendar_connector_missing')}
          </div>
        </div>
      </div>
    );
  }

  if (message.task_id === 'calendar_create') {
    return (
      <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-4">
        <div className="border border-white/5 bg-surface-container p-3">
          <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-on-surface-variant">Status</div>
          <div className="mt-2 text-sm font-medium text-secondary">{String(payload.status || 'created')}</div>
          <div className="mt-1 text-[11px] text-on-surface-variant">{String(payload.provider || 'macos_calendar')}</div>
        </div>
        <div className="border border-white/5 bg-surface-container p-3">
          <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-on-surface-variant">Title</div>
          <div className="mt-2 text-sm font-medium text-on-surface">{String(payload.title || 'Untitled event')}</div>
          <div className="mt-1 text-[11px] text-on-surface-variant">{String(payload.location || '')}</div>
        </div>
        <div className="border border-white/5 bg-surface-container p-3">
          <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-on-surface-variant">Date</div>
          <div className="mt-2 text-sm font-medium text-on-surface">{String(payload.target_formatted || 'Unknown')}</div>
          <div className="mt-1 font-mono text-[11px] text-outline">{String(payload.target_date || '')}</div>
        </div>
        <div className="border border-white/5 bg-surface-container p-3">
          <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-on-surface-variant">Time</div>
          <div className="mt-2 text-sm font-medium text-on-surface">
            {Boolean(payload.all_day) ? '종일 일정' : String(payload.start_label || '')}
          </div>
          <div className="mt-1 text-[11px] text-on-surface-variant">
            {Boolean(payload.all_day)
              ? String(payload.calendar_name || '')
              : `${String(payload.start_label || '')} → ${String(payload.end_label || '')}`}
          </div>
        </div>
      </div>
    );
  }

  if (message.task_id === 'calendar_update') {
    return (
      <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-4">
        <div className="border border-white/5 bg-surface-container p-3">
          <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-on-surface-variant">Status</div>
          <div className="mt-2 text-sm font-medium text-secondary">{String(payload.status || 'updated')}</div>
          <div className="mt-1 text-[11px] text-on-surface-variant">{String(payload.provider || 'macos_calendar')}</div>
        </div>
        <div className="border border-white/5 bg-surface-container p-3">
          <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-on-surface-variant">Title</div>
          <div className="mt-2 text-sm font-medium text-on-surface">{String(payload.title || 'Updated event')}</div>
          <div className="mt-1 text-[11px] text-on-surface-variant">{String(payload.calendar_name || '')}</div>
        </div>
        <div className="border border-white/5 bg-surface-container p-3">
          <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-on-surface-variant">From</div>
          <div className="mt-2 text-sm font-medium text-on-surface">{String(payload.source_date_formatted || 'Unknown')}</div>
          <div className="mt-1 font-mono text-[11px] text-outline">{String(payload.source_date || '')}</div>
        </div>
        <div className="border border-white/5 bg-surface-container p-3">
          <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-on-surface-variant">To</div>
          <div className="mt-2 text-sm font-medium text-on-surface">{String(payload.target_date_formatted || 'Unknown')}</div>
          <div className="mt-1 text-[11px] text-on-surface-variant">
            {Boolean(payload.all_day)
              ? '종일 일정'
              : `${String(payload.start_label || '')} → ${String(payload.end_label || '')}`}
          </div>
        </div>
      </div>
    );
  }

  if (message.task_id === 'calendar_today') {
    const events = Array.isArray(payload.events) ? payload.events as Array<Record<string, unknown>> : [];
    return (
      <div className="space-y-3">
        <div className="grid gap-2 md:grid-cols-4">
          <div className="border border-white/5 bg-surface-container p-3">
            <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-on-surface-variant">Range</div>
            <div className="mt-2 text-sm font-medium text-on-surface">{String(payload.range_label || '일정')}</div>
            <div className="mt-1 font-mono text-[11px] text-outline">{String(payload.range_kind || '')}</div>
          </div>
          <div className="border border-white/5 bg-surface-container p-3">
            <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-on-surface-variant">Count</div>
            <div className="mt-2 text-sm font-medium text-secondary">{String(payload.event_count || 0)} events</div>
            <div className="mt-1 text-[11px] text-on-surface-variant">{String(payload.provider || 'macos_calendar')}</div>
          </div>
          <div className="border border-white/5 bg-surface-container p-3">
            <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-on-surface-variant">From</div>
            <div className="mt-2 font-mono text-sm text-on-surface">{String(payload.start_date || '')}</div>
          </div>
          <div className="border border-white/5 bg-surface-container p-3">
            <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-on-surface-variant">To</div>
            <div className="mt-2 font-mono text-sm text-on-surface">{String(payload.end_date || '')}</div>
          </div>
        </div>
        <div className="space-y-2">
          {events.length === 0 ? (
            <div className="border border-dashed border-white/10 bg-surface-container p-3 text-sm text-on-surface-variant">
              표시할 일정이 없습니다.
            </div>
          ) : (
            events.slice(0, 10).map((event, index) => (
              <div key={`${message.id}-calendar-event-${index}`} className="border border-white/5 bg-surface-container p-3">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="text-sm font-medium text-on-surface">{String(event.title || 'Untitled event')}</div>
                    <div className="mt-1 text-[11px] text-on-surface-variant">
                      {String(event.date_label || '')}
                      {Boolean(event.all_day)
                        ? ' · 종일 일정'
                        : ` · ${String(event.start_label || '')}${String(event.end_label || '').trim() ? ` → ${String(event.end_label || '')}` : ''}`}
                    </div>
                  </div>
                  <div className="text-[11px] text-outline">{String(event.calendar_name || '')}</div>
                </div>
                {String(event.location || '').trim() ? (
                  <div className="mt-2 text-[11px] text-on-surface-variant">{String(event.location || '')}</div>
                ) : null}
              </div>
            ))
          )}
        </div>
      </div>
    );
  }

  if (message.task_id === 'action_map_execute') {
    const summary = (typeof payload.summary === 'object' && payload.summary !== null ? payload.summary : {}) as Record<string, unknown>;
    const steps = Array.isArray(payload.steps) ? payload.steps as Array<Record<string, unknown>> : [];
    return (
      <div className="space-y-3">
        <div className="grid gap-2 md:grid-cols-4">
          <div className="border border-white/5 bg-surface-container p-3">
            <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-on-surface-variant">Map</div>
            <div className="mt-2 text-sm font-medium text-on-surface">{String(payload.title || payload.map_id || 'Action Map')}</div>
            <div className="mt-1 font-mono text-[11px] text-outline">{String(payload.map_id || '')}</div>
          </div>
          <div className="border border-white/5 bg-surface-container p-3">
            <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-on-surface-variant">Match</div>
            <div className="mt-2 text-sm font-medium text-secondary">{String(payload.matched_query || '')}</div>
            <div className="mt-1 font-mono text-[11px] text-outline">score {String(payload.match_score || 0)}</div>
          </div>
          <div className="border border-white/5 bg-surface-container p-3">
            <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-on-surface-variant">Graph</div>
            <div className="mt-2 text-sm font-medium text-on-surface">
              {String(payload.node_count || 0)} nodes · {String(payload.edge_count || 0)} edges
            </div>
            <div className="mt-1 text-[11px] text-on-surface-variant">trigger {String(payload.trigger_query || 'manual')}</div>
          </div>
          <div className="border border-white/5 bg-surface-container p-3">
            <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-on-surface-variant">Summary</div>
            <div className="mt-2 text-xs leading-relaxed text-on-surface-variant">
              실행 {String(summary.executed || 0)} · API {String(summary.api_ready || 0)} · 차단 {String(summary.blocked || 0)} · 수동 {String(summary.manual || 0)}
            </div>
          </div>
        </div>
        {steps.length > 0 ? (
          <div className="space-y-2">
            {steps.map((step, index) => {
              const status = String(step.status || 'manual');
              const statusTone =
                status === 'executed'
                  ? 'text-secondary'
                  : status === 'api_ready'
                    ? 'text-primary'
                    : status === 'blocked' || status === 'failed'
                      ? 'text-[#ffb4ab]'
                      : 'text-on-surface-variant';
              return (
                <div key={`${message.id}-action-step-${index}`} className="border border-white/5 bg-surface-container p-3">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="text-sm font-medium text-on-surface">{String(step.title || `Step ${index + 1}`)}</div>
                      <div className="mt-1 font-mono text-[11px] text-outline">{String(step.skill_id || '')}</div>
                    </div>
                    <div className={cn('text-[10px] font-semibold uppercase tracking-[0.12em]', statusTone)}>
                      {status}
                    </div>
                  </div>
                  <div className="mt-2 flex flex-wrap gap-2 text-[10px] uppercase tracking-[0.12em] text-on-surface-variant">
                    <span className="bg-surface px-2 py-1">{String(step.execution_kind || 'manual')}</span>
                    {step.launch_target ? <span className="bg-surface px-2 py-1">{String(step.launch_target)}</span> : null}
                    {step.api_provider ? <span className="bg-surface px-2 py-1">{String(step.api_provider)}</span> : null}
                  </div>
                  <div className="mt-2 text-xs leading-relaxed text-on-surface-variant">
                    {String(step.result_text || '')}
                  </div>
                </div>
              );
            })}
          </div>
        ) : null}
      </div>
    );
  }

  if (message.task_id === 'capability_gap') {
    const examples = Array.isArray(payload.example_queries) ? payload.example_queries : [];
    return (
      <div className="grid gap-2 md:grid-cols-3">
        <div className="border border-white/5 bg-surface-container p-3">
          <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-on-surface-variant">Intent</div>
          <div className="mt-2 text-sm font-medium text-on-surface">{String(payload.requested_intent || 'unknown')}</div>
          <div className="mt-1 text-[11px] font-mono text-outline">{String(payload.skill_id || '')}</div>
        </div>
        <div className="border border-white/5 bg-surface-container p-3">
          <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-on-surface-variant">Status</div>
          <div className="mt-2 text-sm font-medium text-secondary">{String(payload.implementation_status || 'planned')}</div>
          <div className="mt-1 text-[11px] text-on-surface-variant">
            {Boolean(payload.requires_live_data) ? 'Live connector required' : 'Local implementation pending'}
          </div>
        </div>
        <div className="border border-white/5 bg-surface-container p-3">
          <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-on-surface-variant">Examples</div>
          <div className="mt-2 space-y-1 text-xs leading-relaxed text-on-surface-variant">
            {examples.length > 0 ? examples.map((item, index) => (
              <div key={`${message.id}-gap-${index}`}>{String(item)}</div>
            )) : 'No examples'}
          </div>
        </div>
      </div>
    );
  }

  if (message.task_id === 'unit_convert') {
    return (
      <div className="grid gap-2 md:grid-cols-3">
        <div className="border border-white/5 bg-surface-container p-3">
          <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-on-surface-variant">Source</div>
          <div className="mt-2 font-mono text-sm text-on-surface">
            {String(payload.value || '')}
            {String(payload.from_unit || '')}
          </div>
        </div>
        <div className="border border-white/5 bg-surface-container p-3">
          <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-on-surface-variant">Target</div>
          <div className="mt-2 font-mono text-sm text-on-surface">{String(payload.to_unit || '')}</div>
        </div>
        <div className="border border-white/5 bg-surface-container p-3">
          <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-on-surface-variant">Result</div>
          <div className="mt-2 font-mono text-sm text-secondary">
            {String(payload.result || '')}
            {String(payload.to_unit || '')}
          </div>
        </div>
      </div>
    );
  }

  if (message.task_id === 'capability_help') {
    const groups = Array.isArray(payload.groups) ? payload.groups as Array<Record<string, unknown>> : [];
    if (groups.length === 0) return null;
    return (
      <div className="grid gap-3 md:grid-cols-3">
        {groups.map((group, index) => {
          const items = Array.isArray(group.items) ? group.items : [];
          return (
            <div key={`${message.id}-group-${index}`} className="border border-white/5 bg-surface-container p-3">
              <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-tertiary">
                {String(group.title || `Group ${index + 1}`)}
              </div>
              <div className="mt-2 space-y-1 text-xs leading-relaxed text-on-surface-variant">
                {items.map((item, itemIndex) => (
                  <div key={`${message.id}-group-${index}-${itemIndex}`}>{String(item)}</div>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    );
  }

  if (message.task_id === 'runtime_status') {
    const failedChecks = Array.isArray(payload.failed_checks) ? payload.failed_checks : [];
    return (
      <div className="grid gap-2 md:grid-cols-3">
        <div className="border border-white/5 bg-surface-container p-3">
          <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-on-surface-variant">Status</div>
          <div className="mt-2 text-sm font-medium text-secondary">{String(payload.status_level || 'unknown')}</div>
        </div>
        <div className="border border-white/5 bg-surface-container p-3">
          <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-on-surface-variant">Chunks</div>
          <div className="mt-2 font-mono text-sm text-on-surface">{String(payload.chunk_count || 0)}</div>
        </div>
        <div className="border border-white/5 bg-surface-container p-3">
          <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-on-surface-variant">Checks</div>
          <div className="mt-2 text-xs leading-relaxed text-on-surface-variant">
            {failedChecks.length > 0 ? failedChecks.map((item) => String(item)).join(', ') : 'All clear'}
          </div>
        </div>
      </div>
    );
  }

  if (message.task_id === 'doc_summary') {
    const summaryLines = Array.isArray(payload.summary_lines) ? payload.summary_lines : [];
    const sourceTitles = Array.isArray(payload.source_titles) ? payload.source_titles : [];
    const sourceCount = typeof payload.source_count === 'number' ? payload.source_count : sourceTitles.length;
    const aiSynthesized = Boolean(payload.ai_synthesized);
    const modelId = typeof payload.model_id === 'string' ? payload.model_id : '';
    if (summaryLines.length === 0) return null;
    return (
      <div className="border border-white/5 bg-surface-container p-3">
        <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-tertiary">
          {String(payload.title || 'Document Summary')}
        </div>
        <div className="mt-2 flex flex-wrap gap-2 text-[10px] font-semibold uppercase tracking-[0.12em]">
          <span className={cn('rounded-sm px-2 py-1', aiSynthesized ? 'bg-secondary/15 text-secondary' : 'bg-surface-container-high text-on-surface-variant')}>
            {aiSynthesized ? 'RAG Synthesis' : 'Deterministic Summary'}
          </span>
          <span className="rounded-sm bg-surface-container-high px-2 py-1 text-on-surface-variant">
            {sourceCount} sources
          </span>
          {modelId ? (
            <span className="rounded-sm bg-surface-container-high px-2 py-1 font-mono text-outline">
              {modelId}
            </span>
          ) : null}
        </div>
        <div className="mt-2 space-y-2 text-xs leading-relaxed text-on-surface-variant">
          {summaryLines.slice(0, 5).map((line, index) => (
            <div key={`${message.id}-summary-${index}`}>{String(line)}</div>
          ))}
        </div>
        {sourceTitles.length > 0 ? (
          <div className="mt-3 border border-white/5 bg-surface-container-high p-3">
            <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-on-surface-variant">Sources</div>
            <div className="mt-2 text-[11px] leading-relaxed text-outline">
              {sourceTitles.slice(0, 4).map((item) => String(item)).join(' · ')}
            </div>
          </div>
        ) : null}
      </div>
    );
  }

  if (message.task_id === 'doc_outline') {
    const outline = Array.isArray(payload.outline) ? payload.outline : [];
    if (outline.length === 0) return null;
    return (
      <div className="border border-white/5 bg-surface-container p-3">
        <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-tertiary">
          {String(payload.title || 'Document Outline')}
        </div>
        <div className="mt-2 grid gap-1 text-xs leading-relaxed text-on-surface-variant">
          {outline.slice(0, 8).map((entry, index) => (
            <div key={`${message.id}-outline-${index}`} className="font-mono">
              {String(entry)}
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (message.task_id === 'sheet_list') {
    const sheets = Array.isArray(payload.sheets) ? payload.sheets as Array<Record<string, unknown>> : [];
    if (sheets.length === 0) return null;
    return (
      <div className="grid gap-2 md:grid-cols-2">
        {sheets.slice(0, 6).map((sheet, index) => (
          <div key={`${message.id}-sheet-${index}`} className="border border-white/5 bg-surface-container p-3">
            <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-tertiary">
              {String(sheet.sheet_name || `Sheet ${index + 1}`)}
            </div>
            <div className="mt-2 text-xs leading-relaxed text-on-surface-variant">
              컬럼 {String(sheet.column_count || 0)}개 · 행 {String(sheet.row_count || 0)}개
            </div>
            {sheet.header_preview ? (
              <div className="mt-2 font-mono text-[11px] text-outline">{String(sheet.header_preview)}</div>
            ) : null}
          </div>
        ))}
      </div>
    );
  }

  if (message.task_id === 'doc_sheet') {
    const sheets = Array.isArray(payload.sheets) ? payload.sheets as Array<Record<string, unknown>> : [];
    return (
      <div className="border border-white/5 bg-surface-container p-3">
        <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-tertiary">
          {String(payload.sheet_name || payload.title || 'Selected Sheet')}
        </div>
        <div className="mt-2 grid gap-2 md:grid-cols-3">
          <div className="border border-white/5 bg-surface-container-high p-3">
            <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-on-surface-variant">Index</div>
            <div className="mt-2 font-mono text-sm text-on-surface">
              {payload.sheet_index ? `Sheet ${String(payload.sheet_index)}` : 'Unknown'}
            </div>
          </div>
          <div className="border border-white/5 bg-surface-container-high p-3">
            <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-on-surface-variant">Rows / Columns</div>
            <div className="mt-2 text-sm text-on-surface">
              {String(payload.row_count || 0)} rows · {String(payload.column_count || 0)} columns
            </div>
          </div>
          <div className="border border-white/5 bg-surface-container-high p-3">
            <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-on-surface-variant">Headers</div>
            <div className="mt-2 font-mono text-[11px] text-outline">
              {String(payload.header_preview || 'No header preview')}
            </div>
          </div>
        </div>
        {payload.first_row_preview ? (
          <div className="mt-3 border border-white/5 bg-surface-container-high p-3">
            <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-on-surface-variant">First Row</div>
            <div className="mt-2 font-mono text-[11px] text-on-surface-variant">{String(payload.first_row_preview)}</div>
          </div>
        ) : null}
        {sheets.length > 1 ? (
          <div className="mt-3 text-[11px] text-on-surface-variant">
            Available: {sheets.slice(0, 5).map((sheet) => String(sheet.sheet_name || '')).filter(Boolean).join(', ')}
          </div>
        ) : null}
      </div>
    );
  }

  if (message.task_id === 'doc_section') {
    const sectionLines = Array.isArray(payload.section_lines) ? payload.section_lines : [];
    return (
      <div className="border border-white/5 bg-surface-container p-3">
        <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-tertiary">
          {String(payload.section_label || 'Document Section')}
        </div>
        <div className="mt-2 space-y-1 text-xs leading-relaxed text-on-surface-variant">
          {sectionLines.length > 0 ? (
            sectionLines.slice(0, 8).map((line, index) => (
              <div key={`${message.id}-section-${index}`}>{String(line)}</div>
            ))
          ) : (
            <div>해당 구간의 내용을 찾지 못했습니다.</div>
          )}
        </div>
      </div>
    );
  }

  return null;
}

export const TerminalWorkspace: React.FC<TerminalWorkspaceProps> = ({
  assets,
  backendStatus,
  citations,
  error,
  focusInputNonce,
  guide,
  inputValue,
  isLoading,
  logs,
  messages,
  mode,
  onInputChange,
  onNavigateToFile,
  onOpenArtifact,
  sessionId,
  onSubmit,
  onImageSubmit,
  kbStats,
  indexingState,
  onReindex,
  onRestart,
}) => {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [selectedImage, setSelectedImage] = useState<File | null>(null);
  const [showFailedDocs, setShowFailedDocs] = useState(false);
  const imagePreviewUrl = useMemo(() => (
    selectedImage ? URL.createObjectURL(selectedImage) : null
  ), [selectedImage]);
  useEffect(() => {
    return () => { if (imagePreviewUrl) URL.revokeObjectURL(imagePreviewUrl); };
  }, [imagePreviewUrl]);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const terminalScrollRef = useRef<HTMLDivElement | null>(null);
  const terminalEndRef = useRef<HTMLDivElement | null>(null);
  const commandQueue = guide?.suggested_replies?.slice(0, 3) ?? [];
  const activityLogs = logs.slice(-4).reverse();

  const terminalBlocks = useMemo(() => buildMessageBlocks(messages), [messages]);
  const [collapseAssets, setCollapseAssets] = useState(false);
  const visibleAssets = collapseAssets ? assets.slice(0, 6) : assets;
  const currentCitations = citations.slice(0, 3);
  const sourceMapEntries = useMemo(() => buildSourceMapEntries(citations, assets), [citations, assets]);
  const latestArchitect = [...messages].reverse().find((message) => message.role === 'architect');
  const tokenUsage = Math.min(100, Math.max(8, Math.round((latestArchitect?.content.length || 24) / 8)));
  const latestLog = logs.length > 0 ? logs[logs.length - 1] : null;
  const guideState = guide?.has_clarification
    ? 'clarification'
    : guide?.loop_stage || 'idle';
  const statusTone = backendStatus === 'online' ? 'text-secondary' : backendStatus === 'checking' ? 'text-primary' : 'text-[#ffb4ab]';
  const readinessSummary = backendStatus !== 'online'
    ? '백엔드 연결이 확인되지 않았습니다. 질의 처리는 현재 보장되지 않습니다.'
    : citations.length > 0
      ? `${citations.length}개의 근거가 연결되어 있습니다. 다음 질의부터는 바로 문서와 근거를 중심으로 이어집니다.`
      : '연결은 정상입니다. 아직 질의 기록이 없어 문서와 근거가 비어 있습니다.';
  const latestMessage = messages.length > 0 ? messages[messages.length - 1] : null;
  const responseCount = messages.filter((message) => message.role === 'architect').length;

  const focusTerminalInput = () => {
    inputRef.current?.focus();
    if (inputRef.current) {
      const { value } = inputRef.current;
      inputRef.current.setSelectionRange(value.length, value.length);
    }
  };

  const handleSuggestedCommandSelect = (command: string) => {
    onInputChange(command);
    window.requestAnimationFrame(() => {
      focusTerminalInput();
    });
  };

  useEffect(() => {
    if (mode !== 'terminal') return;
    const timer = window.setTimeout(() => {
      inputRef.current?.focus();
      inputRef.current?.setSelectionRange(inputRef.current.value.length, inputRef.current.value.length);
    }, 0);
    return () => window.clearTimeout(timer);
  }, [focusInputNonce, mode]);

  useEffect(() => {
    if (mode !== 'terminal') return;
    const frame = window.requestAnimationFrame(() => {
      if (terminalEndRef.current) {
        terminalEndRef.current.scrollIntoView({ block: 'end' });
      }
      if (terminalScrollRef.current) {
        terminalScrollRef.current.scrollTop = terminalScrollRef.current.scrollHeight;
      }
    });
    return () => window.cancelAnimationFrame(frame);
  }, [mode, messages.length, isLoading, assets.length, citations.length]);

  if (mode === 'home') {
    return (
      <div className="flex h-full min-h-0 flex-col overflow-hidden bg-surface">
        <div className="grid min-h-0 flex-1 grid-cols-1 xl:grid-cols-[220px_minmax(0,1fr)_284px]">
          <section className="overflow-y-auto border-r border-white/5 bg-surface-container-low px-3 py-4 custom-scrollbar">
            <div className="mb-4 flex items-center justify-between border-b border-white/5 pb-3">
              <span className="text-[11px] font-semibold uppercase tracking-[0.12em] text-on-surface-variant">
                Active Task Queue
              </span>
              <span className="text-[10px] font-mono uppercase text-secondary">
                {backendStatus === 'online' ? 'running' : backendStatus}
              </span>
            </div>
            {commandQueue.length > 0 ? (
              <div className="space-y-1">
                {commandQueue.map((command, index) => (
                  <div
                    key={command}
                    className={cn(
                      'border-l-2 px-3 py-3',
                      index === 0 ? 'border-secondary bg-surface-container' : 'border-transparent bg-surface-container-lowest/40'
                    )}
                  >
                    <p className="text-[13px] font-medium text-primary">
                      Suggested Command {index + 1}
                    </p>
                    <p className="mt-1 text-xs leading-relaxed text-on-surface-variant">
                      {command}
                    </p>
                    <div className="mt-2 flex gap-2">
                      <span className="bg-surface-container-high px-2 py-0.5 text-[10px] font-mono uppercase text-on-surface-variant">
                        {guide?.intent || 'idle'}
                      </span>
                      <span className="bg-surface-container-high px-2 py-0.5 text-[10px] font-mono uppercase text-on-surface-variant">
                        {guide?.skill || guideState}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="border border-white/5 bg-surface-container px-3 py-3 text-xs leading-relaxed text-on-surface-variant">
                아직 백엔드가 제안한 후속 질의가 없습니다. 첫 질문을 보내면 이 영역에 실제 추천 흐름이 표시됩니다.
              </div>
            )}

            <div className="mt-6 rounded-sm bg-surface-container p-3">
              <div className="mb-2 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-tertiary">
                <Sparkles size={12} />
                Workspace State
              </div>
              <p className="text-xs leading-relaxed text-on-surface-variant">
                Session {sessionId.slice(0, 8)} · guide {guideState} · logs {logs.length}
              </p>
            </div>

            <div className="mt-6 border-t border-white/5 pt-4">
              <div className="mb-3 text-[11px] font-semibold uppercase tracking-[0.12em] text-on-surface-variant">
                Draft Command
              </div>
              <div className="rounded-sm bg-surface-container-lowest/40 px-3 py-3 font-mono text-[11px] text-outline">
                {inputValue.trim() ? inputValue : 'No draft input'}
              </div>
            </div>
          </section>

          <section className="flex min-h-0 flex-col overflow-y-auto bg-surface px-4 py-6 xl:px-6 custom-scrollbar">
            <div className="mb-6 flex items-start justify-between gap-4">
              <div>
                <h1 className="text-[30px] font-semibold tracking-tight text-on-surface">Operational Workspace</h1>
                <p className="mt-2 text-sm text-on-surface-variant">
                  {backendStatus === 'online' ? 'JARVIS backend is connected.' : backendStatus === 'checking' ? 'Checking backend connectivity.' : 'JARVIS backend is offline.'}
                  {' '}Session {sessionId.slice(0, 8)}{kbStats ? ` · ${kbStats.docs.toLocaleString()} docs · ${kbStats.chunks.toLocaleString()} chunks · ${formatBytes(kbStats.sizeBytes)}` : ''} · {logs.length} events
                </p>
              </div>
              <div className="flex items-center gap-2">
                {onRestart && (
                  <button
                    onClick={onRestart}
                    disabled={backendStatus === 'checking'}
                    className="rounded bg-surface-container-high px-3 py-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-outline transition hover:text-primary hover:bg-surface-container-highest disabled:opacity-30"
                    title="백엔드 재시작"
                  >
                  Restart
                  </button>
                )}
                {backendStatus === 'checking' ? (
                  <RestartProgress />
                ) : (
                  <div className={cn('bg-surface-container-high px-3 py-2 text-[11px] font-semibold uppercase tracking-[0.12em]', statusTone)}>
                    {backendStatus}
                  </div>
                )}
              </div>
            </div>

            {indexingState && (indexingState.status === 'scanning' || indexingState.status === 'indexing') && (
              <div className="mb-4 flex items-center gap-3 rounded-lg border border-primary/30 bg-primary/5 px-4 py-3">
                <div className="w-4 h-4 border-2 border-primary border-t-transparent rounded-full animate-spin shrink-0" />
                <div className="flex-1 min-w-0">
                  <div className="text-[12px] font-semibold text-primary">
                    {indexingState.status === 'scanning' ? '파일 스캔 중...' : `인덱싱 중 — ${indexingState.processed} / ${indexingState.total} files`}
                  </div>
                  {indexingState.status === 'indexing' && indexingState.total > 0 && (
                    <div className="mt-2 h-1.5 rounded-full bg-surface-container-highest overflow-hidden">
                      <div
                        className="h-full rounded-full bg-primary transition-all duration-500"
                        style={{ width: `${Math.round((indexingState.processed / indexingState.total) * 100)}%` }}
                      />
                    </div>
                  )}
                </div>
              </div>
            )}
            <div className="mb-6 grid grid-cols-2 gap-3 xl:grid-cols-4">
              <div className="border border-white/5 bg-surface-container-low px-4 py-3">
                <div className="mb-2 flex items-center justify-between">
                  <span className="text-[11px] font-semibold uppercase tracking-[0.12em] text-on-surface-variant">Documents</span>
                  {onReindex && backendStatus === 'online' && (
                    <button
                      onClick={onReindex}
                      disabled={indexingState?.status === 'scanning' || indexingState?.status === 'indexing'}
                      className="rounded p-1 text-outline transition hover:bg-surface-container-highest hover:text-primary disabled:opacity-30 disabled:cursor-not-allowed"
                      title="지식베이스 리인덱스"
                    >
                      <RefreshCw size={12} className={indexingState?.status === 'indexing' ? 'animate-spin' : ''} />
                    </button>
                  )}
                </div>
                <div className="text-lg font-mono font-semibold text-on-surface">{kbStats ? kbStats.docs.toLocaleString() : '--'}</div>
                <div className="mt-1 text-[10px] text-outline">
                  {kbStats ? `${formatBytes(kbStats.sizeBytes)} total` : 'offline'}
                  {kbStats && kbStats.failed > 0 && (
                    <button
                      onClick={() => setShowFailedDocs((v) => !v)}
                      className="text-[#ffb4ab] hover:underline ml-1"
                    >
                      · {kbStats.failed} failed {showFailedDocs ? '▾' : '▸'}
                    </button>
                  )}
                </div>
              </div>
              <div className="border border-white/5 bg-surface-container-low px-4 py-3">
                <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-on-surface-variant">Chunks</div>
                <div className="text-lg font-mono font-semibold text-on-surface">{kbStats ? kbStats.chunks.toLocaleString() : '--'}</div>
                <div className="mt-1 text-[10px] text-outline">{kbStats ? 'indexed & searchable' : 'offline'}</div>
              </div>
              <div className="border border-white/5 bg-surface-container-low px-4 py-3">
                <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-on-surface-variant">Vectors</div>
                <div className="text-lg font-mono font-semibold text-on-surface">{kbStats ? kbStats.embeddings.toLocaleString() : '--'}</div>
                <div className="mt-1 text-[10px] text-outline">
                  {kbStats
                    ? kbStats.chunks > 0
                      ? `${Math.round((kbStats.embeddings / kbStats.chunks) * 100)}% coverage`
                      : 'no chunks'
                    : 'offline'}
                </div>
              </div>
              <div className="border border-white/5 bg-surface-container-low px-4 py-3">
                <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-on-surface-variant">Session</div>
                <div className="text-lg font-mono font-semibold text-on-surface">{assets.length + citations.length}</div>
                <div className="mt-1 text-[10px] text-outline">
                  {assets.length} artifacts · {citations.length} citations
                </div>
              </div>
            </div>

            {showFailedDocs && kbStats && kbStats.failedPaths.length > 0 && (
              <div className="mb-6 rounded-lg border border-[#ffb4ab]/20 bg-[#ffb4ab]/5 px-4 py-3">
                <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-[#ffb4ab]">
                  인덱싱 실패 문서 ({kbStats.failedPaths.length})
                </div>
                <div className="space-y-1 max-h-48 overflow-y-auto custom-scrollbar">
                  {kbStats.failedPaths.map((p) => {
                    const kbIdx = p.indexOf('knowledge_base/');
                    const display = kbIdx >= 0 ? p.slice(kbIdx + 'knowledge_base/'.length) : p.split('/').pop() || p;
                    return (
                      <div key={p} className="flex items-center gap-2 text-[11px] font-mono text-on-surface-variant">
                        <span className="shrink-0 text-[#ffb4ab]">✕</span>
                        <span className="truncate" title={p}>{display}</span>
                      </div>
                    );
                  })}
                </div>
                <div className="mt-2 text-[10px] text-outline">
                  파싱 불가능한 PDF, 빈 파일, 또는 지원하지 않는 인코딩일 수 있습니다.
                </div>
              </div>
            )}

            <div className="mb-6">
              <div className="mb-3 text-[11px] font-semibold uppercase tracking-[0.12em] text-on-surface-variant">
                Workspace Artifacts
              </div>
              {visibleAssets.length > 0 ? (
                <>
                  <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
                    {visibleAssets.map((artifact) => (
                      <button
                        key={artifact.id}
                        onClick={() => onOpenArtifact(artifact)}
                        className="border border-white/5 bg-surface-container-lowest text-left transition hover:border-primary/30 hover:bg-surface-container"
                      >
                        <div className="flex h-28 items-end justify-between bg-gradient-to-br from-surface-container-highest via-surface-container-low to-surface-container-lowest p-3">
                          <div className="min-w-0 rounded-sm bg-surface/80 px-2 py-1 text-[10px] font-mono uppercase tracking-[0.12em] text-on-surface">
                            <div className="truncate">{artifact.title}</div>
                          </div>
                          {getArtifactIcon(artifact)}
                        </div>
                      </button>
                    ))}
                  </div>
                  {assets.length > 6 && (
                    <button
                      onClick={() => setCollapseAssets((v) => !v)}
                      className="mt-2 w-full py-2 text-center text-[11px] font-mono text-primary transition hover:bg-surface-container-high"
                    >
                      {collapseAssets ? `전체 보기 (${assets.length}개)` : `접기 (6개만 보기)`}
                    </button>
                  )}
                </>
              ) : (
                <div className="border border-white/5 bg-surface-container-low px-4 py-5 text-sm text-on-surface-variant">
                  아직 로드된 문서가 없습니다. 첫 질의를 보내면 관련 아티팩트가 이 영역에 표시됩니다.
                </div>
              )}
            </div>

            <div className="mt-auto border-t border-white/5 pt-4">
              <div className="mb-3 text-[11px] font-semibold uppercase tracking-[0.12em] text-on-surface-variant">
                Runtime Signals
              </div>
              <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
                <div className="border border-white/5 bg-surface-container-low px-3 py-3">
                  <div className="text-[13px] font-medium text-primary">Backend API</div>
                  <div className="mt-1 text-[11px] font-mono text-on-surface-variant">
                    {backendStatus === 'online' ? 'Connected' : backendStatus === 'checking' ? 'Checking' : 'Offline'}
                  </div>
                  <div className="mt-3 h-0.5 w-full bg-surface-container-highest">
                    <div className={cn('h-full', backendStatus === 'online' ? 'w-full bg-secondary' : backendStatus === 'checking' ? 'w-1/2 bg-primary' : 'w-1/4 bg-[#ffb4ab]')} />
                  </div>
                </div>
                <div className="border border-white/5 bg-surface-container-low px-3 py-3">
                  <div className="text-[13px] font-medium text-primary">Guide Target</div>
                  <div className="mt-1 truncate text-[11px] font-mono text-on-surface-variant">
                    {guide?.target_file || guide?.target_document || 'No active target'}
                  </div>
                  <div className="mt-3 text-[10px] uppercase tracking-[0.12em] text-outline">
                    {guide?.intent || guideState}
                  </div>
                </div>
                <div className="border border-white/5 bg-surface-container-low px-3 py-3">
                  <div className="text-[13px] font-medium text-primary">Last Event</div>
                  <div className="mt-1 text-[11px] font-mono text-on-surface-variant">
                    {latestLog
                      ? new Date(latestLog.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })
                      : 'No events'}
                  </div>
                  <div className="mt-3 line-clamp-2 text-[10px] leading-relaxed text-outline">
                    {latestLog?.message || 'System events will appear here after connectivity or query activity.'}
                  </div>
                </div>
              </div>
            </div>
          </section>

          <aside className="hidden overflow-y-auto border-l border-white/5 bg-surface-container-low p-4 custom-scrollbar xl:block">
            <div className="mb-4 text-[11px] font-semibold uppercase tracking-[0.12em] text-on-surface-variant">
              System Activity
            </div>
            {activityLogs.length > 0 ? (
              <div className="space-y-3">
                {activityLogs.map((log) => (
                  <div key={log.id} className="border border-white/5 bg-surface-container px-3 py-3">
                    <div className="mb-1 flex items-center justify-between gap-3">
                      <div className="flex items-center gap-2">
                        <span className={cn('inline-flex h-2 w-2 rounded-full', log.type === 'error' ? 'bg-[#ffb4ab]' : log.type === 'warning' ? 'bg-tertiary' : 'bg-secondary')} />
                        <span className="text-sm font-medium text-on-surface">{log.type.toUpperCase()}</span>
                      </div>
                      <span className="text-[11px] font-mono text-outline">
                        {new Date(log.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })}
                      </span>
                    </div>
                    <p className="text-xs leading-relaxed text-on-surface-variant">
                      {log.message}
                    </p>
                  </div>
                ))}
              </div>
            ) : (
              <div className="border border-white/5 bg-surface-container px-3 py-3 text-xs leading-relaxed text-on-surface-variant">
                아직 수집된 시스템 이벤트가 없습니다. 연결 확인이나 첫 질의 이후 실제 이벤트가 표시됩니다.
              </div>
            )}

            <div className="mt-6 rounded-sm bg-surface-container px-3 py-3">
              <div className="mb-2 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-tertiary">
                <Sparkles size={12} />
                Workspace Readiness
              </div>
              <p className="text-xs leading-relaxed text-on-surface-variant">
                {readinessSummary}
              </p>
              <div className="mt-4 space-y-2 text-[11px]">
                <div className="flex items-center justify-between gap-3">
                  <span className="text-on-surface-variant">Backend</span>
                  <span className={statusTone}>{backendStatus}</span>
                </div>
                <div className="flex items-center justify-between gap-3">
                  <span className="text-on-surface-variant">Documents</span>
                  <span className="text-primary">{kbStats ? kbStats.docs.toLocaleString() : '--'}</span>
                </div>
                <div className="flex items-center justify-between gap-3">
                  <span className="text-on-surface-variant">Chunks</span>
                  <span className="text-primary">{kbStats ? kbStats.chunks.toLocaleString() : '--'}</span>
                </div>
                <div className="flex items-center justify-between gap-3">
                  <span className="text-on-surface-variant">Vectors</span>
                  <span className="text-secondary">{kbStats ? kbStats.embeddings.toLocaleString() : '--'}</span>
                </div>
                <div className="flex items-center justify-between gap-3">
                  <span className="text-on-surface-variant">KB Size</span>
                  <span className="text-outline">{kbStats ? formatBytes(kbStats.sizeBytes) : '--'}</span>
                </div>
                <div className="flex items-center justify-between gap-3">
                  <span className="text-on-surface-variant">Guide</span>
                  <span className="text-outline">{guideState}</span>
                </div>
              </div>
            </div>
          </aside>
        </div>

        <div className="shrink-0 border-t border-white/5 bg-surface-container-lowest p-4">
          <form onSubmit={onSubmit} className="mx-auto flex max-w-5xl items-center gap-3 border-b-2 border-white/10 bg-surface-container-low px-4 py-3 focus-within:border-secondary">
            <span className="font-mono text-secondary">▌</span>
            <input
              ref={inputRef}
              value={inputValue}
              onChange={(event) => onInputChange(event.target.value)}
              placeholder="Type a command or ask PH_ARCH..."
              className="w-full bg-transparent text-sm text-on-surface outline-none placeholder:text-outline"
            />
            <button type="submit" className="inline-flex items-center gap-2 text-secondary transition hover:opacity-80">
              <span className="rounded border border-white/10 px-1.5 py-0.5 text-[10px] font-mono uppercase text-outline">Cmd+K</span>
              <ArrowRight size={16} />
            </button>
          </form>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full overflow-hidden bg-surface">
      <section className="flex min-w-0 flex-1 flex-col overflow-hidden bg-surface">
        <div className="border-b border-white/8 bg-surface-container-low/70 px-4 py-2.5 backdrop-blur xl:px-6">
          <div className="flex flex-col gap-2">
            <div className="flex flex-col gap-2 lg:flex-row lg:items-center lg:justify-between">
              <div className="flex min-w-0 items-center gap-3">
                <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-primary">
                  <Command size={12} />
                  Terminal
                </div>
                {latestMessage?.role === 'architect' ? (
                  <div className="hidden min-w-0 lg:block">
                    <span className="truncate text-sm text-on-surface-variant">
                      {getArchitectPanelTitle(latestMessage)}
                    </span>
                  </div>
                ) : null}
              </div>
              <div className="flex flex-wrap gap-2 text-[11px]">
                <span className="rounded-full border border-white/10 bg-surface px-2.5 py-1 text-outline">
                  Session {sessionId.slice(0, 8)}
                </span>
                <span className={cn('rounded-full border border-white/10 bg-surface px-2.5 py-1', statusTone)}>
                  {backendStatus}
                </span>
                <span className="rounded-full border border-white/10 bg-surface px-2.5 py-1 text-on-surface-variant">
                  근거 {citations.length}
                </span>
                <span className="rounded-full border border-white/10 bg-surface px-2.5 py-1 text-on-surface-variant">
                  응답 {responseCount}
                </span>
              </div>
            </div>

            {commandQueue.length > 0 ? (
              <div className="flex flex-wrap gap-2">
                {commandQueue.map((command) => (
                  <button
                    key={command}
                    type="button"
                    onClick={() => handleSuggestedCommandSelect(command)}
                    className="max-w-full truncate rounded-full border border-white/10 bg-surface px-3 py-1.5 text-left text-[11px] text-on-surface-variant transition hover:border-primary/30 hover:bg-surface-container hover:text-on-surface"
                  >
                    {command}
                  </button>
                ))}
              </div>
            ) : null}
          </div>
        </div>

        <div ref={terminalScrollRef} className="flex-1 overflow-y-auto px-4 py-4 custom-scrollbar xl:px-6">
          <div className="space-y-4">
            {terminalBlocks.map(({ key, message }) => {
              const timestampLabel = formatMessageTimestamp(message.timestamp);
              const panelTitle = getArchitectPanelTitle(message);
              const structuredPayload = renderStructuredPayload(message);
              const citationCount = message.citations?.length ?? 0;

              return (
                <div key={key} className="space-y-2">
                  {message.role === 'operator' ? (
                    <div className="rounded-xl border border-secondary/20 bg-[linear-gradient(180deg,rgba(136,217,130,0.08),rgba(136,217,130,0.02))] px-4 py-3">
                      <div className="mb-2 flex items-center justify-between gap-3">
                        <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-secondary">
                          <Command size={12} />
                          User Input
                        </div>
                        <div className="flex items-center gap-1 text-[11px] font-mono text-outline">
                          <Clock3 size={11} />
                          {timestampLabel}
                        </div>
                      </div>
                      <div className="flex items-start gap-3">
                        <span className="mt-1 text-secondary">➜</span>
                        <p className="font-sans text-[15px] leading-7 text-on-surface">
                          {message.content}
                        </p>
                      </div>
                    </div>
                  ) : (
                    <div className="rounded-xl border border-white/8 bg-surface-container-low/55 px-4 py-3">
                      <div className="mb-3 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                        <div className="min-w-0">
                          <div className="truncate text-sm font-semibold text-on-surface">
                            {panelTitle}
                          </div>
                        </div>
                        <div className="flex flex-wrap gap-2">
                          <span className="rounded-full border border-white/10 bg-surface px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-outline">
                            {timestampLabel}
                          </span>
                          {message.answer_kind ? (
                            <span className="rounded-full border border-white/10 bg-surface px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-primary">
                              {ANSWER_KIND_LABELS[message.answer_kind]}
                            </span>
                          ) : null}
                          {citationCount > 0 ? (
                            <span className="rounded-full border border-secondary/25 bg-secondary/10 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-secondary">
                              근거 {citationCount}
                            </span>
                          ) : null}
                        </div>
                      </div>

                      <ArchitectResponseBody content={message.content} />

                      {structuredPayload ? (
                        <div className="mt-3 rounded-xl border border-white/8 bg-surface-container-lowest/55 p-3">
                          {structuredPayload}
                        </div>
                      ) : null}

                      {message.citations && message.citations.length > 0 ? (
                        <div className="mt-3 rounded-xl border border-secondary/20 bg-secondary/5 p-3">
                          <div className="mb-2 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-secondary">
                            <Link2 size={12} />
                            Connected Evidence
                          </div>
                          <div className="grid gap-2 md:grid-cols-2">
                            {message.citations.slice(0, 2).map((citation) => (
                              <button
                                key={`${message.id}-${citation.label}`}
                                className="rounded-xl border border-white/8 bg-surface px-3 py-3 text-left transition-colors hover:border-secondary/30 hover:bg-secondary/5 cursor-pointer"
                                onClick={() => onNavigateToFile?.(citation.source_path || citation.full_source_path)}
                              >
                                <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-secondary">
                                  {citation.label}
                                </div>
                                <div className="mt-1 text-[11px] text-outline">
                                  {citation.source_path}
                                </div>
                                <div className="mt-2 text-sm leading-6 text-on-surface-variant">
                                  {citation.quote}
                                </div>
                              </button>
                            ))}
                          </div>
                        </div>
                      ) : null}
                    </div>
                  )}
                </div>
              );
            })}

            {error && (
              <div className="rounded-xl border border-[#ffb4ab]/25 bg-[#93000a]/12 p-4 font-sans text-sm text-[#ffdad6]">
                {error}
              </div>
            )}

            {assets.length > 0 && (
              <div className="rounded-xl border border-white/8 bg-surface-container-low/50 p-3">
                <div className="mb-2 flex items-center justify-between gap-3">
                  <div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-on-surface-variant">
                    Related Documents
                  </div>
                  <div className="text-[11px] font-mono text-outline">{assets.length} available</div>
                </div>
                <div className="grid gap-2 lg:grid-cols-3">
                  {(collapseAssets ? assets.slice(0, 3) : assets).map((artifact) => (
                    <button
                      key={artifact.id}
                      onClick={() => onOpenArtifact(artifact)}
                      className="flex items-center justify-between rounded-xl border border-white/8 bg-surface px-3 py-2.5 text-left transition hover:border-primary/30 hover:bg-surface-container-high"
                    >
                      <div className="min-w-0">
                        <div className="truncate text-[10px] uppercase tracking-[0.12em] text-outline">
                          {artifact.subtitle || 'Evidence Artifact'}
                        </div>
                        <div className="mt-1 truncate text-sm font-medium text-on-surface">{artifact.title}</div>
                      </div>
                      {getArtifactIcon(artifact)}
                    </button>
                  ))}
                </div>
                {assets.length > 3 && (
                  <button
                    onClick={() => setCollapseAssets((v) => !v)}
                    className="mt-2 w-full py-1.5 text-center text-[11px] font-mono text-primary transition hover:bg-surface-container-high rounded"
                  >
                    {collapseAssets ? `전체 ${assets.length}개 보기` : '접기'}
                  </button>
                )}
              </div>
            )}

            {isLoading && (
              <div className="flex items-center gap-3 rounded-xl border border-primary/20 bg-primary/8 px-4 py-3 text-sm text-on-surface-variant">
                <LoaderCircle size={16} className="animate-spin text-primary" />
                JARVIS가 응답을 생성하고 있습니다.
              </div>
            )}
            <div ref={terminalEndRef} />
          </div>
        </div>

        <div className="border-t border-white/8 bg-surface-container-lowest/90 p-4 backdrop-blur">
          <div className="mx-auto max-w-6xl">
            <form
              onSubmit={(event) => {
                if (selectedImage && onImageSubmit) {
                  event.preventDefault();
                  onImageSubmit(inputValue, selectedImage);
                  onInputChange('');
                  setSelectedImage(null);
                  if (fileInputRef.current) fileInputRef.current.value = '';
                  return;
                }
                onSubmit(event);
              }}
              className="flex flex-col gap-2 rounded-xl border border-white/10 bg-surface px-4 py-3 transition focus-within:border-primary/35 focus-within:ring-2 focus-within:ring-primary/15"
            >
              {imagePreviewUrl && (
                <div className="flex items-center gap-3 border-b border-white/10 pb-2">
                  <img src={imagePreviewUrl} alt="첨부" className="h-12 w-12 rounded object-cover border border-white/10" />
                  <div className="flex-1 min-w-0">
                    <div className="truncate text-xs text-on-surface">{selectedImage?.name}</div>
                    <div className="text-[10px] font-mono text-outline">
                      {selectedImage ? `${(selectedImage.size / 1024).toFixed(1)} KB` : ''} · Gemma 4 E4B vision
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => {
                      setSelectedImage(null);
                      if (fileInputRef.current) fileInputRef.current.value = '';
                    }}
                    className="rounded p-1 text-outline hover:bg-white/5 hover:text-on-surface"
                  >
                    <X size={14} />
                  </button>
                </div>
              )}
              <div className="flex items-center gap-3">
                <span className="flex h-8 w-8 items-center justify-center rounded-full bg-secondary/10 font-mono text-secondary">▌</span>
                <input
                  ref={inputRef}
                  value={inputValue}
                  onChange={(event) => onInputChange(event.target.value)}
                  placeholder={selectedImage ? "이미지에 대해 질문하세요..." : "질문이나 명령을 입력하세요. 예: 최근 문서 요약해 줘"}
                  className="w-full min-w-0 bg-transparent font-sans text-[15px] text-on-surface outline-none placeholder:text-outline"
                />
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="image/*"
                  className="hidden"
                  onChange={(event) => {
                    const file = event.target.files?.[0];
                    if (file && file.type.startsWith('image/')) setSelectedImage(file);
                  }}
                />
                {onImageSubmit && (
                  <button
                    type="button"
                    onClick={() => fileInputRef.current?.click()}
                    className="inline-flex items-center gap-1 rounded-full border border-white/10 bg-surface-container-high px-2.5 py-2 text-outline transition hover:border-secondary/30 hover:text-secondary"
                    title="이미지 첨부 (Gemma 4 Vision)"
                  >
                    <ImagePlus size={14} />
                  </button>
                )}
                <button
                  type="submit"
                  className="inline-flex items-center gap-2 rounded-full border border-primary/20 bg-primary/10 px-3 py-2 text-primary transition hover:border-primary/35 hover:bg-primary/14"
                >
                  <span className="rounded border border-white/10 px-1.5 py-0.5 text-[10px] font-mono uppercase text-outline">Cmd+K</span>
                  <ArrowRight size={16} />
                </button>
              </div>
            </form>
          </div>
        </div>
      </section>

      <aside className="hidden w-80 shrink-0 border-l border-white/5 bg-surface-container-low xl:block">
        <div className="border-b border-white/5 px-4 py-3">
          <h2 className="flex items-center gap-2 text-[12px] font-semibold uppercase tracking-[0.12em] text-primary">
            <Link2 size={12} />
            Reference Panel
          </h2>
        </div>
        <div className="space-y-6 overflow-y-auto p-4 custom-scrollbar">
          <div>
            <div className="mb-3 text-[11px] font-semibold uppercase tracking-[0.12em] text-on-surface-variant">
              Current Citations
            </div>
            <div className="space-y-2">
              {currentCitations.length > 0 ? currentCitations.map((citation) => (
                <button
                  key={citation.label}
                  className="w-full rounded-xl border border-white/8 bg-surface-container p-3 text-left transition-colors hover:border-secondary/30 hover:bg-secondary/5 cursor-pointer"
                  onClick={() => onNavigateToFile?.(citation.source_path || citation.full_source_path)}
                >
                  <div className="truncate text-[11px] font-medium text-secondary">{citation.source_path}</div>
                  <div className="mt-1 text-[10px] uppercase tracking-[0.12em] text-outline">
                    {citation.label}
                  </div>
                  <div className="mt-2 line-clamp-3 text-sm leading-6 text-on-surface-variant">
                    {citation.quote}
                  </div>
                </button>
              )) : (
                <div className="rounded-xl border border-white/8 bg-surface-container p-3 text-sm text-on-surface-variant">
                  아직 연결된 근거가 없습니다.
                </div>
              )}
            </div>
          </div>

          <div>
            <div className="mb-3 flex items-center justify-between">
              <span className="text-[11px] font-semibold uppercase tracking-[0.12em] text-on-surface-variant">
                Source Map
              </span>
              {sourceMapEntries.length > 0 && (
                <span className="rounded-full bg-primary/15 px-1.5 text-[10px] font-bold text-primary">
                  {sourceMapEntries.length}
                </span>
              )}
            </div>
            <div className="relative aspect-square overflow-hidden rounded-xl border border-white/8 bg-surface-container-lowest">
              <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,rgba(150,204,255,0.12),transparent_45%)]" />
              <div className="absolute inset-0 bg-[linear-gradient(transparent_24px,rgba(255,255,255,0.03)_25px),linear-gradient(90deg,transparent_24px,rgba(255,255,255,0.03)_25px)] bg-[length:25px_25px]" />
              {sourceMapEntries.length > 0 ? (
                <>
                  {/* Radial lines from center to each node */}
                  <svg className="absolute inset-0 h-full w-full" viewBox="0 0 100 100" preserveAspectRatio="none">
                    {sourceMapEntries.slice(0, GRAPH_MAX).map((entry, i) => {
                      const count = Math.min(sourceMapEntries.length, GRAPH_MAX);
                      const angle = (2 * Math.PI / count) * i - Math.PI / 2;
                      const r = 34;
                      const px = 50 + r * Math.cos(angle);
                      const py = 50 + r * Math.sin(angle);
                      return (
                        <line
                          key={`line-${entry.id}`}
                          x1="50" y1="50" x2={px} y2={py}
                          stroke={entry.kind === 'citation' ? 'rgba(150,204,255,0.25)' : 'rgba(200,170,255,0.20)'}
                          strokeWidth="0.8"
                        />
                      );
                    })}
                  </svg>
                  {/* Center node */}
                  <div className="absolute left-1/2 top-1/2 flex h-10 w-10 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full bg-tertiary/20 text-[9px] font-semibold uppercase tracking-[0.12em] text-tertiary shadow-[0_0_16px_rgba(201,191,255,0.25)]">
                    Answer
                  </div>
                  {/* Radial source nodes */}
                  {sourceMapEntries.slice(0, GRAPH_MAX).map((entry, i) => {
                    const count = Math.min(sourceMapEntries.length, GRAPH_MAX);
                    const angle = (2 * Math.PI / count) * i - Math.PI / 2;
                    const r = 38;
                    const left = 50 + r * Math.cos(angle);
                    const top = 50 + r * Math.sin(angle);
                    const dotColor = entry.kind === 'citation' ? 'bg-secondary' : 'bg-primary';
                    return (
                      <div
                        key={entry.id}
                        className="absolute flex items-center gap-1"
                        style={{
                          left: `${left}%`,
                          top: `${top}%`,
                          transform: 'translate(-50%, -50%)',
                          maxWidth: '42%',
                        }}
                        title={entry.label}
                      >
                        <span className={cn('h-2 w-2 shrink-0 rounded-full shadow-[0_0_10px_rgba(150,204,255,0.3)]', dotColor)} />
                        <span className="truncate text-[8px] leading-tight text-on-surface-variant">
                          {entry.label.split('/').pop() || entry.label}
                        </span>
                      </div>
                    );
                  })}
                </>
              ) : (
                <div className="absolute inset-0 flex items-center justify-center px-6 text-center text-xs leading-relaxed text-on-surface-variant">
                  아직 연결된 근거나 문서가 없어 소스 그래프를 그릴 수 없습니다.
                </div>
              )}
            </div>
            {/* Overflow list for remaining sources */}
            {sourceMapEntries.length > GRAPH_MAX && (
              <div className="mt-2 space-y-1">
                {sourceMapEntries.slice(GRAPH_MAX).map((entry) => (
                  <div key={entry.id} className="flex items-center gap-1.5">
                    <span className={cn('h-1.5 w-1.5 shrink-0 rounded-full', entry.kind === 'citation' ? 'bg-secondary/60' : 'bg-primary/60')} />
                    <span className="truncate text-[10px] text-outline">{entry.label.split('/').pop() || entry.label}</span>
                    {entry.score != null && (
                      <span className="ml-auto shrink-0 text-[9px] font-mono text-outline">{(entry.score * 100).toFixed(0)}%</span>
                    )}
                  </div>
                ))}
              </div>
            )}
            <div className="mt-2 text-[11px] leading-relaxed text-on-surface-variant">
              현재 응답과 연결된 근거 문서 및 결과 문서를 표시합니다.
            </div>
          </div>

          <div>
            <div className="mb-3 text-[11px] font-semibold uppercase tracking-[0.12em] text-on-surface-variant">
              Token Usage
            </div>
            <div className="h-1.5 rounded-full bg-surface-container-highest">
              <div className="h-full bg-primary" style={{ width: `${tokenUsage}%` }} />
            </div>
            <div className="mt-2 flex items-center justify-between text-[10px] font-mono text-outline">
              <span>LL: {latestArchitect?.content.length || 0} chars</span>
              <span>MAX: 200k</span>
            </div>
          </div>

          {guide?.has_clarification && (
            <div className="rounded-sm border border-white/5 bg-surface-container p-3">
              <div className="mb-2 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-tertiary">
                <ShieldAlert size={12} />
                Clarification
              </div>
              <p className="text-xs leading-relaxed text-on-surface-variant">
                {guide.clarification_prompt}
              </p>
            </div>
          )}
        </div>
      </aside>
    </div>
  );
};

export default TerminalWorkspace;
