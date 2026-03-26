"""Tests for JARVIS service socket path helpers."""

from __future__ import annotations

from pathlib import Path

from jarvis.service.socket_path import resolve_socket_path


def test_resolve_socket_path_uses_env_override(monkeypatch, tmp_path: Path) -> None:
    custom = tmp_path / "custom.sock"
    monkeypatch.setenv("JARVIS_SERVICE_SOCKET", str(custom))

    assert resolve_socket_path() == custom.resolve()


def test_resolve_socket_path_defaults_to_tempfile(monkeypatch) -> None:
    monkeypatch.delenv("JARVIS_SERVICE_SOCKET", raising=False)

    path = resolve_socket_path()

    assert path.name == "jarvis_service.sock"
