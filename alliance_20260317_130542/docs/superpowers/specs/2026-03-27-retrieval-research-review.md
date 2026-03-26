# Retrieval Research Review for JARVIS

Date: 2026-03-27

## Goal

Review current retrieval issues in JARVIS against primary-source research and propose a retrieval redesign that reduces heuristic leakage, improves source selection, and handles mixed document/table knowledge more reliably.

## Current JARVIS Observations

Based on the current implementation:

- [orchestrator.py](/Users/codingstudio/__PROJECTHUB__/JARVIS/alliance_20260317_130542/src/jarvis/core/orchestrator.py) mixes generic retrieval with domain-specific supplemental search.
- [planner.py](/Users/codingstudio/__PROJECTHUB__/JARVIS/alliance_20260317_130542/src/jarvis/core/planner.py) is still heuristic-first, with optional lightweight enrichment.
- [evidence_builder.py](/Users/codingstudio/__PROJECTHUB__/JARVIS/alliance_20260317_130542/src/jarvis/retrieval/evidence_builder.py) applies a growing set of hand-tuned score boosts and penalties.
- Structured table lookup, long-document lookup, and general document QA are not cleanly separated as different retrieval tasks.

This creates three failure modes:

1. Query intent leaks into low-level retrieval heuristics.
2. Numeric or lexical cues trigger the wrong retrieval path.
3. Ranking fixes are repeatedly added at the evidence layer instead of solving task routing and representation.

## Research Findings

### 1. Flat retrieval is usually not enough

Recent work argues that one-shot flat retrieval burdens a single retriever too much and reduces ceiling performance.

- FunnelRAG proposes coarse-to-fine retrieval with increasing model capacity and decreasing candidate count.
  - Source: Zhao et al., 2025. "FunnelRAG: A Coarse-to-Fine Progressive Retrieval Paradigm for RAG"
  - https://aclanthology.org/2025.findings-naacl.165/

Implication for JARVIS:

- Retrieval should not be "FTS + vector + patchy boosts" only.
- JARVIS should use staged retrieval:
  - stage 1: broad candidate recall
  - stage 2: task-specific filtering
  - stage 3: reranking

### 2. Long-document retrieval needs structure-aware or hierarchical retrieval

Several papers show that plain chunk retrieval loses document-level structure and context.

- RAPTOR retrieves over hierarchical summaries and improves complex QA.
  - Sarthi et al., 2024
  - https://openreview.net/forum?id=GN921JHCRw
- TreeRAG uses tree chunking and bidirectional traversal for long-document retrieval.
  - Tao et al., 2025
  - https://aclanthology.org/2025.findings-acl.20/
- Context is Gold to find the Gold Passage shows that chunk embeddings often fail because they ignore broader document context.
  - Conti et al., 2025
  - https://aclanthology.org/2025.emnlp-main.1150/

Implication for JARVIS:

- HWP/PDF specification documents should not be indexed only as flat chunks.
- JARVIS should retain section hierarchy:
  - document
  - heading/subheading
  - paragraph/chunk
- Retrieval should first identify the relevant section, then the relevant supporting chunk.

### 3. Table retrieval is a different problem from prose retrieval

Research on table reasoning consistently treats tables as semi-structured data, not just text passages.

- TAP4LLM argues for table sampling, augmentation, and packing instead of naive full-table or flat text prompting.
  - Sui et al., 2024
  - https://aclanthology.org/2024.findings-emnlp.603/
- H-STAR separates semantic interpretation from symbolic/structured table reasoning.
  - Abhyankar et al., 2025
  - https://aclanthology.org/2025.naacl-long.445/

Implication for JARVIS:

- Diet/menu spreadsheet lookup should not share the same retrieval path as HWP prose questions.
- Row/column lookup must be handled by a dedicated structured retrieval path.
- Generic orchestrator logic should not guess table rows from generic number mentions.

### 4. Query rewriting and expansion help, but should be model-driven or task-driven

Research supports query rewriting, but not as scattered low-level heuristics.

- HyDE shows that generated hypothetical documents can improve zero-shot dense retrieval.
  - Gao et al., 2023
  - https://aclanthology.org/2023.acl-long.99/
- BRIGHT shows that reasoning steps used as search queries can significantly improve retrieval.
  - 2024 benchmark paper
  - https://arxiv.org/pdf/2407.12883
- Q-PRM proposes adaptive query rewriting with process supervision.
  - Ye et al., 2025
  - https://aclanthology.org/2025.findings-emnlp.817/

Implication for JARVIS:

- Query rewriting belongs in a query-analysis stage, not in multiple scattered regex branches.
- If LLM resources are available, rewritten search intent or structured retrieval plans are preferable to ad hoc lexical patches.

### 5. Routing is important and should happen at the task level

Recent work supports routing between retrieval strategies rather than forcing one retrieval path to solve everything.

- Self-Route routes between RAG and long-context reasoning based on query self-reflection.
  - Li et al., 2024
  - https://aclanthology.org/2024.emnlp-industry.66/
- Query Routing for Homogeneous Tools formalizes cost-aware routing between similar tools.
  - Mu et al., 2024
  - https://aclanthology.org/2024.findings-emnlp.598/

Implication for JARVIS:

- JARVIS should route between:
  - document QA
  - structured table lookup
  - code/file lookup
  - unsupported/live-data requests
- This routing should happen before retrieval, not after retrieval mistakes.

### 6. Evaluation must diagnose retrieval separately from answer generation

If retrieval is wrong, answer quality fixes will mostly look like prompt hacks.

- RAGAs provides reference-free evaluation across retrieval and generation dimensions.
  - Es et al., 2024
  - https://aclanthology.org/2024.eacl-demo.16/
- CRUX focuses on evaluating retrieval-augmented contexts directly.
  - Ju et al., 2025
  - https://aclanthology.org/2025.findings-emnlp.1151/
- GRADE separates retriever-side and reasoning-side difficulty.
  - Lee et al., 2025
  - https://aclanthology.org/2025.findings-emnlp.236/

Implication for JARVIS:

- Retrieval evaluation must be separated from response/TTS evaluation.
- At minimum, JARVIS should track:
  - source document accuracy
  - section/chunk accuracy
  - table row/column accuracy
  - citation coverage

## Assessment of the Current Algorithm

The current retrieval design is misaligned with research in four ways.

### A. Intent and retrieval are entangled

Low-level retrieval code currently encodes decisions like:

- whether a number means a table row
- whether a chunk is explanatory
- whether certain words imply a special path

This is fragile. Research favors explicit routing or staged retrieval, not heuristic leakage across all layers.

### B. Tables and prose are mixed too early

The system currently allows structured row retrieval logic to be invoked inside general retrieval orchestration. That is exactly how document queries can drift into spreadsheet results.

### C. Ranking is compensating for representation mistakes

Evidence boosting is being used to correct:

- chunking limitations
- section awareness limitations
- document-type limitations
- intent misclassification

This is usually a sign that the retrieval representation is too flat.

### D. Retrieval evaluation is under-specified

The system has many behavioral regressions that only appear in end-to-end assistant testing. That means retrieval is not being measured independently enough.

## Recommended Retrieval Redesign

### 1. Introduce explicit retrieval task routing

The planner should output a structured retrieval task, for example:

```json
{
  "task": "document_qa",
  "entities": {
    "target_document": "한글문서 파일형식",
    "section_topic": "그리기 개체 자료 구조",
    "subtopic": "기본 구조"
  }
}
```

Other task values:

- `table_lookup`
- `code_lookup`
- `multi_doc_qa`
- `live_data_request`

This is the main place where LLM-based intent JSON belongs.

### 2. Split retrieval backends by knowledge type

Recommended backend split:

- `DocumentRetriever`
  - heading-aware and section-aware
  - optimized for PDF/HWP/DOC-like prose
- `TableRetriever`
  - row/column/field aware
  - optimized for XLSX/CSV and structured row chunks
- `CodeRetriever`
  - file/identifier aware

Generic `Orchestrator` should route to one of these, not contain table heuristics inline.

### 3. Move from flat chunk retrieval to hierarchical document retrieval

For long documents:

1. retrieve candidate documents
2. retrieve candidate sections/headings
3. retrieve supporting chunks inside the winning sections
4. rerank final evidence

This follows the spirit of RAPTOR/TreeRAG/FunnelRAG without requiring their exact architectures.

### 4. Keep hybrid retrieval, but add a stronger reranking stage

Recommended practical stack:

- stage 1 recall: BM25/FTS + dense vector retrieval
- stage 2 rerank: stronger reranker over top-k
- stage 3 answer grounding: answer only from reranked evidence

If resources permit, a late-interaction retriever or stronger reranker should replace accumulating many manual score boosts.

Reference:

- ColBERTv2 suggests that stronger retrieval interactions can improve quality without requiring only single-vector matching.
  - https://aclanthology.org/2022.naacl-main.272/

### 5. Treat query rewriting as a single explicit stage

Do not scatter rewriting across:

- STT cleanup
- planner heuristics
- retrieval regexes
- answer formatter

Instead:

1. normalize transcript
2. produce structured retrieval intent
3. optionally produce retrieval-oriented rewritten search phrases

If LLM is unavailable, a lightweight fallback can remain, but only in that one stage.

### 6. Add retrieval evaluation harnesses

Build a gold test set with categories:

- document section lookup
- table row/column lookup
- mixed greeting + task query
- numeric mention inside prose
- near-homophone STT corruption

For each query, store:

- expected source document
- expected section or table row
- expected answer span

This is necessary to stop shipping ranking tweaks based only on anecdotal assistant runs.

## Recommended Implementation Order

### Phase 1

- Move `table-row` supplemental search out of generic retrieval orchestration.
- Introduce explicit `retrieval_task`.
- Keep only minimal fallback heuristics.

### Phase 2

- Build separate `DocumentRetriever` and `TableRetriever`.
- Add section-aware document retrieval.
- Keep current hybrid recall as the first stage.

### Phase 3

- Add stronger reranking.
- Add query rewrite generation as one planner stage.
- Reduce evidence-level boost rules.

### Phase 4

- Build retrieval regression dataset and metrics dashboard.
- Evaluate source accuracy and section accuracy separately from generation quality.

## Immediate Recommendation

The highest-leverage next step is not more heuristic tuning.

It is this:

1. make the planner emit `retrieval_task`
2. split document retrieval and table retrieval
3. remove table-specific row inference from generic retrieval orchestration

That change addresses the core failure mode behind recent regressions more directly than continuing to patch evidence ranking.

## Source List

- FunnelRAG: https://aclanthology.org/2025.findings-naacl.165/
- ColBERTv2: https://aclanthology.org/2022.naacl-main.272/
- HyDE: https://aclanthology.org/2023.acl-long.99/
- RAPTOR: https://openreview.net/forum?id=GN921JHCRw
- TreeRAG: https://aclanthology.org/2025.findings-acl.20/
- TAP4LLM: https://aclanthology.org/2024.findings-emnlp.603/
- H-STAR: https://aclanthology.org/2025.naacl-long.445/
- Self-Route: https://aclanthology.org/2024.emnlp-industry.66/
- Query Routing for Homogeneous Tools: https://aclanthology.org/2024.findings-emnlp.598/
- RAGAs: https://aclanthology.org/2024.eacl-demo.16/
- CRUX: https://aclanthology.org/2025.findings-emnlp.1151/
- GRADE: https://aclanthology.org/2025.findings-emnlp.236/
- BRIGHT: https://arxiv.org/pdf/2407.12883
