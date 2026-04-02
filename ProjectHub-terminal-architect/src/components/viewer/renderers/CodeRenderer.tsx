import React, { useState, useMemo } from 'react';
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

const LINES_PER_PAGE = 40;

const CodeRenderer: React.FC<RendererProps> = ({ artifact, content }) => {
  const fullCode = content || artifact.preview || '';
  const language = detectLanguage(artifact.path || artifact.full_path || '');

  const allLines = useMemo(() => fullCode.split('\n'), [fullCode]);
  const [visibleCount, setVisibleCount] = useState(LINES_PER_PAGE);

  const visibleCode = allLines.slice(0, visibleCount).join('\n');
  const hasMore = visibleCount < allLines.length;
  const remaining = allLines.length - visibleCount;

  return (
    <div className="h-full overflow-auto custom-scrollbar">
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
