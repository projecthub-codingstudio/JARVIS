# JARVIS Decisions

## Fixed Decisions

- Product scope stays `local-first workspace agent`.
- Retrieval stays `SQLite FTS5 + vector index + RRF`.
- Korean tokenizer default stays `Kiwi`.
- Default generation tier stays `14B-class`; deeper tier is explicit or Governor-driven.
- Phase 1 tool surface stays limited to `read_file`, `search_files`, `draft_export`.
- Writes remain approval-gated.
- Voice and menu bar layers remain local wrappers over the Python core.

## Explicit Deferrals

- `MeCab-ko` is not the default path.
- `cross-encoder reranker` is deferred until retrieval quality requires it.
- Broad automation, accessibility-driven UI control, and unrestricted shell execution remain out of scope.

## Runtime Safety

- Governor may reduce context and retrieved chunk count under pressure.
- Repeated model/index failures can degrade generation or force search-only mode.
- SQLite integrity failures force read-only behavior and rebuild recommendation.
