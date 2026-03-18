# Release Notes — 2026-03-19

## Summary

This update moves JARVIS from a CLI-first local RAG prototype to a much more complete desktop workflow:

- Phase 1 runtime, retrieval, observability, tools, and benchmark paths are now implemented
- A macOS menu bar app now exists with a persistent Python bridge
- Voice file mode, push-to-talk once, live voice loop, approval-based export, and health status are wired into the menu bar UI

## Included Commits

- `b53ef19` feat: add macOS menu bar UI and persistent bridge
- `8e8dadb` feat: complete phase1 runtime, retrieval, and observability
- `57421cd` docs: refresh root README for current main status

## Highlights

### Phase 1 completion

- Real tool execution for `read_file`, `search_files`, and `draft_export`
- Model router and runtime safety controls
- Error monitor with degraded mode, safe mode, generation blocking, and write blocking
- Health checks, structured logging, metrics contract alignment, and runtime metric emission
- 50-query benchmark harness and report path
- Hybrid retrieval with FTS + vector search and evidence assembly improvements

### Menu bar UI

- SwiftUI menu bar shell under `alliance_20260317_130542/macos/JarvisMenuBar/`
- Long-running Python bridge over stdin/stdout JSON
- Text ask flow
- Push-to-talk once
- Live voice loop with cooldown, backoff, and auto-stop after repeated errors
- Approval-based draft export UI
- Startup and health status display with per-check details

### Stability

- Governor sampling now tolerates `psutil` permission and OS errors
- Menu bar bridge suppresses non-critical stderr noise
- Export UI now supports location presets, format selection, and overwrite warning

## Validation

- Project venv test result: `320 passed, 13 warnings`
- Menu bar Swift package builds successfully with `swift build`

## Known Gaps

- Voice path still needs additional background polish
- Health reporting can be refined further
- Some optional local dependencies remain conditional, so behavior may degrade to fallback mode depending on environment
