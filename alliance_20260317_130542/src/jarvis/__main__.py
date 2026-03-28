"""Entry point for `python -m jarvis`.

Implements the startup sequence per Implementation Spec Section 1.5:
  python -m jarvis.app.cli chat

Backend selection per Spec Section 1.1:
  - Default inference backend: MLX
  - Compatibility backend: llama.cpp (Ollama)
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

from jarvis.app.runtime_context import build_runtime_context, shutdown_runtime_context
from jarvis.cli.repl import JarvisREPL
from jarvis.cli.voice_session import VoiceSession
from jarvis.observability.logging import configure_logging
from jarvis.runtime.audio_recorder import AudioRecorder
from jarvis.runtime.stt_biasing import build_vocabulary_hint
from jarvis.runtime.stt_runtime import WhisperCppSTT
from jarvis.runtime.tts_runtime import LocalTTSRuntime

logger = logging.getLogger(__name__)


def main() -> None:
    configure_logging(
        level=logging.ERROR,
        json_logs=os.getenv("JARVIS_LOG_FORMAT", "").lower() == "json",
    )

    # Model selection — default: qwen3.5:9b (fast response, switch to qwen3:14b if quality insufficient)
    model_id = os.getenv("JARVIS_MODEL", "qwen3.5:9b")
    voice_file: Path | None = None
    voice_output: Path | None = None
    voice_device: str | None = os.getenv("JARVIS_PTT_DEVICE")
    voice_ptt = False
    wake_word = False
    if len(sys.argv) > 1 and sys.argv[1].startswith("--model="):
        model_id = sys.argv[1].split("=", 1)[1]
    for arg in sys.argv[1:]:
        if arg.startswith("--voice-file="):
            voice_file = Path(arg.split("=", 1)[1]).expanduser()
        elif arg.startswith("--voice-output="):
            voice_output = Path(arg.split("=", 1)[1]).expanduser()
        elif arg.startswith("--voice-device="):
            voice_device = arg.split("=", 1)[1]
        elif arg == "--voice-ptt":
            voice_ptt = True
        elif arg == "--wake-word":
            wake_word = True
        elif arg.startswith("--wake-device="):
            os.environ["JARVIS_WAKE_DEVICE"] = arg.split("=", 1)[1]

    print("\n🤖 JARVIS v0.1.0-beta1")
    print(f"   LLM: {model_id} (MLX primary → Ollama fallback)")
    context = build_runtime_context(
        model_id=model_id,
        reporter=print,
        start_watcher_enabled=True,
    )
    gov_state = context.governor.sample()
    print(f"   System: mem={gov_state.memory_pressure_pct:.0f}%, "
          f"swap={gov_state.swap_used_mb}MB, "
          f"thermal={gov_state.thermal_state}, "
          f"battery={gov_state.battery_pct}%")
    if context.knowledge_base_path is not None:
        print(f"   Knowledge base: {context.knowledge_base_path.name}/ ({context.chunk_count} chunks)")
        if context.watcher is not None:
            print("   File watcher: active (실시간 인덱싱)")
    else:
        print("   Retrieval: stub mode (인덱싱된 데이터 없음)")
    vector_available = context.vector_index._check_available()
    print(f"   Vector search: {'active' if vector_available else 'disabled (FTS only)'}")

    try:
        if wake_word or voice_file is not None or voice_ptt:
            stt_runtime = WhisperCppSTT(
                model_path=(
                    Path(os.getenv("JARVIS_STT_MODEL", "")).expanduser()
                    if os.getenv("JARVIS_STT_MODEL")
                    else None
                ),
                model_router=context.model_router,
                vocabulary_hint=build_vocabulary_hint(context.knowledge_base_path),
            )
            tts_runtime = LocalTTSRuntime(
                voice=os.getenv("JARVIS_TTS_VOICE"),
                backend=os.getenv("JARVIS_TTS_BACKEND", "auto"),
                model_router=context.model_router,
            )
            recorder = AudioRecorder(
                input_device=voice_device,
                duration_seconds=int(os.getenv("JARVIS_PTT_SECONDS", "8")),
            )
            session = VoiceSession(
                orchestrator=context.orchestrator,
                stt_runtime=stt_runtime,
                tts_runtime=tts_runtime,
                recorder=recorder,
            )
            if wake_word:
                # Enable wake word logging for debugging
                logging.getLogger("jarvis.runtime.wake_word").setLevel(logging.INFO)
                logging.getLogger("jarvis.runtime.wake_word").addHandler(
                    logging.StreamHandler(sys.stderr)
                )

                wake_device = os.getenv("JARVIS_WAKE_DEVICE")
                wake_device_idx = int(wake_device) if wake_device and wake_device.isdigit() else None

                print("\n🎙 Wake word mode: 'Hey JARVIS'라고 말하면 자동으로 응답합니다.")
                if wake_device_idx is not None:
                    print(f"   Input device: index {wake_device_idx}")
                print("   종료: Ctrl+C\n")

                def _on_wake():
                    # Chime sound to signal "I'm listening"
                    subprocess.run(
                        ["afplay", "/System/Library/Sounds/Tink.aiff"],
                        check=False, capture_output=True,
                    )
                    print("\n  [감지] 'Hey JARVIS' — 🎙 듣고 있습니다...")

                def _on_response(text: str):
                    print(f"  JARVIS: {text}\n")
                    print("  ... 'Hey JARVIS' 대기 중 ...")

                def _on_error(msg: str):
                    print(f"  [오류] {msg}")

                def _on_transcript(text: str):
                    print(f"  [인식] \"{text}\"")

                session.start_wake_word_loop(
                    on_wake=_on_wake,
                    on_transcript=_on_transcript,
                    on_response=_on_response,
                    on_error=_on_error,
                    device_index=wake_device_idx,
                )
                try:
                    import time
                    print("  ... 'Hey JARVIS' 대기 중 ...")
                    while True:
                        time.sleep(1)
                except KeyboardInterrupt:
                    print("\n\n  Wake word 모드 종료.")
                    session.stop_wake_word_loop()
                return

            if voice_ptt:
                print("\n🎙 push-to-talk once: recording...")
                if voice_device:
                    print(f"   Input device: {voice_device}")

                import sys as _sys

                def _print_token(token: str) -> None:
                    _sys.stdout.write(token)
                    _sys.stdout.flush()

                _sys.stdout.write("\n  ")
                _sys.stdout.flush()
                turn = session.record_and_handle_once_stream(on_token=_print_token)
                _sys.stdout.write("\n")
                _sys.stdout.flush()
            elif voice_output is not None and voice_file is not None:
                turn, generated_audio = session.handle_audio_file_with_tts(
                    voice_file,
                    output_path=voice_output,
                )
                print(f"\n🔊 tts_output: {generated_audio}")
            else:
                assert voice_file is not None
                turn = session.handle_audio_file(voice_file)
            print(f"\n🎙 transcript: {turn.user_input}")
            print(f"  {turn.assistant_output}")
            return

        repl = JarvisREPL(context.orchestrator)
        repl.start()
    finally:
        shutdown_runtime_context(context)


if __name__ == "__main__":
    main()
