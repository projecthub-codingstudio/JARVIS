import React from 'react';
import { Light as SyntaxHighlighter } from 'react-syntax-highlighter';
import { atomOneDark } from 'react-syntax-highlighter/dist/esm/styles/hljs';
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

const CodeRenderer: React.FC<RendererProps> = ({ artifact, content }) => {
  const code = content || artifact.preview || '';
  const language = detectLanguage(artifact.path || artifact.full_path || '');

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
          minHeight: '100%',
          fontSize: '0.8125rem',
        }}
      >
        {code}
      </SyntaxHighlighter>
    </div>
  );
};

export default CodeRenderer;
