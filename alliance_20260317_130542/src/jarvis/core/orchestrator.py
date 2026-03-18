# src/jarvis/core/orchestrator.py
"""Orchestrator — manages a single user turn through the JARVIS pipeline.

Per Spec Section 2.1: the call chain is:
  1. Planner.classify(query) -> intent
  2. Planner.build_retrieval_plan(query, intent) -> search terms
  3. Retriever.retrieve(query, plan) -> evidence
  4. LLM.generate(query, context, intent) -> response
  5. CitationService.enforce(response, context) -> verified response
"""
from __future__ import annotations

import re
import time

from jarvis.contracts import (
    AnswerDraft,
    ConversationTurn,
    ConversationStoreProtocol,
    EvidenceBuilderProtocol,
    FTSRetrieverProtocol,
    GovernorProtocol,
    HybridFusionProtocol,
    LLMGeneratorProtocol,
    QueryDecomposerProtocol,
    TaskLogEntry,
    TaskLogStoreProtocol,
    TaskStatus,
    ToolRegistryProtocol,
    TypedQueryFragment,
    VectorRetrieverProtocol,
    VerifiedEvidenceSet,
)
from jarvis.core.error_monitor import ErrorMonitor
from jarvis.observability.metrics import MetricName, MetricsCollector


class Orchestrator:
    """Manages one user turn end-to-end.

    Per Spec Section 2.1: integrates Planner for AI-based intent
    classification and query normalization before retrieval.
    """

    def __init__(
        self,
        *,
        governor: GovernorProtocol,
        query_decomposer: QueryDecomposerProtocol,
        fts_retriever: FTSRetrieverProtocol,
        vector_retriever: VectorRetrieverProtocol,
        hybrid_fusion: HybridFusionProtocol,
        evidence_builder: EvidenceBuilderProtocol,
        llm_generator: LLMGeneratorProtocol,
        tool_registry: ToolRegistryProtocol,
        conversation_store: ConversationStoreProtocol,
        task_log_store: TaskLogStoreProtocol,
        planner: object | None = None,
        metrics: MetricsCollector | None = None,
        error_monitor: ErrorMonitor | None = None,
    ) -> None:
        self._governor = governor
        self._query_decomposer = query_decomposer
        self._fts_retriever = fts_retriever
        self._vector_retriever = vector_retriever
        self._hybrid_fusion = hybrid_fusion
        self._evidence_builder = evidence_builder
        self._llm_generator = llm_generator
        self._tool_registry = tool_registry
        self._conversation_store = conversation_store
        self._task_log_store = task_log_store
        self._planner = planner
        self._metrics = metrics
        self._error_monitor = error_monitor

    def handle_turn(self, user_input: str) -> ConversationTurn:
        started_at = time.perf_counter()
        turn = ConversationTurn(user_input=user_input)

        # 1. Governor pre-check
        if not self._governor.check_resource_budget():
            turn.assistant_output = "시스템 리소스가 부족하여 처리할 수 없습니다."
            turn.has_evidence = False
            self._last_answer = None
            self._conversation_store.save_turn(turn)
            return turn

        # 2. Log start
        self._task_log_store.log_entry(TaskLogEntry(
            turn_id=turn.turn_id, stage="start", status=TaskStatus.RUNNING,
        ))

        # 3. Planner: AI-based query analysis (Spec Section 2.1)
        search_query = user_input
        if self._planner is not None:
            analysis = self._planner.analyze(user_input)  # type: ignore[union-attr]
            if analysis.search_terms:
                search_query = " ".join(analysis.search_terms)

        # 4. Retrieve evidence using analyzed search terms
        evidence = self._retrieve_evidence(search_query)

        # 5. If no evidence, return early
        if evidence.is_empty:
            turn.assistant_output = "관련 증거를 찾을 수 없어 답변을 생성할 수 없습니다."
            turn.has_evidence = False
            self._last_answer = None
            self._conversation_store.save_turn(turn)
            self._task_log_store.log_entry(TaskLogEntry(
                turn_id=turn.turn_id, stage="complete", status=TaskStatus.COMPLETED,
            ))
            if self._metrics is not None:
                self._metrics.record(
                    MetricName.QUERY_LATENCY_MS,
                    (time.perf_counter() - started_at) * 1000,
                    tags={"has_evidence": "false"},
                )
            return turn

        # 6. Safe mode: search-only response, no generation
        if self._error_monitor is not None and (
            self._error_monitor.safe_mode_active() or self._error_monitor.generation_blocked
        ):
            turn.assistant_output = self._build_safe_mode_response(
                evidence,
                degraded_only=not self._error_monitor.safe_mode_active(),
            )
            turn.has_evidence = True
            self._last_answer = AnswerDraft(
                content=turn.assistant_output,
                evidence=evidence,
                model_id="safe_mode" if self._error_monitor.safe_mode_active() else "degraded",
            )
            self._conversation_store.save_turn(turn)
            self._task_log_store.log_entry(TaskLogEntry(
                turn_id=turn.turn_id, stage="complete", status=TaskStatus.COMPLETED,
                metadata={"mode": "safe_mode"},
            ))
            if self._metrics is not None:
                self._metrics.record(
                    MetricName.QUERY_LATENCY_MS,
                    (time.perf_counter() - started_at) * 1000,
                    tags={
                        "has_evidence": "true",
                        "mode": "safe_mode" if self._error_monitor.safe_mode_active() else "degraded",
                    },
                )
            return turn

        # 7. Generate answer with conversation history (sliding window, 3 turns)
        recent_turns = self._conversation_store.get_recent_turns(limit=3)
        answer = self._generate_answer(user_input, evidence, recent_turns)

        # 8. Persist
        turn.assistant_output = answer.content
        turn.has_evidence = True
        self._last_answer = answer
        self._conversation_store.save_turn(turn)
        self._task_log_store.log_entry(TaskLogEntry(
            turn_id=turn.turn_id, stage="complete", status=TaskStatus.COMPLETED,
        ))
        if self._metrics is not None:
            self._metrics.record(
                MetricName.QUERY_LATENCY_MS,
                (time.perf_counter() - started_at) * 1000,
                tags={"has_evidence": "true"},
            )

        return turn

    @property
    def last_answer(self) -> AnswerDraft | None:
        """Access the last AnswerDraft for citation rendering."""
        return getattr(self, "_last_answer", None)

    # Pattern to detect filenames in queries
    _FILENAME_RE = re.compile(
        r"([\w.-]+\.(?:py|ts|tsx|js|jsx|sql|md|txt|json|yaml|yml|csv|docx|pptx|xlsx|pdf|hwp|hwpx))"
    )

    def _retrieve_evidence(self, query: str) -> VerifiedEvidenceSet:
        fragments = self._query_decomposer.decompose(query)
        if not fragments:
            return VerifiedEvidenceSet(items=(), query_fragments=())

        fts_hits = self._fts_retriever.search(fragments)
        vector_hits = self._vector_retriever.search(fragments)

        # Document-targeted search: if query mentions a filename,
        # also search within that specific document's chunks
        targeted_hits = self._targeted_file_search(query, fragments)
        if targeted_hits:
            fts_hits = targeted_hits + [h for h in fts_hits if h.chunk_id not in
                                         {t.chunk_id for t in targeted_hits}]

        hybrid_results = self._hybrid_fusion.fuse(fts_hits, vector_hits)
        evidence = self._evidence_builder.build(hybrid_results, fragments)
        return evidence

    def _targeted_file_search(
        self, query: str, fragments: list[TypedQueryFragment]
    ) -> list:
        """Search within a specific document when filename is mentioned in query.

        If the user says "pipeline.py의 함수를 알려줘", this finds pipeline.py
        in the DB and searches only its chunks, bypassing BM25 noise from
        large unrelated documents.
        """
        filenames = self._FILENAME_RE.findall(query)
        if not filenames:
            return []

        # FTSIndex has a _db attribute
        db = getattr(self._fts_retriever, "_db", None)
        if db is None:
            return []

        from jarvis.contracts import SearchHit

        targeted: list[SearchHit] = []
        for filename in filenames:
            # Find documents matching this filename
            rows = db.execute(
                "SELECT document_id FROM documents"
                " WHERE path LIKE ? AND indexing_status = 'INDEXED'",
                (f"%/{filename}",),
            ).fetchall()
            if not rows:
                # Try partial match (filename without path)
                rows = db.execute(
                    "SELECT document_id FROM documents"
                    " WHERE path LIKE ? AND indexing_status = 'INDEXED'",
                    (f"%{filename}%",),
                ).fetchall()

            for (doc_id,) in rows:
                # Get all chunks for this document, scored by keyword match
                keyword_terms = [
                    w for f in fragments if f.query_type == "keyword"
                    for w in f.text.split() if len(w) > 2
                ]

                chunk_rows = db.execute(
                    "SELECT chunk_id, document_id, text FROM chunks"
                    " WHERE document_id = ?",
                    (doc_id,),
                ).fetchall()

                for chunk_id, did, text in chunk_rows:
                    # Score by how many query terms appear in this chunk
                    matches = sum(1 for t in keyword_terms if t.lower() in text.lower())
                    if matches > 0:
                        targeted.append(SearchHit(
                            chunk_id=chunk_id,
                            document_id=did,
                            score=matches * 5.0 + 10.0,  # High base score for targeted results
                            snippet=text[:200],
                        ))

        # Sort by score descending, limit to top 5
        targeted.sort(key=lambda h: h.score, reverse=True)
        return targeted[:5]

    def _generate_answer(
        self,
        prompt: str,
        evidence: VerifiedEvidenceSet,
        recent_turns: list[ConversationTurn] | None = None,
    ) -> AnswerDraft:
        return self._llm_generator.generate(prompt, evidence, recent_turns=recent_turns)

    def _build_safe_mode_response(
        self,
        evidence: VerifiedEvidenceSet,
        *,
        degraded_only: bool = False,
    ) -> str:
        """Return a search-only response while safe mode or degraded mode is active."""
        if degraded_only:
            lines = [
                "현재 시스템이 degraded 상태입니다. 생성 기능을 일시 제한하고 검색 결과만 제공합니다.",
            ]
        else:
            lines = [
                "안전 모드입니다. 생성 기능을 일시 비활성화하고 검색 결과만 제공합니다.",
            ]
        for item in evidence.items[:3]:
            source = item.source_path or item.document_id
            snippet = item.text.strip().replace("\n", " ")
            if len(snippet) > 140:
                snippet = snippet[:140] + "..."
            lines.append(f"{item.citation.label} {source}: {snippet}")
        return "\n".join(lines)
