import React, { useEffect, useRef, useState } from 'react';
import DOMPurify from 'dompurify';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import type { RendererProps } from './TextRenderer';

const PptxRenderer: React.FC<RendererProps> = ({ artifact, fileUrl }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [slides, setSlides] = useState<string[]>([]);
  const [slideIndex, setSlideIndex] = useState(0);
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!fileUrl) return;

    setLoading(true);
    (async () => {
      try {
        const { default: pptxToHtml } = await import('@jvmr/pptx-to-html');
        const res = await fetch(fileUrl);
        if (!res.ok) throw new Error('Failed to fetch');
        const buffer = await res.arrayBuffer();
        const result = await pptxToHtml(new Uint8Array(buffer));
        const slideArray = Array.isArray(result) ? result : [result];
        const sanitizedSlides = slideArray.map(s => DOMPurify.sanitize(String(s)));
        setSlides(sanitizedSlides);
        setLoading(false);
      } catch {
        setError(true);
        setLoading(false);
      }
    })();
  }, [fileUrl]);

  if (error || !fileUrl) {
    return (
      <div className="h-full overflow-auto p-6 custom-scrollbar">
        <pre className="text-on-surface-variant text-sm whitespace-pre-wrap">
          {artifact.preview || 'PPTX를 불러올 수 없습니다.'}
        </pre>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col">
      <div className="flex-1 overflow-auto flex items-center justify-center bg-surface-low custom-scrollbar p-4">
        {loading ? (
          <div className="w-6 h-6 border-2 border-primary border-t-transparent rounded-full animate-spin" />
        ) : (
          <div
            ref={containerRef}
            className="bg-white shadow-lg max-w-4xl w-full p-8"
            dangerouslySetInnerHTML={{ __html: slides[slideIndex] || '' }}
          />
        )}
      </div>
      {slides.length > 1 && (
        <div className="flex items-center justify-center gap-4 p-3 bg-surface-highest/50 border-t border-outline/10">
          <button
            onClick={() => setSlideIndex(Math.max(0, slideIndex - 1))}
            disabled={slideIndex <= 0}
            className="p-1 hover:bg-surface-highest disabled:opacity-30 transition-colors"
          >
            <ChevronLeft size={18} />
          </button>
          <span className="font-mono text-xs text-on-surface-variant">
            슬라이드 {slideIndex + 1} / {slides.length}
          </span>
          <button
            onClick={() => setSlideIndex(Math.min(slides.length - 1, slideIndex + 1))}
            disabled={slideIndex >= slides.length - 1}
            className="p-1 hover:bg-surface-highest disabled:opacity-30 transition-colors"
          >
            <ChevronRight size={18} />
          </button>
        </div>
      )}
    </div>
  );
};

export default PptxRenderer;
