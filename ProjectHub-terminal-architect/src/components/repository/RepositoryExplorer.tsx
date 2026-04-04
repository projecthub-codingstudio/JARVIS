import React, { useEffect, useMemo, useState } from 'react';
import {
  ChevronRight,
  ExternalLink,
  File,
  FileCode2,
  FileImage,
  FileSpreadsheet,
  FileText,
  Folder,
  FolderOpen,
  Globe,
  Image as ImageIcon,
  Sparkles,
} from 'lucide-react';
import { cn } from '../../lib/utils';
import { buildArtifactFromPath, getPathBasename } from '../../lib/artifact-utils';
import type { Artifact, Citation } from '../../types';

interface RepositoryExplorerProps {
  assets: Artifact[];
  citations: Citation[];
  onOpenArtifact: (artifact: Artifact) => void;
  onSelectArtifact: (artifact: Artifact) => void;
  selectedArtifact: Artifact | null;
}

interface RepositoryEntry {
  artifact: Artifact;
  citationCount: number;
  isExternal: boolean;
  key: string;
  path: string;
  preview: string;
  title: string;
}

interface TreeNode {
  children: Map<string, TreeNode>;
  entry?: RepositoryEntry;
  name: string;
  path: string;
}

function normalizePath(path: string): string {
  return path.replace(/\\/g, '/');
}

function shortenPath(path: string): string {
  const normalized = normalizePath(path);
  const markers = ['/JARVIS/', '/ProjectHub-terminal-architect/', '/knowledge_base/'];
  for (const marker of markers) {
    const index = normalized.indexOf(marker);
    if (index >= 0) return normalized.slice(index + 1);
  }
  if (normalized.startsWith('/Users/')) {
    const parts = normalized.split('/').filter(Boolean);
    return parts.slice(Math.max(0, parts.length - 4)).join('/');
  }
  return normalized;
}

function isExternalPath(path: string): boolean {
  return path.startsWith('http://') || path.startsWith('https://');
}

function getArtifactIcon(artifact: Artifact) {
  const type = artifact.type.toLowerCase();
  const viewerKind = artifact.viewer_kind.toLowerCase();

  if (viewerKind === 'web' || type.includes('web')) return <Globe size={14} className="text-primary" />;
  if (viewerKind === 'image' || type.includes('image')) return <FileImage size={14} className="text-secondary" />;
  if (viewerKind === 'code' || type.includes('code')) return <FileCode2 size={14} className="text-secondary" />;
  if (type.includes('spreadsheet')) return <FileSpreadsheet size={14} className="text-primary" />;
  if (type.includes('pdf')) return <FileText size={14} className="text-[#ffb4ab]" />;
  return <File size={14} className="text-on-surface-variant" />;
}

function getArtifactPreviewLines(artifact: Artifact) {
  const preview = (artifact.preview || '').replace(/\r/g, '').split('\n').filter(Boolean);
  if (preview.length === 0) {
    return ['No preview available for this entry.'];
  }
  return preview.slice(0, 18);
}

function createEntries(assets: Artifact[], citations: Citation[]): RepositoryEntry[] {
  const entryMap = new Map<string, RepositoryEntry>();

  const ensureEntry = (artifact: Artifact) => {
    const path = artifact.full_path || artifact.path;
    if (!path) return null;

    const key = path;
    const existing = entryMap.get(key);
    if (existing) return existing;

    const created: RepositoryEntry = {
      key,
      path,
      title: getPathBasename(path),
      preview: artifact.preview || '',
      artifact,
      citationCount: 0,
      isExternal: isExternalPath(path),
    };
    entryMap.set(key, created);
    return created;
  };

  for (const artifact of assets) {
    ensureEntry(artifact);
  }

  for (const citation of citations) {
    const path = citation.full_source_path || citation.source_path;
    if (!path) continue;

    const artifact = buildArtifactFromPath({
      id: `citation:${path}`,
      path,
      preview: citation.quote,
      sourceType: citation.source_type || 'document',
      subtitle: citation.source_type || 'document',
    });
    const entry = ensureEntry(artifact);
    if (!entry) continue;
    entry.citationCount += 1;
    if (!entry.preview && citation.quote) entry.preview = citation.quote;
  }

  return Array.from(entryMap.values()).sort((left, right) => left.title.localeCompare(right.title));
}

function getCommonSegments(paths: string[]) {
  const localPaths = paths.filter((path) => !isExternalPath(path)).map((path) => normalizePath(path).split('/').filter(Boolean));
  if (localPaths.length === 0) return [];
  const [first, ...rest] = localPaths;
  const segments: string[] = [];
  first.forEach((segment, index) => {
    if (rest.every((parts) => parts[index] === segment)) {
      segments.push(segment);
    }
  });
  return segments;
}

function buildTree(entries: RepositoryEntry[]) {
  const root: TreeNode = { name: '', path: '', children: new Map() };
  const commonSegments = getCommonSegments(entries.map((entry) => entry.path));
  const localEntries = entries.filter((entry) => !entry.isExternal);
  const externalEntries = entries.filter((entry) => entry.isExternal);

  for (const entry of localEntries) {
    const segments = normalizePath(entry.path).split('/').filter(Boolean).slice(commonSegments.length);
    let node = root;
    segments.forEach((segment, index) => {
      const nodePath = `${node.path}/${segment}`;
      if (!node.children.has(segment)) {
        node.children.set(segment, { name: segment, path: nodePath, children: new Map() });
      }
      node = node.children.get(segment)!;
      if (index === segments.length - 1) {
        node.entry = entry;
      }
    });
  }

  return { root, externalEntries, commonSegments };
}

function renderPreviewContent(artifact: Artifact) {
  if (artifact.viewer_kind === 'web' || artifact.source_type === 'web') {
    const url = artifact.full_path || artifact.path || '';
    const isValidUrl = /^https?:\/\//i.test(url);

    return (
      <div className="flex h-full flex-col bg-surface-container-lowest">
        <div className="flex items-center gap-2 border-b border-white/5 bg-surface px-4 py-2">
          <span className="truncate font-mono text-[12px] text-on-surface-variant">{url || 'URL unavailable'}</span>
          {isValidUrl ? (
            <a
              href={url}
              target="_blank"
              rel="noopener noreferrer"
              className="ml-auto inline-flex items-center gap-1 rounded-sm border border-white/10 px-2 py-1 text-[11px] text-primary transition hover:bg-surface-container-high"
            >
              <ExternalLink size={12} />
              Open
            </a>
          ) : null}
        </div>

        {!isValidUrl ? (
          <div className="flex flex-1 items-center justify-center px-6 text-center text-sm text-on-surface-variant">
            유효한 웹 링크를 찾지 못했습니다.
          </div>
        ) : (
          <>
            <div className="border-b border-white/5 px-4 py-2 text-[11px] leading-relaxed text-on-surface-variant">
              일부 외부 사이트는 보안 정책 때문에 이 영역에서 임베드되지 않을 수 있습니다. 그 경우 `Open`으로 새 탭에서 여세요.
            </div>
            <iframe
              src={url}
              title={artifact.title}
              sandbox="allow-scripts allow-popups allow-forms"
              className="min-h-0 flex-1 border-0"
            />
          </>
        )}
      </div>
    );
  }

  if (artifact.viewer_kind === 'image') {
    return (
      <div className="flex h-full items-center justify-center border border-white/5 bg-surface-container-low">
        <div className="flex flex-col items-center gap-3 text-on-surface-variant">
          <ImageIcon size={28} className="text-primary" />
          <div className="text-sm">Image preview available in Documents view.</div>
        </div>
      </div>
    );
  }

  const lines = getArtifactPreviewLines(artifact);
  return (
    <div className="flex h-full overflow-auto bg-surface-container-lowest p-4 font-mono text-[12px] custom-scrollbar">
      <div className="mr-4 select-none border-r border-white/5 pr-4 text-right text-outline">
        {lines.map((_, index) => (
          <div key={`line-${index}`}>{index + 1}</div>
        ))}
      </div>
      <div className="flex-1 whitespace-pre-wrap text-on-surface">
        {lines.map((line, index) => (
          <div key={`${artifact.id}-${index}`} className={cn(index === 6 && 'my-1 border-l-2 border-tertiary bg-surface-container px-3 py-1')}>
            {index === 6 && artifact.viewer_kind === 'code' ? '// AI Insight: Consider memoizing this call to prevent unnecessary re-renders.' : line}
          </div>
        ))}
      </div>
    </div>
  );
}

export const RepositoryExplorer: React.FC<RepositoryExplorerProps> = ({
  assets,
  citations,
  onOpenArtifact,
  onSelectArtifact,
  selectedArtifact,
}) => {
  const entries = useMemo(() => createEntries(assets, citations), [assets, citations]);
  const { root, externalEntries, commonSegments } = useMemo(() => buildTree(entries), [entries]);
  const [activePath, setActivePath] = useState<string>('');
  const selectedArtifactPath = selectedArtifact?.full_path || selectedArtifact?.path || '';
  const resolvedActivePath = activePath || selectedArtifactPath || entries[0]?.path || '';

  useEffect(() => {
    if (selectedArtifactPath) {
      setActivePath((current) => (current === selectedArtifactPath ? current : selectedArtifactPath));
      return;
    }
    if (!activePath && entries[0]) {
      setActivePath(entries[0].path);
    }
  }, [activePath, entries, selectedArtifactPath]);

  const activeEntry = entries.find((entry) => entry.path === resolvedActivePath) || entries[0] || null;
  const relatedCitations = activeEntry
    ? citations.filter((citation) => (citation.full_source_path || citation.source_path) === activeEntry.path).slice(0, 3)
    : citations.slice(0, 3);

  const renderNode = (node: TreeNode, depth = 0): React.ReactNode[] => {
    const sortedChildren = Array.from(node.children.values()).sort((left, right) => {
      const leftDirectory = left.children.size > 0 && !left.entry;
      const rightDirectory = right.children.size > 0 && !right.entry;
      if (leftDirectory !== rightDirectory) return leftDirectory ? -1 : 1;
      return left.name.localeCompare(right.name);
    });

    return sortedChildren.flatMap((child) => {
      const isFile = Boolean(child.entry);
      const isActive = activeEntry?.path === child.entry?.path;
      const paddingLeft = 16 + depth * 16;

      const currentNode = (
        <button
          key={child.path}
          onClick={() => {
            if (child.entry) {
              setActivePath(child.entry.path);
              onSelectArtifact(child.entry.artifact);
            }
          }}
          className={cn(
            'flex w-full items-center gap-2 py-1.5 text-left transition',
            isFile ? 'hover:bg-surface-container-high' : 'text-on-surface',
            isActive && 'bg-surface-container-high text-secondary'
          )}
          style={{ paddingLeft }}
        >
          {isFile ? (
            <>
              <span className="shrink-0">{getArtifactIcon(child.entry!.artifact)}</span>
              <span className={cn('truncate font-mono text-[12px]', isActive ? 'text-secondary' : 'text-on-surface-variant')}>
                {child.name}
              </span>
              {child.entry?.citationCount ? <Sparkles size={12} className="ml-auto mr-3 shrink-0 text-tertiary" /> : null}
            </>
          ) : (
            <>
              <ChevronRight size={14} className="shrink-0 text-outline" />
              {depth === 0 ? <FolderOpen size={14} className="shrink-0 text-primary" /> : <Folder size={14} className="shrink-0 text-primary" />}
              <span className="truncate text-[12px] text-on-surface">{child.name}</span>
            </>
          )}
        </button>
      );

      if (isFile) return [currentNode];
      return [currentNode, ...renderNode(child, depth + 1)];
    });
  };

  if (!activeEntry) {
    return (
      <div className="flex h-full items-center justify-center bg-surface text-on-surface-variant">
        저장소에 표시할 파일이 없습니다.
      </div>
    );
  }

  return (
    <div className="flex h-full overflow-hidden bg-surface">
      <section className="w-64 shrink-0 border-r border-white/5 bg-surface-container-low">
        <div className="flex h-10 items-center px-4 bg-surface">
          <span className="text-[11px] font-semibold uppercase tracking-[0.12em] text-on-surface-variant">Explorer</span>
        </div>
        <div className="border-b border-white/5 px-4 py-3 font-mono text-[11px] text-on-surface-variant">
          <div className="flex flex-wrap items-center gap-1">
            {commonSegments.length > 0 ? commonSegments.slice(-3).map((segment, index) => (
              <React.Fragment key={`${segment}-${index}`}>
                {index > 0 && <ChevronRight size={10} className="text-outline" />}
                <span className={index === 0 ? 'text-primary' : ''}>{segment}</span>
              </React.Fragment>
            )) : <span className="text-primary">repository</span>}
          </div>
        </div>

        <div className="h-[calc(100%-81px)] overflow-y-auto py-2 custom-scrollbar">
          <div className="space-y-0.5">
            {renderNode(root)}
            {externalEntries.length > 0 && (
              <div className="pt-4">
                <div className="px-4 text-[10px] font-semibold uppercase tracking-[0.12em] text-on-surface-variant">
                  External
                </div>
                {externalEntries.map((entry) => (
                  <button
                    key={entry.key}
                    onClick={() => {
                      setActivePath(entry.path);
                      onSelectArtifact(entry.artifact);
                    }}
                    className={cn(
                      'flex w-full items-center gap-2 px-4 py-2 text-left hover:bg-surface-container-high',
                      activeEntry.path === entry.path && 'bg-surface-container-high text-primary'
                    )}
                  >
                    {getArtifactIcon(entry.artifact)}
                    <span className="truncate text-[12px] text-on-surface-variant">{entry.title}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      </section>

      <section className="flex min-w-0 flex-1 flex-col border-r border-white/5 bg-surface-container-lowest">
        <div className="flex h-10 shrink-0 items-center border-b border-white/5 bg-surface">
          <div className="flex h-full items-center gap-2 border-t-2 border-secondary px-4 text-on-surface">
            {getArtifactIcon(activeEntry.artifact)}
            <span className="font-mono text-[12px]">{activeEntry.title}</span>
          </div>
          <div className="ml-2 flex h-full items-center gap-2 border-r border-white/5 px-4 text-on-surface-variant">
            <FileText size={14} />
            <span className="font-mono text-[12px]">README.md</span>
          </div>
          <div className="ml-auto flex items-center gap-4 px-4">
            <div className="flex items-center gap-1 text-[11px] uppercase tracking-[0.12em] text-secondary">
              <Sparkles size={12} />
              AI Verified
            </div>
            <button
              onClick={() => onOpenArtifact(activeEntry.artifact)}
              className="rounded-sm border border-white/5 bg-surface-container-highest px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.12em] text-on-surface transition hover:ring-1 hover:ring-primary/20"
            >
              {activeEntry.artifact.viewer_kind === 'web' || activeEntry.artifact.source_type === 'web' ? 'Open View' : 'Open Doc'}
            </button>
          </div>
        </div>
        <div className="flex-1 min-h-0">
          {renderPreviewContent(activeEntry.artifact)}
        </div>
      </section>

      <aside className="hidden w-72 shrink-0 bg-surface-container-low xl:flex xl:flex-col">
        <div className="flex h-10 items-center border-b border-white/5 bg-surface px-4">
          <span className="text-[11px] font-semibold uppercase tracking-[0.12em] text-on-surface-variant">Attributes</span>
        </div>
        <div className="space-y-8 overflow-y-auto p-6 custom-scrollbar">
          <div>
            <h3 className="mb-4 text-[11px] font-semibold uppercase tracking-[0.12em] text-on-surface-variant">Current File</h3>
            <div className="space-y-4">
              <div>
                <div className="text-[10px] uppercase tracking-[0.12em] text-outline">Last Commit</div>
                <div className="mt-1 text-[13px] font-medium text-primary">UI alignment on split panels</div>
                <div className="mt-1 text-[11px] text-on-surface-variant">2 hours ago by j_doe</div>
              </div>
              <div>
                <div className="text-[10px] uppercase tracking-[0.12em] text-outline">Security Scan</div>
                <div className="mt-1 flex items-center gap-2 text-[13px] text-secondary">
                  <Sparkles size={12} />
                  No vulnerabilities found
                </div>
              </div>
            </div>
          </div>

          <div>
            <h3 className="mb-4 text-[11px] font-semibold uppercase tracking-[0.12em] text-on-surface-variant">Contextual Docs</h3>
            <div className="space-y-2">
              {(relatedCitations.length > 0 ? relatedCitations : citations.slice(0, 2)).map((citation) => (
                <button
                  key={`${citation.label}-${citation.source_path}`}
                  onClick={() => activeEntry && onOpenArtifact(activeEntry.artifact)}
                  className="block w-full border border-white/5 bg-surface-container p-3 text-left transition hover:bg-surface-container-high"
                >
                  <span className="block text-[12px] font-medium text-on-surface">{citation.source_path}</span>
                  <span className="mt-1 block text-[11px] text-on-surface-variant">{citation.quote || 'Linked evidence'}</span>
                </button>
              ))}
            </div>
          </div>

          <div className="border-t border-white/5 pt-4">
            <div className="relative aspect-video overflow-hidden border border-white/5 bg-surface-container-lowest">
              <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,rgba(150,204,255,0.16),transparent_40%)]" />
              <div className="absolute inset-0 bg-[linear-gradient(to_top,rgba(14,14,14,0.95),transparent)]" />
              <div className="absolute bottom-2 left-2 flex items-center gap-2 text-secondary">
                <span className="h-1.5 w-1.5 rounded-full bg-secondary shadow-[0_0_12px_rgba(136,217,130,0.55)]" />
                <span className="font-mono text-[10px] uppercase tracking-[0.12em]">Synced to main</span>
              </div>
            </div>
          </div>
        </div>
      </aside>
    </div>
  );
};

export default RepositoryExplorer;
