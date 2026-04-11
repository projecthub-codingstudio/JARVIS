import React, { useEffect, useRef, useState } from 'react';
import DOMPurify from 'dompurify';
import { ChevronLeft, ChevronRight, PanelLeftClose, PanelLeftOpen } from 'lucide-react';
import { cn } from '../../../lib/utils';
import type { RendererProps } from './TextRenderer';

const DEFAULT_VIEWPORT = { width: 960, height: 540 };
const THUMB_VIEWPORT = { width: 160, height: 90 };

const PptxRenderer: React.FC<RendererProps> = ({ artifact, fileUrl, scale }) => {
  const stageRef = useRef<HTMLDivElement>(null);
  const [slides, setSlides] = useState<string[]>([]);
  const [thumbSlides, setThumbSlides] = useState<string[]>([]);
  const [pptxBuffer, setPptxBuffer] = useState<ArrayBuffer | null>(null);
  const [slideIndex, setSlideIndex] = useState(0);
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState(true);
  const [viewport, setViewport] = useState(DEFAULT_VIEWPORT);
  const [showThumbs, setShowThumbs] = useState(true);
  const thumbListRef = useRef<HTMLDivElement>(null);

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

  // Scroll thumbnail list to keep current slide visible
  useEffect(() => {
    if (!thumbListRef.current) return;
    const thumbHeight = THUMB_VIEWPORT.height + 28;
    const scrollTarget = slideIndex * thumbHeight - thumbListRef.current.clientHeight / 2 + thumbHeight / 2;
    thumbListRef.current.scrollTo({ top: Math.max(0, scrollTarget), behavior: 'smooth' });
  }, [slideIndex]);

  useEffect(() => {
    if (!fileUrl) return;

    let cancelled = false;
    const controller = new AbortController();
    setError(false);
    setLoading(true);
    setSlides([]);
    setThumbSlides([]);
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

  // Render main slides
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
        // All HTML is sanitized via DOMPurify before rendering
        const sanitizedSlides = slideArray.map(slide =>
          DOMPurify.sanitize(String(slide), { FORBID_TAGS: ['base'], FORBID_ATTR: ['onerror', 'onload'] }),
        );
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

  // Render thumbnail slides (small viewport, only once when buffer loads)
  useEffect(() => {
    if (!pptxBuffer) return;

    let cancelled = false;

    (async () => {
      try {
        const { pptxToHtml } = await import('@jvmr/pptx-to-html');
        const result = await pptxToHtml(pptxBuffer, {
          width: THUMB_VIEWPORT.width,
          height: THUMB_VIEWPORT.height,
          scaleToFit: true,
          letterbox: true,
        });
        if (cancelled) return;
        const slideArray = Array.isArray(result) ? result : [result];
        // Thumbnails also sanitized via DOMPurify
        const sanitized = slideArray.map(slide =>
          DOMPurify.sanitize(String(slide), { FORBID_TAGS: ['base'], FORBID_ATTR: ['onerror', 'onload'] }),
        );
        setThumbSlides(sanitized);
      } catch {
        // Thumbnails are optional — ignore errors
      }
    })();

    return () => { cancelled = true; };
  }, [pptxBuffer]);

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
      <div className="flex flex-1 min-h-0">
        {/* Thumbnail sidebar — all HTML is DOMPurify-sanitized */}
        {showThumbs && thumbSlides.length > 1 && (
          <div
            ref={thumbListRef}
            className="w-[180px] shrink-0 space-y-1 overflow-y-auto border-r border-white/5 bg-surface-container-high p-2 custom-scrollbar"
          >
            {thumbSlides.map((sanitizedHtml, i) => (
              <button
                key={i}
                onClick={() => setSlideIndex(i)}
                className={cn(
                  'group relative w-full shrink-0 border-2 transition',
                  i === slideIndex
                    ? 'border-secondary'
                    : 'border-transparent hover:border-primary/30',
                )}
              >
                <div
                  className="pointer-events-none bg-white"
                  dangerouslySetInnerHTML={{ __html: sanitizedHtml }}
                />
                <div className={cn(
                  'absolute bottom-0 left-0 right-0 bg-black/60 py-0.5 text-center text-[9px] font-mono',
                  i === slideIndex ? 'text-secondary' : 'text-white/70',
                )}>
                  {i + 1}
                </div>
              </button>
            ))}
          </div>
        )}

        {/* Main slide view — HTML is DOMPurify-sanitized */}
        <div
          ref={stageRef}
          className="flex-1 overflow-auto flex items-center justify-center bg-surface-low custom-scrollbar p-4"
        >
          {loading ? (
            <div className="w-6 h-6 border-2 border-primary border-t-transparent rounded-full animate-spin" />
          ) : (
            <div
              className="bg-white shadow-lg"
              style={scale && scale !== 1 ? { transform: `scale(${scale})`, transformOrigin: 'top center', transition: 'transform 0.2s' } : undefined}
            >
              {/* Slide HTML is DOMPurify-sanitized in the render effect (line 106) */}
              <div dangerouslySetInnerHTML={{ __html: slides[slideIndex] || '' }} />
            </div>
          )}
        </div>
      </div>

      {/* Bottom bar */}
      {slides.length > 1 && (
        <div className="relative flex h-10 shrink-0 items-center justify-center gap-4 border-t border-white/5 bg-surface px-4">
          <button
            onClick={() => setShowThumbs((v) => !v)}
            className="absolute left-2 rounded p-1 text-outline transition hover:bg-surface-container-highest hover:text-primary"
            title={showThumbs ? 'Hide thumbnails' : 'Show thumbnails'}
          >
            {showThumbs ? <PanelLeftClose size={14} /> : <PanelLeftOpen size={14} />}
          </button>
          <button
            onClick={() => setSlideIndex(Math.max(0, slideIndex - 1))}
            disabled={slideIndex <= 0}
            className="rounded p-1 text-on-surface transition-colors hover:bg-surface-container-highest disabled:opacity-30"
          >
            <ChevronLeft size={14} />
          </button>
          <span className="font-mono text-[12px] text-outline">
            슬라이드 {slideIndex + 1} / {slides.length}
          </span>
          <button
            onClick={() => setSlideIndex(Math.min(slides.length - 1, slideIndex + 1))}
            disabled={slideIndex >= slides.length - 1}
            className="rounded p-1 text-on-surface transition-colors hover:bg-surface-container-highest disabled:opacity-30"
          >
            <ChevronRight size={14} />
          </button>
        </div>
      )}
    </div>
  );
};

export default PptxRenderer;
