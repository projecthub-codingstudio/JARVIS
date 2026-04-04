import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  AppWindow,
  Cloud,
  GitBranch,
  Link2,
  Plus,
  RefreshCw,
  Save,
  Workflow,
} from 'lucide-react';
import { cn } from '../../lib/utils';
import type {
  ActionMap,
  ActionMapCreateInput,
  ActionMapEdge,
  ActionMapInput,
  ActionMapNode,
  SkillCard,
  SkillCatalog,
  SkillProfileCreateInput,
  SkillProfileInput,
} from '../../types';

interface SkillsWorkspaceProps {
  actionMaps: ActionMap[];
  actionMapsError: string | null;
  actionMapsLoading: boolean;
  backendStatus: 'checking' | 'online' | 'offline';
  catalog: SkillCatalog | null;
  catalogError: string | null;
  catalogLoading: boolean;
  onCreateActionMap: (input: ActionMapCreateInput) => Promise<void>;
  onCreateSkill: (input: SkillProfileCreateInput) => Promise<void>;
  onRefreshActionMaps: () => Promise<void>;
  onRefreshSkills: () => Promise<void>;
  onSaveActionMap: (mapId: string, input: ActionMapInput) => Promise<void>;
  onSaveSkill: (skillId: string, input: SkillProfileInput) => Promise<void>;
}

type SkillTab = 'registry' | 'action_maps';
type InstalledMode = 'auto' | 'yes' | 'no';

interface SkillFormState {
  title: string;
  parent_skill_id: string;
  summary: string;
  local_app_name: string;
  local_app_installed: InstalledMode;
  launch_target: string;
  open_supported: boolean;
  local_notes: string;
  api_provider: string;
  api_configured: boolean;
  api_scopes: string;
  api_notes: string;
  notes: string;
  tags: string;
  linked_intents: string;
  custom_fields: string;
}

interface MapFormState {
  title: string;
  description: string;
  trigger_query: string;
  notes: string;
  tags: string;
  nodes: ActionMapNode[];
  edges: ActionMapEdge[];
}

const NODE_WIDTH = 220;
const NODE_HEIGHT = 76;

function toCsv(values: string[]): string {
  return values.join(', ');
}

function fromCsv(value: string): string[] {
  return value
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean);
}

function formatDateTime(value: string): string {
  if (!value) return 'N/A';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString('ko-KR', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function skillFormFromCard(skill: SkillCard): SkillFormState {
  return {
    title: skill.title || '',
    parent_skill_id: skill.parent_skill_id || '',
    summary: skill.summary || '',
    local_app_name: skill.local_app_name || '',
    local_app_installed: skill.local_app_installed === true ? 'yes' : skill.local_app_installed === false ? 'no' : 'auto',
    launch_target: skill.launch_target || '',
    open_supported: Boolean(skill.open_supported),
    local_notes: skill.local_notes || '',
    api_provider: skill.api_provider || '',
    api_configured: Boolean(skill.api_configured),
    api_scopes: toCsv(skill.api_scopes || []),
    api_notes: skill.api_notes || '',
    notes: skill.notes || '',
    tags: toCsv(skill.tags || []),
    linked_intents: toCsv(skill.linked_intent_ids || []),
    custom_fields: JSON.stringify(skill.custom_fields || {}, null, 2),
  };
}

function mapFormFromMap(actionMap: ActionMap): MapFormState {
  return {
    title: actionMap.title || '',
    description: actionMap.description || '',
    trigger_query: actionMap.trigger_query || '',
    notes: actionMap.notes || '',
    tags: toCsv(actionMap.tags || []),
    nodes: Array.isArray(actionMap.nodes) ? actionMap.nodes : [],
    edges: Array.isArray(actionMap.edges) ? actionMap.edges : [],
  };
}

function payloadFromSkillForm(form: SkillFormState): SkillProfileInput {
  return {
    title: form.title,
    parent_skill_id: form.parent_skill_id,
    summary: form.summary,
    local_app_name: form.local_app_name,
    local_app_installed: form.local_app_installed === 'auto' ? null : form.local_app_installed === 'yes',
    launch_target: form.launch_target,
    open_supported: form.open_supported,
    local_notes: form.local_notes,
    api_provider: form.api_provider,
    api_configured: form.api_configured,
    api_scopes: fromCsv(form.api_scopes),
    api_notes: form.api_notes,
    notes: form.notes,
    tags: fromCsv(form.tags),
    linked_intents: fromCsv(form.linked_intents),
    custom_fields: JSON.parse(form.custom_fields || '{}') as Record<string, string>,
  };
}

function payloadFromMapForm(form: MapFormState): ActionMapInput {
  return {
    title: form.title,
    description: form.description,
    trigger_query: form.trigger_query,
    notes: form.notes,
    tags: fromCsv(form.tags),
    nodes: form.nodes,
    edges: form.edges,
  };
}

export const SkillsWorkspace: React.FC<SkillsWorkspaceProps> = ({
  actionMaps,
  actionMapsError,
  actionMapsLoading,
  backendStatus,
  catalog,
  catalogError,
  catalogLoading,
  onCreateActionMap,
  onCreateSkill,
  onRefreshActionMaps,
  onRefreshSkills,
  onSaveActionMap,
  onSaveSkill,
}) => {
  const [activeTab, setActiveTab] = useState<SkillTab>('registry');
  const [selectedCategory, setSelectedCategory] = useState<string>('all');
  const [selectedSkillId, setSelectedSkillId] = useState<string>('');
  const [selectedMapId, setSelectedMapId] = useState<string>('');
  const [selectedNodeId, setSelectedNodeId] = useState<string>('');
  const [skillForm, setSkillForm] = useState<SkillFormState | null>(null);
  const [mapForm, setMapForm] = useState<MapFormState | null>(null);
  const [createSkillForm, setCreateSkillForm] = useState<SkillProfileCreateInput>({
    skill_id: '',
    title: '',
    summary: '',
    local_app_name: '',
    api_provider: '',
  });
  const [createMapForm, setCreateMapForm] = useState<ActionMapCreateInput>({
    map_id: '',
    title: '',
    description: '',
    nodes: [],
    edges: [],
  });
  const [skillFormError, setSkillFormError] = useState<string>('');
  const [mapFormError, setMapFormError] = useState<string>('');
  const [isSavingSkill, setIsSavingSkill] = useState(false);
  const [isSavingMap, setIsSavingMap] = useState(false);
  const [isCreatingSkill, setIsCreatingSkill] = useState(false);
  const [isCreatingMap, setIsCreatingMap] = useState(false);
  const [connectTargetId, setConnectTargetId] = useState<string>('');
  const canvasRef = useRef<HTMLDivElement | null>(null);
  const [dragState, setDragState] = useState<{
    nodeId: string;
    startX: number;
    startY: number;
    originX: number;
    originY: number;
  } | null>(null);

  const skills = catalog?.skills || [];
  const categories = catalog?.categories || [];

  const filteredSkills = useMemo(() => {
    if (selectedCategory === 'all') return skills;
    return skills.filter((skill) => skill.categories.includes(selectedCategory));
  }, [selectedCategory, skills]);

  const selectedSkill = useMemo(
    () => filteredSkills.find((skill) => skill.skill_id === selectedSkillId) || skills.find((skill) => skill.skill_id === selectedSkillId) || null,
    [filteredSkills, selectedSkillId, skills]
  );
  const selectedActionMap = useMemo(
    () => actionMaps.find((actionMap) => actionMap.map_id === selectedMapId) || null,
    [actionMaps, selectedMapId]
  );
  const selectedNode = useMemo(
    () => mapForm?.nodes.find((node) => node.node_id === selectedNodeId) || null,
    [mapForm, selectedNodeId]
  );

  useEffect(() => {
    if (!selectedSkillId && skills[0]) {
      setSelectedSkillId(skills[0].skill_id);
    }
  }, [selectedSkillId, skills]);

  useEffect(() => {
    if (selectedSkill) {
      setSkillForm(skillFormFromCard(selectedSkill));
      setSkillFormError('');
    }
  }, [selectedSkill]);

  useEffect(() => {
    if (!selectedMapId && actionMaps[0]) {
      setSelectedMapId(actionMaps[0].map_id);
    }
  }, [actionMaps, selectedMapId]);

  useEffect(() => {
    if (selectedActionMap) {
      setMapForm(mapFormFromMap(selectedActionMap));
      const firstNode = selectedActionMap.nodes[0];
      setSelectedNodeId(firstNode ? firstNode.node_id : '');
      setMapFormError('');
    }
  }, [selectedActionMap]);

  useEffect(() => {
    if (!dragState || !mapForm) return;
    const handleMove = (event: MouseEvent) => {
      setMapForm((current) => {
        if (!current) return current;
        return {
          ...current,
          nodes: current.nodes.map((node) =>
            node.node_id === dragState.nodeId
              ? {
                  ...node,
                  x: Math.max(16, dragState.originX + (event.clientX - dragState.startX)),
                  y: Math.max(16, dragState.originY + (event.clientY - dragState.startY)),
                }
              : node
          ),
        };
      });
    };
    const handleUp = () => setDragState(null);
    window.addEventListener('mousemove', handleMove);
    window.addEventListener('mouseup', handleUp);
    return () => {
      window.removeEventListener('mousemove', handleMove);
      window.removeEventListener('mouseup', handleUp);
    };
  }, [dragState, mapForm]);

  const handleSaveSkill = async () => {
    if (!selectedSkill || !skillForm) return;
    setSkillFormError('');
    setIsSavingSkill(true);
    try {
      const payload = payloadFromSkillForm(skillForm);
      await onSaveSkill(selectedSkill.skill_id, payload);
    } catch (error) {
      setSkillFormError(error instanceof Error ? error.message : 'Skill save failed');
    } finally {
      setIsSavingSkill(false);
    }
  };

  const handleCreateSkill = async () => {
    if (!createSkillForm.skill_id.trim()) return;
    setSkillFormError('');
    setIsCreatingSkill(true);
    try {
      await onCreateSkill(createSkillForm);
      setCreateSkillForm({
        skill_id: '',
        title: '',
        summary: '',
        local_app_name: '',
        api_provider: '',
      });
    } catch (error) {
      setSkillFormError(error instanceof Error ? error.message : 'Skill create failed');
    } finally {
      setIsCreatingSkill(false);
    }
  };

  const handleSaveMap = async () => {
    if (!selectedActionMap || !mapForm) return;
    setMapFormError('');
    setIsSavingMap(true);
    try {
      await onSaveActionMap(selectedActionMap.map_id, payloadFromMapForm(mapForm));
    } catch (error) {
      setMapFormError(error instanceof Error ? error.message : 'Action map save failed');
    } finally {
      setIsSavingMap(false);
    }
  };

  const handleCreateMap = async () => {
    if (!createMapForm.map_id.trim()) return;
    setMapFormError('');
    setIsCreatingMap(true);
    try {
      await onCreateActionMap(createMapForm);
      setCreateMapForm({
        map_id: '',
        title: '',
        description: '',
        nodes: [],
        edges: [],
      });
    } catch (error) {
      setMapFormError(error instanceof Error ? error.message : 'Action map create failed');
    } finally {
      setIsCreatingMap(false);
    }
  };

  const addNodeToMap = () => {
    if (!mapForm || skills.length === 0) return;
    const defaultSkill = selectedSkill || skills[0];
    if (!defaultSkill) return;
    const nextIndex = mapForm.nodes.length;
    const newNode: ActionMapNode = {
      node_id: `node_${Math.random().toString(36).slice(2, 8)}`,
      skill_id: defaultSkill.skill_id,
      title: defaultSkill.title,
      x: 32 + (nextIndex % 3) * 250,
      y: 32 + Math.floor(nextIndex / 3) * 120,
      config: {},
    };
    setMapForm({
      ...mapForm,
      nodes: [...mapForm.nodes, newNode],
    });
    setSelectedNodeId(newNode.node_id);
  };

  const connectSelectedNode = () => {
    if (!mapForm || !selectedNode || !connectTargetId || selectedNode.node_id === connectTargetId) return;
    const duplicate = mapForm.edges.some((edge) => edge.source === selectedNode.node_id && edge.target === connectTargetId);
    if (duplicate) return;
    setMapForm({
      ...mapForm,
      edges: [
        ...mapForm.edges,
        {
          edge_id: `edge_${Math.random().toString(36).slice(2, 8)}`,
          source: selectedNode.node_id,
          target: connectTargetId,
          label: '',
        },
      ],
    });
    setConnectTargetId('');
  };

  const removeSelectedNode = () => {
    if (!mapForm || !selectedNode) return;
    setMapForm({
      ...mapForm,
      nodes: mapForm.nodes.filter((node) => node.node_id !== selectedNode.node_id),
      edges: mapForm.edges.filter((edge) => edge.source !== selectedNode.node_id && edge.target !== selectedNode.node_id),
    });
    setSelectedNodeId('');
  };

  const updateSelectedNode = (patch: Partial<ActionMapNode>) => {
    if (!mapForm || !selectedNode) return;
    setMapForm({
      ...mapForm,
      nodes: mapForm.nodes.map((node) => (node.node_id === selectedNode.node_id ? { ...node, ...patch } : node)),
    });
  };

  return (
    <div className="flex h-full flex-col overflow-hidden bg-surface">
      <div className="flex h-14 shrink-0 items-center justify-between border-b border-white/5 bg-surface-container-low px-6">
        <div className="flex items-center gap-4">
          <h1 className="text-lg font-semibold tracking-tight text-on-surface">
            Skills & Action Maps
            <span className={cn('ml-3 font-mono text-xs', backendStatus === 'online' ? 'text-secondary' : backendStatus === 'checking' ? 'text-primary' : 'text-[#ffb4ab]')}>
              {backendStatus.toUpperCase()}
            </span>
          </h1>
          <div className="hidden gap-2 md:flex">
            <button
              onClick={() => setActiveTab('registry')}
              className={cn(
                'px-3 py-2 text-[11px] font-semibold uppercase tracking-[0.12em]',
                activeTab === 'registry' ? 'bg-secondary text-[#003909]' : 'bg-surface-container-high text-on-surface-variant'
              )}
            >
              Skill Registry
            </button>
            <button
              onClick={() => setActiveTab('action_maps')}
              className={cn(
                'px-3 py-2 text-[11px] font-semibold uppercase tracking-[0.12em]',
                activeTab === 'action_maps' ? 'bg-secondary text-[#003909]' : 'bg-surface-container-high text-on-surface-variant'
              )}
            >
              Action Maps
            </button>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => void onRefreshSkills()}
            className="inline-flex items-center gap-2 bg-surface-container-highest px-3 py-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-on-surface"
          >
            <RefreshCw size={14} />
            Skills
          </button>
          <button
            onClick={() => void onRefreshActionMaps()}
            className="inline-flex items-center gap-2 bg-surface-container-highest px-3 py-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-on-surface"
          >
            <RefreshCw size={14} />
            Maps
          </button>
        </div>
      </div>

      {activeTab === 'registry' ? (
        <div className="grid min-h-0 flex-1 grid-cols-1 gap-2 overflow-hidden p-4 xl:grid-cols-[260px_minmax(0,1fr)_360px]">
          <aside className="min-h-0 overflow-y-auto border border-white/5 bg-surface-container-low p-4 custom-scrollbar">
            <div className="mb-4">
              <div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-on-surface-variant">Registry Summary</div>
              <div className="mt-3 grid gap-2">
                <div className="border border-white/5 bg-surface-container p-3">
                  <div className="text-[10px] uppercase tracking-[0.12em] text-on-surface-variant">Skills</div>
                  <div className="mt-2 font-mono text-xl text-secondary">{catalog?.skill_count || 0}</div>
                </div>
                <div className="border border-white/5 bg-surface-container p-3">
                  <div className="text-[10px] uppercase tracking-[0.12em] text-on-surface-variant">Implemented Intents</div>
                  <div className="mt-2 font-mono text-xl text-primary">{catalog?.implemented_intent_count || 0}</div>
                </div>
                <div className="border border-white/5 bg-surface-container p-3">
                  <div className="text-[10px] uppercase tracking-[0.12em] text-on-surface-variant">Backlog</div>
                  <div className="mt-2 font-mono text-xl text-tertiary">{catalog?.backlog.length || 0}</div>
                </div>
              </div>
            </div>

            <div className="mb-4">
              <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-on-surface-variant">Categories</div>
              <button
                onClick={() => setSelectedCategory('all')}
                className={cn(
                  'mb-2 w-full border px-3 py-2 text-left text-xs',
                  selectedCategory === 'all' ? 'border-secondary bg-surface-container text-on-surface' : 'border-white/5 bg-surface-container-lowest text-on-surface-variant'
                )}
              >
                All Skills ({skills.length})
              </button>
              <div className="space-y-2">
                {categories.map((category) => (
                  <button
                    key={category.category}
                    onClick={() => setSelectedCategory(category.category)}
                    className={cn(
                      'w-full border px-3 py-2 text-left text-xs',
                      selectedCategory === category.category ? 'border-secondary bg-surface-container text-on-surface' : 'border-white/5 bg-surface-container-lowest text-on-surface-variant'
                    )}
                  >
                    <div className="font-medium">{category.category}</div>
                    <div className="mt-1 font-mono text-[11px]">{category.count} cards</div>
                  </button>
                ))}
              </div>
            </div>

            <div>
              <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-on-surface-variant">Unmapped Backlog</div>
              <div className="space-y-2">
                {catalog?.backlog.slice(0, 10).map((item) => (
                  <div key={item.query_key} className="border border-white/5 bg-surface-container-lowest p-3">
                    <div className="text-xs font-medium text-on-surface">{item.query_text}</div>
                    <div className="mt-1 flex items-center justify-between font-mono text-[11px] text-on-surface-variant">
                      <span>{item.occurrence_count} hits</span>
                      <span>{formatDateTime(item.last_seen_at)}</span>
                    </div>
                    <div className="mt-2 text-[11px] leading-relaxed text-outline">
                      intent: {item.inferred_intent || 'unmapped'}
                    </div>
                  </div>
                ))}
                {!catalog?.backlog.length && (
                  <div className="border border-dashed border-white/10 p-3 text-xs text-on-surface-variant">
                    아직 backlog가 없습니다.
                  </div>
                )}
              </div>
            </div>
          </aside>

          <section className="min-h-0 overflow-y-auto border border-white/5 bg-surface-container-low p-4 custom-scrollbar">
            <div className="mb-4 grid gap-2 xl:grid-cols-[1.1fr_1fr]">
              <div className="border border-white/5 bg-surface-container p-4">
                <div className="mb-3 text-[11px] font-semibold uppercase tracking-[0.12em] text-on-surface-variant">Create Custom Skill</div>
                <div className="grid gap-2 md:grid-cols-2">
                  <input
                    value={createSkillForm.skill_id}
                    onChange={(event) => setCreateSkillForm({ ...createSkillForm, skill_id: event.target.value })}
                    className="bg-surface-container-lowest px-3 py-2 text-sm text-on-surface outline-none placeholder:text-outline"
                    placeholder="skill_id e.g. spotify"
                  />
                  <input
                    value={createSkillForm.title || ''}
                    onChange={(event) => setCreateSkillForm({ ...createSkillForm, title: event.target.value })}
                    className="bg-surface-container-lowest px-3 py-2 text-sm text-on-surface outline-none placeholder:text-outline"
                    placeholder="Display title"
                  />
                  <input
                    value={createSkillForm.local_app_name || ''}
                    onChange={(event) => setCreateSkillForm({ ...createSkillForm, local_app_name: event.target.value })}
                    className="bg-surface-container-lowest px-3 py-2 text-sm text-on-surface outline-none placeholder:text-outline"
                    placeholder="Local app name"
                  />
                  <input
                    value={createSkillForm.api_provider || ''}
                    onChange={(event) => setCreateSkillForm({ ...createSkillForm, api_provider: event.target.value })}
                    className="bg-surface-container-lowest px-3 py-2 text-sm text-on-surface outline-none placeholder:text-outline"
                    placeholder="API provider"
                  />
                </div>
                <textarea
                  value={createSkillForm.summary || ''}
                  onChange={(event) => setCreateSkillForm({ ...createSkillForm, summary: event.target.value })}
                  className="mt-2 min-h-20 w-full resize-none bg-surface-container-lowest px-3 py-2 text-sm text-on-surface outline-none placeholder:text-outline"
                  placeholder="Skill summary"
                />
                <div className="mt-3 flex justify-end">
                  <button
                    onClick={() => void handleCreateSkill()}
                    disabled={isCreatingSkill}
                    className="inline-flex items-center gap-2 bg-secondary px-3 py-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-[#003909]"
                  >
                    <Plus size={14} />
                    {isCreatingSkill ? 'Creating' : 'Create Skill'}
                  </button>
                </div>
              </div>

              <div className="border border-white/5 bg-surface-container p-4">
                <div className="mb-3 text-[11px] font-semibold uppercase tracking-[0.12em] text-on-surface-variant">Spotify Example</div>
                <div className="space-y-3 text-sm leading-relaxed text-on-surface-variant">
                  <div className="flex items-start gap-3">
                    <AppWindow size={16} className="mt-0.5 text-secondary" />
                    <div>앱만 설치돼 있어도 기본 open skill을 카드에 기록할 수 있습니다.</div>
                  </div>
                  <div className="flex items-start gap-3">
                    <Cloud size={16} className="mt-0.5 text-primary" />
                    <div>API provider, scopes, notes를 적어두면 재생/검색/플레이리스트 같은 세부 제어 준비 상태를 같이 관리할 수 있습니다.</div>
                  </div>
                  <div className="flex items-start gap-3">
                    <Workflow size={16} className="mt-0.5 text-tertiary" />
                    <div>저장된 skill은 Action Map 탭에서 바로 노드로 연결해 복합 자동화로 묶을 수 있습니다.</div>
                  </div>
                </div>
              </div>
            </div>

            {catalogLoading ? (
              <div className="flex h-40 items-center justify-center text-sm text-on-surface-variant">Loading skill catalog...</div>
            ) : catalogError ? (
              <div className="border border-[#ffb4ab]/20 bg-[#3b1210] p-4 text-sm text-[#ffdad6]">{catalogError}</div>
            ) : (
              <div className="grid gap-3 md:grid-cols-2 2xl:grid-cols-3">
                {filteredSkills.map((skill) => (
                  <button
                    key={skill.skill_id}
                    onClick={() => setSelectedSkillId(skill.skill_id)}
                    className={cn(
                      'border p-4 text-left transition',
                      selectedSkillId === skill.skill_id
                        ? 'border-secondary bg-surface-container'
                        : 'border-white/5 bg-surface-container-lowest hover:border-white/15'
                    )}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="text-sm font-semibold text-on-surface">{skill.title}</div>
                        <div className="mt-1 font-mono text-[11px] text-outline">{skill.skill_id}</div>
                      </div>
                      <span className="bg-surface px-2 py-1 text-[10px] uppercase tracking-[0.12em] text-tertiary">
                        {skill.source_kind}
                      </span>
                    </div>
                    <div className="mt-3 line-clamp-3 min-h-12 text-xs leading-relaxed text-on-surface-variant">
                      {skill.summary || '등록된 intent와 integration detail을 기반으로 skill을 관리합니다.'}
                    </div>
                    <div className="mt-3 flex flex-wrap gap-1">
                      {skill.implementation_statuses.slice(0, 2).map((status) => (
                        <span key={status} className="bg-surface px-2 py-1 text-[10px] font-mono text-on-surface-variant">
                          {status}
                        </span>
                      ))}
                      {skill.local_app_name ? (
                        <span className={cn('px-2 py-1 text-[10px] font-mono', skill.effective_local_app_installed ? 'bg-secondary-container/35 text-secondary' : 'bg-surface text-outline')}>
                          app:{skill.local_app_name}
                        </span>
                      ) : null}
                      {skill.api_provider ? (
                        <span className={cn('px-2 py-1 text-[10px] font-mono', skill.api_configured ? 'bg-primary/20 text-primary' : 'bg-surface text-outline')}>
                          api:{skill.api_provider}
                        </span>
                      ) : null}
                    </div>
                    <div className="mt-3 text-[11px] text-outline">
                      intents {skill.linked_intents.length} · examples {skill.example_queries.length}
                    </div>
                  </button>
                ))}
              </div>
            )}
          </section>

          <aside className="min-h-0 overflow-y-auto border border-white/5 bg-surface-container-low p-4 custom-scrollbar">
            <div className="mb-4 flex items-center justify-between">
              <div>
                <div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-on-surface-variant">Skill Details</div>
                <div className="mt-1 font-mono text-[11px] text-outline">{selectedSkill?.skill_id || 'No selection'}</div>
              </div>
              <button
                onClick={() => void handleSaveSkill()}
                disabled={!selectedSkill || !skillForm || isSavingSkill}
                className="inline-flex items-center gap-2 bg-secondary px-3 py-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-[#003909]"
              >
                <Save size={14} />
                {isSavingSkill ? 'Saving' : 'Save'}
              </button>
            </div>

            {selectedSkill && skillForm ? (
              <div className="space-y-3">
                <input
                  value={skillForm.title}
                  onChange={(event) => setSkillForm({ ...skillForm, title: event.target.value })}
                  className="w-full bg-surface-container-lowest px-3 py-2 text-sm text-on-surface outline-none"
                  placeholder="Title"
                />
                <input
                  value={skillForm.parent_skill_id}
                  onChange={(event) => setSkillForm({ ...skillForm, parent_skill_id: event.target.value })}
                  className="w-full bg-surface-container-lowest px-3 py-2 text-sm text-on-surface outline-none"
                  placeholder="Parent skill id"
                />
                <textarea
                  value={skillForm.summary}
                  onChange={(event) => setSkillForm({ ...skillForm, summary: event.target.value })}
                  className="min-h-20 w-full resize-none bg-surface-container-lowest px-3 py-2 text-sm text-on-surface outline-none"
                  placeholder="Summary"
                />
                <div className="grid gap-2 md:grid-cols-2">
                  <input
                    value={skillForm.local_app_name}
                    onChange={(event) => setSkillForm({ ...skillForm, local_app_name: event.target.value })}
                    className="bg-surface-container-lowest px-3 py-2 text-sm text-on-surface outline-none"
                    placeholder="Local app"
                  />
                  <input
                    value={skillForm.launch_target}
                    onChange={(event) => setSkillForm({ ...skillForm, launch_target: event.target.value })}
                    className="bg-surface-container-lowest px-3 py-2 text-sm text-on-surface outline-none"
                    placeholder="Launch target"
                  />
                </div>
                <div className="grid gap-2 md:grid-cols-2">
                  <select
                    value={skillForm.local_app_installed}
                    onChange={(event) => setSkillForm({ ...skillForm, local_app_installed: event.target.value as InstalledMode })}
                    className="bg-surface-container-lowest px-3 py-2 text-sm text-on-surface outline-none"
                  >
                    <option value="auto">Install Status: Auto Detect</option>
                    <option value="yes">Installed</option>
                    <option value="no">Not Installed</option>
                  </select>
                  <label className="flex items-center gap-2 bg-surface-container-lowest px-3 py-2 text-sm text-on-surface">
                    <input
                      type="checkbox"
                      checked={skillForm.open_supported}
                      onChange={(event) => setSkillForm({ ...skillForm, open_supported: event.target.checked })}
                    />
                    Open Supported
                  </label>
                </div>
                <textarea
                  value={skillForm.local_notes}
                  onChange={(event) => setSkillForm({ ...skillForm, local_notes: event.target.value })}
                  className="min-h-16 w-full resize-none bg-surface-container-lowest px-3 py-2 text-sm text-on-surface outline-none"
                  placeholder="Local integration notes"
                />
                <div className="grid gap-2 md:grid-cols-2">
                  <input
                    value={skillForm.api_provider}
                    onChange={(event) => setSkillForm({ ...skillForm, api_provider: event.target.value })}
                    className="bg-surface-container-lowest px-3 py-2 text-sm text-on-surface outline-none"
                    placeholder="API provider"
                  />
                  <label className="flex items-center gap-2 bg-surface-container-lowest px-3 py-2 text-sm text-on-surface">
                    <input
                      type="checkbox"
                      checked={skillForm.api_configured}
                      onChange={(event) => setSkillForm({ ...skillForm, api_configured: event.target.checked })}
                    />
                    API Configured
                  </label>
                </div>
                <input
                  value={skillForm.api_scopes}
                  onChange={(event) => setSkillForm({ ...skillForm, api_scopes: event.target.value })}
                  className="w-full bg-surface-container-lowest px-3 py-2 text-sm text-on-surface outline-none"
                  placeholder="API scopes, comma separated"
                />
                <textarea
                  value={skillForm.api_notes}
                  onChange={(event) => setSkillForm({ ...skillForm, api_notes: event.target.value })}
                  className="min-h-16 w-full resize-none bg-surface-container-lowest px-3 py-2 text-sm text-on-surface outline-none"
                  placeholder="API notes"
                />
                <input
                  value={skillForm.tags}
                  onChange={(event) => setSkillForm({ ...skillForm, tags: event.target.value })}
                  className="w-full bg-surface-container-lowest px-3 py-2 text-sm text-on-surface outline-none"
                  placeholder="Tags, comma separated"
                />
                <input
                  value={skillForm.linked_intents}
                  onChange={(event) => setSkillForm({ ...skillForm, linked_intents: event.target.value })}
                  className="w-full bg-surface-container-lowest px-3 py-2 text-sm text-on-surface outline-none"
                  placeholder="Linked intents, comma separated"
                />
                <textarea
                  value={skillForm.notes}
                  onChange={(event) => setSkillForm({ ...skillForm, notes: event.target.value })}
                  className="min-h-16 w-full resize-none bg-surface-container-lowest px-3 py-2 text-sm text-on-surface outline-none"
                  placeholder="General notes"
                />
                <textarea
                  value={skillForm.custom_fields}
                  onChange={(event) => setSkillForm({ ...skillForm, custom_fields: event.target.value })}
                  className="min-h-28 w-full resize-none bg-surface-container-lowest px-3 py-2 font-mono text-[12px] text-on-surface outline-none"
                  placeholder='Custom fields JSON, e.g. {"playlist_scope":"required"}'
                />
                <div className="border border-white/5 bg-surface-container-lowest p-3 text-xs text-on-surface-variant">
                  <div>Detected install: {selectedSkill.detected_local_app_installed ? 'yes' : 'no'}</div>
                  <div className="mt-1">Updated: {formatDateTime(selectedSkill.updated_at)}</div>
                </div>
                {skillFormError ? (
                  <div className="border border-[#ffb4ab]/20 bg-[#3b1210] p-3 text-xs text-[#ffdad6]">{skillFormError}</div>
                ) : null}
              </div>
            ) : (
              <div className="flex h-40 items-center justify-center text-sm text-on-surface-variant">
                Select a skill card.
              </div>
            )}
          </aside>
        </div>
      ) : (
        <div className="grid min-h-0 flex-1 grid-cols-1 gap-2 overflow-hidden p-4 xl:grid-cols-[280px_minmax(0,1fr)_320px]">
          <aside className="min-h-0 overflow-y-auto border border-white/5 bg-surface-container-low p-4 custom-scrollbar">
            <div className="mb-4">
              <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-on-surface-variant">Create Action Map</div>
              <input
                value={createMapForm.map_id}
                onChange={(event) => setCreateMapForm({ ...createMapForm, map_id: event.target.value })}
                className="mb-2 w-full bg-surface-container-lowest px-3 py-2 text-sm text-on-surface outline-none"
                placeholder="map_id e.g. morning_brief"
              />
              <input
                value={createMapForm.title || ''}
                onChange={(event) => setCreateMapForm({ ...createMapForm, title: event.target.value })}
                className="mb-2 w-full bg-surface-container-lowest px-3 py-2 text-sm text-on-surface outline-none"
                placeholder="Map title"
              />
              <textarea
                value={createMapForm.description || ''}
                onChange={(event) => setCreateMapForm({ ...createMapForm, description: event.target.value })}
                className="min-h-20 w-full resize-none bg-surface-container-lowest px-3 py-2 text-sm text-on-surface outline-none"
                placeholder="What this action map does"
              />
              <button
                onClick={() => void handleCreateMap()}
                disabled={isCreatingMap}
                className="mt-3 inline-flex items-center gap-2 bg-secondary px-3 py-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-[#003909]"
              >
                <Plus size={14} />
                {isCreatingMap ? 'Creating' : 'Create Map'}
              </button>
            </div>

            <div>
              <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-on-surface-variant">Saved Maps</div>
              <div className="space-y-2">
                {actionMaps.map((item) => (
                  <button
                    key={item.map_id}
                    onClick={() => setSelectedMapId(item.map_id)}
                    className={cn(
                      'w-full border p-3 text-left',
                      selectedMapId === item.map_id ? 'border-secondary bg-surface-container' : 'border-white/5 bg-surface-container-lowest'
                    )}
                  >
                    <div className="text-sm font-medium text-on-surface">{item.title}</div>
                    <div className="mt-1 font-mono text-[11px] text-outline">{item.map_id}</div>
                    <div className="mt-2 text-xs text-on-surface-variant">
                      nodes {item.nodes.length} · edges {item.edges.length}
                    </div>
                  </button>
                ))}
                {!actionMaps.length && !actionMapsLoading && (
                  <div className="border border-dashed border-white/10 p-3 text-xs text-on-surface-variant">
                    아직 저장된 action map이 없습니다.
                  </div>
                )}
              </div>
            </div>
          </aside>

          <section className="flex min-h-0 flex-col overflow-hidden border border-white/5 bg-surface-container-low">
            <div className="flex h-12 shrink-0 items-center justify-between border-b border-white/5 px-4">
              <div className="flex items-center gap-3">
                <GitBranch size={16} className="text-secondary" />
                <div>
                  <div className="text-sm font-semibold text-on-surface">{selectedActionMap?.title || 'Action Map Canvas'}</div>
                  <div className="font-mono text-[11px] text-outline">{selectedActionMap?.map_id || 'No selection'}</div>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={addNodeToMap}
                  disabled={!mapForm || skills.length === 0}
                  className="inline-flex items-center gap-2 bg-surface-container-highest px-3 py-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-on-surface"
                >
                  <Plus size={14} />
                  Add Node
                </button>
                <button
                  onClick={() => void handleSaveMap()}
                  disabled={!selectedActionMap || !mapForm || isSavingMap}
                  className="inline-flex items-center gap-2 bg-secondary px-3 py-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-[#003909]"
                >
                  <Save size={14} />
                  {isSavingMap ? 'Saving' : 'Save Map'}
                </button>
              </div>
            </div>

            {actionMapsLoading ? (
              <div className="flex flex-1 items-center justify-center text-sm text-on-surface-variant">Loading action maps...</div>
            ) : actionMapsError ? (
              <div className="m-4 border border-[#ffb4ab]/20 bg-[#3b1210] p-4 text-sm text-[#ffdad6]">{actionMapsError}</div>
            ) : mapForm ? (
              <div ref={canvasRef} className="relative flex-1 overflow-auto bg-[radial-gradient(circle_at_center,rgba(255,255,255,0.04)_1px,transparent_1px)] [background-size:24px_24px]">
                <svg className="pointer-events-none absolute inset-0 h-full w-full">
                  {mapForm.edges.map((edge) => {
                    const source = mapForm.nodes.find((node) => node.node_id === edge.source);
                    const target = mapForm.nodes.find((node) => node.node_id === edge.target);
                    if (!source || !target) return null;
                    const x1 = source.x + NODE_WIDTH / 2;
                    const y1 = source.y + NODE_HEIGHT / 2;
                    const x2 = target.x + NODE_WIDTH / 2;
                    const y2 = target.y + NODE_HEIGHT / 2;
                    return (
                      <g key={edge.edge_id}>
                        <line x1={x1} y1={y1} x2={x2} y2={y2} stroke="rgba(137,207,140,0.7)" strokeWidth="2" />
                        {edge.label ? (
                          <text x={(x1 + x2) / 2} y={(y1 + y2) / 2 - 6} fill="rgba(221,228,215,0.72)" fontSize="10" textAnchor="middle">
                            {edge.label}
                          </text>
                        ) : null}
                      </g>
                    );
                  })}
                </svg>

                {mapForm.nodes.map((node) => (
                  <button
                    key={node.node_id}
                    onMouseDown={(event) => {
                      event.preventDefault();
                      setSelectedNodeId(node.node_id);
                      setDragState({
                        nodeId: node.node_id,
                        startX: event.clientX,
                        startY: event.clientY,
                        originX: node.x,
                        originY: node.y,
                      });
                    }}
                    onClick={() => setSelectedNodeId(node.node_id)}
                    className={cn(
                      'absolute border p-4 text-left shadow-[0_10px_30px_rgba(0,0,0,0.22)]',
                      selectedNodeId === node.node_id ? 'border-secondary bg-surface-container' : 'border-white/10 bg-surface-container-lowest'
                    )}
                    style={{ left: node.x, top: node.y, width: NODE_WIDTH, height: NODE_HEIGHT }}
                  >
                    <div className="text-sm font-semibold text-on-surface">{node.title}</div>
                    <div className="mt-1 font-mono text-[11px] text-outline">{node.skill_id}</div>
                    <div className="mt-2 flex items-center gap-2 text-[11px] text-on-surface-variant">
                      <Link2 size={12} />
                      {mapForm.edges.filter((edge) => edge.source === node.node_id || edge.target === node.node_id).length} links
                    </div>
                  </button>
                ))}
              </div>
            ) : (
              <div className="flex flex-1 items-center justify-center text-sm text-on-surface-variant">
                Select or create an action map.
              </div>
            )}
          </section>

          <aside className="min-h-0 overflow-y-auto border border-white/5 bg-surface-container-low p-4 custom-scrollbar">
            {selectedActionMap && mapForm ? (
              <div className="space-y-4">
                <div>
                  <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-on-surface-variant">Map Metadata</div>
                  <input
                    value={mapForm.title}
                    onChange={(event) => setMapForm({ ...mapForm, title: event.target.value })}
                    className="mb-2 w-full bg-surface-container-lowest px-3 py-2 text-sm text-on-surface outline-none"
                    placeholder="Map title"
                  />
                  <input
                    value={mapForm.trigger_query}
                    onChange={(event) => setMapForm({ ...mapForm, trigger_query: event.target.value })}
                    className="mb-2 w-full bg-surface-container-lowest px-3 py-2 text-sm text-on-surface outline-none"
                    placeholder="Trigger query"
                  />
                  <input
                    value={mapForm.tags}
                    onChange={(event) => setMapForm({ ...mapForm, tags: event.target.value })}
                    className="mb-2 w-full bg-surface-container-lowest px-3 py-2 text-sm text-on-surface outline-none"
                    placeholder="Tags, comma separated"
                  />
                  <textarea
                    value={mapForm.description}
                    onChange={(event) => setMapForm({ ...mapForm, description: event.target.value })}
                    className="mb-2 min-h-16 w-full resize-none bg-surface-container-lowest px-3 py-2 text-sm text-on-surface outline-none"
                    placeholder="Description"
                  />
                  <textarea
                    value={mapForm.notes}
                    onChange={(event) => setMapForm({ ...mapForm, notes: event.target.value })}
                    className="min-h-20 w-full resize-none bg-surface-container-lowest px-3 py-2 text-sm text-on-surface outline-none"
                    placeholder="Execution notes"
                  />
                </div>

                <div>
                  <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-on-surface-variant">Selected Node</div>
                  {selectedNode ? (
                    <div className="space-y-2">
                      <select
                        value={selectedNode.skill_id}
                        onChange={(event) => {
                          const nextSkill = skills.find((skill) => skill.skill_id === event.target.value);
                          updateSelectedNode({
                            skill_id: event.target.value,
                            title: nextSkill?.title || event.target.value,
                          });
                        }}
                        className="w-full bg-surface-container-lowest px-3 py-2 text-sm text-on-surface outline-none"
                      >
                        {skills.map((skill) => (
                          <option key={skill.skill_id} value={skill.skill_id}>{skill.title}</option>
                        ))}
                      </select>
                      <input
                        value={selectedNode.title}
                        onChange={(event) => updateSelectedNode({ title: event.target.value })}
                        className="w-full bg-surface-container-lowest px-3 py-2 text-sm text-on-surface outline-none"
                        placeholder="Node title"
                      />
                      <textarea
                        value={JSON.stringify(selectedNode.config || {}, null, 2)}
                        onChange={(event) => {
                          try {
                            updateSelectedNode({ config: JSON.parse(event.target.value || '{}') as Record<string, string> });
                            setMapFormError('');
                          } catch {
                            setMapFormError('Node config must be valid JSON.');
                          }
                        }}
                        className="min-h-24 w-full resize-none bg-surface-container-lowest px-3 py-2 font-mono text-[12px] text-on-surface outline-none"
                        placeholder='{"playlist":"focus"}'
                      />
                      <div className="border border-white/5 bg-surface-container-lowest p-3 text-[11px] leading-relaxed text-on-surface-variant">
                        <span className="font-mono text-outline">{'{"mode":"api"}'}</span>
                        {' '}로 API 단계,
                        {' '}
                        <span className="font-mono text-outline">{'{"launch_target":"Spotify"}'}</span>
                        {' '}또는 URL로 실행 대상을 덮어쓸 수 있습니다.
                      </div>
                      <div className="grid gap-2 md:grid-cols-[1fr_auto]">
                        <select
                          value={connectTargetId}
                          onChange={(event) => setConnectTargetId(event.target.value)}
                          className="bg-surface-container-lowest px-3 py-2 text-sm text-on-surface outline-none"
                        >
                          <option value="">Connect to node...</option>
                          {mapForm.nodes
                            .filter((node) => node.node_id !== selectedNode.node_id)
                            .map((node) => (
                              <option key={node.node_id} value={node.node_id}>{node.title}</option>
                            ))}
                        </select>
                        <button
                          onClick={connectSelectedNode}
                          className="inline-flex items-center gap-2 bg-surface-container-highest px-3 py-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-on-surface"
                        >
                          <Link2 size={14} />
                          Connect
                        </button>
                      </div>
                      <button
                        onClick={removeSelectedNode}
                        className="w-full bg-[#3b1210] px-3 py-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-[#ffdad6]"
                      >
                        Remove Node
                      </button>
                    </div>
                  ) : (
                    <div className="border border-dashed border-white/10 p-3 text-xs text-on-surface-variant">
                      캔버스에서 노드를 선택하세요.
                    </div>
                  )}
                </div>

                <div>
                  <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-on-surface-variant">Skill Links</div>
                  <div className="space-y-2">
                    {mapForm.edges.map((edge) => (
                      <div key={edge.edge_id} className="flex items-center justify-between border border-white/5 bg-surface-container-lowest px-3 py-2 text-xs text-on-surface">
                        <span>{edge.source} → {edge.target}</span>
                        <button
                          onClick={() => setMapForm({ ...mapForm, edges: mapForm.edges.filter((item) => item.edge_id !== edge.edge_id) })}
                          className="text-outline hover:text-on-surface"
                        >
                          remove
                        </button>
                      </div>
                    ))}
                    {!mapForm.edges.length && (
                      <div className="border border-dashed border-white/10 p-3 text-xs text-on-surface-variant">
                        아직 연결된 edge가 없습니다.
                      </div>
                    )}
                  </div>
                </div>

                {mapFormError ? (
                  <div className="border border-[#ffb4ab]/20 bg-[#3b1210] p-3 text-xs text-[#ffdad6]">{mapFormError}</div>
                ) : null}
              </div>
            ) : (
              <div className="flex h-40 items-center justify-center text-sm text-on-surface-variant">
                Select an action map.
              </div>
            )}
          </aside>
        </div>
      )}
    </div>
  );
};
