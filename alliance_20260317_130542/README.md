# JARVIS Beta 1

Local-first workspace AI agent for Apple Silicon.

## Beta 1 Scope

- Python core with hybrid retrieval (`SQLite FTS5 + vector search + freshness`)
- Approval-gated draft export
- Governor-based runtime safety and degraded/search-only fallback
- CLI REPL, file-based voice mode, push-to-talk once, menu bar bridge
- Health, metrics, task logging, and indexing pipeline

## Beta 1 Non-Goals

- Microphone device selection
- Avatar voice personas
- Microphone level animation / live capture UI polish
- Full live voice assistant UX
- Cross-encoder reranker and MeCab-ko default path

## Validation

- Full test suite: `335 passed`
- Recommended command: `alliance_20260317_130542/.venv/bin/python -m pytest -q alliance_20260317_130542/tests`
- Optional parser dependency tests now skip when the local environment does not have the library installed

## Docs

- [Agent Notes](AGENTS.md)
- [Decisions](docs/DECISIONS.md)
- [Release Notes](docs/RELEASE_NOTES_BETA_1.md)
- [Known Issues](docs/KNOWN_ISSUES_BETA_1.md)
- [Beta Checklist](docs/BETA_1_CHECKLIST.md)
- [Next UI / Voice Backlog](docs/NEXT_ITERATION_UI_VOICE.md)
- [Audit Report](docs/AUDIT_REPORT_20260318.md)
