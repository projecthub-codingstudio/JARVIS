import type { Artifact, FileNode } from '../types';

/* ── Extension sets ── */

const CODE_EXTENSIONS = new Set([
  '.py', '.ts', '.tsx', '.js', '.jsx', '.mjs', '.cjs',
  '.swift', '.java', '.go', '.rs', '.kt', '.rb', '.scala', '.dart',
  '.c', '.cc', '.cpp', '.h', '.hpp', '.cs', '.php', '.lua', '.r',
  '.sh', '.bash', '.zsh', '.fish', '.ps1',
  '.yml', '.yaml', '.json', '.jsonc', '.toml', '.ini', '.cfg', '.conf', '.env',
  '.css', '.scss', '.sass', '.less',
  '.sql', '.graphql', '.proto', '.xml', '.ex', '.exs',
]);

const IMAGE_EXTENSIONS = new Set(['.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.bmp', '.heic']);
const VIDEO_EXTENSIONS = new Set(['.mp4', '.mov', '.webm', '.m4v']);
const TEXT_EXTENSIONS = new Set(['.txt', '.log', '.csv', '.tsv', '.env', '.nfo']);
const MARKDOWN_EXTENSIONS = new Set(['.md', '.markdown']);
const WEB_EXTENSIONS = new Set(['.html', '.htm']);

/* ── FileNode → Artifact ── */

export function fileNodeToArtifact(node: FileNode): Artifact {
  const ext = (node.extension ?? '').toLowerCase();
  let viewerKind = 'document';
  if (CODE_EXTENSIONS.has(ext)) viewerKind = 'code';
  else if (MARKDOWN_EXTENSIONS.has(ext)) viewerKind = 'markdown';
  else if (TEXT_EXTENSIONS.has(ext)) viewerKind = 'text';
  else if (IMAGE_EXTENSIONS.has(ext)) viewerKind = 'image';
  else if (VIDEO_EXTENSIONS.has(ext)) viewerKind = 'video';
  else if (WEB_EXTENSIONS.has(ext)) viewerKind = 'html';

  return {
    id: node.path,
    type: ext.replace('.', '') || 'unknown',
    title: node.name,
    subtitle: node.path,
    path: node.path,
    full_path: node.path,
    preview: '',
    source_type: 'file',
    viewer_kind: viewerKind,
  };
}

/* ── File size formatter ── */

export function formatFileSize(bytes: number | null | undefined): string {
  if (bytes == null || bytes === 0) return '';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/* ── Icon color by extension ── */

export function getFileColor(ext: string | null | undefined): string {
  const e = (ext ?? '').toLowerCase();
  if (e === '.pdf') return '#ef4444';
  if (['.xlsx', '.xls', '.csv'].includes(e)) return '#22c55e';
  if (['.pptx', '.ppt'].includes(e)) return '#f97316';
  if (['.docx', '.doc'].includes(e)) return '#3b82f6';
  if (['.md', '.txt', '.log'].includes(e)) return '#94a3b8';
  if (CODE_EXTENSIONS.has(e)) return '#a855f7';
  if (IMAGE_EXTENSIONS.has(e)) return '#ec4899';
  if (['.hwp', '.hwpx'].includes(e)) return '#06b6d4';
  if (['.json', '.yaml', '.yml', '.toml', '.xml'].includes(e)) return '#f59e0b';
  return '#64748b';
}
