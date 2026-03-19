# Next Iteration: UI and Voice Backlog

## Priority 1

- Add microphone input device selection in CLI and menu bar flows
- Surface recording device errors and permission state more clearly in UI
- Improve menu bar status presentation and action hierarchy

## Priority 2

- Add microphone activity / input level animation
- Improve push-to-talk feedback states: idle, recording, transcribing, answering, error
- Rework menu bar layout for clearer evidence, health, and response sections

## Priority 3

- Add avatar voice / persona layer on top of existing TTS runtime
- Design richer live voice loop UX beyond single-shot push-to-talk
- Evaluate wake word and VAD integration after baseline UX is stable

## Engineering Notes

- Keep Beta 1 baseline stable and branch new UI/voice work separately when possible.
- Treat microphone device selection as a functional feature, not just visual polish.
- Treat avatar voice and mic animation as a dedicated UX iteration with explicit acceptance criteria.
