# Streaming LLM Response Display Design

**Date**: 2026-03-22
**Status**: Approved
**Scope**: Real-time token-by-token response display (REPL first, menu bar follow-up)
**Priority**: Priority 1 per NEXT_ITERATION_UI_VOICE.md

## Problem

Ollama streaming (`stream:true`) is enabled but tokens are accumulated in memory and returned as a single string. Users wait 5-30 seconds seeing nothing, then the full response appears at once.

## Solution: Generator-Based Streaming Pipeline

### Layer Changes (bottom → top)

#### 1. LlamaCppBackend.generate_stream()
- New generator method yielding tokens as Ollama sends them
- Existing `generate()` unchanged (backward compat)
- Parses newline-delimited JSON chunks: `{"response": "token", "done": false}`

#### 2. MLXBackend.generate_stream()
- Wraps `mlx_lm.stream_generate()` if available
- Fallback: yields entire `generate()` result as single chunk

#### 3. MLXRuntime.generate_stream()
- Calls backend `generate_stream()`, filters `<think>` tags mid-stream
- Think-tag state machine: NORMAL → IN_THINK (buffering, not yielding) → NORMAL
- After stream completes, assembles full AnswerDraft for citation verification

#### 4. Orchestrator.handle_turn_stream()
- Retrieval phase: synchronous (same as handle_turn)
- Generation phase: yields tokens from MLXRuntime.generate_stream()
- Final yield: sentinel with completed ConversationTurn
- Existing handle_turn() unchanged

#### 5. REPL streaming display
- Calls handle_turn_stream() instead of handle_turn()
- sys.stdout.write(token) + flush() for each yielded token
- After stream: display citations in existing format

#### 6. Menu Bar Bridge (follow-up)
- Stream partial JSON envelopes: `{"kind": "stream_chunk", "token": "..."}`
- Final envelope: `{"kind": "stream_done", "query_result": {...}}`

### Think-Tag Streaming Filter

```
State Machine:
  NORMAL: yield tokens as-is
  → sees "<think>" → switch to IN_THINK, stop yielding
  IN_THINK: buffer tokens silently
  → sees "</think>" → discard buffer, switch to NORMAL
```

### Backward Compatibility
- All existing `generate()` / `handle_turn()` interfaces unchanged
- Streaming detected via `hasattr(backend, 'generate_stream')`
- Tests continue to use non-streaming path
- Menu bar continues to use non-streaming path until Phase 2

### Expected Impact
- TTFT perception: from 5-30s → <1s (first token visible immediately)
- Total generation time: unchanged (same model, same tokens)
- User experience: dramatically improved perceived responsiveness
