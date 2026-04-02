import React, { Component, Suspense } from 'react';
import type { Artifact } from '../../types';

class ViewerErrorBoundary extends Component<
  { children: React.ReactNode; fallbackMessage: string },
  { hasError: boolean }
> {
  state = { hasError: false };
  static getDerivedStateFromError() { return { hasError: true }; }
  render() {
    if (this.state.hasError) {
      return (
        <div className="h-full flex items-center justify-center text-on-surface-variant">
          <p className="text-sm">{this.props.fallbackMessage}</p>
        </div>
      );
    }
    return this.props.children;
  }
}

export interface ViewerRouterProps {
  artifact: Artifact;
  fileUrl?: string;
  content?: string;
}

const TextRenderer = React.lazy(() => import('./renderers/TextRenderer'));
const CodeRenderer = React.lazy(() => import('./renderers/CodeRenderer'));
const ImageRenderer = React.lazy(() => import('./renderers/ImageRenderer'));
const VideoRenderer = React.lazy(() => import('./renderers/VideoRenderer'));
const HtmlRenderer = React.lazy(() => import('./renderers/HtmlRenderer'));
const WebRenderer = React.lazy(() => import('./renderers/WebRenderer'));
const PdfRenderer = React.lazy(() => import('./renderers/PdfRenderer'));
const DocxRenderer = React.lazy(() => import('./renderers/DocxRenderer'));
const PptxRenderer = React.lazy(() => import('./renderers/PptxRenderer'));
const XlsxRenderer = React.lazy(() => import('./renderers/XlsxRenderer'));
const HwpRenderer = React.lazy(() => import('./renderers/HwpRenderer'));

function getExtension(path: string): string {
  return (path.split('.').pop() || '').toLowerCase();
}

const EXT_TO_RENDERER: Record<string, typeof TextRenderer> = {};

function selectRendererByExtension(ext: string) {
  if (ext === 'pdf') return PdfRenderer;
  if (ext === 'docx') return DocxRenderer;
  if (ext === 'pptx') return PptxRenderer;
  if (ext === 'xlsx' || ext === 'xls') return XlsxRenderer;
  if (ext === 'hwp' || ext === 'hwpx') return HwpRenderer;
  if (['png', 'jpg', 'jpeg', 'gif', 'webp', 'heic', 'svg', 'bmp'].includes(ext)) return ImageRenderer;
  if (['mp4', 'mov', 'webm', 'm4v'].includes(ext)) return VideoRenderer;
  if (['html', 'htm'].includes(ext)) return HtmlRenderer;
  if (['py', 'js', 'ts', 'tsx', 'jsx', 'rs', 'go', 'java', 'swift', 'kt', 'rb',
       'sh', 'bash', 'yml', 'yaml', 'json', 'css', 'sql', 'toml', 'xml'].includes(ext)) return CodeRenderer;
  return null;
}

function selectRenderer(artifact: Artifact) {
  const viewerKind = (artifact.viewer_kind || '').toLowerCase();
  const path = artifact.path || artifact.full_path || '';
  const ext = getExtension(path);

  // 1차: viewer_kind가 명확한 경우 바로 매핑
  switch (viewerKind) {
    case 'image': return ImageRenderer;
    case 'video': return VideoRenderer;
    case 'code': return CodeRenderer;
    case 'html': return HtmlRenderer;
    case 'web': return WebRenderer;
    case 'document': {
      const byExt = selectRendererByExtension(ext);
      if (byExt) return byExt;
      // document인데 확장자를 모르면 텍스트 + 다운로드
      return HwpRenderer;
    }
  }

  // 2차: viewer_kind가 없거나 'text'인 경우, 파일 확장자로 렌더러 추론
  if (ext) {
    const byExt = selectRendererByExtension(ext);
    if (byExt) return byExt;
  }

  // 3차: source_type 필드로 추론
  const sourceType = (artifact.source_type || '').toLowerCase();
  if (sourceType === 'document') {
    // document인데 확장자를 모르면 텍스트 + 다운로드
    return HwpRenderer;
  }
  if (sourceType === 'code') return CodeRenderer;
  if (sourceType === 'web') return WebRenderer;

  // 4차: artifact.type 필드로 추론
  const artType = (artifact.type || '').toLowerCase();
  if (artType.includes('spreadsheet') || artType.includes('excel') || artType.includes('xlsx')) return XlsxRenderer;
  if (artType.includes('presentation') || artType.includes('pptx')) return PptxRenderer;
  if (artType.includes('pdf')) return PdfRenderer;
  if (artType.includes('doc')) return DocxRenderer;
  if (artType.includes('image')) return ImageRenderer;
  if (artType.includes('video')) return VideoRenderer;
  if (artType.includes('code')) return CodeRenderer;

  return TextRenderer;
}

const LoadingSpinner = () => (
  <div className="h-full flex items-center justify-center">
    <div className="w-6 h-6 border-2 border-primary border-t-transparent rounded-full animate-spin" />
  </div>
);

export const ViewerRouter: React.FC<ViewerRouterProps> = ({ artifact, fileUrl, content }) => {
  const Renderer = selectRenderer(artifact);

  if (import.meta.env.DEV) {
    console.log('[ViewerRouter]', {
      viewer_kind: artifact.viewer_kind,
      type: artifact.type,
      source_type: artifact.source_type,
      path: artifact.path,
      full_path: artifact.full_path,
      renderer: Renderer.displayName || Renderer.name || 'lazy',
    });
  }

  return (
    <ViewerErrorBoundary fallbackMessage="뷰어를 불러올 수 없습니다.">
      <Suspense fallback={<LoadingSpinner />}>
        <Renderer artifact={artifact} fileUrl={fileUrl} content={content} />
      </Suspense>
    </ViewerErrorBoundary>
  );
};
