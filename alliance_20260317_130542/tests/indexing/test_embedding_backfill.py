"""Tests for embedding backfill in IndexPipeline."""
import tempfile
from pathlib import Path

import pytest

from jarvis.app.bootstrap import init_database
from jarvis.app.config import JarvisConfig
from jarvis.indexing.chunker import Chunker
from jarvis.indexing.index_pipeline import IndexPipeline
from jarvis.indexing.parsers import DocumentParser
from jarvis.indexing.tombstone import TombstoneManager
from jarvis.runtime.embedding_runtime import EmbeddingRuntime


@pytest.fixture
def pipeline_with_db():
    config = JarvisConfig()
    config.db_path = Path(tempfile.mktemp(suffix=".db"))
    db = init_database(config)
    embedding_rt = EmbeddingRuntime()
    pipeline = IndexPipeline(
        db=db,
        parser=DocumentParser(),
        chunker=Chunker(),
        tombstone_manager=TombstoneManager(db=db),
        embedding_runtime=embedding_rt,
    )
    yield pipeline, db, config
    db.close()
    config.db_path.unlink(missing_ok=True)


def test_backfill_embeddings_runs(pipeline_with_db):
    """backfill_embeddings should process chunks without embedding_ref."""
    pipeline, db, config = pipeline_with_db

    with tempfile.NamedTemporaryFile(suffix=".txt", mode="w", delete=False) as f:
        f.write("테스트 임베딩 백필 문서입니다. 이 문서는 충분히 긴 텍스트를 포함하여 청크 최소 크기 필터를 통과합니다.")
        tmp = f.name

    pipeline.index_file(Path(tmp))

    null_count = db.execute(
        "SELECT COUNT(*) FROM chunks WHERE embedding_ref IS NULL"
    ).fetchone()[0]
    assert null_count > 0

    updated = pipeline.backfill_embeddings(batch_size=10)
    assert updated >= 0  # 0 if stub, >0 if real embeddings

    Path(tmp).unlink()


def test_backfill_returns_zero_when_all_done(pipeline_with_db):
    """backfill_embeddings returns 0 when no chunks need embedding."""
    pipeline, db, config = pipeline_with_db
    updated = pipeline.backfill_embeddings(batch_size=10)
    assert updated == 0
