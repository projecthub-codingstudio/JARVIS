"""Tests for the JARVIS service entrypoint."""

from __future__ import annotations

from jarvis.service.__main__ import main


def test_service_main_defaults_to_stdio(monkeypatch) -> None:
    monkeypatch.delenv("JARVIS_SERVICE_TRANSPORT", raising=False)
    monkeypatch.setattr("jarvis.service.__main__.stdio_main", lambda: 11)
    monkeypatch.setattr("jarvis.service.__main__.socket_main", lambda: 22)

    assert main([]) == 11


def test_service_main_selects_socket(monkeypatch) -> None:
    monkeypatch.setattr("jarvis.service.__main__.stdio_main", lambda: 11)
    monkeypatch.setattr("jarvis.service.__main__.socket_main", lambda: 22)

    assert main(["--transport=socket"]) == 22
