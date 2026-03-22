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
import logging
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor

_logger = logging.getLogger(__name__)

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

_DESTRUCTIVE_REQUEST_PATTERNS = (
    re.compile(r"\brm\s+-rf\b", re.IGNORECASE),
    re.compile(r"\b(format|wipe|erase)\b", re.IGNORECASE),
    re.compile(r"(모두|전체).*(삭제|지워|제거)"),
    re.compile(r"(파일|폴더|디렉터리).*(전부|모두).*(삭제|제거)"),
)


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
        reranker: object | None = None,
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
        self._reranker = reranker
        self._metrics = metrics
        self._error_monitor = error_monitor
        self._query_complexity: str = "moderate"

    def handle_turn(self, user_input: str) -> ConversationTurn:
        started_at = time.perf_counter()
        turn = ConversationTurn(user_input=user_input)

        if self._is_destructive_request(user_input):
            turn.assistant_output = (
                "파괴적이거나 대량 삭제로 이어질 수 있는 요청은 안전 정책상 수행할 수 없습니다."
            )
            turn.has_evidence = False
            self._conversation_store.save_turn(turn)
            self._task_log_store.log_entry(TaskLogEntry(
                turn_id=turn.turn_id,
                stage="blocked",
                status=TaskStatus.SKIPPED,
                metadata={"reason": "hard_kill"},
            ))
            return turn

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
            # Complexity classification for model routing
            classify = getattr(self._planner, "classify_complexity", None)
            if callable(classify):
                self._query_complexity = classify(user_input)

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

    def handle_turn_stream(self, user_input: str) -> Iterator[str | ConversationTurn]:
        """Stream a turn — yields tokens then a final ConversationTurn.

        Retrieval is synchronous. Only the LLM generation phase streams.
        The last yielded item is always a ConversationTurn.
        """
        started_at = time.perf_counter()
        turn = ConversationTurn(user_input=user_input)

        # Safety, governor, planner checks (same as handle_turn)
        if self._is_destructive_request(user_input):
            turn.assistant_output = (
                "파괴적이거나 대량 삭제로 이어질 수 있는 요청은 안전 정책상 수행할 수 없습니다."
            )
            turn.has_evidence = False
            self._conversation_store.save_turn(turn)
            yield turn
            return

        if not self._governor.check_resource_budget():
            turn.assistant_output = "시스템 리소스가 부족하여 처리할 수 없습니다."
            turn.has_evidence = False
            self._conversation_store.save_turn(turn)
            yield turn
            return

        self._task_log_store.log_entry(TaskLogEntry(
            turn_id=turn.turn_id, stage="start", status=TaskStatus.RUNNING,
        ))

        search_query = user_input
        if self._planner is not None:
            analysis = self._planner.analyze(user_input)  # type: ignore[union-attr]
            if analysis.search_terms:
                search_query = " ".join(analysis.search_terms)
            classify = getattr(self._planner, "classify_complexity", None)
            if callable(classify):
                self._query_complexity = classify(user_input)

        evidence = self._retrieve_evidence(search_query)

        if evidence.is_empty:
            turn.assistant_output = "관련 증거를 찾을 수 없어 답변을 생성할 수 없습니다."
            turn.has_evidence = False
            self._conversation_store.save_turn(turn)
            self._task_log_store.log_entry(TaskLogEntry(
                turn_id=turn.turn_id, stage="complete", status=TaskStatus.COMPLETED,
            ))
            yield turn
            return

        # Stream LLM generation
        recent_turns = self._conversation_store.get_recent_turns(limit=3)
        generate_stream = getattr(self._llm_generator, "generate_stream", None)

        if callable(generate_stream):
            full_text_parts: list[str] = []
            answer: AnswerDraft | None = None

            for item in generate_stream(user_input, evidence, recent_turns=recent_turns):
                if isinstance(item, str):
                    full_text_parts.append(item)
                    yield item
                else:
                    # AnswerDraft sentinel
                    answer = item

            if answer is None:
                # Shouldn't happen, but handle gracefully
                from jarvis.runtime.mlx_runtime import strip_think_tags
                answer = AnswerDraft(
                    content=strip_think_tags("".join(full_text_parts)),
                    evidence=evidence,
                    model_id="unknown",
                )
        else:
            # No streaming — fall back to non-streaming
            answer = self._generate_answer(user_input, evidence, recent_turns)

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
                tags={"has_evidence": "true", "streaming": "true"},
            )
        yield turn

    @property
    def last_answer(self) -> AnswerDraft | None:
        """Access the last AnswerDraft for citation rendering."""
        return getattr(self, "_last_answer", None)

    # Pattern to detect filenames in queries
    _FILENAME_RE = re.compile(
        r"([\w.-]+\.(?:py|ts|tsx|js|jsx|sql|md|txt|json|yaml|yml|csv|docx|pptx|xlsx|pdf|hwp|hwpx))"
    )

    def _retrieve_evidence(self, query: str) -> VerifiedEvidenceSet:
        retrieval_start = time.perf_counter()
        fragments = self._query_decomposer.decompose(query)
        if not fragments:
            return VerifiedEvidenceSet(items=(), query_fragments=())

        runtime_decision = self._resolve_runtime_decision()
        retrieval_top_k = max(4, runtime_decision.max_retrieved_chunks * 2)

        search_start = time.perf_counter()
        try:
            with ThreadPoolExecutor(max_workers=2) as executor:
                fts_future = executor.submit(self._fts_retriever.search, fragments, retrieval_top_k)
                vector_future = executor.submit(self._vector_retriever.search, fragments, retrieval_top_k)
                fts_hits = fts_future.result()
                vector_hits = vector_future.result()
        except Exception:
            _logger.warning("Parallel search failed, falling back to sequential")
            fts_hits = self._fts_retriever.search(fragments, retrieval_top_k)
            vector_hits = self._vector_retriever.search(fragments, retrieval_top_k)
        search_ms = (time.perf_counter() - search_start) * 1000

        # Document-targeted search: if query mentions a filename,
        # also search within that specific document's chunks
        targeted_hits = self._targeted_file_search(query, fragments)
        if targeted_hits:
            fts_hits = targeted_hits + [h for h in fts_hits if h.chunk_id not in
                                         {t.chunk_id for t in targeted_hits}]

        hybrid_results = self._hybrid_fusion.fuse(
            fts_hits,
            vector_hits,
            # Fetch more candidates for reranker to filter
            top_k=runtime_decision.max_retrieved_chunks * 2 if self._reranker else runtime_decision.max_retrieved_chunks,
        )

        # Rerank if available: cross-encoder re-scores candidates
        if self._reranker is not None and hasattr(self._reranker, "rerank"):
            # Fetch chunk texts for better reranking (snippets may be truncated)
            chunk_texts: dict[str, str] = {}
            db = getattr(self._fts_retriever, "_db", None)
            if db is not None:
                for r in hybrid_results:
                    row = db.execute(
                        "SELECT text FROM chunks WHERE chunk_id = ?", (r.chunk_id,)
                    ).fetchone()
                    if row:
                        chunk_texts[r.chunk_id] = row[0]

            hybrid_results = self._reranker.rerank(
                query,
                hybrid_results,
                top_k=runtime_decision.max_retrieved_chunks,
                chunk_texts=chunk_texts,
            )

        evidence = self._evidence_builder.build(hybrid_results, fragments)
        if len(evidence.items) > runtime_decision.max_retrieved_chunks:
            evidence = VerifiedEvidenceSet(
                items=evidence.items[:runtime_decision.max_retrieved_chunks],
                query_fragments=evidence.query_fragments,
            )

        retrieval_ms = (time.perf_counter() - retrieval_start) * 1000
        _logger.info(
            "Retrieval: search=%.0fms total=%.0fms fts=%d vector=%d fused=%d",
            search_ms, retrieval_ms, len(fts_hits), len(vector_hits),
            len(hybrid_results),
        )
        if self._metrics is not None:
            self._metrics.record(
                MetricName.QUERY_LATENCY_MS, search_ms,
                tags={"stage": "parallel_search"},
            )
        return evidence

    def _targeted_file_search(
        self, query: str, fragments: list[TypedQueryFragment]
    ) -> list:
        """Search within a specific document when filename is mentioned in query.

        Handles both exact filenames ("pipeline.py") and space-separated
        references ("14day diet supplements final" → 14day_diet_supplements_final).
        """
        from jarvis.retrieval.query_decomposer import _extract_filenames

        filenames = self._FILENAME_RE.findall(query)
        # Also detect underscore-separated stems and space-separated variants
        filenames.extend(_extract_filenames(query))
        # Deduplicate
        filenames = list(dict.fromkeys(filenames))
        if not filenames:
            return []

        # FTSIndex has a _db attribute
        db = getattr(self._fts_retriever, "_db", None)
        if db is None:
            return []

        from jarvis.contracts import SearchHit

        targeted: list[SearchHit] = []
        for filename in filenames:
            # Find documents matching this filename (exact path ending)
            rows = db.execute(
                "SELECT document_id FROM documents"
                " WHERE path LIKE ? AND indexing_status = 'INDEXED'",
                (f"%/{filename}",),
            ).fetchall()
            if not rows:
                # Try partial match (filename without path, stem match)
                rows = db.execute(
                    "SELECT document_id FROM documents"
                    " WHERE path LIKE ? AND indexing_status = 'INDEXED'",
                    (f"%{filename}%",),
                ).fetchall()
            if not rows:
                # Try space→underscore conversion
                underscore_name = filename.replace(" ", "_").replace("-", "_")
                if underscore_name != filename:
                    rows = db.execute(
                        "SELECT document_id FROM documents"
                        " WHERE path LIKE ? AND indexing_status = 'INDEXED'",
                        (f"%{underscore_name}%",),
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

    def _resolve_runtime_decision(self):
        select_runtime = getattr(self._governor, "select_runtime", None)
        if callable(select_runtime):
            requested_tier = "balanced"
            suggest_idle = getattr(self._governor, "suggest_idle_requested_tier", None)
            if callable(suggest_idle):
                requested_tier = suggest_idle()
            if self._error_monitor is not None and self._error_monitor.degraded_mode:
                requested_tier = "fast"
            # Complexity-based tier adjustment
            complexity = getattr(self, "_query_complexity", "moderate")
            if complexity == "complex" and requested_tier != "fast":
                requested_tier = "deep"
            elif complexity == "simple" and requested_tier == "deep":
                requested_tier = "balanced"
            return select_runtime(requested_tier)

        class _FallbackDecision:
            max_retrieved_chunks = 4 if self._governor.should_degrade() else 8

        return _FallbackDecision()

    @staticmethod
    def _is_destructive_request(user_input: str) -> bool:
        text = user_input.strip()
        if not text:
            return False
        return any(pattern.search(text) for pattern in _DESTRUCTIVE_REQUEST_PATTERNS)
