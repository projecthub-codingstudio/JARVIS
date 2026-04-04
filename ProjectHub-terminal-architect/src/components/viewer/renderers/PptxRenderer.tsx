import React, { useEffect, useRef, useState } from 'react';
import DOMPurify from 'dompurify';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import type { RendererProps } from './TextRenderer';

const DEFAULT_VIEWPORT = { width: 960, height: 540 };

const PptxRenderer: React.FC<RendererProps> = ({ artifact, fileUrl }) => {
  const stageRef = useRef<HTMLDivElement>(null);
  const [slides, setSlides] = useState<string[]>([]);
  const [pptxBuffer, setPptxBuffer] = useState<ArrayBuffer | null>(null);
  const [slideIndex, setSlideIndex] = useState(0);
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState(true);
  const [viewport, setViewport] = useState(DEFAULT_VIEWPORT);

  useEffect(() => {
    if (!stageRef.current) return;

    const element = stageRef.current;
    const updateViewport = () => {
      const rect = element.getBoundingClientRect();
      const width = Math.max(320, Math.floor(rect.width) - 32);
      const height = Math.max(240, Math.floor(rect.height) - 32);

      setViewport(prev => (
        prev.width === width && prev.height === height
          ? prev
          : { width, height }
      ));
    };

    updateViewport();

    const observer = new ResizeObserver(updateViewport);
    observer.observe(element);

    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!fileUrl) return;

    let cancelled = false;
    const controller = new AbortController();
    setError(false);
    setLoading(true);
    setSlides([]);
    setPptxBuffer(null);
    setSlideIndex(0);

    fetch(fileUrl, { signal: controller.signal })
      .then(res => {
        if (!res.ok) throw new Error(`Failed to fetch: ${res.status}`);
        return res.arrayBuffer();
      })
      .then(buffer => {
        if (!cancelled) setPptxBuffer(buffer);
      })
      .catch((err) => {
        if (!cancelled) {
          console.error('[PptxRenderer] Failed to load file', err);
          setError(true);
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [fileUrl]);

  useEffect(() => {
    if (!pptxBuffer) return;

    let cancelled = false;

    (async () => {
      try {
        const { pptxToHtml } = await import('@jvmr/pptx-to-html');
        const result = await pptxToHtml(pptxBuffer, {
          width: viewport.width,
          height: viewport.height,
          scaleToFit: true,
          letterbox: true,
        });
        if (cancelled) return;
        const slideArray = Array.isArray(result) ? result : [result];
        const sanitizedSlides = slideArray.map(slide => DOMPurify.sanitize(String(slide)));
        setSlides(sanitizedSlides);
        setError(false);
        setLoading(false);
      } catch (err) {
        if (!cancelled) {
          console.error('[PptxRenderer] Failed to render slides', err);
          setError(true);
          setLoading(false);
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [pptxBuffer, viewport.height, viewport.width]);

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
      <div
        ref={stageRef}
        className="flex-1 overflow-auto flex items-center justify-center bg-surface-low custom-scrollbar p-4"
      >
        {loading ? (
          <div className="w-6 h-6 border-2 border-primary border-t-transparent rounded-full animate-spin" />
        ) : (
          <div
            className="bg-white shadow-lg"
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
