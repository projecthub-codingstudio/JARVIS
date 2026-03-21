# Next Iteration: UI and Voice Backlog

**Updated**: 2026-03-21

## Completed (2026-03-21)

- ~~Add microphone input device selection in CLI and menu bar flows~~ → Device picker with Unicode NFC/NFD normalization
- ~~Surface recording device errors and permission state more clearly in UI~~ → Human-readable Korean error messages
- ~~Improve push-to-talk feedback states: idle, recording, transcribing, answering, error~~ → VoiceLoopPhase 6-state cycle implemented
- Replace ffmpeg subprocess recording with Swift AVAudioEngine native recording (zero-latency mic activation)
- Add `com.apple.security.device.audio-input` entitlement for TCC microphone access
- Strip `<think>` tags from Qwen3 LLM output
- Dynamic max_tokens calculation (context_window - prompt_tokens - reserve)
- Citation relevance threshold (MIN_RELEVANCE_SCORE = 0.15)
- Long response truncation with "...more" button and temp file storage
- Inline export approval panel (prevents MenuBarExtra window dismiss)
- Quit JARVIS button with ⌘Q shortcut

## Completed (2026-03-22)

- Two-Stage VAD with adaptive noise floor (energy-based, IDLE→LISTENING→TENTATIVE→CONFIRMED)
- AVAudioEngine native recording (replaces AVCaptureSession — handles deinterleaved/multi-channel formats)
- CoreAudio device enumeration (replaces AVCaptureDevice — prevents aggregate device hang)
- Ollama streaming (`stream: true` with chunk parsing)
- Engine pre-warm on app launch for first-recording readiness
- Xcode project with entitlements and scheme

## Priority 1

- Upgrade to Silero VAD (ML-based) for more accurate speech/silence detection
- Streaming LLM response display in real-time (progressive text rendering)
- Improve menu bar status presentation and action hierarchy

## Priority 2

- Add microphone activity / input level animation
- Rework menu bar layout for clearer evidence, health, and response sections
- Implement citation post-verification (display response first, verify citations asynchronously)

## Priority 3

- Add avatar voice / persona layer on top of existing TTS runtime
- Evaluate Apple SFSpeechRecognizer as alternative/complement to whisper-cli (native STT, real-time streaming capable)
- Evaluate Siri Shortcuts integration via App Intents framework ("Hey Siri, JARVIS")
- Evaluate wake word integration after baseline UX is stable

## Engineering Notes

- Keep Beta 1 baseline stable and branch new UI/voice work separately when possible.
- Build with `make build` to include entitlements (not `swift build` alone).
- Native recording uses AVAudioEngine kept alive between recordings — mic stays warm for instant capture.
- CoreAudio API replaces AVCaptureDevice for device enumeration — AVCaptureDevice hangs on aggregate devices.
- Treat avatar voice and mic animation as a dedicated UX iteration with explicit acceptance criteria.
