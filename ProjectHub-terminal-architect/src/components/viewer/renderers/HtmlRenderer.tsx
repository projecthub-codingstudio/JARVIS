import React, { useEffect, useMemo, useState } from 'react';
import DOMPurify from 'dompurify';
import { Light as SyntaxHighlighter } from 'react-syntax-highlighter';
import { atomOneDark } from 'react-syntax-highlighter/dist/esm/styles/hljs';
import { WrapText } from 'lucide-react';
import type { RendererProps } from './TextRenderer';

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

const HtmlRenderer: React.FC<RendererProps> = ({ artifact, fileUrl, content, scale }) => {
  const [fileContent, setFileContent] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [encoding, setEncoding] = useState<string | null>(null);
  const [fileSize, setFileSize] = useState<number | null>(null);
  const [mode, setMode] = useState<'rendered' | 'source'>('rendered');
  const [wrapLines, setWrapLines] = useState(true);

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

  const html = fileContent || content || artifact.preview || '';
  const sanitizedHtml = useMemo(() => DOMPurify.sanitize(html), [html]);

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center bg-surface-lowest">
        <div className="w-6 h-6 border-2 border-primary border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col bg-surface-lowest">
      <div className="flex items-center gap-3 border-b border-outline/10 bg-surface/90 px-4 py-2 text-[10px] font-mono uppercase tracking-wider text-outline">
        <span>HTML</span>
        {encoding && <span>ENC: <span className="text-secondary">{encoding}</span></span>}
        {fileSize !== null && <span>SIZE: <span className="text-secondary">{formatSize(fileSize)}</span></span>}
        <div className="ml-auto flex items-center gap-1">
          {mode === 'source' && (
            <button
              onClick={() => setWrapLines(w => !w)}
              className={`flex items-center gap-1 rounded px-2 py-0.5 transition-colors ${
                wrapLines ? 'bg-primary/15 text-primary' : 'text-outline hover:text-on-surface'
              }`}
              title={wrapLines ? "줄바꿈 끄기 (가로 스크롤)" : "줄바꿈 켜기"}
            >
              <WrapText size={10} />
              {wrapLines ? 'WRAP' : 'NOWRAP'}
            </button>
          )}
          <button
            onClick={() => setMode('rendered')}
            className={`px-2 py-0.5 rounded ${mode === 'rendered' ? 'bg-primary/20 text-primary' : 'text-outline hover:text-on-surface'}`}
          >
            Rendered
          </button>
          <button
            onClick={() => setMode('source')}
            className={`px-2 py-0.5 rounded ${mode === 'source' ? 'bg-primary/20 text-primary' : 'text-outline hover:text-on-surface'}`}
          >
            Source
          </button>
        </div>
      </div>
      {mode === 'rendered' ? (
        <div className="flex-1 overflow-auto custom-scrollbar" style={scale && scale !== 1 ? { transform: `scale(${scale})`, transformOrigin: 'top left', transition: 'transform 0.2s' } : undefined}>
          <iframe
            srcDoc={sanitizedHtml}
            sandbox=""
            title={artifact.title}
            className="w-full border-0 bg-white"
            style={{ height: `${100 / (scale || 1)}%`, width: `${100 / (scale || 1)}%` }}
          />
        </div>
      ) : (
        <div className="flex-1 overflow-auto custom-scrollbar">
          <SyntaxHighlighter
            language="xml"
            style={atomOneDark}
            showLineNumbers
            wrapLongLines={wrapLines}
            customStyle={{
              margin: 0,
              padding: '1.5rem',
              background: 'transparent',
              fontSize: `${13 * (scale || 1)}px`,
            }}
          >
            {html || '내용 없음'}
          </SyntaxHighlighter>
        </div>
      )}
    </div>
  );
};

export default HtmlRenderer;
