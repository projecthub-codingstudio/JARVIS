import React, { useEffect, useState } from 'react';
import { ExternalLink, FileText } from 'lucide-react';
import { apiClient } from '../../../lib/api-client';
import type { ExtractedTextChunk } from '../../../types';
import type { RendererProps } from './TextRenderer';

const HwpRenderer: React.FC<RendererProps> = ({ artifact }) => {
  const [chunks, setChunks] = useState<ExtractedTextChunk[]>([]);
  const [totalChunks, setTotalChunks] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const relativePath = artifact.path || artifact.full_path || '';
  const fileUrl = artifact.full_path ? apiClient.getFileUrl(artifact.full_path) : '';

  useEffect(() => {
    if (!relativePath) return;
    let cancelled = false;
    setLoading(true);
    setError(null);

    apiClient
      .getExtractedText(relativePath, 500)
      .then((res) => {
        if (!cancelled) {
          setChunks(res.chunks);
          setTotalChunks(res.total_chunks);
          setLoading(false);
        }
      })
      .catch((e) => {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : 'unknown');
          setLoading(false);
        }
      });

    return () => { cancelled = true; };
  }, [relativePath]);

  const fallbackText = artifact.preview || '인덱싱된 미리보기가 없습니다.';

  return (
    <div className="flex h-full flex-col bg-surface-lowest">
      <div className="flex-1 overflow-auto p-4 md:p-6 custom-scrollbar">
        <div className="mx-auto max-w-[1200px] rounded-xl border border-white/8 bg-surface px-8 py-6 shadow-[0_16px_48px_rgba(0,0,0,0.18)]">
          <div className="mb-6 flex items-center gap-3 border-b border-outline/10 pb-4">
            <FileText size={20} className="text-primary" />
            <div className="flex-1">
              <h3 className="text-sm font-bold text-on-surface">{artifact.title}</h3>
              <p className="text-[10px] font-mono text-on-surface-variant uppercase">
                HWP 문서 — 인덱스 추출 텍스트
                {totalChunks !== null && (
                  <> · <span className="text-secondary">{chunks.length} / {totalChunks}</span> chunks</>
                )}
              </p>
            </div>
          </div>

          {loading && (
            <div className="flex items-center justify-center py-12">
              <div className="w-6 h-6 border-2 border-primary border-t-transparent rounded-full animate-spin" />
            </div>
          )}

          {!loading && error && (
            <pre className="text-on-surface text-sm leading-relaxed whitespace-pre-wrap font-sans">
              {fallbackText}
              {'\n\n'}
              <span className="text-outline text-xs">(인덱스 조회 실패: {error})</span>
            </pre>
          )}

          {!loading && !error && chunks.length === 0 && (
            <pre className="text-on-surface text-sm leading-relaxed whitespace-pre-wrap font-sans">
              {fallbackText}
            </pre>
          )}

          {!loading && chunks.length > 0 && (
            <div className="space-y-3">
              {chunks.map((c) => (
                <div key={c.chunk_id} className="group">
                  {c.heading_path && (
                    <div className="text-[10px] font-mono uppercase tracking-wider text-outline mb-1 group-hover:text-secondary transition-colors">
                      {c.heading_path}
                    </div>
                  )}
                  <div className="text-on-surface text-sm leading-relaxed whitespace-pre-wrap font-sans border-l-2 border-outline/10 pl-3 group-hover:border-primary/30 transition-colors">
                    {c.text}
                  </div>
                </div>
              ))}
              {totalChunks !== null && chunks.length < totalChunks && (
                <div className="mt-6 pt-4 border-t border-outline/10 text-center text-xs text-outline font-mono">
                  전체 {totalChunks} chunks 중 처음 {chunks.length}개만 표시 중 — 원본 열기로 전체 보기
                </div>
              )}
            </div>
          )}
        </div>
      </div>
      {fileUrl && (
        <div className="flex h-10 shrink-0 items-center justify-center border-t border-white/5 bg-surface px-4">
          <a
            href={fileUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-on-surface hover:text-primary transition-colors"
          >
            <ExternalLink size={12} />
            원본 파일 열기
          </a>
        </div>
      )}
    </div>
  );
};

export default HwpRenderer;
