import React from 'react';
import { ExternalLink, FileText } from 'lucide-react';
import { apiClient } from '../../../lib/api-client';
import type { RendererProps } from './TextRenderer';

const HwpRenderer: React.FC<RendererProps> = ({ artifact }) => {
  const text = artifact.preview || '미리보기 내용이 없습니다.';
  const fileUrl = artifact.full_path ? apiClient.getFileUrl(artifact.full_path) : '';

  return (
    <div className="flex h-full flex-col bg-surface-lowest">
      <div className="flex-1 overflow-auto p-4 md:p-6 custom-scrollbar">
        <div className="mx-auto max-w-[1200px] rounded-xl border border-white/8 bg-surface px-8 py-6 shadow-[0_16px_48px_rgba(0,0,0,0.18)]">
          <div className="mb-6 flex items-center gap-3 border-b border-outline/10 pb-4">
            <FileText size={20} className="text-primary" />
            <div>
              <h3 className="text-sm font-bold text-on-surface">{artifact.title}</h3>
              <p className="text-[10px] font-mono text-on-surface-variant uppercase">
                HWP 문서 — 텍스트 미리보기
              </p>
            </div>
          </div>
          <pre className="text-on-surface text-sm leading-relaxed whitespace-pre-wrap font-sans">
            {text}
          </pre>
        </div>
      </div>
      {fileUrl && (
        <div className="flex items-center justify-center p-4 bg-surface-highest/30 border-t border-outline/10">
          <a
            href={fileUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-2 px-6 py-2 bg-primary text-on-primary font-bold text-xs hover:opacity-80 transition-all"
          >
            <ExternalLink size={14} />
            원본 파일 열기
          </a>
        </div>
      )}
    </div>
  );
};

export default HwpRenderer;
