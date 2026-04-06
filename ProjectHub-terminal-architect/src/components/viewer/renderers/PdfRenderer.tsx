import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Document, Page, pdfjs } from 'react-pdf';
import 'react-pdf/dist/Page/AnnotationLayer.css';
import 'react-pdf/dist/Page/TextLayer.css';
import { ChevronLeft, ChevronRight, PanelLeftClose, PanelLeftOpen } from 'lucide-react';
import { cn } from '../../../lib/utils';
import type { RendererProps } from './TextRenderer';

pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  'pdfjs-dist/build/pdf.worker.min.mjs',
  import.meta.url,
).toString();

const THUMB_WIDTH = 120;
const BATCH_SIZE = 10; // render thumbnails in batches

/**
 * Progressively renders PDF page thumbnails to cached image data URLs.
 * Renders in batches starting from the current page outward.
 */
function useThumbnailCache(fileUrl: string | undefined, numPages: number, currentPage: number) {
  const [cache, setCache] = useState<Record<number, string>>({});
  const pdfDocRef = useRef<any>(null);
  const renderingRef = useRef(false);

  // Load PDF document once
  useEffect(() => {
    if (!fileUrl || numPages === 0) return;
    let cancelled = false;

    pdfjs.getDocument(fileUrl).promise.then((doc) => {
      if (!cancelled) pdfDocRef.current = doc;
    });

    return () => {
      cancelled = true;
      pdfDocRef.current = null;
      setCache({});
    };
  }, [fileUrl, numPages]);

  // Render thumbnails progressively from current page outward
  useEffect(() => {
    if (!pdfDocRef.current || numPages === 0 || renderingRef.current) return;

    // Build render queue: current page first, then expand outward
    const toRender: number[] = [];
    for (let offset = 0; offset < numPages; offset++) {
      const before = currentPage - offset;
      const after = currentPage + offset;
      if (before >= 1 && !cache[before]) toRender.push(before);
      if (after !== before && after <= numPages && !cache[after]) toRender.push(after);
      if (toRender.length >= BATCH_SIZE) break;
    }

    if (toRender.length === 0) return;

    renderingRef.current = true;

    (async () => {
      const newEntries: Record<number, string> = {};
      for (const pageNum of toRender) {
        try {
          const page = await pdfDocRef.current.getPage(pageNum);
          const viewport = page.getViewport({ scale: THUMB_WIDTH / page.getViewport({ scale: 1 }).width });
          const canvas = document.createElement('canvas');
          canvas.width = viewport.width;
          canvas.height = viewport.height;
          const ctx = canvas.getContext('2d');
          if (ctx) {
            await page.render({ canvasContext: ctx, viewport }).promise;
            newEntries[pageNum] = canvas.toDataURL('image/jpeg', 0.6);
          }
        } catch {
          // skip failed pages
        }
      }
      renderingRef.current = false;
      if (Object.keys(newEntries).length > 0) {
        setCache((prev) => ({ ...prev, ...newEntries }));
      }
    })();
  }, [fileUrl, numPages, currentPage, cache]);

  return cache;
}

const PdfRenderer: React.FC<RendererProps> = ({ artifact, fileUrl, scale }) => {
  const [numPages, setNumPages] = useState<number>(0);
  const [pageNumber, setPageNumber] = useState(1);
  const [error, setError] = useState(false);
  const [editingPage, setEditingPage] = useState(false);
  const [pageInput, setPageInput] = useState('');
  const [showThumbs, setShowThumbs] = useState(true);
  const thumbListRef = useRef<HTMLDivElement>(null);

  const thumbCache = useThumbnailCache(fileUrl, numPages, pageNumber);

  // Scroll thumbnail list to keep current page visible
  useEffect(() => {
    if (!thumbListRef.current || numPages === 0) return;
    const container = thumbListRef.current;
    const thumbEl = container.children[pageNumber - 1] as HTMLElement | undefined;
    if (thumbEl) {
      const top = thumbEl.offsetTop - container.clientHeight / 2 + thumbEl.clientHeight / 2;
      container.scrollTo({ top: Math.max(0, top), behavior: 'smooth' });
    }
  }, [pageNumber, numPages]);

  if (error || !fileUrl) {
    return (
      <div className="h-full overflow-auto p-6 custom-scrollbar">
        <pre className="text-on-surface-variant text-sm whitespace-pre-wrap">
          {artifact.preview || 'PDF를 불러올 수 없습니다.'}
        </pre>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col">
      <div className="flex flex-1 min-h-0">
        {/* Thumbnail sidebar */}
        {showThumbs && numPages > 0 && (
          <div
            ref={thumbListRef}
            className="w-[140px] shrink-0 space-y-1 overflow-y-auto border-r border-white/5 bg-surface-container-high p-2 custom-scrollbar"
          >
            {Array.from({ length: numPages }, (_, i) => {
              const pageNum = i + 1;
              const src = thumbCache[pageNum];
              return (
                <button
                  key={pageNum}
                  onClick={() => setPageNumber(pageNum)}
                  className={cn(
                    'relative w-full shrink-0 border-2 transition',
                    pageNum === pageNumber
                      ? 'border-secondary'
                      : 'border-transparent hover:border-primary/30',
                  )}
                >
                  {src ? (
                    <img src={src} alt={`Page ${pageNum}`} className="w-full" />
                  ) : (
                    <div
                      className="flex items-center justify-center bg-surface-container-highest"
                      style={{ width: THUMB_WIDTH, height: THUMB_WIDTH * 1.4 }}
                    >
                      <span className="text-[10px] text-outline">{pageNum}</span>
                    </div>
                  )}
                  <div className={cn(
                    'absolute bottom-0 left-0 right-0 bg-black/60 py-0.5 text-center text-[9px] font-mono',
                    pageNum === pageNumber ? 'text-secondary' : 'text-white/70',
                  )}>
                    {pageNum}
                  </div>
                </button>
              );
            })}
          </div>
        )}

        {/* Main page view */}
        <div className="flex-1 overflow-auto flex justify-center bg-surface-low custom-scrollbar p-4">
          <Document
            file={fileUrl}
            onLoadSuccess={({ numPages: n }) => setNumPages(n)}
            onLoadError={() => setError(true)}
            loading={
              <div className="flex items-center justify-center h-64">
                <div className="w-6 h-6 border-2 border-primary border-t-transparent rounded-full animate-spin" />
              </div>
            }
          >
            <Page
              pageNumber={pageNumber}
              scale={scale || 1.0}
              renderTextLayer
              renderAnnotationLayer
              className="shadow-lg"
            />
          </Document>
        </div>
      </div>

      {/* Bottom bar */}
      {numPages > 0 && (
        <div className="relative flex h-10 shrink-0 items-center justify-center gap-4 border-t border-white/5 bg-surface px-4">
          <button
            onClick={() => setShowThumbs((v) => !v)}
            className="absolute left-2 rounded p-1 text-outline transition hover:bg-surface-container-highest hover:text-primary"
            title={showThumbs ? 'Hide thumbnails' : 'Show thumbnails'}
          >
            {showThumbs ? <PanelLeftClose size={14} /> : <PanelLeftOpen size={14} />}
          </button>
          <button
            onClick={() => setPageNumber(Math.max(1, pageNumber - 1))}
            disabled={pageNumber <= 1}
            className="rounded p-1 text-on-surface transition-colors hover:bg-surface-container-highest disabled:opacity-30"
          >
            <ChevronLeft size={14} />
          </button>
          {editingPage ? (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                const parsed = parseInt(pageInput, 10);
                if (!isNaN(parsed) && parsed >= 1 && parsed <= numPages) {
                  setPageNumber(parsed);
                }
                setEditingPage(false);
              }}
              className="flex items-center gap-1"
            >
              <input
                autoFocus
                value={pageInput}
                onChange={(e) => setPageInput(e.target.value)}
                onBlur={() => setEditingPage(false)}
                className="w-14 rounded border border-white/10 bg-surface-container-lowest px-1.5 py-0.5 text-center font-mono text-[12px] text-on-surface outline-none focus:border-primary"
              />
              <span className="font-mono text-[12px] text-outline">/ {numPages}</span>
            </form>
          ) : (
            <button
              onClick={() => { setPageInput(String(pageNumber)); setEditingPage(true); }}
              className="font-mono text-[12px] text-outline transition hover:text-primary"
              title="Click to jump to page"
            >
              {pageNumber} / {numPages}
            </button>
          )}
          <button
            onClick={() => setPageNumber(Math.min(numPages, pageNumber + 1))}
            disabled={pageNumber >= numPages}
            className="rounded p-1 text-on-surface transition-colors hover:bg-surface-container-highest disabled:opacity-30"
          >
            <ChevronRight size={14} />
          </button>
        </div>
      )}
    </div>
  );
};

export default PdfRenderer;
