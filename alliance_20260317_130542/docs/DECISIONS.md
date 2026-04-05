# JARVIS Decisions

## Fixed Decisions

- Product scope stays `local-first workspace agent`.
- Retrieval stays `SQLite FTS5 + vector index + RRF`.
- Korean tokenizer default stays `Kiwi`.
- Default generation tier stays `14B-class`; deeper tier is explicit or Governor-driven.
- Phase 1 tool surface stays limited to `read_file`, `search_files`, `draft_export`.
- Writes remain approval-gated.
- Voice and menu bar layers remain local wrappers over the Python core.
- Voice/menu-bar regressions are handled by `stage classification -> single-owner fix -> regression fixture update`, not by scattering symptom patches across layers.
- Transcript repair remains a Python-owned stage; Swift consumes repaired payloads and must not become a second source of truth for semantic STT fixes.

## Explicit Deferrals

- `MeCab-ko` is not the default path.
- `cross-encoder reranker` is deferred until retrieval quality requires it.
- Broad automation, accessibility-driven UI control, and unrestricted shell execution remain out of scope.
- VAD (Silero VAD, silence-aware recording) deferred to Phase 2.
- Streaming LLM response deferred to Phase 2.
- Apple SFSpeechRecognizer and Siri Shortcuts evaluation deferred to Phase 2.

## Runtime Safety

- Governor may reduce context and retrieved chunk count under pressure.
- Repeated model/index failures can degrade generation or force search-only mode.
- SQLite integrity failures force read-only behavior and rebuild recommendation.

## Regression Policy

- Wrong final answers are treated as pipeline bugs, not just UI/TTS bugs.
- Failures should be classified into one primary stage:
  `STT`, `transcript_repair`, `planner`, `retrieval`, `response_rendering`, `spoken_response`, or `tts_playback`.
- Repeatable failures should be added to fixture-backed regression sets.
- Retrieval/source regressions live in [`tests/fixtures/retrieval_regression_v1.json`](../tests/fixtures/retrieval_regression_v1.json).
- End-user menu-bar voice regressions live in [`tests/fixtures/menu_acceptance_regression_v1.json`](../tests/fixtures/menu_acceptance_regression_v1.json).
