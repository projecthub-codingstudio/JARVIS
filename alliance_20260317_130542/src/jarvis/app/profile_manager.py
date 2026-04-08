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
    env = os.getenv("JARVIS_PROFILES_ROOT", "").strip()
    if env:
        return Path(env)
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
    from jarvis.runtime_paths import resolve_alliance_root

    kb_path = str(resolve_knowledge_base_path())
    profile = Profile(id="default", name="Default", kb_path=kb_path)
    config = ProfileConfig(active="default", profiles=[profile])

    # Migrate existing data into profiles/default/
    # Check legacy locations in priority order:
    #   1. alliance_root/.jarvis-menubar (web API mode — most likely to have current data)
    #   2. ~/.jarvis (CLI mode)
    legacy_candidates = [
        resolve_alliance_root() / ".jarvis-menubar",
        Path.home() / ".jarvis",
    ]
    legacy_dir = None
    for candidate in legacy_candidates:
        if (candidate / "jarvis.db").exists():
            legacy_dir = candidate
            break

    profile_dir = _profiles_dir() / "default"
    profile_dir.mkdir(parents=True, exist_ok=True)

    if legacy_dir is not None:
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
