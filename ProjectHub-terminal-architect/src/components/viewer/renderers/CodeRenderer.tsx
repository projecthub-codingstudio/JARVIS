import React, { useState, useMemo, useEffect } from 'react';
import { Light as SyntaxHighlighter } from 'react-syntax-highlighter';
import { atomOneDark } from 'react-syntax-highlighter/dist/esm/styles/hljs';
import { ChevronDown } from 'lucide-react';
import type { RendererProps } from './TextRenderer';

const EXT_TO_LANG: Record<string, string> = {
  py: 'python', js: 'javascript', ts: 'typescript', tsx: 'typescript',
  jsx: 'javascript', rs: 'rust', go: 'go', java: 'java', swift: 'swift',
  kt: 'kotlin', rb: 'ruby', sh: 'bash', zsh: 'bash', bash: 'bash',
  yml: 'yaml', yaml: 'yaml', json: 'json', md: 'markdown', html: 'xml',
  css: 'css', sql: 'sql', toml: 'ini', cfg: 'ini', xml: 'xml',
};

function detectLanguage(path: string): string {
  const ext = path.split('.').pop()?.toLowerCase() || '';
  return EXT_TO_LANG[ext] || 'plaintext';
}

const INITIAL_LINE_LIMIT = 3000;  // syntax highlighting is CPU-heavy; paginate very long files
const LINES_PER_PAGE = 2000;

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

const CodeRenderer: React.FC<RendererProps> = ({ artifact, fileUrl, content }) => {
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

  const fullCode = fileContent || content || artifact.preview || '';
  const language = detectLanguage(artifact.path || artifact.full_path || '');

  const allLines = useMemo(() => fullCode.split('\n'), [fullCode]);
  const [visibleCount, setVisibleCount] = useState(INITIAL_LINE_LIMIT);

  // Reset visible count when content changes (e.g., file loaded)
  useEffect(() => { setVisibleCount(INITIAL_LINE_LIMIT); }, [fullCode]);

  const visibleCode = allLines.slice(0, visibleCount).join('\n');
  const hasMore = visibleCount < allLines.length;
  const remaining = allLines.length - visibleCount;

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="w-6 h-6 border-2 border-primary border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="h-full overflow-auto custom-scrollbar">
      {(encoding || fileSize !== null) && (
        <div className="sticky top-0 z-10 flex items-center gap-3 border-b border-outline/10 bg-surface/90 px-6 py-2 text-[10px] font-mono uppercase tracking-wider text-outline backdrop-blur">
          <span>LANG: <span className="text-secondary">{language}</span></span>
          {encoding && <span>ENC: <span className="text-secondary">{encoding}</span></span>}
          {fileSize !== null && <span>SIZE: <span className="text-secondary">{formatSize(fileSize)}</span></span>}
          <span>LINES: <span className="text-secondary">{allLines.length}</span></span>
        </div>
      )}
      <SyntaxHighlighter
        language={language}
        style={atomOneDark}
        showLineNumbers
        wrapLongLines
        customStyle={{
          margin: 0,
          padding: '1.5rem',
          background: 'transparent',
          fontSize: '0.8125rem',
        }}
      >
        {visibleCode}
      </SyntaxHighlighter>
      {hasMore && (
        <div className="px-6 pb-6">
          <button
            onClick={() => setVisibleCount(prev => prev + LINES_PER_PAGE)}
            className="w-full py-3 flex items-center justify-center gap-2 text-primary border border-primary/30 hover:bg-primary/10 transition-all text-xs font-mono uppercase tracking-widest"
          >
            <ChevronDown size={14} />
            더 보기 ({remaining}줄 남음)
          </button>
        </div>
      )}
    </div>
  );
};

export default CodeRenderer;
