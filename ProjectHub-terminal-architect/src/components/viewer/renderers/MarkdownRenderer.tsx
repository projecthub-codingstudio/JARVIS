import React, { useState, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { RendererProps } from './TextRenderer';

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

const MarkdownRenderer: React.FC<RendererProps> = ({ artifact, fileUrl, content }) => {
  const [fileContent, setFileContent] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [encoding, setEncoding] = useState<string | null>(null);
  const [fileSize, setFileSize] = useState<number | null>(null);

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

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center bg-surface-lowest">
        <div className="w-6 h-6 border-2 border-primary border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="h-full overflow-auto custom-scrollbar bg-surface-lowest p-6">
      <div className="mx-auto max-w-4xl rounded-xl border border-white/8 bg-surface px-8 py-8 shadow-[0_16px_48px_rgba(0,0,0,0.18)]">
        {(encoding || fileSize !== null) && (
          <div className="mb-4 flex items-center gap-3 border-b border-outline/10 pb-3 text-[10px] font-mono uppercase tracking-wider text-outline">
            <span>MD</span>
            {encoding && <span>ENC: <span className="text-secondary">{encoding}</span></span>}
            {fileSize !== null && <span>SIZE: <span className="text-secondary">{formatSize(fileSize)}</span></span>}
          </div>
        )}
        <article className="prose prose-invert prose-sm max-w-none
          prose-headings:text-on-surface prose-headings:font-semibold
          prose-h1:text-2xl prose-h1:border-b prose-h1:border-outline/20 prose-h1:pb-2 prose-h1:mb-4
          prose-h2:text-xl prose-h2:mt-6 prose-h2:mb-3
          prose-h3:text-lg prose-h3:mt-5 prose-h3:mb-2
          prose-p:text-on-surface prose-p:leading-relaxed
          prose-a:text-primary prose-a:no-underline hover:prose-a:underline
          prose-strong:text-on-surface prose-strong:font-semibold
          prose-code:text-secondary prose-code:bg-surface-container-high prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded prose-code:text-xs prose-code:before:content-[''] prose-code:after:content-['']
          prose-pre:bg-surface-container-highest prose-pre:border prose-pre:border-outline/20
          prose-blockquote:border-l-primary prose-blockquote:text-on-surface-variant
          prose-ul:text-on-surface prose-ol:text-on-surface
          prose-li:text-on-surface
          prose-table:text-sm prose-th:text-on-surface prose-td:text-on-surface-variant prose-th:border-outline/30 prose-td:border-outline/20
          prose-hr:border-outline/20">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
        </article>
      </div>
    </div>
  );
};

export default MarkdownRenderer;
