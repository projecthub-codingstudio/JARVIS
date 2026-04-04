import React, { useMemo, useState } from 'react';
import { Bookmark, ChevronLeft, ChevronRight, Download, Search, Sparkles } from 'lucide-react';
import { apiClient } from '../../lib/api-client';
import { cn } from '../../lib/utils';
import { ViewerRouter } from './ViewerRouter';
import type { Artifact, Citation } from '../../types';

interface ViewerShellProps {
  artifact: Artifact;
  artifacts: Artifact[];
  citations: Citation[];
  isMobile: boolean;
  isLoading?: boolean;
  onAskArtifact?: (artifact: Artifact, prompt: string) => Promise<void> | void;
  onSelectArtifact: (artifact: Artifact) => void;
}

function getMatchScore(index: number) {
  return Math.max(42, 98 - index * 14);
}

function getPageLabel(artifact: Artifact) {
  if (artifact.viewer_kind === 'document') return 'Page 1 of 1';
  if (artifact.viewer_kind === 'image') return 'Asset View';
  if (artifact.viewer_kind === 'web') return 'Live Source';
  return 'Document View';
}

function shouldUseLightDocumentCanvas(artifact: Artifact) {
  const path = (artifact.full_path || artifact.path || '').toLowerCase();
  return ['.pdf', '.doc', '.docx', '.ppt', '.pptx', '.xls', '.xlsx', '.csv'].some((ext) => path.endsWith(ext));
}

export const ViewerShell: React.FC<ViewerShellProps> = ({
  artifact,
  artifacts,
  citations,
  isMobile,
  isLoading = false,
  onAskArtifact,
  onSelectArtifact,
}) => {
  const [documentPrompt, setDocumentPrompt] = useState('');
  const filePath = artifact.full_path || artifact.path || '';
  const fileUrl = filePath ? apiClient.getFileUrl(filePath) : undefined;

  const activeCitations = useMemo(() => {
    const filtered = citations.filter((citation) => (citation.full_source_path || citation.source_path) === filePath);
    return (filtered.length > 0 ? filtered : citations).slice(0, 3);
  }, [citations, filePath]);

  const contextualSummary = activeCitations[0]?.quote || artifact.preview || artifact.subtitle || 'No contextual summary available.';

  const handleDocumentAsk = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const nextPrompt = documentPrompt.trim();
    if (!nextPrompt || !onAskArtifact || isLoading) return;
    await onAskArtifact(artifact, nextPrompt);
    setDocumentPrompt('');
  };

  return (
    <div className="flex h-full overflow-hidden bg-surface">
      <section className="hidden w-72 shrink-0 bg-surface-container-low lg:flex lg:flex-col">
        <div className="border-b border-white/5 bg-surface px-4 py-4">
          <h2 className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-on-surface-variant">
            <Search size={12} />
            Document Library
          </h2>
          <div className="mt-3 inline-flex items-center gap-2 rounded-sm bg-surface-container px-2 py-1.5 text-[12px] text-on-surface-variant">
            <span className="text-primary">⇅</span>
            Relevance: Highest First
          </div>
        </div>
        <div className="flex-1 overflow-y-auto p-2 custom-scrollbar">
          <div className="space-y-1">
            {artifacts.map((item, index) => {
              const selected = item.id === artifact.id;
              return (
                <button
                  key={item.id}
                  onClick={() => onSelectArtifact(item)}
                  className={cn(
                    'w-full rounded-r px-3 py-3 text-left transition',
                    selected ? 'border-l-2 border-secondary bg-surface-container-high' : 'hover:bg-surface-container-high'
                  )}
                >
                  <div className="mb-1 flex items-start justify-between gap-3">
                    <span className={cn('font-mono text-[10px] uppercase', selected ? 'text-secondary' : 'text-primary')}>
                      Match {getMatchScore(index)}%
                    </span>
                    <span className="text-[10px] text-outline">v{Math.max(1, 4 - index)}.{index}</span>
                  </div>
                  <div className="text-[13px] font-medium leading-tight text-on-surface">
                    {item.title}
                  </div>
                  <div className="mt-1 line-clamp-2 text-[11px] leading-relaxed text-on-surface-variant">
                    {item.preview || item.subtitle || item.source_type}
                  </div>
                </button>
              );
            })}
          </div>
        </div>
      </section>

      <section className="relative flex min-w-0 flex-1 flex-col bg-surface-container">
        <div className="flex h-10 shrink-0 items-center justify-between border-b border-white/5 bg-surface px-4">
          <div className="flex items-center gap-4">
            <button className="transition hover:text-primary">
              <Search size={14} />
            </button>
            <span className="font-mono text-[12px] text-outline">{artifact.viewer_kind === 'document' ? '125%' : '100%'}</span>
            <button className="transition hover:text-primary">
              <Bookmark size={14} />
            </button>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-[12px] text-outline">{getPageLabel(artifact)}</span>
            <div className="flex gap-1">
              <button className="rounded p-1 transition hover:bg-surface-container-highest">
                <ChevronLeft size={14} />
              </button>
              <button className="rounded p-1 transition hover:bg-surface-container-highest">
                <ChevronRight size={14} />
              </button>
            </div>
            {fileUrl && (
              <a
                href={fileUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="rounded-sm bg-surface-container-highest px-3 py-1 text-[11px] font-semibold tracking-[0.08em] text-on-surface transition hover:ring-1 hover:ring-primary/20"
              >
                원문보기
              </a>
            )}
          </div>
        </div>

        <div className={cn('flex-1 overflow-hidden', shouldUseLightDocumentCanvas(artifact) && 'bg-[#f5f5f4]')}>
          <ViewerRouter artifact={artifact} fileUrl={fileUrl} content={artifact.preview} />
        </div>

        {!isMobile && onAskArtifact && (
          <div className="shrink-0 border-t border-white/5 bg-surface px-6 py-4">
            <form onSubmit={handleDocumentAsk} className="mx-auto flex w-full max-w-3xl items-center gap-3 rounded-xl border border-white/10 bg-surface-container-high px-3 py-2">
              <Sparkles size={16} className="text-tertiary" />
              <input
                value={documentPrompt}
                onChange={(event) => setDocumentPrompt(event.target.value)}
                className="w-full bg-transparent text-sm text-on-surface outline-none placeholder:text-outline"
                placeholder="문서 질문 또는 주제를 명시한 전역 질문을 입력하세요..."
              />
              <button
                type="submit"
                disabled={!documentPrompt.trim() || isLoading}
                className="rounded-lg bg-secondary px-4 py-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-[#003909] transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
              >
                Ask
              </button>
            </form>
          </div>
        )}
      </section>

      <aside className="hidden w-80 shrink-0 border-l border-white/5 bg-surface-container-low xl:flex xl:flex-col">
        <div className="border-b border-white/5 bg-surface px-4 py-4">
          <h2 className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-on-surface-variant">
            <Sparkles size={12} className="text-tertiary" />
            Evidence Inspector
          </h2>
        </div>
        <div className="space-y-6 overflow-y-auto p-4 custom-scrollbar">
          <div className="relative overflow-hidden rounded-lg bg-surface-container-highest p-4">
            <div className="absolute right-3 top-3 text-tertiary">
              <Sparkles size={14} />
            </div>
            <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-tertiary">
              Contextual Summary
            </div>
            <p className="text-xs italic leading-relaxed text-on-surface-variant">
              “{contextualSummary.slice(0, 220)}{contextualSummary.length > 220 ? '…' : ''}”
            </p>
          </div>

          <div>
            <h3 className="mb-4 text-[11px] font-semibold uppercase tracking-[0.12em] text-on-surface-variant">
              Active Citations ({activeCitations.length})
            </h3>
            <div className="space-y-4">
              {activeCitations.map((citation) => (
                <div
                  key={`${citation.label}-${citation.source_path}`}
                  className="border-l-2 border-secondary pl-3 py-1"
                >
                  <div className="text-[12px] font-medium text-on-surface">{citation.source_path}</div>
                  <div className="mt-1 text-[11px] leading-relaxed text-on-surface-variant">
                    {citation.quote || 'Linked source'}
                  </div>
                  <div className="mt-2 flex items-center gap-4 text-[10px] font-mono uppercase">
                    <span className="text-secondary">Source</span>
                    <span className="text-outline">{citation.source_type}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="border-t border-white/5 pt-4">
            <h3 className="mb-3 text-[11px] font-semibold uppercase tracking-[0.12em] text-on-surface-variant">
              Reasoning Context
            </h3>
            <div className="rounded-sm border border-white/5 bg-surface-container-lowest p-3 font-mono text-[11px] leading-relaxed text-on-surface-variant">
              <span className="mb-2 block text-secondary/70">// logical inference</span>
              User is investigating the selected document. Current evidence indicates this source is the highest-confidence artifact for the active query.
            </div>
          </div>

          <div className="border-t border-white/5 pt-4 text-[11px] font-mono text-on-surface-variant">
            <div>Owner: {artifact.source_type || 'document'}</div>
            <div className="mt-2">Path: {artifact.path || artifact.full_path}</div>
          </div>
        </div>
      </aside>
    </div>
  );
};

export default ViewerShell;
