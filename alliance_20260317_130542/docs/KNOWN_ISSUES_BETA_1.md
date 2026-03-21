# JARVIS Beta 1 Known Issues

**Updated**: 2026-03-21

## Product / UX

- Menu bar UI is functional but not yet polished for final visual quality.
- Voice mode supports push-to-talk with native AVCaptureDevice recording and live voice loop.
- ~~Microphone device selection is not yet exposed.~~ **Resolved**: Device selection implemented with Unicode NFC/NFD normalization for Korean device names.
- Avatar voice, animated mic state, and richer audio feedback are not implemented.
- Live voice loop operates as sequential polling (~15-18s per cycle), not real-time streaming conversation. VAD (silence-aware recording) and streaming LLM response are deferred to Phase 2.
- LLM responses with `<think>` tags (Qwen3) are now stripped before display.
- Long responses (>500 chars) are truncated in menu bar with "...more" button; full content saved to temp file.

## Retrieval / Runtime

- Claim-level citation verification is still conservative and not fully granular.
- Reranker is deferred, so retrieval quality relies on FTS, vector search, Kiwi tokenization, and fusion.
- Governor and ModelRouter coordination works, but deeper runtime shaping remains a follow-up.
- Citation display now filtered by MIN_RELEVANCE_SCORE (0.15) to suppress noise from irrelevant queries (e.g., greetings).
- Dynamic max_tokens calculation replaces fixed 512-token limit for LLM generation.

## Environment

- Some parser capabilities depend on optional local libraries and tools such as `pymupdf`, `openpyxl`, `python-docx`, `python-pptx`, and `hwp5txt`.
- When optional parser dependencies are absent, runtime parsing degrades gracefully and related tests are skipped.
- Swift app requires `com.apple.security.device.audio-input` entitlement for microphone access. Build with `make build` (not `swift build` alone) to include entitlements.

## Release Gate Notes

- Beta 1 is suitable as a functional baseline for internal validation.
- Beta 1 should not yet be treated as the final UI/voice experience.
