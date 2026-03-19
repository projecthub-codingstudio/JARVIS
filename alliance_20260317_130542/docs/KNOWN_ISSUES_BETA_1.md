# JARVIS Beta 1 Known Issues

## Product / UX

- Menu bar UI is functional but not yet polished for final visual quality.
- Voice mode supports file input and push-to-talk once, but not full live assistant UX.
- Microphone device selection is not yet exposed.
- Avatar voice, animated mic state, and richer audio feedback are not implemented.

## Retrieval / Runtime

- Claim-level citation verification is still conservative and not fully granular.
- Reranker is deferred, so retrieval quality relies on FTS, vector search, Kiwi tokenization, and fusion.
- Governor and ModelRouter coordination works, but deeper runtime shaping remains a follow-up.

## Environment

- Some parser capabilities depend on optional local libraries and tools such as `pymupdf`, `openpyxl`, `python-docx`, `python-pptx`, and `hwp5txt`.
- When optional parser dependencies are absent, runtime parsing degrades gracefully and related tests are skipped.

## Release Gate Notes

- Beta 1 is suitable as a functional baseline for internal validation.
- Beta 1 should not yet be treated as the final UI/voice experience.
