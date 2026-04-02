import React from 'react';
import type { Artifact } from '../../../types';

export interface RendererProps {
  artifact: Artifact;
  fileUrl?: string;
  content?: string;
}

const TextRenderer: React.FC<RendererProps> = ({ artifact, content }) => {
  const text = content || artifact.preview || '내용 없음';
  const lines = text.split('\n');

  return (
    <div className="h-full overflow-auto custom-scrollbar bg-surface-low p-6 font-mono text-sm">
      <table className="w-full border-collapse">
        <tbody>
          {lines.map((line, i) => (
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
    </div>
  );
};

export default TextRenderer;
