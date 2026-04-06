import React, { useEffect, useState, useMemo } from 'react';
import * as XLSX from 'xlsx';
import DOMPurify from 'dompurify';
import type { RendererProps } from './TextRenderer';

interface SheetData {
  name: string;
  html: string;
}

const XlsxRenderer: React.FC<RendererProps> = ({ artifact, fileUrl }) => {
  const [sheets, setSheets] = useState<SheetData[]>([]);
  const [activeSheet, setActiveSheet] = useState(0);
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!fileUrl) return;

    setLoading(true);
    fetch(fileUrl)
      .then(res => {
        if (!res.ok) throw new Error('Failed to fetch');
        return res.arrayBuffer();
      })
      .then(buffer => {
        const wb = XLSX.read(buffer, { type: 'array' });
        const parsed: SheetData[] = wb.SheetNames.map(name => {
          const rawHtml = XLSX.utils.sheet_to_html(wb.Sheets[name]);
          return { name, html: DOMPurify.sanitize(rawHtml, { FORBID_TAGS: ['base'], FORBID_ATTR: ['onerror', 'onload'] }) };
        });
        setSheets(parsed);
        setLoading(false);
      })
      .catch((err) => {
        console.error('[XlsxRenderer] Failed to load:', fileUrl, err);
        setError(true);
        setLoading(false);
      });
  }, [fileUrl]);

  const currentHtml = useMemo(() => sheets[activeSheet]?.html || '', [sheets, activeSheet]);

  if (error || !fileUrl) {
    return (
      <div className="h-full overflow-auto p-6 custom-scrollbar">
        <div className="mb-4 p-3 bg-yellow-500/10 border border-yellow-500/30 text-yellow-200 text-xs font-mono">
          {error ? '⚠ XLSX 파일 로드 실패 — 텍스트 미리보기로 표시합니다' : '⚠ 파일 경로가 없습니다'}
          {fileUrl && <span className="block mt-1 text-[10px] opacity-60">{fileUrl}</span>}
        </div>
        <pre className="text-on-surface-variant text-sm whitespace-pre-wrap">
          {artifact.preview || 'XLSX를 불러올 수 없습니다.'}
        </pre>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col">
      {sheets.length > 1 && (
        <div className="flex gap-0 bg-surface-highest border-b border-outline/10 overflow-x-auto">
          {sheets.map((s, i) => (
            <button
              key={s.name}
              onClick={() => setActiveSheet(i)}
              className={`px-4 py-2 text-xs font-mono border-b-2 transition-colors whitespace-nowrap ${
                i === activeSheet
                  ? 'border-primary text-primary'
                  : 'border-transparent text-on-surface-variant hover:text-on-surface'
              }`}
            >
              {s.name}
            </button>
          ))}
        </div>
      )}
      <div className="flex-1 overflow-auto custom-scrollbar bg-white text-black p-4">
        {loading ? (
          <div className="flex items-center justify-center h-64">
            <div className="w-6 h-6 border-2 border-primary border-t-transparent rounded-full animate-spin" />
          </div>
        ) : (
          <div
            className="xlsx-preview text-sm"
            dangerouslySetInnerHTML={{ __html: currentHtml }}
          />
        )}
      </div>
    </div>
  );
};

export default XlsxRenderer;
