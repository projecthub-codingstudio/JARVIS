from __future__ import annotations

from jarvis.cli import retrieval_regression


def test_default_fixture_path_points_to_repo_fixture() -> None:
    path = retrieval_regression._default_fixture_path()

    assert path.name == "retrieval_regression_v1.json"
    assert path.exists()
