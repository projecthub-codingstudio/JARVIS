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

    def handle_turn(self, user_input: str) -> ConversationTurn:
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
            return turn

        # 6. Generate answer with conversation history (sliding window, 3 turns)
        recent_turns = self._conversation_store.get_recent_turns(limit=3)
        answer = self._generate_answer(user_input, evidence, recent_turns)

        # 7. Persist
        turn.assistant_output = answer.content
        turn.has_evidence = True
        self._last_answer = answer
        self._conversation_store.save_turn(turn)
        self._task_log_store.log_entry(TaskLogEntry(
            turn_id=turn.turn_id, stage="complete", status=TaskStatus.COMPLETED,
        ))

        return turn

    @property
    def last_answer(self) -> AnswerDraft | None:
        """Access the last AnswerDraft for citation rendering."""
        return getattr(self, "_last_answer", None)

    def _retrieve_evidence(self, query: str) -> VerifiedEvidenceSet:
        fragments = self._query_decomposer.decompose(query)
        if not fragments:
            return VerifiedEvidenceSet(items=(), query_fragments=())

        fts_hits = self._fts_retriever.search(fragments)
        vector_hits = self._vector_retriever.search(fragments)
        hybrid_results = self._hybrid_fusion.fuse(fts_hits, vector_hits)
        evidence = self._evidence_builder.build(hybrid_results, fragments)
        return evidence

    def _generate_answer(
        self,
        prompt: str,
        evidence: VerifiedEvidenceSet,
        recent_turns: list[ConversationTurn] | None = None,
    ) -> AnswerDraft:
        return self._llm_generator.generate(prompt, evidence, recent_turns=recent_turns)
