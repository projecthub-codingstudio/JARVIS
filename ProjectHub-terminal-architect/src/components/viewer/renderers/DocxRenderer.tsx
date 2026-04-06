import React, { useEffect, useRef, useState } from 'react';
import DOMPurify from 'dompurify';
import { renderAsync } from 'docx-preview';
import type { RendererProps } from './TextRenderer';

const DocxRenderer: React.FC<RendererProps> = ({ artifact, fileUrl }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!fileUrl || !containerRef.current) return;

    let cancelled = false;
    const controller = new AbortController();
    setLoading(true);

    fetch(fileUrl, { signal: controller.signal })
      .then(res => {
        if (!res.ok) throw new Error('Failed to fetch');
        return res.arrayBuffer();
      })
      .then(buffer => {
        if (cancelled || !containerRef.current) return;
        return renderAsync(buffer, containerRef.current, undefined, {
          className: 'docx-preview',
          inWrapper: true,
        });
      })
      .then(() => {
        // Sanitize docx-preview output to prevent XSS from malicious DOCX files
        // Using DOMPurify (sanitizer library) to clean the rendered HTML
        if (!cancelled && containerRef.current) {
          const sanitized = DOMPurify.sanitize(
            containerRef.current.innerHTML,
            { FORBID_TAGS: ['base'], FORBID_ATTR: ['onerror', 'onload'] },
          );
          containerRef.current.textContent = '';
          const wrapper = document.createElement('div');
          wrapper.innerHTML = sanitized; // DOMPurify-sanitized HTML is safe
          while (wrapper.firstChild) {
            containerRef.current.appendChild(wrapper.firstChild);
          }
        }
        if (!cancelled) setLoading(false);
      })
      .catch(() => { if (!cancelled) { setError(true); setLoading(false); } });

    return () => { cancelled = true; controller.abort(); };
  }, [fileUrl]);

  if (error || !fileUrl) {
    return (
      <div className="h-full overflow-auto p-6 custom-scrollbar">
        <pre className="text-on-surface-variant text-sm whitespace-pre-wrap">
          {artifact.preview || 'DOCX를 불러올 수 없습니다.'}
        </pre>
      </div>
    );
  }

  return (
    <div className="h-full overflow-auto custom-scrollbar bg-white">
      {loading && (
        <div className="flex items-center justify-center h-64">
          <div className="w-6 h-6 border-2 border-primary border-t-transparent rounded-full animate-spin" />
        </div>
      )}
      <div ref={containerRef} className={loading ? 'hidden' : ''} />
    </div>
  );
};

export default DocxRenderer;
