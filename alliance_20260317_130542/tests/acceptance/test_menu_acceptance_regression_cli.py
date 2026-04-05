from __future__ import annotations

from jarvis.cli import menu_acceptance_regression


def test_default_fixture_path_points_to_repo_fixture() -> None:
    path = menu_acceptance_regression._default_fixture_path()

    assert path.name == "menu_acceptance_regression_v1.json"
    assert path.exists()
