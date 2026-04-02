import React, { useState } from 'react';
import { ChevronDown } from 'lucide-react';
import type { Artifact } from '../../../types';

export interface RendererProps {
  artifact: Artifact;
  fileUrl?: string;
  content?: string;
}

const LINES_PER_PAGE = 30;

const TextRenderer: React.FC<RendererProps> = ({ artifact, content }) => {
  const text = content || artifact.preview || '내용 없음';
  const allLines = text.split('\n');
  const [visibleCount, setVisibleCount] = useState(LINES_PER_PAGE);

  const visibleLines = allLines.slice(0, visibleCount);
  const hasMore = visibleCount < allLines.length;
  const remaining = allLines.length - visibleCount;

  return (
    <div className="h-full overflow-auto custom-scrollbar bg-surface-low p-6 font-mono text-sm">
      <table className="w-full border-collapse">
        <tbody>
          {visibleLines.map((line, i) => (
            <tr key={i} className="hover:bg-surface-highest/30">
              <td className="pr-4 text-right text-outline select-none w-12 align-top text-xs">
                {i + 1}
              </td>
              <td className="text-on-surface-variant whitespace-pre-wrap break-all">
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
  );
};

export default TextRenderer;
