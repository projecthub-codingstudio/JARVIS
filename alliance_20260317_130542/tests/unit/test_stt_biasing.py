from __future__ import annotations

import sqlite3
from pathlib import Path

from jarvis.runtime.stt_biasing import build_vocabulary_hint


def test_build_vocabulary_hint_includes_indexed_chunk_terms(tmp_path: Path, monkeypatch) -> None:
    workdir = tmp_path / "workspace"
    workdir.mkdir()
    kb = workdir / "knowledge_base"
    kb.mkdir()
    (kb / "dummy.py").write_text("class Pipeline:\n    pass\n", encoding="utf-8")

    data_dir = workdir / ".jarvis-menubar"
    data_dir.mkdir()
    db_path = data_dir / "jarvis.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE chunks (chunk_id TEXT, text TEXT)")
    conn.execute(
        "INSERT INTO chunks (chunk_id, text) VALUES (?, ?)",
        ("chunk-1", "Day=9 | Dinner=순두부+김+피망 | Breakfast=구운계란2+요거트+베리"),
    )
    conn.commit()
    conn.close()

    monkeypatch.chdir(workdir)

    hint = build_vocabulary_hint(kb)

    assert "헤이 자비스" in hint
    assert "순두부" in hint
    assert "피망" in hint
    assert "Dinner" in hint
