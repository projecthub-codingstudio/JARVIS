import type { Artifact } from '../types';

const IMAGE_EXTENSIONS = new Set(['png', 'jpg', 'jpeg', 'gif', 'webp', 'heic', 'svg', 'bmp']);
const VIDEO_EXTENSIONS = new Set(['mp4', 'mov', 'webm', 'm4v']);
const CODE_EXTENSIONS = new Set([
  'py', 'js', 'ts', 'tsx', 'jsx', 'rs', 'go', 'java', 'swift', 'kt', 'rb',
  'sh', 'bash', 'yml', 'yaml', 'json', 'css', 'sql', 'toml', 'xml', 'md',
]);

function normalizePath(path: string): string {
  return path.replace(/\\/g, '/');
}

function getExtension(path: string): string {
  const normalized = normalizePath(path);
  return (normalized.split('.').pop() || '').toLowerCase();
}

function getBasename(path: string): string {
  const normalized = normalizePath(path).replace(/\/+$/, '');
  const parts = normalized.split('/').filter(Boolean);
  return parts[parts.length - 1] || normalized;
}

export function inferArtifactType(path: string): { type: string; viewerKind: string } {
  const normalized = path.trim().toLowerCase();

  if (normalized.startsWith('http://') || normalized.startsWith('https://')) {
    return { type: 'web', viewerKind: 'web' };
  }

  const ext = getExtension(normalized);

  if (IMAGE_EXTENSIONS.has(ext)) return { type: 'image', viewerKind: 'image' };
  if (VIDEO_EXTENSIONS.has(ext)) return { type: 'video', viewerKind: 'video' };
  if (CODE_EXTENSIONS.has(ext)) return { type: 'code', viewerKind: 'code' };
  if (ext === 'pdf') return { type: 'pdf', viewerKind: 'document' };
  if (ext === 'pptx' || ext === 'ppt') return { type: 'presentation', viewerKind: 'document' };
  if (ext === 'xlsx' || ext === 'xls' || ext === 'csv') return { type: 'spreadsheet', viewerKind: 'document' };
  if (ext === 'docx' || ext === 'doc' || ext === 'hwp' || ext === 'hwpx') {
    return { type: 'document', viewerKind: 'document' };
  }
  if (ext === 'html' || ext === 'htm') return { type: 'html', viewerKind: 'html' };

  return { type: 'document', viewerKind: 'document' };
}

export function buildArtifactFromPath(params: {
  id?: string;
  path: string;
  preview?: string;
  sourceType?: string;
  subtitle?: string;
}): Artifact {
  const { id, path, preview = '', sourceType = 'document', subtitle = '' } = params;
  const { type, viewerKind } = inferArtifactType(path);
  const title = getBasename(path);

  return {
    id: id || `repo:${path}`,
    type,
    title,
    subtitle: subtitle || sourceType,
    path,
    full_path: path,
    preview,
    source_type: sourceType,
    viewer_kind: viewerKind,
  };
}

export function getPathBasename(path: string): string {
  return getBasename(path);
}

export function getPathDirectory(path: string): string {
  const normalized = normalizePath(path).replace(/\/+$/, '');
  const index = normalized.lastIndexOf('/');
  return index > 0 ? normalized.slice(0, index) : '/';
}
