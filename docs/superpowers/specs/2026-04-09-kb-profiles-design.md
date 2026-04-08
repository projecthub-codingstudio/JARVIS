# KB Profile System Design

## Goal

Allow users to register multiple knowledge base directories as "profiles" and switch between them instantly without re-indexing. Each profile has its own isolated SQLite DB and LanceDB vector index.

## Data Structure

```
~/.jarvis/
  profiles.json              ← profile list + active profile ID
  profiles/
    default/
      jarvis.db
      vectors.lance/
    work-docs/
      jarvis.db
      vectors.lance/
```

### profiles.json Schema

```json
{
  "active": "default",
  "profiles": [
    {
      "id": "default",
      "name": "Default",
      "kb_path": "/Users/.../knowledge_base",
      "created_at": "2026-04-09T12:00:00"
    }
  ]
}
```

- `id`: URL-safe slug derived from name (lowercase, hyphens)
- `name`: Display name (Korean allowed)
- `kb_path`: Absolute path to knowledge base directory
- `created_at`: ISO timestamp

## Backend

### Profile Manager Module

New file: `jarvis/app/profile_manager.py`

Responsibilities:
- CRUD for `profiles.json`
- Resolve active profile's `data_dir` → `~/.jarvis/profiles/<id>/`
- Generate safe profile IDs from names
- Validate profile operations (can't delete active, can't create duplicate)

Key functions:
- `load_profiles() -> ProfileConfig` — read profiles.json
- `save_profiles(config: ProfileConfig)` — write profiles.json
- `get_active_profile() -> Profile` — return active profile
- `resolve_active_data_dir() -> Path` — return `~/.jarvis/profiles/<active_id>/`
- `create_profile(name, kb_path) -> Profile` — validate + add to profiles.json
- `delete_profile(profile_id)` — remove from profiles.json + delete data dir
- `set_active_profile(profile_id)` — update active in profiles.json

### Migration: Existing Data

On first run with profile system:
1. Check if `profiles.json` exists
2. If not, create it with a "default" profile
3. Move existing `~/.jarvis/jarvis.db` and `~/.jarvis/vectors.lance` into `~/.jarvis/profiles/default/`
4. Set current `JARVIS_KNOWLEDGE_BASE` as default profile's `kb_path`

### Path Resolution Change

`resolve_menubar_data_dir()` in `runtime_paths.py`:
- Currently returns: `resolve_alliance_root() / ".jarvis-menubar"` or env var
- Change to: call `resolve_active_data_dir()` from profile_manager
- Fallback: if profiles.json doesn't exist, use legacy path

### API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `GET /api/profiles` | GET | List all profiles with active flag |
| `POST /api/profiles` | POST | Create new profile (name + kb_path) |
| `DELETE /api/profiles/{id}` | DELETE | Delete profile (not active one) |
| `POST /api/profiles/{id}/activate` | POST | Switch active profile → restart |

Existing endpoints affected:
- `GET /api/kb/status` — add `profile_id` and `profile_name` to response
- `POST /api/kb/change` — becomes "change current profile's KB path" (keep for editing)
- `POST /api/kb/validate` — unchanged

### Profile Switch Flow

1. `POST /api/profiles/{id}/activate`
2. Update `profiles.json` with new active
3. Set `JARVIS_KNOWLEDGE_BASE` env var to new profile's `kb_path`
4. Respond with `{ switching: true }`
5. `os.execv` restart (same pattern as `/api/restart`)
6. On restart, `resolve_menubar_data_dir()` reads new active profile → new data_dir

### Profile Create Flow

1. `POST /api/profiles` with `{ name, kb_path }`
2. Validate kb_path (exists, readable, is directory)
3. Generate ID from name
4. Create `~/.jarvis/profiles/<id>/` directory
5. Add to profiles.json
6. Return profile (no auto-switch, no auto-index)
7. User explicitly activates to switch + first indexing happens on activation

## Frontend

### SettingsWorkspace Changes

Restructure the page into two sections:

**Section 1: Profile List**
- Cards showing each profile: name, kb_path, doc count, active badge
- Active profile has highlighted border
- Click non-active → switch confirmation dialog
- "Add Profile" button at bottom

**Section 2: Active Profile Details** (current KB status section)
- Shows detailed stats for active profile
- "Change Directory" for editing active profile's KB path (existing functionality)

### New Components

**ProfileCard**: name, path, stats preview, active indicator, delete button (only non-active)

**AddProfileDialog**: modal with name + path input, path validation (reuse existing validation)

**SwitchConfirmDialog**: warning that backend restarts, search temporarily unavailable

### Switch UX

1. Click profile card → SwitchConfirmDialog
2. Warning: "백엔드가 재시작됩니다. 2-3초간 검색이 불가능합니다."
3. If profile has no index yet: additional note "최초 전환이므로 인덱싱이 시작됩니다."
4. Confirm → POST activate → frontend sets `backendStatus = 'checking'`
5. Existing health polling auto-reconnects (2s interval during checking)
6. Reconnected → refresh profile list + KB status

### Delete UX

1. Delete button on non-active profile card
2. Confirm: "프로필 '<name>'과 인덱스 데이터가 삭제됩니다."
3. DELETE → refresh list

## Error Handling

- Delete active profile → 400 "활성 프로필은 삭제할 수 없습니다."
- Duplicate profile name → 400 "이미 존재하는 프로필 이름입니다."
- Switch during indexing → 409 "인덱싱 진행 중. 완료 후 전환해주세요."
- Invalid kb_path on create → validation errors (reuse existing)
