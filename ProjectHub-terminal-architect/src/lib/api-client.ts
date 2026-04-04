import type {
  AnswerKind,
  Citation,
  Artifact,
  ActionMap,
  ActionMapCreateInput,
  ActionMapInput,
  Presentation,
  GuideDirective,
  Exploration,
  SourcePresentation,
  RenderHints,
  SkillCatalog,
  SkillProfileCreateInput,
  SkillProfileInput,
  Status,
} from '../types';

const API_BASE_URL = import.meta.env.VITE_JARVIS_API_URL || 'http://localhost:8000';

// ── Request / Response ────────────────────────
export interface AskRequest {
  text: string;
  session_id: string;
}

export interface Response {
  query: string;
  response: string;
  has_evidence: boolean;
  spoken_response: string;
  citations: Citation[];
  status: Status;
  render_hints: RenderHints;
  exploration: Exploration | null;
  guide_directive: {
    intent: string;
    skill: string;
    loop_stage: string;
    clarification_prompt: string;
    missing_slots: string[];
    suggested_replies: string[];
    should_hold: boolean;
  } | null;
  full_response_path: string;
  source_presentation: SourcePresentation | null;
}

export interface Answer {
  text: string;
  spoken_text: string;
  has_evidence: boolean;
  citation_count: number;
  kind: AnswerKind;
  task_id?: string | null;
  structured_payload?: Record<string, unknown> | null;
  full_response_path?: string;
}

export interface AskResponse {
  response: Response;
  answer: Answer;
  guide: GuideDirective;
}

export interface HealthResponse {
  health: {
    status: string;
    model_loaded: boolean;
    memory_usage: number;
    index_status: string;
  };
}

export interface SkillCatalogResponse {
  catalog: SkillCatalog;
}

export interface SkillMutationResponse {
  catalog: SkillCatalog;
}

export interface ActionMapsResponse {
  maps: ActionMap[];
}

// ── API Client ────────────────────────────────
export const apiClient = {
  async ask(request: AskRequest): Promise<AskResponse> {
    const response = await fetch(`${API_BASE_URL}/api/ask`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || `API error: ${response.statusText}`);
    }

    return response.json();
  },

  async health(): Promise<HealthResponse> {
    const response = await fetch(`${API_BASE_URL}/api/health`);
    if (!response.ok) {
      throw new Error(`Health check failed: ${response.statusText}`);
    }
    return response.json();
  },

  async normalizeQuery(text: string): Promise<{ normalized_query: string }> {
    const response = await fetch(`${API_BASE_URL}/api/normalize`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    });

    if (!response.ok) {
      throw new Error(`Normalization failed: ${response.statusText}`);
    }

    return response.json();
  },

  async fetchSkillCatalog(): Promise<SkillCatalogResponse> {
    const response = await fetch(`${API_BASE_URL}/api/skills`);
    if (!response.ok) {
      throw new Error(`Skill catalog failed: ${response.statusText}`);
    }
    return response.json();
  },

  async createSkillProfile(request: SkillProfileCreateInput): Promise<SkillMutationResponse> {
    const response = await fetch(`${API_BASE_URL}/api/skills`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
    });
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || `Create skill failed: ${response.statusText}`);
    }
    return response.json();
  },

  async updateSkillProfile(skillId: string, request: SkillProfileInput): Promise<SkillMutationResponse> {
    const response = await fetch(`${API_BASE_URL}/api/skills/${encodeURIComponent(skillId)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
    });
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || `Update skill failed: ${response.statusText}`);
    }
    return response.json();
  },

  async fetchActionMaps(): Promise<ActionMapsResponse> {
    const response = await fetch(`${API_BASE_URL}/api/action-maps`);
    if (!response.ok) {
      throw new Error(`Action maps failed: ${response.statusText}`);
    }
    return response.json();
  },

  async createActionMap(request: ActionMapCreateInput): Promise<ActionMapsResponse> {
    const response = await fetch(`${API_BASE_URL}/api/action-maps`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
    });
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || `Create action map failed: ${response.statusText}`);
    }
    return response.json();
  },

  async updateActionMap(mapId: string, request: ActionMapInput): Promise<ActionMapsResponse> {
    const response = await fetch(`${API_BASE_URL}/api/action-maps/${encodeURIComponent(mapId)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
    });
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || `Update action map failed: ${response.statusText}`);
    }
    return response.json();
  },

  getFileUrl(fullPath: string): string {
    return `${API_BASE_URL}/api/file?path=${encodeURIComponent(fullPath)}`;
  },
};
