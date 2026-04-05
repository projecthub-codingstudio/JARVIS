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
const MarkdownRenderer = React.lazy(() => import('./renderers/MarkdownRenderer'));
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
  if (ext === 'md' || ext === 'markdown') return MarkdownRenderer;
  if (['png', 'jpg', 'jpeg', 'gif', 'webp', 'heic', 'svg', 'bmp'].includes(ext)) return ImageRenderer;
  if (['mp4', 'mov', 'webm', 'm4v'].includes(ext)) return VideoRenderer;
  if (['html', 'htm'].includes(ext)) return HtmlRenderer;
  if (['py', 'js', 'ts', 'tsx', 'jsx', 'mjs', 'cjs', 'rs', 'go', 'java', 'swift', 'kt', 'rb',
       'c', 'cc', 'cpp', 'h', 'hpp', 'cs', 'php', 'lua', 'r', 'scala', 'dart', 'ex', 'exs',
       'sh', 'bash', 'zsh', 'fish', 'ps1',
       'yml', 'yaml', 'json', 'jsonc', 'toml', 'ini', 'cfg', 'conf', 'env',
       'css', 'scss', 'sass', 'less',
       'sql', 'graphql', 'proto',
       'xml', 'svg', 'dockerfile', 'makefile'].includes(ext)) return CodeRenderer;
  if (['txt', 'text', 'log', 'csv', 'tsv', 'nfo', 'readme'].includes(ext)) return TextRenderer;
  return null;
}

function findExtension(artifact: Artifact): string {
  // full_path가 보통 실제 파일 경로 (확장자 포함) — 우선 확인
  const fullPathExt = getExtension(artifact.full_path || '');
  if (fullPathExt && fullPathExt.length <= 5) return fullPathExt;
  const pathExt = getExtension(artifact.path || '');
  if (pathExt && pathExt.length <= 5) return pathExt;
  return '';
}

function selectRenderer(artifact: Artifact) {
  const viewerKind = (artifact.viewer_kind || '').toLowerCase();
  const ext = findExtension(artifact);

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
      // document이지만 확장자를 모르면 텍스트로 표시 (다운로드만 X)
      return TextRenderer;
    }
    case 'markdown': return MarkdownRenderer;
    case 'text': return TextRenderer;
  }

  // 2차: viewer_kind가 없거나 'text'인 경우, 파일 확장자로 렌더러 추론
  if (ext) {
    const byExt = selectRendererByExtension(ext);
    if (byExt) return byExt;
  }

  // 3차: source_type 필드로 추론
  const sourceType = (artifact.source_type || '').toLowerCase();
  if (sourceType === 'document') {
    // document인데 확장자를 모르면 텍스트로
    return TextRenderer;
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
  const rendererMeta = Renderer as unknown as { displayName?: string; name?: string };

  if (import.meta.env.DEV) {
    console.log('[ViewerRouter]', {
      viewer_kind: artifact.viewer_kind,
      type: artifact.type,
      source_type: artifact.source_type,
      path: artifact.path,
      full_path: artifact.full_path,
      renderer: rendererMeta.displayName || rendererMeta.name || 'lazy',
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
