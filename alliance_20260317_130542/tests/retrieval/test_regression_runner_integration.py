from __future__ import annotations

from pathlib import Path
from typing import Sequence

from jarvis.app.bootstrap import init_database
from jarvis.app.config import JarvisConfig
from jarvis.core.governor import GovernorStub
from jarvis.core.orchestrator import Orchestrator
from jarvis.core.planner import Planner
from jarvis.core.tool_registry import ToolRegistry
from jarvis.indexing.chunker import Chunker
from jarvis.indexing.index_pipeline import IndexPipeline
from jarvis.indexing.parsers import DocumentParser
from jarvis.indexing.tombstone import TombstoneManager
from jarvis.memory.conversation_store import ConversationStore
from jarvis.memory.task_log import TaskLogStore
from jarvis.retrieval.evidence_builder import EvidenceBuilder
from jarvis.retrieval.fts_index import FTSIndex
from jarvis.retrieval.hybrid_search import HybridSearch
from jarvis.retrieval.query_decomposer import QueryDecomposer
from jarvis.retrieval.regression_runner import RetrievalRegressionCase, run_regression_suite
from jarvis.retrieval.vector_index import VectorIndex
from jarvis.runtime.mlx_runtime import MLXRuntime


class FakeEmbeddingRuntime:
    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [[0.0] * 8 for _ in texts]


def test_regression_runner_with_real_orchestrator_path(tmp_path: Path) -> None:
    config = JarvisConfig(watched_folders=[tmp_path], data_dir=tmp_path / ".jarvis")
    db = init_database(config)
    pipeline = IndexPipeline(
        db=db,
        parser=DocumentParser(),
        chunker=Chunker(max_chunk_bytes=512, overlap_bytes=64),
        tombstone_manager=TombstoneManager(db=db),
        embedding_runtime=FakeEmbeddingRuntime(),
    )
    (tmp_path / "hwp-format.md").write_text(
        "# 그리기 개체 자료 구조\n\n## 기본 구조\n\n"
        "그리기 개체는 여러 개의 개체를 하나의 틀로 묶을 수 있기 때문에 파일상에는 다음과 같은 구조로 저장된다.",
        encoding="utf-8",
    )
    (tmp_path / "diet-plan.txt").write_text(
        "Day=3 | Breakfast=구운계란2+요거트+베리 | Lunch=닭가슴살+현미밥1/3+김2장 | Dinner=순두부+방울토마토\n",
        encoding="utf-8",
    )
    for file_path in tmp_path.iterdir():
        if file_path.is_file():
            pipeline.index_file(file_path)

    planner = Planner(lightweight_backend=None)
    orchestrator = Orchestrator(
        governor=GovernorStub(),
        query_decomposer=QueryDecomposer(),
        fts_retriever=FTSIndex(db=db),
        vector_retriever=VectorIndex(),
        hybrid_fusion=HybridSearch(),
        evidence_builder=EvidenceBuilder(db=db),
        llm_generator=MLXRuntime(),
        tool_registry=ToolRegistry(),
        conversation_store=ConversationStore(db=db),
        task_log_store=TaskLogStore(db=db),
        planner=planner,
    )

    cases = [
        RetrievalRegressionCase(
            case_id="doc-local",
            query="그리기 개체 자료 구조 기본 구조 설명",
            expected_retrieval_task="document_qa",
            category="document_section_lookup",
            expected_source_suffix="hwp-format.md",
            expected_heading_keywords=("그리기 개체", "기본 구조"),
        ),
    ]

    report = run_regression_suite(
        cases=cases,
        planner=planner,
        retrieve_fn=lambda query, analysis: orchestrator._retrieve_evidence(query, analysis=analysis),
    )

    assert report.total_cases == 1
    assert report.task_accuracy == 1.0
    assert report.source_accuracy == 1.0
    assert report.section_accuracy == 1.0
