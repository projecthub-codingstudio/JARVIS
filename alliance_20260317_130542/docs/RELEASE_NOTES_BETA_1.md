# JARVIS Beta 1 Release Notes

## Release

- Version: `0.1.0-beta1`
- Date: `2026-03-19`
- Status: `Beta 1 baseline complete`

## Included in Beta 1

- Hybrid retrieval with FTS, vector search, and freshness handling
- Evidence-backed answer flow with citation rendering
- Approval-gated draft export path
- Governor-driven runtime safety, degraded mode, and search-only fallback
- Indexing pipeline with binary/text parser coverage and real-time file watching
- Menu bar bridge with persistent Python runtime integration
- Voice file input and push-to-talk-once microphone flow
- Health checks, metrics capture, and task logging

## Stabilization Completed

- Health status semantics aligned between Python core and menu bar payload
- Vector DB health check updated to reflect actual `VectorIndex` behavior
- Microphone permission preflight added for macOS push-to-talk flow
- Parser runtime now degrades gracefully when optional libraries are missing
- Parser tests now skip cleanly when optional local dependencies are unavailable

## Post-Beta Updates (2026-03-21)

- Native microphone recording via Swift AVCaptureDevice (replaces ffmpeg subprocess)
- Microphone device selection with Unicode NFC/NFD normalization
- Audio-input entitlement for TCC microphone access
- `<think>` tag stripping from Qwen3 LLM output
- Dynamic max_tokens calculation (replaces fixed 512)
- Citation relevance threshold (MIN_RELEVANCE_SCORE = 0.15)
- Long response truncation with "...more" and temp file storage
- Inline export approval panel (prevents window dismiss)
- Quit button with ⌘Q shortcut
- `transcribe-file` bridge command for native recording → whisper-cli pipeline

## Deferred to Phase 2

- VAD (silence-aware recording) and streaming LLM response
- Avatar voice and persona layer
- Microphone input animation and richer voice UI
- Apple SFSpeechRecognizer / Siri Shortcuts evaluation
- Reranker integration and deeper retrieval quality tuning
- Governor / ModelRouter coupling hardening

## Validation Snapshot

- `alliance_20260317_130542/.venv/bin/python -m pytest -q alliance_20260317_130542/tests`
- Result at Beta 1 cut: `335 passed`
- Result at 2026-03-21 update: `357 passed, 7 skipped`
