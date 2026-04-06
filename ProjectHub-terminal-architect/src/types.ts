export type AnswerKind =
  | 'utility_result'
  | 'action_result'
  | 'live_data_result'
  | 'retrieval_result'
  | 'capability_gap';

// ── Chat ──────────────────────────────────────
export interface Message {
  id: string;
  role: 'operator' | 'architect';
  timestamp: string;
  content: string;
  citations?: Citation[];
  has_evidence?: boolean;
  answer_kind?: AnswerKind;
  task_id?: string;
  structured_payload?: Record<string, unknown> | null;
}

// ── Citation / Evidence ───────────────────────
export interface Citation {
  label: string;
  source_path: string;
  full_source_path: string;
  source_type: string;
  quote: string;
  state?: string;
  relevance_score: number;
  heading_path?: string;
}

// ── Asset (legacy demo cards) ─────────────────
export interface Asset {
  id: string;
  type: 'pdf' | 'image' | 'docx' | 'hwp' | 'html';
  name: string;
  size?: string;
  status?: string;
  description?: string;
  matchPrecision?: string;
  imageUrl?: string;
  content?: string;
}

// ── Artifact (JARVIS backend response) ────────
export interface Artifact {
  id: string;
  type: string;
  title: string;
  subtitle: string;
  path: string;
  full_path: string;
  preview: string;
  source_type: string;
  viewer_kind: string;
}

// ── Guide Directive ───────────────────────────
export interface GuideDirective {
  intent?: string;
  skill?: string;
  loop_stage: string;
  clarification_prompt: string;
  suggested_replies: string[];
  clarification_options?: string[];
  missing_slots: string[];
  clarification_reasons?: string[];
  should_hold?: boolean;
  has_clarification: boolean;
  interaction_mode?: string;
  exploration_mode?: string;
  target_file?: string;
  target_document?: string;
  ui_hints?: {
    show_documents: boolean;
    show_repository: boolean;
    show_inspector: boolean;
    preferred_view?: string;
  };
  presentation: Presentation | null;
  artifacts: Artifact[];
}

// ── Presentation / Block ──────────────────────
export interface Presentation {
  layout: string;
  title: string;
  subtitle: string;
  selected_artifact_id: string;
  blocks: Block[];
}

export interface Block {
  id: string;
  kind: string;
  title: string;
  subtitle: string;
  artifact_ids: string[];
  citation_labels: string[];
  empty_state: string;
}

// ── Exploration ───────────────────────────────
export interface ExplorationCandidate {
  label: string;
  kind: string;
  path: string;
  score: number;
  preview: string;
}

export interface Exploration {
  mode: string;
  target_file: string;
  target_document: string;
  file_candidates: ExplorationCandidate[];
  class_candidates: ExplorationCandidate[];
  function_candidates: ExplorationCandidate[];
  document_candidates: ExplorationCandidate[];
}

// ── Source Presentation ───────────────────────
export interface SourcePresentation {
  kind: string;
  source_path: string;
  full_source_path: string;
  source_type: string;
  heading_path: string;
  quote: string;
  title: string;
  preview_lines: string[];
}

// ── Render Hints ──────────────────────────────
export interface RenderHints {
  response_type: string;
  primary_source_type: string;
  source_profile: string;
  interaction_mode: string;
  citation_count: number;
  truncated: boolean;
}

// ── Status ────────────────────────────────────
export interface Status {
  mode: string;
  safe_mode: boolean;
  degraded_mode: boolean;
  generation_blocked: boolean;
  write_blocked: boolean;
  rebuild_index_required: boolean;
}

// ── System Log ────────────────────────────────
export interface SystemLog {
  id: string;
  timestamp: string;
  type: 'info' | 'warning' | 'error';
  message: string;
}

// ── Skills / Action Maps ─────────────────────
export interface SkillIntentLink {
  intent_id: string;
  category: string;
  response_kind: string;
  implementation_status: string;
  requires_live_data: boolean;
  requires_retrieval: boolean;
  automation_ready: boolean;
  example_queries: string[];
}

export interface SkillCard {
  skill_id: string;
  title: string;
  parent_skill_id: string;
  summary: string;
  categories: string[];
  implementation_statuses: string[];
  requires_live_data: boolean;
  requires_retrieval: boolean;
  automation_ready: boolean;
  response_kinds: string[];
  example_queries: string[];
  linked_intents: SkillIntentLink[];
  linked_intent_ids: string[];
  local_app_name: string;
  local_app_installed: boolean | null;
  detected_local_app_installed: boolean;
  effective_local_app_installed: boolean;
  launch_target: string;
  open_supported: boolean;
  local_notes: string;
  api_provider: string;
  api_configured: boolean;
  api_scopes: string[];
  api_notes: string;
  notes: string;
  tags: string[];
  custom_fields: Record<string, string>;
  created_at: string;
  updated_at: string;
  source_kind: string;
}

export interface SkillCategorySummary {
  category: string;
  count: number;
}

export interface SkillBacklogEntry {
  query_key: string;
  query_text: string;
  query_samples: string[];
  occurrence_count: number;
  first_seen_at: string;
  last_seen_at: string;
  last_session_id: string;
  session_ids: string[];
  weekday_histogram: Record<string, number>;
  hour_histogram: Record<string, number>;
  date_histogram: Record<string, number>;
  last_status_mode: string;
  last_response_text: string;
  inferred_intent: string;
  review_state: string;
  suggested_skill_id: string;
}

export interface SkillCatalog {
  registry_version: string;
  generated_at: string;
  implemented_intent_count: number;
  planned_intent_count: number;
  skill_count: number;
  categories: SkillCategorySummary[];
  skills: SkillCard[];
  backlog: SkillBacklogEntry[];
}

export interface SkillProfileInput {
  title?: string | null;
  parent_skill_id?: string | null;
  summary?: string | null;
  local_app_name?: string | null;
  local_app_installed?: boolean | null;
  launch_target?: string | null;
  open_supported?: boolean | null;
  local_notes?: string | null;
  api_provider?: string | null;
  api_configured?: boolean | null;
  api_scopes?: string[];
  api_notes?: string | null;
  notes?: string | null;
  tags?: string[];
  linked_intents?: string[];
  custom_fields?: Record<string, string>;
}

export interface SkillProfileCreateInput extends SkillProfileInput {
  skill_id: string;
}

export interface ActionMapNode {
  node_id: string;
  skill_id: string;
  title: string;
  x: number;
  y: number;
  config: Record<string, string>;
}

export interface ActionMapEdge {
  edge_id: string;
  source: string;
  target: string;
  label: string;
}

export interface ActionMap {
  map_id: string;
  title: string;
  description: string;
  trigger_query: string;
  notes: string;
  tags: string[];
  nodes: ActionMapNode[];
  edges: ActionMapEdge[];
  created_at: string;
  updated_at: string;
}

export interface ActionMapInput {
  title?: string | null;
  description?: string | null;
  trigger_query?: string | null;
  notes?: string | null;
  tags?: string[];
  nodes?: ActionMapNode[];
  edges?: ActionMapEdge[];
}

export interface ActionMapCreateInput extends ActionMapInput {
  map_id: string;
}

// ── View ──────────────────────────────────────
export type ViewState = 'home' | 'terminal' | 'explorer' | 'skills' | 'admin';

/* ── Repository file tree ── */

export interface FileNode {
  name: string;
  path: string;
  type: 'file' | 'directory';
  extension?: string | null;
  size?: number | null;
}

export interface BrowseResponse {
  path: string;
  entries: FileNode[];
}

/* ── Learned Patterns ── */

export interface LearnedPatternSummary {
  pattern_id: string;
  canonical_query: string;
  failed_variants: string[];
  retrieval_task: string;
  entity_hints: Record<string, unknown>;
  reformulation_type: string;
  success_count: number;
  citation_paths: string[];
  created_at: number;
  last_used_at: number;
}

export interface LearnedPatternsResponse {
  patterns: LearnedPatternSummary[];
  total: number;
}

/* ── Extracted text (binary docs indexed as chunks) ── */

export interface ExtractedTextChunk {
  chunk_id: string;
  text: string;
  heading_path: string;
}

export interface ExtractedTextResponse {
  path: string;
  document_id: string;
  total_chunks: number;
  chunks: ExtractedTextChunk[];
}
