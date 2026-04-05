"""Persistent state for intent/skill profiles and unmapped request backlog."""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import re
from typing import Any
import uuid
from zoneinfo import ZoneInfo

from jarvis.runtime_paths import resolve_menubar_data_dir
from jarvis.service.intent_skill_registry import IntentSkillEntry, load_intent_skill_registry

_SEOUL_TZ = ZoneInfo("Asia/Seoul")
_WEEKDAY_LABELS = ("월", "화", "수", "목", "금", "토", "일")
_SKILL_ID_RE = re.compile(r"[^a-z0-9_.-]+")


def _skills_dir() -> Path:
    path = resolve_menubar_data_dir() / "skills"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _profiles_path() -> Path:
    return _skills_dir() / "skill_profiles.v1.json"


def _default_profiles_path() -> Path:
    return Path(__file__).with_name("default_skill_profiles.v1.json")


def _backlog_path() -> Path:
    return _skills_dir() / "skill_backlog.v1.json"


def _action_maps_path() -> Path:
    return _skills_dir() / "action_maps.v1.json"


def _now() -> datetime:
    return datetime.now(_SEOUL_TZ)


def _now_iso() -> str:
    return _now().isoformat()


def _weekday_label(moment: datetime) -> str:
    return _WEEKDAY_LABELS[moment.weekday()]


def _read_json(path: Path, *, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return json.loads(json.dumps(default))
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return json.loads(json.dumps(default))
    return payload if isinstance(payload, dict) else json.loads(json.dumps(default))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _profiles_payload() -> dict[str, Any]:
    return _read_json(
        _profiles_path(),
        default={"version": "2026-04-04", "profiles": {}},
    )


def _default_profiles_payload() -> dict[str, Any]:
    return _read_json(
        _default_profiles_path(),
        default={"version": "2026-04-04", "profiles": {}},
    )


def _backlog_payload() -> dict[str, Any]:
    return _read_json(
        _backlog_path(),
        default={"version": "2026-04-04", "entries": []},
    )


def _action_maps_payload() -> dict[str, Any]:
    return _read_json(
        _action_maps_path(),
        default={"version": "2026-04-04", "maps": []},
    )


def _normalize_string(value: object) -> str:
    return str(value or "").strip()


def _normalize_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = _normalize_string(item)
        if not text or text in seen:
            continue
        seen.add(text)
        normalized.append(text)
    return normalized


def _normalize_custom_fields(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    normalized: dict[str, str] = {}
    for key, raw_value in value.items():
        normalized_key = _normalize_string(key)
        normalized_value = _normalize_string(raw_value)
        if not normalized_key or not normalized_value:
            continue
        normalized[normalized_key] = normalized_value
    return normalized


def _slugify_skill_id(value: str) -> str:
    lowered = value.strip().lower()
    if not lowered:
        return ""
    slug = _SKILL_ID_RE.sub("_", lowered).strip("._-")
    slug = re.sub(r"_+", "_", slug)
    return slug


def _registry_entries_by_skill() -> dict[str, list[IntentSkillEntry]]:
    grouped: dict[str, list[IntentSkillEntry]] = {}
    for entry in load_intent_skill_registry().entries:
        grouped.setdefault(entry.skill_id, []).append(entry)
    return grouped


def _skill_title(skill_id: str, entries: list[IntentSkillEntry], profile: dict[str, Any]) -> str:
    if _normalize_string(profile.get("title")):
        return _normalize_string(profile.get("title"))
    if entries:
        first = entries[0]
        return first.skill_id.replace("_", " ").strip().title()
    return skill_id.replace("_", " ").strip().title() or skill_id


def _detect_local_app_installed(app_name: str) -> bool:
    normalized_name = app_name.strip().lower().replace(" ", "")
    if not normalized_name:
        return False
    roots = (Path("/Applications"), Path.home() / "Applications")
    for root in roots:
        if not root.exists():
            continue
        try:
            candidates = root.glob("*.app")
        except Exception:
            continue
        for candidate in candidates:
            stem = candidate.stem.strip().lower().replace(" ", "")
            if not stem:
                continue
            if stem == normalized_name or normalized_name in stem or stem in normalized_name:
                return True
    return False


def list_skill_profiles() -> dict[str, dict[str, Any]]:
    def _normalize_profiles(profiles: object) -> dict[str, dict[str, Any]]:
        if not isinstance(profiles, dict):
            return {}
        normalized: dict[str, dict[str, Any]] = {}
        for key, value in profiles.items():
            skill_id = _slugify_skill_id(_normalize_string(key))
            if not skill_id or not isinstance(value, dict):
                continue
            normalized[skill_id] = {
                "skill_id": skill_id,
                "title": _normalize_string(value.get("title")),
                "parent_skill_id": _slugify_skill_id(_normalize_string(value.get("parent_skill_id"))),
                "summary": _normalize_string(value.get("summary")),
                "local_app_name": _normalize_string(value.get("local_app_name")),
                "local_app_installed": value.get("local_app_installed")
                if isinstance(value.get("local_app_installed"), bool)
                else None,
                "launch_target": _normalize_string(value.get("launch_target")),
                "open_supported": bool(value.get("open_supported", False)),
                "local_notes": _normalize_string(value.get("local_notes")),
                "api_provider": _normalize_string(value.get("api_provider")),
                "api_configured": bool(value.get("api_configured", False)),
                "api_scopes": _normalize_string_list(value.get("api_scopes")),
                "api_notes": _normalize_string(value.get("api_notes")),
                "notes": _normalize_string(value.get("notes")),
                "tags": _normalize_string_list(value.get("tags")),
                "linked_intents": _normalize_string_list(value.get("linked_intents")),
                "custom_fields": _normalize_custom_fields(value.get("custom_fields")),
                "created_at": _normalize_string(value.get("created_at")),
                "updated_at": _normalize_string(value.get("updated_at")),
                "is_custom": bool(value.get("is_custom", False)),
            }
        return normalized

    default_profiles = _normalize_profiles(_default_profiles_payload().get("profiles"))
    user_profiles = _normalize_profiles(_profiles_payload().get("profiles"))
    normalized: dict[str, dict[str, Any]] = {}
    normalized.update(default_profiles)
    normalized.update(user_profiles)
    return normalized


def upsert_skill_profile(skill_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    normalized_skill_id = _slugify_skill_id(skill_id)
    if not normalized_skill_id:
        raise ValueError("skill_id is required")

    profiles_payload = _profiles_payload()
    profiles = list_skill_profiles()
    existing = profiles.get(normalized_skill_id, {})
    timestamp = _now_iso()
    next_profile = {
        "skill_id": normalized_skill_id,
        "title": _normalize_string(payload.get("title") if "title" in payload else existing.get("title")),
        "parent_skill_id": _slugify_skill_id(
            _normalize_string(payload.get("parent_skill_id") if "parent_skill_id" in payload else existing.get("parent_skill_id"))
        ),
        "summary": _normalize_string(payload.get("summary") if "summary" in payload else existing.get("summary")),
        "local_app_name": _normalize_string(payload.get("local_app_name") if "local_app_name" in payload else existing.get("local_app_name")),
        "local_app_installed": payload.get("local_app_installed")
        if isinstance(payload.get("local_app_installed"), bool)
        else existing.get("local_app_installed"),
        "launch_target": _normalize_string(payload.get("launch_target") if "launch_target" in payload else existing.get("launch_target")),
        "open_supported": bool(payload.get("open_supported")) if "open_supported" in payload else bool(existing.get("open_supported", False)),
        "local_notes": _normalize_string(payload.get("local_notes") if "local_notes" in payload else existing.get("local_notes")),
        "api_provider": _normalize_string(payload.get("api_provider") if "api_provider" in payload else existing.get("api_provider")),
        "api_configured": bool(payload.get("api_configured")) if "api_configured" in payload else bool(existing.get("api_configured", False)),
        "api_scopes": _normalize_string_list(payload.get("api_scopes")) if "api_scopes" in payload else _normalize_string_list(existing.get("api_scopes")),
        "api_notes": _normalize_string(payload.get("api_notes") if "api_notes" in payload else existing.get("api_notes")),
        "notes": _normalize_string(payload.get("notes") if "notes" in payload else existing.get("notes")),
        "tags": _normalize_string_list(payload.get("tags")) if "tags" in payload else _normalize_string_list(existing.get("tags")),
        "linked_intents": _normalize_string_list(payload.get("linked_intents")) if "linked_intents" in payload else _normalize_string_list(existing.get("linked_intents")),
        "custom_fields": _normalize_custom_fields(payload.get("custom_fields")) if "custom_fields" in payload else _normalize_custom_fields(existing.get("custom_fields")),
        "created_at": _normalize_string(existing.get("created_at")) or timestamp,
        "updated_at": timestamp,
        "is_custom": bool(payload.get("is_custom")) if "is_custom" in payload else bool(existing.get("is_custom", False)),
    }

    raw_profiles = profiles_payload.get("profiles")
    if not isinstance(raw_profiles, dict):
        raw_profiles = {}
    raw_profiles[normalized_skill_id] = next_profile
    profiles_payload["profiles"] = raw_profiles
    _write_json(_profiles_path(), profiles_payload)
    return next_profile


def create_skill_profile(payload: dict[str, Any]) -> dict[str, Any]:
    normalized_skill_id = _slugify_skill_id(_normalize_string(payload.get("skill_id")))
    if not normalized_skill_id:
        raise ValueError("skill_id is required")
    profiles = list_skill_profiles()
    if normalized_skill_id in profiles:
        raise ValueError(f"skill_id already exists: {normalized_skill_id}")
    next_payload = dict(payload)
    next_payload["is_custom"] = True
    return upsert_skill_profile(normalized_skill_id, next_payload)


def list_skill_backlog() -> list[dict[str, Any]]:
    payload = _backlog_payload()
    entries = payload.get("entries")
    if not isinstance(entries, list):
        return []
    normalized_entries = [entry for entry in entries if isinstance(entry, dict)]
    normalized_entries.sort(key=lambda item: _normalize_string(item.get("last_seen_at")), reverse=True)
    return normalized_entries


def _normalize_action_map_nodes(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    nodes: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        skill_id = _slugify_skill_id(_normalize_string(item.get("skill_id")))
        if not skill_id:
            continue
        node_id = _normalize_string(item.get("node_id")) or f"node_{uuid.uuid4().hex[:8]}"
        nodes.append(
            {
                "node_id": node_id,
                "skill_id": skill_id,
                "title": _normalize_string(item.get("title")) or skill_id.replace("_", " ").title(),
                "x": float(item.get("x", 40) or 40),
                "y": float(item.get("y", 40) or 40),
                "config": _normalize_custom_fields(item.get("config")),
            }
        )
    return nodes


def _normalize_action_map_edges(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    edges: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        source = _normalize_string(item.get("source"))
        target = _normalize_string(item.get("target"))
        if not source or not target:
            continue
        edges.append(
            {
                "edge_id": _normalize_string(item.get("edge_id")) or f"edge_{uuid.uuid4().hex[:8]}",
                "source": source,
                "target": target,
                "label": _normalize_string(item.get("label")),
            }
        )
    return edges


def list_action_maps() -> list[dict[str, Any]]:
    payload = _action_maps_payload()
    maps = payload.get("maps")
    if not isinstance(maps, list):
        return []
    normalized_maps = [item for item in maps if isinstance(item, dict)]
    normalized_maps.sort(key=lambda item: _normalize_string(item.get("updated_at")), reverse=True)
    return normalized_maps


def upsert_action_map(map_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    normalized_map_id = _slugify_skill_id(map_id)
    if not normalized_map_id:
        raise ValueError("map_id is required")

    maps_payload = _action_maps_payload()
    existing_maps = list_action_maps()
    existing = next((item for item in existing_maps if _normalize_string(item.get("map_id")) == normalized_map_id), {})
    timestamp = _now_iso()
    next_map = {
        "map_id": normalized_map_id,
        "title": _normalize_string(payload.get("title") if "title" in payload else existing.get("title")) or normalized_map_id.replace("_", " ").title(),
        "description": _normalize_string(payload.get("description") if "description" in payload else existing.get("description")),
        "trigger_query": _normalize_string(payload.get("trigger_query") if "trigger_query" in payload else existing.get("trigger_query")),
        "notes": _normalize_string(payload.get("notes") if "notes" in payload else existing.get("notes")),
        "tags": _normalize_string_list(payload.get("tags")) if "tags" in payload else _normalize_string_list(existing.get("tags")),
        "nodes": _normalize_action_map_nodes(payload.get("nodes")) if "nodes" in payload else _normalize_action_map_nodes(existing.get("nodes")),
        "edges": _normalize_action_map_edges(payload.get("edges")) if "edges" in payload else _normalize_action_map_edges(existing.get("edges")),
        "created_at": _normalize_string(existing.get("created_at")) or timestamp,
        "updated_at": timestamp,
    }

    raw_maps = maps_payload.get("maps")
    if not isinstance(raw_maps, list):
        raw_maps = []
    found_index = next(
        (index for index, item in enumerate(raw_maps) if isinstance(item, dict) and _normalize_string(item.get("map_id")) == normalized_map_id),
        None,
    )
    if found_index is None:
        raw_maps.append(next_map)
    else:
        raw_maps[found_index] = next_map
    raw_maps.sort(key=lambda item: _normalize_string(item.get("updated_at")), reverse=True)
    maps_payload["maps"] = raw_maps
    _write_json(_action_maps_path(), maps_payload)
    return next_map


def create_action_map(payload: dict[str, Any]) -> dict[str, Any]:
    normalized_map_id = _slugify_skill_id(_normalize_string(payload.get("map_id")))
    if not normalized_map_id:
        raise ValueError("map_id is required")
    if any(_normalize_string(item.get("map_id")) == normalized_map_id for item in list_action_maps()):
        raise ValueError(f"map_id already exists: {normalized_map_id}")
    return upsert_action_map(normalized_map_id, payload)


_ACTION_MAP_MATCH_STOPWORDS = {
    "실행",
    "실행해",
    "실행해줘",
    "열어",
    "열어줘",
    "시작",
    "시작해",
    "시작해줘",
    "재생",
    "재생해",
    "재생해줘",
    "줘",
    "좀",
    "please",
}


def _normalize_match_text(value: object) -> str:
    lowered = _normalize_string(value).lower()
    if not lowered:
        return ""
    lowered = re.sub(r"[^a-z0-9가-힣]+", " ", lowered)
    return " ".join(lowered.split())


def _match_tokens(value: object) -> list[str]:
    return [
        token
        for token in _normalize_match_text(value).split()
        if len(token) >= 2 and token not in _ACTION_MAP_MATCH_STOPWORDS
    ]


def _coerce_bool(value: object, *, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    normalized = _normalize_string(value).lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _ordered_action_map_nodes(action_map: dict[str, Any]) -> list[dict[str, Any]]:
    nodes = [item for item in action_map.get("nodes", []) if isinstance(item, dict)]
    if len(nodes) <= 1:
        return nodes

    nodes_by_id = {str(node.get("node_id", "")).strip(): node for node in nodes if str(node.get("node_id", "")).strip()}
    order_index = {node_id: index for index, node_id in enumerate(nodes_by_id.keys())}
    indegree = {node_id: 0 for node_id in nodes_by_id}
    adjacency: dict[str, list[str]] = {node_id: [] for node_id in nodes_by_id}

    for edge in action_map.get("edges", []):
        if not isinstance(edge, dict):
            continue
        source = _normalize_string(edge.get("source"))
        target = _normalize_string(edge.get("target"))
        if source not in nodes_by_id or target not in nodes_by_id:
            continue
        adjacency[source].append(target)
        indegree[target] += 1

    queue = sorted((node_id for node_id, degree in indegree.items() if degree == 0), key=lambda node_id: order_index[node_id])
    ordered_ids: list[str] = []
    while queue:
        current = queue.pop(0)
        ordered_ids.append(current)
        for target in adjacency.get(current, []):
            indegree[target] -= 1
            if indegree[target] == 0:
                queue.append(target)
                queue.sort(key=lambda node_id: order_index[node_id])

    for node_id in nodes_by_id:
        if node_id not in ordered_ids:
            ordered_ids.append(node_id)
    return [nodes_by_id[node_id] for node_id in ordered_ids]


def _action_map_match_score(query: str, action_map: dict[str, Any]) -> int:
    normalized_query = _normalize_match_text(query)
    if not normalized_query:
        return 0

    trigger_query = _normalize_match_text(action_map.get("trigger_query"))
    title = _normalize_match_text(action_map.get("title"))
    best = 0

    for candidate, score in ((trigger_query, 120), (title, 70)):
        if not candidate:
            continue
        if candidate == normalized_query:
            best = max(best, score + 20)
            continue
        if candidate in normalized_query or normalized_query in candidate:
            best = max(best, score)

    trigger_tokens = _match_tokens(trigger_query)
    query_tokens = set(_match_tokens(normalized_query))
    if trigger_tokens and query_tokens:
        hits = sum(1 for token in trigger_tokens if token in query_tokens)
        if hits == len(trigger_tokens):
            best = max(best, 105 if len(trigger_tokens) >= 2 else 85)
        elif len(trigger_tokens) >= 2 and hits >= len(trigger_tokens) - 1:
            best = max(best, 82)

    return best


def resolve_action_map_for_query(query: str) -> dict[str, Any] | None:
    best_map: dict[str, Any] | None = None
    best_score = 0
    for action_map in list_action_maps():
        score = _action_map_match_score(query, action_map)
        if score < 80:
            continue
        if best_map is None or score > best_score:
            best_map = action_map
            best_score = score
    if best_map is None:
        return None
    resolved = dict(best_map)
    resolved["match_score"] = best_score
    return resolved


def build_action_map_execution_plan(query: str) -> dict[str, Any] | None:
    action_map = resolve_action_map_for_query(query)
    if action_map is None:
        return None

    catalog = build_skill_catalog()
    skills_by_id = {
        str(skill.get("skill_id", "")).strip(): skill
        for skill in catalog.get("skills", [])
        if isinstance(skill, dict) and str(skill.get("skill_id", "")).strip()
    }

    steps: list[dict[str, Any]] = []
    for index, node in enumerate(_ordered_action_map_nodes(action_map), start=1):
        skill_id = _slugify_skill_id(_normalize_string(node.get("skill_id")))
        if not skill_id:
            continue
        skill = skills_by_id.get(skill_id, {})
        config = node.get("config") if isinstance(node.get("config"), dict) else {}
        mode = _normalize_string(config.get("mode") or config.get("action_mode") or config.get("step_type")).lower()
        local_app_name = _normalize_string(config.get("local_app_name")) or _normalize_string(skill.get("local_app_name"))
        launch_target = _normalize_string(config.get("launch_target")) or _normalize_string(skill.get("launch_target")) or local_app_name
        open_supported = _coerce_bool(config.get("open_supported"), default=bool(skill.get("open_supported", False)))
        api_provider = _normalize_string(config.get("api_provider")) or _normalize_string(skill.get("api_provider"))
        api_configured = _coerce_bool(config.get("api_configured"), default=bool(skill.get("api_configured", False)))

        effective_local_app_installed = skill.get("effective_local_app_installed")
        if isinstance(config.get("local_app_installed"), bool):
            effective_local_app_installed = bool(config.get("local_app_installed"))
        elif not isinstance(effective_local_app_installed, bool) and local_app_name:
            effective_local_app_installed = _detect_local_app_installed(local_app_name)

        execution_kind = "manual"
        status = "manual"
        status_reason = "manual_step"
        if mode in {"api", "remote"} and api_provider:
            execution_kind = "api_call"
            if api_configured:
                status = "api_ready"
                status_reason = "api_configured"
            else:
                status = "blocked"
                status_reason = "api_not_configured"
        elif open_supported and launch_target:
            execution_kind = "launch"
            is_url = launch_target.lower().startswith(("http://", "https://"))
            if is_url or effective_local_app_installed or not local_app_name:
                status = "ready_to_launch"
                status_reason = "launch_target_ready"
            else:
                status = "blocked"
                status_reason = "local_app_missing"
        elif api_provider:
            execution_kind = "api_call"
            if api_configured:
                status = "api_ready"
                status_reason = "api_configured"
            else:
                status = "blocked"
                status_reason = "api_not_configured"

        steps.append(
            {
                "index": index,
                "node_id": _normalize_string(node.get("node_id")),
                "skill_id": skill_id,
                "title": _normalize_string(node.get("title")) or _normalize_string(skill.get("title")) or skill_id.replace("_", " " ).title(),
                "execution_kind": execution_kind,
                "status": status,
                "status_reason": status_reason,
                "mode": mode,
                "open_supported": open_supported,
                "local_app_name": local_app_name,
                "launch_target": launch_target,
                "effective_local_app_installed": bool(effective_local_app_installed),
                "api_provider": api_provider,
                "api_configured": api_configured,
                "config": config,
            }
        )

    return {
        "map_id": _normalize_string(action_map.get("map_id")),
        "title": _normalize_string(action_map.get("title")) or _normalize_string(action_map.get("map_id")),
        "description": _normalize_string(action_map.get("description")),
        "trigger_query": _normalize_string(action_map.get("trigger_query")),
        "match_score": int(action_map.get("match_score", 0) or 0),
        "matched_query": " ".join(query.split()).strip(),
        "tags": _normalize_string_list(action_map.get("tags")),
        "notes": _normalize_string(action_map.get("notes")),
        "steps": steps,
        "node_count": len(steps),
        "edge_count": len([edge for edge in action_map.get("edges", []) if isinstance(edge, dict)]),
    }


def _query_key(query: str) -> str:
    return " ".join(query.lower().split()).strip()


def record_unmapped_request(
    *,
    query: str,
    session_id: str,
    response_payload: dict[str, Any],
) -> dict[str, Any]:
    normalized_query = " ".join(query.split()).strip()
    if not normalized_query:
        raise ValueError("query is required")

    payload = _backlog_payload()
    raw_entries = payload.get("entries")
    if not isinstance(raw_entries, list):
        raw_entries = []

    moment = _now()
    date_key = moment.strftime("%Y-%m-%d")
    hour_key = moment.strftime("%H")
    weekday_key = _weekday_label(moment)
    key = _query_key(normalized_query)
    status = response_payload.get("status") if isinstance(response_payload.get("status"), dict) else {}
    directive = response_payload.get("guide_directive") if isinstance(response_payload.get("guide_directive"), dict) else {}
    response_text = _normalize_string(response_payload.get("response"))

    existing_index = next(
        (index for index, entry in enumerate(raw_entries) if isinstance(entry, dict) and _normalize_string(entry.get("query_key")) == key),
        None,
    )

    if existing_index is None:
        entry: dict[str, Any] = {
            "query_key": key,
            "query_text": normalized_query,
            "query_samples": [normalized_query],
            "occurrence_count": 0,
            "first_seen_at": moment.isoformat(),
            "last_seen_at": moment.isoformat(),
            "last_session_id": session_id,
            "session_ids": [],
            "weekday_histogram": {},
            "hour_histogram": {},
            "date_histogram": {},
            "last_status_mode": _normalize_string(status.get("mode")),
            "last_response_text": response_text,
            "inferred_intent": _normalize_string(directive.get("intent")),
            "review_state": "new",
            "suggested_skill_id": "",
        }
        raw_entries.append(entry)
    else:
        entry = raw_entries[existing_index]

    entry["occurrence_count"] = int(entry.get("occurrence_count", 0) or 0) + 1
    entry["last_seen_at"] = moment.isoformat()
    entry["last_session_id"] = session_id
    entry["last_status_mode"] = _normalize_string(status.get("mode"))
    entry["last_response_text"] = response_text
    entry["inferred_intent"] = _normalize_string(directive.get("intent"))

    session_ids = _normalize_string_list(entry.get("session_ids"))
    if session_id and session_id not in session_ids:
        session_ids.append(session_id)
    entry["session_ids"] = session_ids[-12:]

    query_samples = _normalize_string_list(entry.get("query_samples"))
    if normalized_query not in query_samples:
        query_samples.append(normalized_query)
    entry["query_samples"] = query_samples[-6:]

    weekday_histogram = entry.get("weekday_histogram") if isinstance(entry.get("weekday_histogram"), dict) else {}
    weekday_histogram[weekday_key] = int(weekday_histogram.get(weekday_key, 0) or 0) + 1
    entry["weekday_histogram"] = weekday_histogram

    hour_histogram = entry.get("hour_histogram") if isinstance(entry.get("hour_histogram"), dict) else {}
    hour_histogram[hour_key] = int(hour_histogram.get(hour_key, 0) or 0) + 1
    entry["hour_histogram"] = hour_histogram

    date_histogram = entry.get("date_histogram") if isinstance(entry.get("date_histogram"), dict) else {}
    date_histogram[date_key] = int(date_histogram.get(date_key, 0) or 0) + 1
    entry["date_histogram"] = date_histogram

    raw_entries.sort(key=lambda item: _normalize_string(item.get("last_seen_at")), reverse=True)
    payload["entries"] = raw_entries
    _write_json(_backlog_path(), payload)
    return entry


def _linked_intent_payload(entry: IntentSkillEntry) -> dict[str, Any]:
    return {
        "intent_id": entry.intent_id,
        "category": entry.category,
        "response_kind": entry.response_kind,
        "implementation_status": entry.implementation_status,
        "requires_live_data": entry.requires_live_data,
        "requires_retrieval": entry.requires_retrieval,
        "automation_ready": entry.automation_ready,
        "example_queries": list(entry.example_queries),
    }


def build_skill_catalog() -> dict[str, Any]:
    registry = load_intent_skill_registry()
    profiles = list_skill_profiles()
    by_skill = _registry_entries_by_skill()
    all_skill_ids = sorted(set(by_skill) | set(profiles))

    skills: list[dict[str, Any]] = []
    for skill_id in all_skill_ids:
        entries = by_skill.get(skill_id, [])
        profile = profiles.get(skill_id, {})
        linked_intents = [_linked_intent_payload(entry) for entry in entries]
        linked_intent_ids = [entry["intent_id"] for entry in linked_intents]
        for extra_intent in _normalize_string_list(profile.get("linked_intents")):
            if extra_intent not in linked_intent_ids:
                linked_intent_ids.append(extra_intent)

        example_queries: list[str] = []
        seen_queries: set[str] = set()
        for entry in entries:
            for query in entry.example_queries:
                if query in seen_queries:
                    continue
                seen_queries.add(query)
                example_queries.append(query)
        local_app_name = _normalize_string(profile.get("local_app_name"))
        detected_local_app_installed = _detect_local_app_installed(local_app_name)
        manual_install_flag = profile.get("local_app_installed")
        effective_local_app_installed = (
            bool(manual_install_flag)
            if isinstance(manual_install_flag, bool)
            else detected_local_app_installed
        )
        statuses = sorted({entry.implementation_status for entry in entries}) or ["custom"]
        categories = sorted({entry.category for entry in entries}) or ["custom"]
        requires_live_data = any(entry.requires_live_data for entry in entries)
        requires_retrieval = any(entry.requires_retrieval for entry in entries)
        automation_ready = any(entry.automation_ready for entry in entries)
        response_kinds = sorted({entry.response_kind for entry in entries})
        source_kind = "custom"
        if entries and profile:
            source_kind = "hybrid"
        elif entries:
            source_kind = "registry"

        skills.append(
            {
                "skill_id": skill_id,
                "title": _skill_title(skill_id, entries, profile),
                "parent_skill_id": _normalize_string(profile.get("parent_skill_id")),
                "summary": _normalize_string(profile.get("summary")),
                "categories": categories,
                "implementation_statuses": statuses,
                "requires_live_data": requires_live_data,
                "requires_retrieval": requires_retrieval,
                "automation_ready": automation_ready,
                "response_kinds": response_kinds,
                "example_queries": example_queries[:6],
                "linked_intents": linked_intents,
                "linked_intent_ids": linked_intent_ids,
                "local_app_name": local_app_name,
                "local_app_installed": manual_install_flag,
                "detected_local_app_installed": detected_local_app_installed,
                "effective_local_app_installed": effective_local_app_installed,
                "launch_target": _normalize_string(profile.get("launch_target")),
                "open_supported": bool(profile.get("open_supported", False)),
                "local_notes": _normalize_string(profile.get("local_notes")),
                "api_provider": _normalize_string(profile.get("api_provider")),
                "api_configured": bool(profile.get("api_configured", False)),
                "api_scopes": _normalize_string_list(profile.get("api_scopes")),
                "api_notes": _normalize_string(profile.get("api_notes")),
                "notes": _normalize_string(profile.get("notes")),
                "tags": _normalize_string_list(profile.get("tags")),
                "custom_fields": _normalize_custom_fields(profile.get("custom_fields")),
                "created_at": _normalize_string(profile.get("created_at")),
                "updated_at": _normalize_string(profile.get("updated_at")),
                "source_kind": source_kind,
            }
        )

    categories: list[dict[str, Any]] = []
    for category in sorted({category for skill in skills for category in skill.get("categories", [])}):
        categories.append(
            {
                "category": category,
                "count": sum(1 for skill in skills if category in skill.get("categories", [])),
            }
        )

    implemented_count = len([entry for entry in registry.entries if entry.implementation_status == "implemented"])
    backlog_entries = list_skill_backlog()
    return {
        "registry_version": registry.version,
        "generated_at": _now_iso(),
        "implemented_intent_count": implemented_count,
        "planned_intent_count": len(registry.backlog_entries()),
        "skill_count": len(skills),
        "categories": categories,
        "skills": skills,
        "backlog": backlog_entries[:24],
    }
