import React, { useState } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { Download, Share2, Printer, Info } from 'lucide-react';
import { cn } from '../../lib/utils';
import { apiClient } from '../../lib/api-client';
import { ViewerRouter } from './ViewerRouter';
import type { Artifact, Citation } from '../../types';

interface ViewerShellProps {
  artifact: Artifact;
  citations: Citation[];
  onBack: () => void;
  isMobile: boolean;
}

export const ViewerShell: React.FC<ViewerShellProps> = ({
  artifact,
  citations,
  onBack,
  isMobile,
}) => {
  const [isSidebarOpen, setIsSidebarOpen] = useState(!isMobile);

  const fileUrl = artifact.full_path
    ? apiClient.getFileUrl(artifact.full_path)
    : undefined;

  return (
    <motion.div
      key="viewer"
      initial={{ opacity: 0, x: 20 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: -20 }}
      className="h-full flex flex-col overflow-hidden"
    >
      {/* Header */}
      <div className="px-4 md:px-10 pt-6 bg-surface-low shrink-0">
        <nav className="flex items-center gap-2 text-[10px] font-mono uppercase tracking-widest text-on-surface-variant mb-4">
          <button onClick={onBack} className="hover:text-primary transition-colors">
            대시보드
          </button>
          <span>/</span>
          <button onClick={onBack} className="hover:text-primary transition-colors">
            자산
          </button>
          <span>/</span>
          <span className="text-primary-dim">{artifact.title}</span>
        </nav>
        <div className="flex flex-col md:flex-row md:justify-between md:items-center pb-6 gap-4">
          <div>
            <h1 className="text-lg md:text-xl font-bold tracking-tight text-primary-dim font-headline">
              {artifact.title}
            </h1>
            <p className="text-on-surface-variant text-[10px] font-mono uppercase tracking-widest mt-1">
              {artifact.path || artifact.source_type || ''}
            </p>
          </div>
          <div className="flex flex-wrap gap-2 md:gap-3">
            <button
              onClick={() => setIsSidebarOpen(!isSidebarOpen)}
              className={cn(
                "flex-1 md:flex-none px-3 md:px-5 py-2 border border-outline transition-all text-[10px] md:text-xs flex items-center justify-center gap-2",
                isSidebarOpen
                  ? "bg-primary/10 text-primary border-primary"
                  : "text-on-surface-variant hover:text-white hover:bg-surface-highest"
              )}
            >
              <Info size={14} /> {isSidebarOpen ? '정보_숨기기' : '정보_보기'}
            </button>
            <button className="flex-1 md:flex-none px-3 md:px-5 py-2 border border-outline text-on-surface-variant hover:text-white hover:bg-surface-highest transition-all text-[10px] md:text-xs flex items-center justify-center gap-2">
              <Share2 size={14} /> 공유
            </button>
            <button className="flex-1 md:flex-none px-3 md:px-5 py-2 border border-outline text-on-surface-variant hover:text-white hover:bg-surface-highest transition-all text-[10px] md:text-xs flex items-center justify-center gap-2">
              <Printer size={14} /> 인쇄
            </button>
            {fileUrl && (
              <a
                href={fileUrl}
                download
                className="w-full md:w-auto px-4 md:px-6 py-2 bg-primary text-on-primary font-bold hover:opacity-80 transition-all text-[10px] md:text-xs flex items-center justify-center gap-2"
              >
                <Download size={14} /> 다운로드
              </a>
            )}
          </div>
        </div>
      </div>

      {/* Content + Sidebar */}
      <div className="flex-1 flex flex-col md:flex-row overflow-hidden">
        <section className="flex-1 overflow-hidden">
          <ViewerRouter
            artifact={artifact}
            fileUrl={fileUrl}
            content={artifact.preview}
          />
        </section>

        <AnimatePresence>
          {isSidebarOpen && (
            <motion.aside
              initial={isMobile ? { height: 0, opacity: 0 } : { width: 0, opacity: 0 }}
              animate={isMobile ? { height: 'auto', opacity: 1 } : { width: 320, opacity: 1 }}
              exit={isMobile ? { height: 0, opacity: 0 } : { width: 0, opacity: 0 }}
              className="w-full md:w-80 bg-surface-low border-t md:border-t-0 md:border-l border-outline/10 shrink-0 overflow-hidden"
            >
              <div className="p-6 md:p-8 h-full overflow-y-auto custom-scrollbar">
                <h4 className="text-primary text-xs font-mono mb-6 uppercase tracking-widest">
                  문서 정보
                </h4>
                <div className="space-y-6 mb-10">
                  <div>
                    <p className="text-xs text-on-surface-variant uppercase mb-1">문서 유형</p>
                    <p className="text-sm font-mono text-on-surface uppercase">
                      {artifact.source_type || '-'}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs text-on-surface-variant uppercase mb-1">뷰어 종류</p>
                    <p className="text-sm font-mono text-on-surface uppercase">
                      {artifact.viewer_kind || '-'}
                    </p>
                  </div>
                  {artifact.path && (
                    <div>
                      <p className="text-xs text-on-surface-variant uppercase mb-1">경로</p>
                      <p className="text-xs font-mono text-on-surface break-all">
                        {artifact.path}
                      </p>
                    </div>
                  )}
                  {artifact.subtitle && (
                    <div>
                      <p className="text-xs text-on-surface-variant uppercase mb-1">설명</p>
                      <p className="text-xs text-on-surface">{artifact.subtitle}</p>
                    </div>
                  )}
                </div>

                {citations.length > 0 && (
                  <div>
                    <h4 className="text-primary text-xs font-mono mb-4 uppercase tracking-widest">
                      관련 근거
                    </h4>
                    <div className="space-y-3">
                      {citations.slice(0, 5).map((c, i) => (
                        <div
                          key={i}
                          className="bg-surface-high/50 border border-outline/10 p-3"
                        >
                          <p className="text-[10px] font-mono text-primary mb-1">[{c.label}]</p>
                          <p className="text-xs text-on-surface-variant line-clamp-3">
                            {c.quote}
                          </p>
                          <p className="text-[10px] font-mono text-outline mt-1">
                            {c.source_path}
                          </p>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </motion.aside>
          )}
        </AnimatePresence>
      </div>
    </motion.div>
  );
};
