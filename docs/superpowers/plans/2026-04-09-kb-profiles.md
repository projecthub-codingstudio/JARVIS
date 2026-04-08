# KB Profile System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow users to register multiple knowledge base directories as profiles with isolated indexes, and switch between them from the web UI.

**Architecture:** A `profiles.json` file stores the profile list and active ID. Each profile gets its own `data_dir` under `~/.jarvis/profiles/<id>/` containing an independent SQLite DB and LanceDB vector index. Switching profiles updates `profiles.json` and restarts the backend via `os.execv`. The frontend SettingsWorkspace is extended with profile cards, add/delete/switch dialogs.

**Tech Stack:** Python/FastAPI (backend), React/TypeScript/Tailwind (frontend), JSON file storage for profile config

---

## File Structure

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `alliance_20260317_130542/src/jarvis/app/profile_manager.py` | Profile CRUD, active profile resolution, data migration |
| Modify | `alliance_20260317_130542/src/jarvis/runtime_paths.py` | `resolve_menubar_data_dir()` reads active profile |
| Modify | `alliance_20260317_130542/src/jarvis/web_api.py` | Profile API endpoints + extend KbStatusResponse |
| Modify | `ProjectHub-terminal-architect/src/lib/api-client.ts` | Profile API client methods + types |
| Modify | `ProjectHub-terminal-architect/src/components/workspaces/SettingsWorkspace.tsx` | Profile list UI, add/switch/delete dialogs |

---

### Task 1: Backend — Profile Manager Module

**Files:**
- Create: `alliance_20260317_130542/src/jarvis/app/profile_manager.py`

- [ ] **Step 1: Create profile_manager.py**

```python
"""Knowledge Base profile management — CRUD for profiles.json."""

from __future__ import annotations

import json
import os
import re
import shutil
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import logging

logger = logging.getLogger(__name__)


@dataclass
class Profile:
    id: str
    name: str
    kb_path: str
    created_at: str = ""

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = time.strftime("%Y-%m-%dT%H:%M:%S")


@dataclass
class ProfileConfig:
    active: str = "default"
    profiles: list[Profile] = field(default_factory=list)


def _profiles_dir() -> Path:
    """Return the root profiles directory (~/.jarvis/profiles/)."""
    base = Path(os.getenv("JARVIS_PROFILES_ROOT", "")).strip() if os.getenv("JARVIS_PROFILES_ROOT") else None
    if base:
        return Path(base)
    return Path.home() / ".jarvis" / "profiles"


def _profiles_json_path() -> Path:
    return _profiles_dir().parent / "profiles.json"


def _name_to_id(name: str) -> str:
    """Convert display name to URL-safe slug."""
    slug = name.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = slug.strip("-")
    return slug or "profile"


def load_profiles() -> ProfileConfig:
    """Load profiles.json, creating default if it doesn't exist."""
    path = _profiles_json_path()
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            profiles = [Profile(**p) for p in data.get("profiles", [])]
            return ProfileConfig(active=data.get("active", "default"), profiles=profiles)
        except (json.JSONDecodeError, TypeError, KeyError) as exc:
            logger.warning("Corrupt profiles.json, recreating: %s", exc)

    return _create_default_config()


def save_profiles(config: ProfileConfig) -> None:
    """Write profiles.json atomically."""
    path = _profiles_json_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "active": config.active,
        "profiles": [asdict(p) for p in config.profiles],
    }
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _create_default_config() -> ProfileConfig:
    """Create a default profile, migrating existing data if present."""
    from jarvis.app.runtime_context import resolve_knowledge_base_path

    kb_path = str(resolve_knowledge_base_path())
    profile = Profile(id="default", name="Default", kb_path=kb_path)
    config = ProfileConfig(active="default", profiles=[profile])

    # Migrate existing data into profiles/default/
    legacy_dir = Path.home() / ".jarvis"
    profile_dir = _profiles_dir() / "default"
    profile_dir.mkdir(parents=True, exist_ok=True)

    for filename in ("jarvis.db", "jarvis.db-wal", "jarvis.db-shm"):
        src = legacy_dir / filename
        dst = profile_dir / filename
        if src.exists() and not dst.exists():
            shutil.move(str(src), str(dst))
            logger.info("Migrated %s -> %s", src, dst)

    src_vectors = legacy_dir / "vectors.lance"
    dst_vectors = profile_dir / "vectors.lance"
    if src_vectors.exists() and not dst_vectors.exists():
        shutil.move(str(src_vectors), str(dst_vectors))
        logger.info("Migrated vectors.lance -> profiles/default/")

    save_profiles(config)
    return config


def get_active_profile() -> Profile:
    """Return the currently active profile."""
    config = load_profiles()
    for p in config.profiles:
        if p.id == config.active:
            return p
    if config.profiles:
        return config.profiles[0]
    raise RuntimeError("No profiles configured")


def resolve_active_data_dir() -> Path:
    """Return the data directory for the active profile."""
    profile = get_active_profile()
    data_dir = _profiles_dir() / profile.id
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def create_profile(name: str, kb_path: str) -> Profile:
    """Create a new profile. Raises ValueError on validation failure."""
    config = load_profiles()

    profile_id = _name_to_id(name)
    if any(p.id == profile_id for p in config.profiles):
        raise ValueError(f"이미 존재하는 프로필 ID입니다: {profile_id}")

    p = Path(kb_path).expanduser().resolve()
    if not p.is_dir():
        raise ValueError("유효한 디렉토리가 아닙니다.")
    if not os.access(p, os.R_OK):
        raise ValueError("읽기 권한이 없습니다.")

    profile = Profile(id=profile_id, name=name, kb_path=str(p))
    config.profiles.append(profile)

    # Create data directory
    (_profiles_dir() / profile_id).mkdir(parents=True, exist_ok=True)

    save_profiles(config)
    return profile


def delete_profile(profile_id: str) -> None:
    """Delete a profile and its data. Raises ValueError if active."""
    config = load_profiles()

    if config.active == profile_id:
        raise ValueError("활성 프로필은 삭제할 수 없습니다.")

    profile = next((p for p in config.profiles if p.id == profile_id), None)
    if profile is None:
        raise ValueError(f"프로필을 찾을 수 없습니다: {profile_id}")

    config.profiles = [p for p in config.profiles if p.id != profile_id]
    save_profiles(config)

    # Remove data directory
    data_dir = _profiles_dir() / profile_id
    if data_dir.exists():
        shutil.rmtree(data_dir)
        logger.info("Deleted profile data: %s", data_dir)


def set_active_profile(profile_id: str) -> Profile:
    """Set the active profile. Raises ValueError if not found."""
    config = load_profiles()

    profile = next((p for p in config.profiles if p.id == profile_id), None)
    if profile is None:
        raise ValueError(f"프로필을 찾을 수 없습니다: {profile_id}")

    config.active = profile_id
    save_profiles(config)
    return profile


def list_profiles_with_stats() -> list[dict]:
    """Return all profiles with basic stats (doc count from each DB)."""
    import sqlite3
    config = load_profiles()
    result = []
    for p in config.profiles:
        data_dir = _profiles_dir() / p.id
        db_path = data_dir / "jarvis.db"
        doc_count = 0
        chunk_count = 0
        if db_path.exists():
            try:
                conn = sqlite3.connect(str(db_path))
                row = conn.execute("SELECT COUNT(*) FROM documents WHERE indexing_status != 'TOMBSTONED'").fetchone()
                doc_count = row[0] if row else 0
                row = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()
                chunk_count = row[0] if row else 0
                conn.close()
            except Exception:
                pass
        result.append({
            "id": p.id,
            "name": p.name,
            "kb_path": p.kb_path,
            "created_at": p.created_at,
            "is_active": p.id == config.active,
            "doc_count": doc_count,
            "chunk_count": chunk_count,
            "has_index": db_path.exists(),
        })
    return result
```

- [ ] **Step 2: Verify syntax**

Run: `python3 -c "import ast; ast.parse(open('alliance_20260317_130542/src/jarvis/app/profile_manager.py').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add alliance_20260317_130542/src/jarvis/app/profile_manager.py
git commit -m "feat(profiles): add profile manager module with CRUD and migration"
```

---

### Task 2: Backend — Update runtime_paths to use active profile

**Files:**
- Modify: `alliance_20260317_130542/src/jarvis/runtime_paths.py`

- [ ] **Step 1: Update resolve_menubar_data_dir()**

Replace the entire file content with:

```python
"""Shared path resolution helpers for menu bar runtime data."""

from __future__ import annotations

import os
from pathlib import Path


def resolve_alliance_root(default_cwd: Path | None = None) -> Path:
    configured = os.getenv("JARVIS_ALLIANCE_ROOT", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return (default_cwd or Path.cwd()).expanduser().resolve()


def resolve_menubar_data_dir(default_cwd: Path | None = None) -> Path:
    """Resolve the data directory for the active profile.

    Priority:
      1. JARVIS_MENUBAR_DATA_DIR env var (explicit override)
      2. Active profile's data directory from profiles.json
      3. Legacy fallback: alliance_root / .jarvis-menubar
    """
    configured = os.getenv("JARVIS_MENUBAR_DATA_DIR", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()

    try:
        from jarvis.app.profile_manager import resolve_active_data_dir
        return resolve_active_data_dir()
    except Exception:
        return resolve_alliance_root(default_cwd) / ".jarvis-menubar"
```

- [ ] **Step 2: Verify syntax**

Run: `python3 -c "import ast; ast.parse(open('alliance_20260317_130542/src/jarvis/runtime_paths.py').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add alliance_20260317_130542/src/jarvis/runtime_paths.py
git commit -m "feat(profiles): resolve_menubar_data_dir uses active profile"
```

---

### Task 3: Backend — Profile API Endpoints

**Files:**
- Modify: `alliance_20260317_130542/src/jarvis/web_api.py`

- [ ] **Step 1: Add Pydantic models for profiles**

Add after the `KbChangeResponse` model (around line 320):

```python
class ProfileResponse(BaseModel):
    id: str
    name: str
    kb_path: str
    created_at: str
    is_active: bool
    doc_count: int
    chunk_count: int
    has_index: bool


class ProfileListResponse(BaseModel):
    profiles: list[ProfileResponse]
    active: str


class ProfileCreateRequest(BaseModel):
    name: str = Field(max_length=100)
    kb_path: str = Field(max_length=4096)


class ProfileCreateResponse(BaseModel):
    profile: ProfileResponse
    profiles: list[ProfileResponse]
    active: str
```

- [ ] **Step 2: Add profile endpoints**

Add after the `/api/kb/change` endpoint:

```python
@app.get("/api/profiles", response_model=ProfileListResponse)
def list_profiles() -> ProfileListResponse:
    """List all KB profiles with stats."""
    from jarvis.app.profile_manager import list_profiles_with_stats, load_profiles

    profiles = list_profiles_with_stats()
    config = load_profiles()
    return ProfileListResponse(
        profiles=[ProfileResponse(**p) for p in profiles],
        active=config.active,
    )


@app.post("/api/profiles", response_model=ProfileCreateResponse)
def create_profile_endpoint(http_request: Request, request: ProfileCreateRequest) -> ProfileCreateResponse:
    """Create a new KB profile."""
    _check_origin(http_request)

    from jarvis.app.profile_manager import create_profile, list_profiles_with_stats, load_profiles

    try:
        profile = create_profile(request.name, request.kb_path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    profiles = list_profiles_with_stats()
    config = load_profiles()
    profile_resp = next(p for p in profiles if p["id"] == profile.id)
    return ProfileCreateResponse(
        profile=ProfileResponse(**profile_resp),
        profiles=[ProfileResponse(**p) for p in profiles],
        active=config.active,
    )


@app.delete("/api/profiles/{profile_id}")
def delete_profile_endpoint(profile_id: str, http_request: Request):
    """Delete a KB profile and its data."""
    _check_origin(http_request)

    from jarvis.app.profile_manager import delete_profile, list_profiles_with_stats, load_profiles

    try:
        delete_profile(profile_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    profiles = list_profiles_with_stats()
    config = load_profiles()
    return {
        "deleted": True,
        "profiles": [ProfileResponse(**p).model_dump() for p in profiles],
        "active": config.active,
    }


@app.post("/api/profiles/{profile_id}/activate")
def activate_profile(profile_id: str, http_request: Request):
    """Switch to a different profile. Restarts the backend."""
    _check_origin(http_request)

    from jarvis.app.profile_manager import set_active_profile, load_profiles

    if _index_state["status"] in ("scanning", "indexing"):
        raise HTTPException(status_code=409, detail="인덱싱 진행 중입니다. 완료 후 전환해주세요.")

    try:
        profile = set_active_profile(profile_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Set env var for the restarted process
    os.environ["JARVIS_KNOWLEDGE_BASE"] = profile.kb_path

    def _do_restart() -> None:
        _time.sleep(0.5)
        logger.info("Restarting for profile switch: %s", profile_id)
        pid_file = Path(__file__).resolve().parent.parent.parent.parent / "ProjectHub-terminal-architect" / ".pids" / "backend.pid"
        if pid_file.exists():
            try:
                pid_file.write_text(str(os.getpid()))
            except Exception:
                pass
        os.execv(sys.executable, [sys.executable] + sys.argv)

    threading.Thread(target=_do_restart, daemon=True, name="profile-switch").start()

    return {"switching": True, "profile_id": profile_id, "profile_name": profile.name}
```

- [ ] **Step 3: Extend KbStatusResponse with profile info**

Change the `KbStatusResponse` model to add profile fields:

```python
class KbStatusResponse(BaseModel):
    path: str
    exists: bool
    doc_count: int
    chunk_count: int
    embedding_count: int
    total_size_bytes: int
    last_indexed: str | None
    profile_id: str | None = None
    profile_name: str | None = None
```

Update the `kb_status()` endpoint to include profile info:

```python
@app.get("/api/kb/status", response_model=KbStatusResponse)
def kb_status() -> KbStatusResponse:
    """Return current knowledge base directory status."""
    kb_path = _resolve_kb_root()
    path_str = str(kb_path) if kb_path else ""
    exists = kb_path is not None and kb_path.exists()

    health = dict(_cached_health)

    profile_id = None
    profile_name = None
    try:
        from jarvis.app.profile_manager import get_active_profile
        active = get_active_profile()
        profile_id = active.id
        profile_name = active.name
    except Exception:
        pass

    return KbStatusResponse(
        path=path_str,
        exists=exists,
        doc_count=int(health.get("doc_count", 0)),
        chunk_count=int(health.get("chunk_count", 0)),
        embedding_count=int(health.get("embedding_count", 0)),
        total_size_bytes=int(health.get("total_size_bytes", 0)),
        last_indexed=_index_state.get("last_completed"),
        profile_id=profile_id,
        profile_name=profile_name,
    )
```

- [ ] **Step 4: Verify syntax**

Run: `python3 -c "import ast; ast.parse(open('alliance_20260317_130542/src/jarvis/web_api.py').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add alliance_20260317_130542/src/jarvis/web_api.py
git commit -m "feat(api): add profile list/create/delete/activate endpoints"
```

---

### Task 4: Frontend — API Client for Profiles

**Files:**
- Modify: `ProjectHub-terminal-architect/src/lib/api-client.ts`

- [ ] **Step 1: Add profile TypeScript interfaces**

Add after the `KbChangeResponse` interface (around line 113):

```typescript
export interface ProfileItem {
  id: string;
  name: string;
  kb_path: string;
  created_at: string;
  is_active: boolean;
  doc_count: number;
  chunk_count: number;
  has_index: boolean;
}

export interface ProfileListResponse {
  profiles: ProfileItem[];
  active: string;
}

export interface ProfileCreateResponse {
  profile: ProfileItem;
  profiles: ProfileItem[];
  active: string;
}
```

- [ ] **Step 2: Update KbStatusResponse with profile fields**

```typescript
export interface KbStatusResponse {
  path: string;
  exists: boolean;
  doc_count: number;
  chunk_count: number;
  embedding_count: number;
  total_size_bytes: number;
  last_indexed: string | null;
  profile_id: string | null;
  profile_name: string | null;
}
```

- [ ] **Step 3: Add profile API client methods**

Add inside the `apiClient` object, after the `kbChange()` method:

```typescript
async listProfiles(): Promise<ProfileListResponse> {
  const res = await fetch(`${API_BASE_URL}/api/profiles`);
  if (!res.ok) throw new Error(`List profiles failed: ${res.statusText}`);
  return res.json();
},

async createProfile(name: string, kbPath: string): Promise<ProfileCreateResponse> {
  const res = await fetch(`${API_BASE_URL}/api/profiles`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, kb_path: kbPath }),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail.detail || `Create profile failed: ${res.statusText}`);
  }
  return res.json();
},

async deleteProfile(profileId: string): Promise<void> {
  const res = await fetch(`${API_BASE_URL}/api/profiles/${encodeURIComponent(profileId)}`, {
    method: 'DELETE',
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail.detail || `Delete profile failed: ${res.statusText}`);
  }
},

async activateProfile(profileId: string): Promise<{ switching: boolean; profile_id: string; profile_name: string }> {
  const res = await fetch(`${API_BASE_URL}/api/profiles/${encodeURIComponent(profileId)}/activate`, {
    method: 'POST',
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail.detail || `Activate profile failed: ${res.statusText}`);
  }
  return res.json();
},
```

- [ ] **Step 4: Commit**

```bash
git add ProjectHub-terminal-architect/src/lib/api-client.ts
git commit -m "feat(api-client): add profile list/create/delete/activate methods"
```

---

### Task 5: Frontend — Rewrite SettingsWorkspace with Profile Support

**Files:**
- Modify: `ProjectHub-terminal-architect/src/components/workspaces/SettingsWorkspace.tsx`

- [ ] **Step 1: Rewrite SettingsWorkspace.tsx**

Replace the entire file with the new version that includes:
1. Profile list section with cards
2. Active profile details (existing KB status)
3. Add Profile dialog (name + path input with validation)
4. Switch confirmation dialog
5. Delete confirmation dialog
6. Existing "Change Directory" for active profile's KB path

```tsx
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import {
  AlertTriangle,
  CheckCircle2,
  Database,
  FolderOpen,
  HardDrive,
  LoaderCircle,
  Plus,
  RefreshCw,
  Trash2,
  XCircle,
} from 'lucide-react';
import { cn } from '../../lib/utils';
import {
  apiClient,
  type IndexingState,
  type KbStatusResponse,
  type KbValidateResponse,
  type ProfileItem,
} from '../../lib/api-client';
import type { SystemLog } from '../../types';

interface SettingsWorkspaceProps {
  backendStatus: 'checking' | 'online' | 'offline';
  indexingState: IndexingState;
  onIndexingStateChange: (state: IndexingState) => void;
  addLog: (log: SystemLog) => void;
}

// ── Helpers ──────────────────────────────────────
function formatBytes(bytes: number) {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
}

// ── Modal Backdrop ───────────────────────────────
function ModalBackdrop({
  children,
  onClose,
  disabled,
}: {
  children: React.ReactNode;
  onClose: () => void;
  disabled?: boolean;
}) {
  return (
    <motion.div
      className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      onClick={() => !disabled && onClose()}
    >
      <motion.div
        className="mx-4 w-full max-w-lg rounded-lg border border-white/10 bg-surface-container-high p-6 shadow-2xl"
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.95 }}
        onClick={(e) => e.stopPropagation()}
      >
        {children}
      </motion.div>
    </motion.div>
  );
}

// ── Main Component ───────────────────────────────
export const SettingsWorkspace: React.FC<SettingsWorkspaceProps> = ({
  backendStatus,
  indexingState,
  onIndexingStateChange,
  addLog,
}) => {
  // Profile state
  const [profiles, setProfiles] = useState<ProfileItem[]>([]);
  const [activeProfileId, setActiveProfileId] = useState<string>('');
  const [profilesLoading, setProfilesLoading] = useState(true);

  // KB status state
  const [kbStatus, setKbStatus] = useState<KbStatusResponse | null>(null);
  const [statusLoading, setStatusLoading] = useState(true);

  // Add profile dialog
  const [showAddDialog, setShowAddDialog] = useState(false);
  const [addName, setAddName] = useState('');
  const [addPath, setAddPath] = useState('');
  const [addValidation, setAddValidation] = useState<KbValidateResponse | null>(null);
  const [addValidating, setAddValidating] = useState(false);
  const [addSubmitting, setAddSubmitting] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);
  const addValidateTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Switch dialog
  const [switchTarget, setSwitchTarget] = useState<ProfileItem | null>(null);
  const [switching, setSwitching] = useState(false);

  // Delete dialog
  const [deleteTarget, setDeleteTarget] = useState<ProfileItem | null>(null);
  const [deleting, setDeleting] = useState(false);

  // Change directory (existing feature for active profile)
  const [changePath, setChangePath] = useState('');
  const [changeValidation, setChangeValidation] = useState<KbValidateResponse | null>(null);
  const [changeValidating, setChangeValidating] = useState(false);
  const [showChangeConfirm, setShowChangeConfirm] = useState(false);
  const [changing, setChanging] = useState(false);
  const [changeError, setChangeError] = useState<string | null>(null);
  const [changeSuccess, setChangeSuccess] = useState(false);
  const changeValidateTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const isIndexing = indexingState.status === 'scanning' || indexingState.status === 'indexing';
  const progressPercent = indexingState.total > 0
    ? Math.round((indexingState.processed / indexingState.total) * 100)
    : 0;

  // ── Load Data ──
  const loadProfiles = useCallback(async () => {
    try {
      setProfilesLoading(true);
      const data = await apiClient.listProfiles();
      setProfiles(data.profiles);
      setActiveProfileId(data.active);
    } catch {
      // backend may be offline
    } finally {
      setProfilesLoading(false);
    }
  }, []);

  const loadStatus = useCallback(async () => {
    try {
      setStatusLoading(true);
      const status = await apiClient.kbStatus();
      setKbStatus(status);
    } catch {
      // ignore
    } finally {
      setStatusLoading(false);
    }
  }, []);

  useEffect(() => {
    if (backendStatus === 'online') {
      void loadProfiles();
      void loadStatus();
    }
  }, [backendStatus, loadProfiles, loadStatus]);

  // Refresh status when indexing completes
  useEffect(() => {
    if (changeSuccess && (indexingState.status === 'done' || indexingState.status === 'idle')) {
      void loadStatus();
      void loadProfiles();
    }
  }, [indexingState.status, changeSuccess, loadStatus, loadProfiles]);

  // ── Add Profile: debounced validation ──
  useEffect(() => {
    if (!addPath.trim()) {
      setAddValidation(null);
      return;
    }
    if (addValidateTimer.current) clearTimeout(addValidateTimer.current);
    addValidateTimer.current = setTimeout(async () => {
      setAddValidating(true);
      try {
        const result = await apiClient.kbValidate(addPath);
        setAddValidation(result);
      } catch {
        setAddValidation(null);
      } finally {
        setAddValidating(false);
      }
    }, 500);
    return () => {
      if (addValidateTimer.current) clearTimeout(addValidateTimer.current);
    };
  }, [addPath]);

  // ── Change Directory: debounced validation ──
  useEffect(() => {
    if (!changePath.trim()) {
      setChangeValidation(null);
      return;
    }
    if (changeValidateTimer.current) clearTimeout(changeValidateTimer.current);
    changeValidateTimer.current = setTimeout(async () => {
      setChangeValidating(true);
      try {
        const result = await apiClient.kbValidate(changePath);
        setChangeValidation(result);
      } catch {
        setChangeValidation(null);
      } finally {
        setChangeValidating(false);
      }
    }, 500);
    return () => {
      if (changeValidateTimer.current) clearTimeout(changeValidateTimer.current);
    };
  }, [changePath]);

  // ── Handlers ──
  const handleAddProfile = async () => {
    setAddSubmitting(true);
    setAddError(null);
    try {
      const result = await apiClient.createProfile(addName, addPath);
      setProfiles(result.profiles);
      setActiveProfileId(result.active);
      setShowAddDialog(false);
      setAddName('');
      setAddPath('');
      setAddValidation(null);
      addLog({
        id: `${Date.now()}-profile-add`,
        timestamp: new Date().toISOString(),
        type: 'info',
        message: `Profile created: ${result.profile.name}`,
      });
    } catch (err) {
      setAddError(err instanceof Error ? err.message : 'Failed to create profile');
    } finally {
      setAddSubmitting(false);
    }
  };

  const handleSwitchProfile = async () => {
    if (!switchTarget) return;
    setSwitching(true);
    try {
      await apiClient.activateProfile(switchTarget.id);
      addLog({
        id: `${Date.now()}-profile-switch`,
        timestamp: new Date().toISOString(),
        type: 'info',
        message: `Switching to profile: ${switchTarget.name}`,
      });
      setSwitchTarget(null);
      // Backend will restart — frontend auto-reconnects via health polling
    } catch (err) {
      addLog({
        id: `${Date.now()}-profile-switch-err`,
        timestamp: new Date().toISOString(),
        type: 'error',
        message: `Profile switch failed: ${err instanceof Error ? err.message : 'unknown'}`,
      });
    } finally {
      setSwitching(false);
    }
  };

  const handleDeleteProfile = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await apiClient.deleteProfile(deleteTarget.id);
      await loadProfiles();
      setDeleteTarget(null);
      addLog({
        id: `${Date.now()}-profile-delete`,
        timestamp: new Date().toISOString(),
        type: 'info',
        message: `Profile deleted: ${deleteTarget.name}`,
      });
    } catch (err) {
      addLog({
        id: `${Date.now()}-profile-delete-err`,
        timestamp: new Date().toISOString(),
        type: 'error',
        message: `Delete failed: ${err instanceof Error ? err.message : 'unknown'}`,
      });
    } finally {
      setDeleting(false);
    }
  };

  const handleChangeConfirm = async () => {
    setChanging(true);
    setChangeError(null);
    try {
      const result = await apiClient.kbChange(changePath);
      onIndexingStateChange(result.indexing);
      setShowChangeConfirm(false);
      setChangeSuccess(true);
      setChangePath('');
      setChangeValidation(null);
      addLog({
        id: `${Date.now()}-kb-change`,
        timestamp: new Date().toISOString(),
        type: 'info',
        message: `KB directory changed: ${result.previous_path} → ${result.new_path}`,
      });
    } catch (err) {
      setChangeError(err instanceof Error ? err.message : 'Failed to change directory');
    } finally {
      setChanging(false);
    }
  };

  const canAddProfile = addName.trim().length > 0 && addValidation && !addValidation.error && !addSubmitting;
  const canChangeDir = changeValidation && changeValidation.exists && changeValidation.is_directory && changeValidation.readable && !isIndexing;

  return (
    <div className="flex h-full flex-col overflow-hidden bg-surface">
      {/* Header */}
      <div className="flex h-14 shrink-0 items-center justify-between border-b border-white/5 bg-surface-container-low px-6">
        <div className="flex items-center gap-4">
          <h1 className="text-lg font-semibold tracking-tight text-on-surface">Settings</h1>
          <div className="hidden h-4 w-px bg-white/10 md:block" />
          <span className="hidden font-mono text-[11px] text-on-surface-variant md:inline">
            Knowledge Base Profiles
          </span>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto custom-scrollbar p-6">
        <div className="mx-auto max-w-2xl space-y-8">

          {/* ── Profile List ── */}
          <section className="rounded-lg border border-white/5 bg-surface-container-low p-6">
            <div className="mb-4 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <Database size={18} className="text-primary" />
                <h2 className="text-sm font-semibold uppercase tracking-widest text-on-surface">
                  Profiles
                </h2>
              </div>
              <button
                onClick={() => { setShowAddDialog(true); setAddError(null); }}
                disabled={backendStatus !== 'online'}
                className={cn(
                  'flex items-center gap-1.5 rounded px-3 py-1.5 text-[11px] font-semibold uppercase tracking-widest transition',
                  backendStatus === 'online'
                    ? 'bg-primary/10 text-primary hover:bg-primary/20'
                    : 'cursor-not-allowed text-outline',
                )}
              >
                <Plus size={14} />
                Add Profile
              </button>
            </div>

            {profilesLoading ? (
              <div className="flex items-center gap-2 text-outline">
                <LoaderCircle size={14} className="animate-spin" />
                <span className="text-[12px]">Loading profiles...</span>
              </div>
            ) : profiles.length === 0 ? (
              <div className="text-[12px] text-outline">No profiles configured.</div>
            ) : (
              <div className="space-y-2">
                {profiles.map((profile) => (
                  <div
                    key={profile.id}
                    className={cn(
                      'group flex items-center gap-3 rounded-lg border px-4 py-3 transition',
                      profile.is_active
                        ? 'border-secondary/30 bg-secondary/5'
                        : 'border-white/5 bg-surface-container hover:border-white/10 cursor-pointer',
                    )}
                    onClick={() => {
                      if (!profile.is_active && !isIndexing) setSwitchTarget(profile);
                    }}
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="text-[13px] font-semibold text-on-surface">{profile.name}</span>
                        {profile.is_active && (
                          <span className="rounded bg-secondary/20 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-widest text-secondary">
                            Active
                          </span>
                        )}
                      </div>
                      <code className="mt-0.5 block truncate text-[11px] text-outline">{profile.kb_path}</code>
                      <div className="mt-1 flex gap-3 text-[10px] text-on-surface-variant">
                        <span>{profile.doc_count} docs</span>
                        <span>{profile.chunk_count} chunks</span>
                        {!profile.has_index && <span className="text-[#ffb4ab]">not indexed</span>}
                      </div>
                    </div>
                    {!profile.is_active && (
                      <button
                        onClick={(e) => { e.stopPropagation(); setDeleteTarget(profile); }}
                        className="shrink-0 rounded p-1.5 text-outline opacity-0 transition hover:bg-[#93000a]/20 hover:text-[#ffb4ab] group-hover:opacity-100"
                        title="Delete profile"
                      >
                        <Trash2 size={14} />
                      </button>
                    )}
                  </div>
                ))}
              </div>
            )}
          </section>

          {/* ── Active Profile Details ── */}
          <section className="rounded-lg border border-white/5 bg-surface-container-low p-6">
            <div className="mb-4 flex items-center gap-3">
              <FolderOpen size={18} className="text-primary" />
              <h2 className="text-sm font-semibold uppercase tracking-widest text-on-surface">
                Active Knowledge Base
              </h2>
            </div>

            {statusLoading ? (
              <div className="flex items-center gap-2 text-outline">
                <LoaderCircle size={14} className="animate-spin" />
                <span className="text-[12px]">Loading...</span>
              </div>
            ) : kbStatus ? (
              <div className="space-y-3">
                <div className="flex items-center gap-2 rounded bg-surface-container px-3 py-2">
                  <FolderOpen size={14} className="shrink-0 text-secondary" />
                  <code className="break-all text-[12px] text-on-surface">{kbStatus.path}</code>
                  {kbStatus.exists ? (
                    <CheckCircle2 size={14} className="ml-auto shrink-0 text-secondary" />
                  ) : (
                    <XCircle size={14} className="ml-auto shrink-0 text-[#ffb4ab]" />
                  )}
                </div>
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                  {[
                    { label: 'Documents', value: kbStatus.doc_count.toLocaleString() },
                    { label: 'Chunks', value: kbStatus.chunk_count.toLocaleString() },
                    { label: 'Vectors', value: kbStatus.embedding_count.toLocaleString() },
                    { label: 'Size', value: formatBytes(kbStatus.total_size_bytes) },
                  ].map(({ label, value }) => (
                    <div key={label} className="rounded bg-surface-container px-3 py-2">
                      <div className="text-[10px] uppercase tracking-widest text-outline">{label}</div>
                      <div className="mt-0.5 font-mono text-[13px] font-semibold text-on-surface">{value}</div>
                    </div>
                  ))}
                </div>
                {kbStatus.last_indexed && (
                  <div className="text-[11px] text-outline">
                    Last indexed: {new Date(kbStatus.last_indexed).toLocaleString('ko-KR')}
                  </div>
                )}
              </div>
            ) : (
              <div className="text-[12px] text-[#ffb4ab]">Backend offline</div>
            )}
          </section>

          {/* ── Change Active Profile's Directory ── */}
          <section className="rounded-lg border border-white/5 bg-surface-container-low p-6">
            <div className="mb-4 flex items-center gap-3">
              <HardDrive size={18} className="text-primary" />
              <h2 className="text-sm font-semibold uppercase tracking-widest text-on-surface">
                Change Directory
              </h2>
            </div>
            <div className="space-y-4">
              <div>
                <label className="mb-1.5 block text-[11px] uppercase tracking-widest text-outline">
                  New Directory Path
                </label>
                <div className="relative">
                  <input
                    type="text"
                    value={changePath}
                    onChange={(e) => { setChangePath(e.target.value); setChangeSuccess(false); setChangeError(null); }}
                    placeholder="/Users/username/Documents/my-knowledge-base"
                    disabled={isIndexing}
                    className={cn(
                      'w-full rounded border bg-surface-container px-3 py-2 font-mono text-[12px] text-on-surface placeholder:text-outline/50 focus:outline-none focus:ring-1',
                      changeValidation?.error ? 'border-[#ffb4ab]/50 focus:ring-[#ffb4ab]'
                        : changeValidation && !changeValidation.error ? 'border-secondary/50 focus:ring-secondary'
                        : 'border-white/10 focus:ring-primary',
                      isIndexing && 'cursor-not-allowed opacity-50',
                    )}
                  />
                  {changeValidating && <LoaderCircle size={14} className="absolute right-3 top-1/2 -translate-y-1/2 animate-spin text-primary" />}
                </div>
              </div>
              <AnimatePresence mode="wait">
                {changeValidation && (
                  <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }}>
                    {changeValidation.error ? (
                      <div className="flex items-center gap-2 rounded bg-[#93000a]/20 px-3 py-2 text-[12px] text-[#ffb4ab]">
                        <XCircle size={14} className="shrink-0" />{changeValidation.error}
                      </div>
                    ) : (
                      <div className="flex items-center gap-2 rounded bg-secondary/10 px-3 py-2 text-[12px] text-secondary">
                        <CheckCircle2 size={14} className="shrink-0" />
                        Valid — {changeValidation.file_count.toLocaleString()} indexable files
                      </div>
                    )}
                  </motion.div>
                )}
              </AnimatePresence>
              <button
                onClick={() => setShowChangeConfirm(true)}
                disabled={!canChangeDir || backendStatus !== 'online'}
                className={cn(
                  'rounded px-4 py-2 text-[12px] font-semibold uppercase tracking-widest transition',
                  canChangeDir && backendStatus === 'online' ? 'bg-primary text-surface hover:bg-primary/80' : 'cursor-not-allowed bg-white/5 text-outline',
                )}
              >
                Change Directory
              </button>
              {changeError && (
                <div className="flex items-center gap-2 rounded bg-[#93000a]/20 px-3 py-2 text-[12px] text-[#ffb4ab]">
                  <XCircle size={14} className="shrink-0" />{changeError}
                </div>
              )}
              {changeSuccess && (
                <div className="space-y-3">
                  <div className="flex items-center gap-2 rounded bg-secondary/10 px-3 py-2 text-[12px] text-secondary">
                    <CheckCircle2 size={14} className="shrink-0" />Directory changed. Re-indexing...
                  </div>
                  {isIndexing && (
                    <div className="space-y-2">
                      <div className="flex items-center justify-between text-[11px]">
                        <span className="flex items-center gap-2 text-primary">
                          <RefreshCw size={12} className="animate-spin" />
                          {indexingState.status === 'scanning' ? 'Scanning...' : 'Indexing...'}
                        </span>
                        <span className="font-mono text-outline">{indexingState.processed}/{indexingState.total} ({progressPercent}%)</span>
                      </div>
                      <div className="h-1.5 overflow-hidden rounded-full bg-white/5">
                        <motion.div className="h-full rounded-full bg-primary" initial={{ width: 0 }} animate={{ width: `${progressPercent}%` }} transition={{ duration: 0.3 }} />
                      </div>
                    </div>
                  )}
                  {indexingState.status === 'done' && (
                    <div className="flex items-center gap-2 text-[11px] text-secondary">
                      <CheckCircle2 size={12} />Complete — {indexingState.total} files processed.
                    </div>
                  )}
                  {indexingState.status === 'error' && (
                    <div className="flex items-center gap-2 text-[11px] text-[#ffb4ab]">
                      <XCircle size={12} />Failed: {indexingState.error}
                    </div>
                  )}
                </div>
              )}
            </div>
          </section>
        </div>
      </div>

      {/* ── Add Profile Dialog ── */}
      <AnimatePresence>
        {showAddDialog && (
          <ModalBackdrop onClose={() => setShowAddDialog(false)} disabled={addSubmitting}>
            <h3 className="mb-4 text-base font-semibold text-on-surface">Add Profile</h3>
            <div className="space-y-4">
              <div>
                <label className="mb-1.5 block text-[11px] uppercase tracking-widest text-outline">Profile Name</label>
                <input
                  type="text"
                  value={addName}
                  onChange={(e) => setAddName(e.target.value)}
                  placeholder="e.g. Work Documents"
                  className="w-full rounded border border-white/10 bg-surface-container px-3 py-2 text-[12px] text-on-surface placeholder:text-outline/50 focus:outline-none focus:ring-1 focus:ring-primary"
                />
              </div>
              <div>
                <label className="mb-1.5 block text-[11px] uppercase tracking-widest text-outline">Knowledge Base Path</label>
                <div className="relative">
                  <input
                    type="text"
                    value={addPath}
                    onChange={(e) => setAddPath(e.target.value)}
                    placeholder="/Users/username/Documents/work-kb"
                    className={cn(
                      'w-full rounded border bg-surface-container px-3 py-2 font-mono text-[12px] text-on-surface placeholder:text-outline/50 focus:outline-none focus:ring-1',
                      addValidation?.error ? 'border-[#ffb4ab]/50 focus:ring-[#ffb4ab]'
                        : addValidation && !addValidation.error ? 'border-secondary/50 focus:ring-secondary'
                        : 'border-white/10 focus:ring-primary',
                    )}
                  />
                  {addValidating && <LoaderCircle size={14} className="absolute right-3 top-1/2 -translate-y-1/2 animate-spin text-primary" />}
                </div>
              </div>
              <AnimatePresence mode="wait">
                {addValidation && (
                  <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }}>
                    {addValidation.error ? (
                      <div className="flex items-center gap-2 rounded bg-[#93000a]/20 px-3 py-2 text-[12px] text-[#ffb4ab]">
                        <XCircle size={14} className="shrink-0" />{addValidation.error}
                      </div>
                    ) : (
                      <div className="flex items-center gap-2 rounded bg-secondary/10 px-3 py-2 text-[12px] text-secondary">
                        <CheckCircle2 size={14} className="shrink-0" />
                        Valid — {addValidation.file_count.toLocaleString()} indexable files
                      </div>
                    )}
                  </motion.div>
                )}
              </AnimatePresence>
              {addError && (
                <div className="flex items-center gap-2 rounded bg-[#93000a]/20 px-3 py-2 text-[12px] text-[#ffb4ab]">
                  <XCircle size={14} className="shrink-0" />{addError}
                </div>
              )}
              <div className="flex justify-end gap-3 pt-2">
                <button onClick={() => setShowAddDialog(false)} disabled={addSubmitting} className="rounded px-4 py-2 text-[12px] font-semibold text-outline hover:bg-white/5">Cancel</button>
                <button
                  onClick={handleAddProfile}
                  disabled={!canAddProfile}
                  className={cn(
                    'flex items-center gap-2 rounded px-4 py-2 text-[12px] font-semibold transition',
                    canAddProfile ? 'bg-primary text-surface hover:bg-primary/80' : 'cursor-not-allowed bg-white/5 text-outline',
                  )}
                >
                  {addSubmitting && <LoaderCircle size={14} className="animate-spin" />}
                  Create
                </button>
              </div>
            </div>
          </ModalBackdrop>
        )}
      </AnimatePresence>

      {/* ── Switch Profile Dialog ── */}
      <AnimatePresence>
        {switchTarget && (
          <ModalBackdrop onClose={() => setSwitchTarget(null)} disabled={switching}>
            <div className="mb-4 flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-full bg-primary/20">
                <RefreshCw size={20} className="text-primary" />
              </div>
              <h3 className="text-base font-semibold text-on-surface">Switch Profile</h3>
            </div>
            <div className="mb-6 space-y-3 text-[12px] leading-relaxed text-on-surface-variant">
              <p>
                <strong className="text-on-surface">Target:</strong>{' '}
                <span className="text-primary">{switchTarget.name}</span>
              </p>
              <div className="rounded border border-primary/20 bg-primary/5 p-3">
                <ul className="ml-4 list-disc space-y-1">
                  <li>Backend will <strong>restart</strong> (2-3 seconds)</li>
                  <li>Search will be temporarily <strong>unavailable</strong></li>
                  {!switchTarget.has_index && (
                    <li className="text-[#ffb4ab]">First switch — <strong>full indexing</strong> will start automatically</li>
                  )}
                  {switchTarget.has_index && (
                    <li className="text-secondary">Index exists — <strong>immediate</strong> availability</li>
                  )}
                </ul>
              </div>
            </div>
            <div className="flex justify-end gap-3">
              <button onClick={() => setSwitchTarget(null)} disabled={switching} className="rounded px-4 py-2 text-[12px] font-semibold text-outline hover:bg-white/5">Cancel</button>
              <button
                onClick={handleSwitchProfile}
                disabled={switching}
                className={cn(
                  'flex items-center gap-2 rounded px-4 py-2 text-[12px] font-semibold transition',
                  switching ? 'cursor-not-allowed bg-primary/30 text-primary' : 'bg-primary text-surface hover:bg-primary/80',
                )}
              >
                {switching && <LoaderCircle size={14} className="animate-spin" />}
                {switching ? 'Switching...' : 'Switch'}
              </button>
            </div>
          </ModalBackdrop>
        )}
      </AnimatePresence>

      {/* ── Delete Profile Dialog ── */}
      <AnimatePresence>
        {deleteTarget && (
          <ModalBackdrop onClose={() => setDeleteTarget(null)} disabled={deleting}>
            <div className="mb-4 flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-full bg-[#ffb4ab]/20">
                <AlertTriangle size={20} className="text-[#ffb4ab]" />
              </div>
              <h3 className="text-base font-semibold text-on-surface">Delete Profile</h3>
            </div>
            <div className="mb-6 text-[12px] leading-relaxed text-on-surface-variant">
              <p>
                Profile <strong className="text-on-surface">{deleteTarget.name}</strong> and all its index data
                ({deleteTarget.doc_count} docs, {deleteTarget.chunk_count} chunks) will be permanently deleted.
              </p>
              <p className="mt-2 text-outline">The original knowledge base directory will not be affected.</p>
            </div>
            <div className="flex justify-end gap-3">
              <button onClick={() => setDeleteTarget(null)} disabled={deleting} className="rounded px-4 py-2 text-[12px] font-semibold text-outline hover:bg-white/5">Cancel</button>
              <button
                onClick={handleDeleteProfile}
                disabled={deleting}
                className={cn(
                  'flex items-center gap-2 rounded px-4 py-2 text-[12px] font-semibold transition',
                  deleting ? 'cursor-not-allowed bg-[#ffb4ab]/30 text-[#ffdad6]' : 'bg-[#ffb4ab] text-[#690005] hover:bg-[#ffb4ab]/80',
                )}
              >
                {deleting && <LoaderCircle size={14} className="animate-spin" />}
                Delete
              </button>
            </div>
          </ModalBackdrop>
        )}
      </AnimatePresence>

      {/* ── Change Directory Confirm Dialog ── */}
      <AnimatePresence>
        {showChangeConfirm && (
          <ModalBackdrop onClose={() => setShowChangeConfirm(false)} disabled={changing}>
            <div className="mb-4 flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-full bg-[#ffb4ab]/20">
                <AlertTriangle size={20} className="text-[#ffb4ab]" />
              </div>
              <h3 className="text-base font-semibold text-on-surface">Change Directory</h3>
            </div>
            <div className="mb-6 space-y-3 text-[12px] leading-relaxed text-on-surface-variant">
              <p>
                <strong className="text-on-surface">New path:</strong>{' '}
                <code className="rounded bg-surface-container px-1.5 py-0.5 font-mono text-[11px] text-primary">{changeValidation?.path || changePath}</code>
              </p>
              <div className="rounded border border-[#ffb4ab]/20 bg-[#93000a]/10 p-3">
                <p className="mb-2 font-semibold text-[#ffb4ab]">Warning</p>
                <ul className="ml-4 list-disc space-y-1 text-[#ffdad6]">
                  <li>Existing index will be <strong>purged</strong></li>
                  <li>{changeValidation?.file_count.toLocaleString() ?? '?'} files will be <strong>re-indexed</strong></li>
                  <li>Search will be <strong>limited</strong> during indexing</li>
                </ul>
              </div>
            </div>
            <div className="flex justify-end gap-3">
              <button onClick={() => setShowChangeConfirm(false)} disabled={changing} className="rounded px-4 py-2 text-[12px] font-semibold text-outline hover:bg-white/5">Cancel</button>
              <button
                onClick={handleChangeConfirm}
                disabled={changing}
                className={cn(
                  'flex items-center gap-2 rounded px-4 py-2 text-[12px] font-semibold transition',
                  changing ? 'cursor-not-allowed bg-[#ffb4ab]/30 text-[#ffdad6]' : 'bg-[#ffb4ab] text-[#690005] hover:bg-[#ffb4ab]/80',
                )}
              >
                {changing && <LoaderCircle size={14} className="animate-spin" />}
                {changing ? 'Processing...' : 'Confirm'}
              </button>
            </div>
          </ModalBackdrop>
        )}
      </AnimatePresence>
    </div>
  );
};
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd /Users/codingstudio/__PROJECTHUB__/JARVIS/ProjectHub-terminal-architect && npx tsc --noEmit 2>&1 | head -20`
Expected: No new errors (pre-existing App.tsx:449 is OK)

- [ ] **Step 3: Commit**

```bash
git add ProjectHub-terminal-architect/src/components/workspaces/SettingsWorkspace.tsx
git commit -m "feat(settings): rewrite with profile list, add/switch/delete dialogs"
```

---
