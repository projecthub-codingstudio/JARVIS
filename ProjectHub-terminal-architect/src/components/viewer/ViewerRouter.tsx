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

function selectRenderer(viewerKind: string, path: string) {
  switch (viewerKind) {
    case 'image':
      return ImageRenderer;
    case 'video':
      return VideoRenderer;
    case 'code':
      return CodeRenderer;
    case 'html':
      return HtmlRenderer;
    case 'web':
      return WebRenderer;
    case 'document': {
      const ext = getExtension(path);
      if (ext === 'pdf') return PdfRenderer;
      if (ext === 'docx') return DocxRenderer;
      if (ext === 'pptx') return PptxRenderer;
      if (ext === 'xlsx' || ext === 'xls') return XlsxRenderer;
      if (ext === 'hwp' || ext === 'hwpx') return HwpRenderer;
      return TextRenderer;
    }
    case 'text':
    default:
      return TextRenderer;
  }
}

const LoadingSpinner = () => (
  <div className="h-full flex items-center justify-center">
    <div className="w-6 h-6 border-2 border-primary border-t-transparent rounded-full animate-spin" />
  </div>
);

export const ViewerRouter: React.FC<ViewerRouterProps> = ({ artifact, fileUrl, content }) => {
  const Renderer = selectRenderer(
    artifact.viewer_kind || 'text',
    artifact.path || artifact.full_path || '',
  );

  return (
    <ViewerErrorBoundary fallbackMessage="뷰어를 불러올 수 없습니다.">
      <Suspense fallback={<LoadingSpinner />}>
        <Renderer artifact={artifact} fileUrl={fileUrl} content={content} />
      </Suspense>
    </ViewerErrorBoundary>
  );
};
