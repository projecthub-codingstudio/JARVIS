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
from pathlib import Path

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
    SearchHit,
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
from jarvis.query_normalization import normalize_spoken_code_query

_DESTRUCTIVE_REQUEST_PATTERNS = (
    re.compile(r"\brm\s+-rf\b", re.IGNORECASE),
    re.compile(r"\b(format|wipe|erase)\b", re.IGNORECASE),
    re.compile(r"(모두|전체).*(삭제|지워|제거)"),
    re.compile(r"(파일|폴더|디렉터리).*(전부|모두).*(삭제|제거)"),
)
_CLASS_HINT_RE = re.compile(r"(?:\bclass\b|클래스)", re.IGNORECASE)
_FUNCTION_HINT_RE = re.compile(r"(?:\bfunction\b|\bmethod\b|\bdef\b|함수|메서드|메소드)", re.IGNORECASE)
_IDENTIFIER_TOKEN_RE = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]{2,}\b")
_CODE_SCOPE_HINT_RE = re.compile(r"(?:소스|코드|파일|\.(?:py|ts|tsx|js|jsx|sql))", re.IGNORECASE)


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
        user_knowledge_store: object | None = None,
        knowledge_base_path: Path | None = None,
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
        self._user_knowledge_store = user_knowledge_store
        self._knowledge_base_path = knowledge_base_path

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
        self._extract_user_knowledge(turn)
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
        self._extract_user_knowledge(turn)
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
            targeted_chunk_ids = {t.chunk_id for t in targeted_hits}
            targeted_doc_ids = {t.document_id for t in targeted_hits}
            if self._is_explicit_file_scoped_query(query):
                fts_hits = targeted_hits + [
                    h for h in fts_hits
                    if h.chunk_id not in targeted_chunk_ids and h.document_id in targeted_doc_ids
                ]
                vector_hits = [h for h in vector_hits if h.document_id in targeted_doc_ids]
            else:
                fts_hits = targeted_hits + [h for h in fts_hits if h.chunk_id not in targeted_chunk_ids]

        # Row-ID supplemental search: when query references specific row
        # identifiers (e.g., "3일차", "Day 5"), directly query the DB for
        # matching chunks that FTS/vector may have missed.
        # This is the row-level equivalent of _targeted_file_search.
        _ROW_SUPP_RE = re.compile(r"(\d+)\s*(?:일\s*차|일차|일|번째|day|번)", re.IGNORECASE)
        query_row_ids = set(_ROW_SUPP_RE.findall(query))
        meal_fields = self._table_field_hints(query)
        use_structured_row_lookup = self._should_use_structured_row_lookup(query, meal_fields)
        if query_row_ids and use_structured_row_lookup:
            db = getattr(self._fts_retriever, "_db", None)
            if db is not None:
                existing_ids = {h.chunk_id for h in fts_hits} | {h.chunk_id for h in vector_hits}
                supplemental_hits: list[SearchHit] = []
                for rid in query_row_ids:
                    rows = db.execute(
                        "SELECT chunk_id, document_id, text FROM chunks"
                        " WHERE heading_path LIKE 'table-row-%'"
                        " AND text LIKE ?",
                        (f"%Day={rid} |%",),
                    ).fetchall()
                    for chunk_id, doc_id, text in rows:
                        if chunk_id not in existing_ids:
                            supplemental_hits.append(SearchHit(
                                chunk_id=chunk_id,
                                document_id=doc_id,
                                score=50.0,
                                snippet=text[:200],
                            ))
                            existing_ids.add(chunk_id)
                if supplemental_hits:
                    fts_hits = supplemental_hits + [h for h in fts_hits if h.chunk_id not in existing_ids]

        # Table field supplemental search: when query asks for a specific
        # meal/column inside a numbered plan row, directly surface that row.
        if query_row_ids and meal_fields:
            db = getattr(self._fts_retriever, "_db", None)
            if db is not None:
                existing_ids = {h.chunk_id for h in fts_hits} | {h.chunk_id for h in vector_hits}
                table_hits: list[SearchHit] = []
                for rid in query_row_ids:
                    for meal_field in meal_fields:
                        rows = db.execute(
                            "SELECT chunk_id, document_id, text FROM chunks"
                            " WHERE heading_path LIKE 'table-row-%'"
                            " AND text LIKE ?"
                            " AND text LIKE ?",
                            (f"%Day={rid} |%", f"%{meal_field}=%"),
                        ).fetchall()
                        for chunk_id, doc_id, text in rows:
                            if chunk_id not in existing_ids:
                                table_hits.append(SearchHit(
                                    chunk_id=chunk_id,
                                    document_id=doc_id,
                                    score=100.0,
                                    snippet=text[:200],
                                ))
                                existing_ids.add(chunk_id)
                if table_hits:
                    fts_hits = table_hits + [h for h in fts_hits if h.chunk_id not in existing_ids]

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

            pre_rerank_results = list(hybrid_results)
            hybrid_results = self._reranker.rerank(
                query,
                hybrid_results,
                top_k=runtime_decision.max_retrieved_chunks,
                chunk_texts=chunk_texts,
            )

            # Protect row-matched chunks: if query mentions specific day/row
            # numbers, ensure those chunks survive reranking even if they
            # were ranked below the top_k cutoff.
            _ROW_NUM_RE = re.compile(r"(\d+)\s*(?:일\s*차|일차|일|번째|day|번)", re.IGNORECASE)
            query_numbers = _ROW_NUM_RE.findall(query)
            if query_numbers:
                reranked_ids = {r.chunk_id for r in hybrid_results}
                for r in pre_rerank_results:
                    if r.chunk_id in reranked_ids:
                        continue
                    ct = chunk_texts.get(r.chunk_id, "")
                    for num in query_numbers:
                        if f"Day={num} " in ct or f"Day={num}|" in ct:
                            hybrid_results.append(r)
                            reranked_ids.add(r.chunk_id)
                            break

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

        normalized_query = normalize_spoken_code_query(
            query,
            knowledge_base_path=self._knowledge_base_path,
        )
        filenames = self._FILENAME_RE.findall(normalized_query)
        # Also detect underscore-separated stems and space-separated variants
        filenames.extend(_extract_filenames(normalized_query))
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
        wants_class = bool(_CLASS_HINT_RE.search(normalized_query))
        wants_function = bool(_FUNCTION_HINT_RE.search(normalized_query))
        identifier_terms = {
            token for token in _IDENTIFIER_TOKEN_RE.findall(normalized_query)
            if "." not in token and len(token) > 2
        }
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
                    signature_boost = 0.0
                    if wants_class and any(
                        re.search(rf"\bclass\s+{re.escape(term)}\b", text, re.IGNORECASE)
                        for term in identifier_terms
                    ):
                        signature_boost += 12.0
                    if wants_function and any(
                        re.search(rf"\b(?:def|function)\s+{re.escape(term)}\b", text, re.IGNORECASE)
                        for term in identifier_terms
                    ):
                        signature_boost += 10.0
                    if matches > 0 or signature_boost > 0:
                        targeted.append(SearchHit(
                            chunk_id=chunk_id,
                            document_id=did,
                            score=matches * 5.0 + 10.0 + signature_boost,  # Prefer exact file/signature hits
                            snippet=text[:200],
                        ))

        # Sort by score descending, limit to top 5
        targeted.sort(key=lambda h: h.score, reverse=True)
        return targeted[:5]

    @staticmethod
    def _table_field_hints(query: str) -> list[str] | None:
        lowered = query.lower()
        field_aliases = {
            "Breakfast": ("아침", "조식", "breakfast"),
            "Lunch": ("점심", "중식", "lunch"),
            "Dinner": ("저녁", "석식", "dinner"),
            "Drinks": ("음료", "drink", "drinks"),
            "Morning Supplements": ("아침 보충제", "morning supplement"),
            "Lunch Supplements": ("점심 보충제", "lunch supplement"),
            "Evening Supplements": ("저녁 보충제", "evening supplement"),
        }
        matched_fields: list[str] = []
        for field, aliases in field_aliases.items():
            if any(alias in lowered for alias in aliases):
                matched_fields.append(field)
        return matched_fields or None

    @staticmethod
    def _should_use_structured_row_lookup(query: str, meal_fields: list[str] | None) -> bool:
        lowered = query.lower()
        if meal_fields:
            return True

        table_context_terms = (
            "식단표",
            "식단",
            "메뉴",
            "표",
            "행",
            "열",
            "row",
            "column",
            "day ",
            "day=",
        )
        if any(term in lowered for term in table_context_terms):
            return True

        return False

    def _extract_user_knowledge(self, turn: ConversationTurn) -> None:
        """Extract and store user knowledge from a completed turn (Tier 3 memory)."""
        if self._user_knowledge_store is None:
            return
        try:
            from jarvis.memory.user_knowledge import extract_knowledge

            entries = extract_knowledge(
                turn.user_input, turn.assistant_output or "",
                turn_id=turn.turn_id,
            )
            upsert = getattr(self._user_knowledge_store, "upsert", None)
            if callable(upsert):
                for entry in entries:
                    upsert(entry)
        except Exception:
            pass  # Knowledge extraction failure should never block the main flow

    def _get_user_knowledge_context(self) -> str:
        """Get formatted user knowledge for LLM prompt injection."""
        if self._user_knowledge_store is None:
            return ""
        fmt = getattr(self._user_knowledge_store, "format_for_prompt", None)
        if callable(fmt):
            return fmt(max_entries=8)
        return ""

    def _generate_answer(
        self,
        prompt: str,
        evidence: VerifiedEvidenceSet,
        recent_turns: list[ConversationTurn] | None = None,
    ) -> AnswerDraft:
        # Inject user knowledge into prompt if available
        knowledge_ctx = self._get_user_knowledge_context()
        if knowledge_ctx:
            prompt = f"{knowledge_ctx}\n\n{prompt}"
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

    def _is_explicit_file_scoped_query(self, query: str) -> bool:
        normalized_query = normalize_spoken_code_query(
            query,
            knowledge_base_path=self._knowledge_base_path,
        )
        has_filename = bool(self._FILENAME_RE.search(normalized_query))
        if not has_filename:
            return False
        return bool(
            _CODE_SCOPE_HINT_RE.search(normalized_query)
            or _CLASS_HINT_RE.search(normalized_query)
            or _FUNCTION_HINT_RE.search(normalized_query)
        )
