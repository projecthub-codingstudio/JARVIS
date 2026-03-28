from __future__ import annotations

from pathlib import Path

from jarvis.runtime_paths import resolve_alliance_root, resolve_menubar_data_dir


def test_resolve_menubar_data_dir_prefers_explicit_env(monkeypatch, tmp_path: Path) -> None:
    configured = tmp_path / "custom-menubar"
    monkeypatch.setenv("JARVIS_MENUBAR_DATA_DIR", str(configured))
    monkeypatch.delenv("JARVIS_ALLIANCE_ROOT", raising=False)

    assert resolve_menubar_data_dir(tmp_path / "ignored") == configured.resolve()


def test_resolve_menubar_data_dir_falls_back_to_alliance_root(monkeypatch, tmp_path: Path) -> None:
    alliance_root = tmp_path / "alliance"
    monkeypatch.delenv("JARVIS_MENUBAR_DATA_DIR", raising=False)
    monkeypatch.setenv("JARVIS_ALLIANCE_ROOT", str(alliance_root))

    assert resolve_alliance_root() == alliance_root.resolve()
    assert resolve_menubar_data_dir() == (alliance_root / ".jarvis-menubar").resolve()
