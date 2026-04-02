// ── Chat ──────────────────────────────────────
export interface Message {
  id: string;
  role: 'operator' | 'architect';
  timestamp: string;
  content: string;
  citations?: Citation[];
  has_evidence?: boolean;
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

// ── View ──────────────────────────────────────
export type ViewState = 'dashboard' | 'detail_report' | 'detail_image' | 'detail_code' | 'admin';
