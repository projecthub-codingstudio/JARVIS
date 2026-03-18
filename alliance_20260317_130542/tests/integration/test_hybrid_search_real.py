"""Integration test: full hybrid search with FTS + vector."""
import tempfile
from pathlib import Path

import pytest

from jarvis.app.bootstrap import init_database
from jarvis.app.config import JarvisConfig
from jarvis.indexing.chunker import Chunker
from jarvis.indexing.index_pipeline import IndexPipeline
from jarvis.indexing.parsers import DocumentParser
from jarvis.indexing.tombstone import TombstoneManager
from jarvis.retrieval.fts_index import FTSIndex
from jarvis.retrieval.hybrid_search import HybridSearch
from jarvis.retrieval.query_decomposer import QueryDecomposer
from jarvis.retrieval.vector_index import VectorIndex
from jarvis.runtime.embedding_runtime import EmbeddingRuntime


@pytest.fixture
def indexed_db():
    """Create a DB with indexed test documents."""
    config = JarvisConfig()
    config.db_path = Path(tempfile.mktemp(suffix=".db"))
    db = init_database(config)

    embedding_rt = EmbeddingRuntime()
    vector_idx = VectorIndex(
        db_path=Path(tempfile.mkdtemp()) / "test.lance",
        embedding_runtime=embedding_rt,
    )

    pipeline = IndexPipeline(
        db=db, parser=DocumentParser(), chunker=Chunker(),
        tombstone_manager=TombstoneManager(db=db),
        embedding_runtime=embedding_rt,
        vector_index=vector_idx,
    )

    # Create test files
    tmpdir = Path(tempfile.mkdtemp())
    (tmpdir / "python_guide.txt").write_text(
        "Python은 간결하고 읽기 쉬운 프로그래밍 언어입니다. 데이터 분석과 웹 개발에 널리 사용됩니다."
    )
    (tmpdir / "database_design.txt").write_text(
        "데이터베이스 설계에서 정규화는 중요한 개념입니다. 테이블 간의 관계를 정의합니다."
    )

    for f in tmpdir.iterdir():
        pipeline.index_file(f)

    # Backfill embeddings
    pipeline.backfill_embeddings(batch_size=10)

    yield db, vector_idx, embedding_rt
    embedding_rt.unload_model()
    db.close()
    config.db_path.unlink(missing_ok=True)


def test_hybrid_search_returns_fts_results(indexed_db):
    """Hybrid search should at minimum return FTS results."""
    db, vector_idx, _ = indexed_db

    decomposer = QueryDecomposer()
    fts = FTSIndex(db=db)
    hybrid = HybridSearch()

    fragments = decomposer.decompose("Python 프로그래밍")
    fts_hits = fts.search(fragments)
    vector_hits = vector_idx.search(fragments)

    # FTS should always find results (keyword match)
    assert len(fts_hits) > 0

    # Hybrid should combine both
    results = hybrid.fuse(fts_hits, vector_hits)
    assert len(results) > 0


def test_fts_only_works_without_vectors(indexed_db):
    """When vector index returns empty, hybrid still works via FTS."""
    db, _, _ = indexed_db

    decomposer = QueryDecomposer()
    fts = FTSIndex(db=db)
    empty_vector = VectorIndex()  # No embedding runtime — always returns []
    hybrid = HybridSearch()

    fragments = decomposer.decompose("데이터베이스 설계")
    fts_hits = fts.search(fragments)
    vector_hits = empty_vector.search(fragments)

    assert vector_hits == []
    results = hybrid.fuse(fts_hits, vector_hits)
    assert len(results) > 0  # FTS carries the search alone
