import React, { useState, useEffect } from 'react';
import { ChevronDown } from 'lucide-react';
import type { Artifact } from '../../../types';

export interface RendererProps {
  artifact: Artifact;
  fileUrl?: string;
  content?: string;
}

const LINES_PER_PAGE = 30;

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

const TextRenderer: React.FC<RendererProps> = ({ artifact, fileUrl, content }) => {
  const [fileContent, setFileContent] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [encoding, setEncoding] = useState<string | null>(null);
  const [fileSize, setFileSize] = useState<number | null>(null);

  // Fetch full file content when fileUrl is available
  useEffect(() => {
    if (!fileUrl) return;
    let cancelled = false;
    const controller = new AbortController();
    setLoading(true);

    fetch(fileUrl, { signal: controller.signal })
      .then(res => {
        if (!res.ok) throw new Error('Failed to fetch');
        if (!cancelled) {
          setEncoding(res.headers.get('X-Detected-Encoding'));
          const sizeHdr = res.headers.get('X-File-Size');
          setFileSize(sizeHdr ? parseInt(sizeHdr, 10) : null);
        }
        return res.text();
      })
      .then(text => { if (!cancelled) { setFileContent(text); setLoading(false); } })
      .catch(() => { if (!cancelled) setLoading(false); });

    return () => { cancelled = true; controller.abort(); };
  }, [fileUrl]);

  const text = fileContent || content || artifact.preview || '내용 없음';
  const allLines = text.split('\n');
  const [visibleCount, setVisibleCount] = useState(LINES_PER_PAGE);

  // Reset visible count when content changes
  useEffect(() => { setVisibleCount(LINES_PER_PAGE); }, [text]);

  const visibleLines = allLines.slice(0, visibleCount);
  const hasMore = visibleCount < allLines.length;
  const remaining = allLines.length - visibleCount;

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center bg-surface-lowest">
        <div className="w-6 h-6 border-2 border-primary border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="h-full overflow-auto custom-scrollbar bg-surface-lowest p-6 font-mono text-sm">
      <div className="mx-auto max-w-5xl rounded-xl border border-white/8 bg-surface px-4 py-4 shadow-[0_16px_48px_rgba(0,0,0,0.18)]">
      {(encoding || fileSize !== null) && (
        <div className="mb-3 flex items-center gap-3 border-b border-outline/10 pb-2 text-[10px] font-mono uppercase tracking-wider text-outline">
          {encoding && <span>ENC: <span className="text-secondary">{encoding}</span></span>}
          {fileSize !== null && <span>SIZE: <span className="text-secondary">{formatSize(fileSize)}</span></span>}
          <span>LINES: <span className="text-secondary">{allLines.length}</span></span>
        </div>
      )}
      <table className="w-full border-collapse">
        <tbody>
          {visibleLines.map((line, i) => (
            <tr key={i} className="hover:bg-surface-container-high/45">
              <td className="pr-4 text-right text-outline select-none w-12 align-top text-xs">
                {i + 1}
              </td>
              <td className="text-on-surface whitespace-pre-wrap break-all">
                {line || '\u00A0'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {hasMore && (
        <button
          onClick={() => setVisibleCount(prev => prev + LINES_PER_PAGE)}
          className="w-full mt-4 py-3 flex items-center justify-center gap-2 text-primary border border-primary/30 hover:bg-primary/10 transition-all text-xs font-mono uppercase tracking-widest"
        >
          <ChevronDown size={14} />
          더 보기 ({remaining}줄 남음)
        </button>
      )}
      </div>
    </div>
  );
};

export default TextRenderer;
