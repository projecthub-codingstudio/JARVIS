#!/usr/bin/env python3
"""Collect voice samples for Qwen3-TTS JARVIS voice fine-tuning.

Records reference voice clips to create a custom JARVIS voice persona.
The collected samples are used to fine-tune Qwen3-TTS-CustomVoice.

Usage:
    python scripts/collect_voice_samples.py --count 20

Each sample should be 5-10 seconds of clear speech in the desired
JARVIS voice tone. Read the provided scripts naturally.

Samples saved to: ~/.jarvis/tts_training/reference_voice/
"""
from __future__ import annotations

import argparse
import wave
from pathlib import Path

SAMPLE_RATE = 24000  # Qwen3-TTS native rate
CHANNELS = 1
SAMPLE_WIDTH = 2
RECORD_SECONDS = 8.0
OUTPUT_DIR = Path.home() / ".jarvis" / "tts_training" / "reference_voice"

# Scripts to read — JARVIS-style Korean responses
SCRIPTS = [
    "네, 확인했습니다. 말씀하신 파일을 분석하고 있습니다.",
    "3일차 점심 메뉴는 닭가슴살 샐러드와 아보카도입니다.",
    "흥미로운 질문이시군요. 관련 자료를 찾아보겠습니다.",
    "시스템 상태가 정상입니다. 메모리 사용률 50퍼센트, 배터리 77퍼센트입니다.",
    "검색 결과 5건의 관련 문서를 찾았습니다.",
    "죄송합니다. 해당 정보는 현재 데이터베이스에 없습니다.",
    "파일 업데이트가 감지되었습니다. 자동으로 재인덱싱합니다.",
    "말씀하신 내용을 정리하면 다음과 같습니다.",
    "보안 정책상 해당 작업은 승인이 필요합니다.",
    "분석이 완료되었습니다. 결과를 보여드리겠습니다.",
    "현재 14일 다이어트 식단 파일에서 정보를 찾고 있습니다.",
    "네트워크 연결 없이도 모든 기능이 정상 작동합니다.",
    "씨샵 문서에서 관련 내용을 발견했습니다.",
    "음성 인식이 완료되었습니다. 질문을 처리하고 있습니다.",
    "자비스 시스템이 준비되었습니다. 무엇을 도와드릴까요?",
    "해당 코드에서 함수 3개와 클래스 1개를 찾았습니다.",
    "오늘의 보충제 일정을 확인해 드리겠습니다.",
    "프로젝트 분석 결과, 검색 품질이 87퍼센트 향상되었습니다.",
    "말씀하신 기간의 데이터를 비교 분석하겠습니다.",
    "출처 표시와 함께 답변을 준비했습니다.",
]


def record_sample(device_index: int | None, duration: float) -> bytes:
    """Record a single audio sample."""
    import pyaudio

    pa = pyaudio.PyAudio()
    stream = pa.open(
        format=pyaudio.paInt16,
        channels=CHANNELS,
        rate=SAMPLE_RATE,
        input=True,
        input_device_index=device_index,
        frames_per_buffer=1024,
    )

    frames = []
    for _ in range(int(SAMPLE_RATE / 1024 * duration)):
        data = stream.read(1024, exception_on_overflow=False)
        frames.append(data)

    stream.stop_stream()
    stream.close()
    pa.terminate()
    return b"".join(frames)


def save_wav(path: Path, audio_data: bytes) -> None:
    """Save raw PCM data as WAV."""
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(SAMPLE_WIDTH)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(audio_data)


def main():
    parser = argparse.ArgumentParser(description="TTS voice sample collection")
    parser.add_argument("--count", type=int, default=20, help="Number of samples")
    parser.add_argument("--device", type=int, default=None, help="Input device index")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    existing = len(list(OUTPUT_DIR.glob("*.wav")))

    print("\nJARVIS 음성 샘플 수집 (Qwen3-TTS fine-tuning용)")
    print(f"  저장 위치: {OUTPUT_DIR}")
    print(f"  기존 샘플: {existing}개")
    print(f"  수집 목표: {args.count}개")
    print(f"  녹음 시간: {RECORD_SECONDS}초/샘플")
    print()
    print("  차분하고 정중한 JARVIS 톤으로 읽어주세요.")
    print("  Enter로 녹음 시작, Ctrl+C로 종료\n")

    collected = 0
    try:
        for i in range(min(args.count, len(SCRIPTS))):
            script = SCRIPTS[(existing + i) % len(SCRIPTS)]
            print(f"  [{i + 1}/{args.count}] 📋 \"{script}\"")
            input("         Enter를 누르면 녹음 시작...")
            print("         🎙 녹음 중...", end="", flush=True)
            audio = record_sample(args.device, RECORD_SECONDS)
            path = OUTPUT_DIR / f"voice_{existing + i:04d}.wav"
            save_wav(path, audio)
            print(f" 저장됨")
            collected += 1
    except KeyboardInterrupt:
        pass

    total = len(list(OUTPUT_DIR.glob("*.wav")))
    print(f"\n  총 음성 샘플: {total}개")
    if total >= 10:
        print("  fine-tuning 준비 완료!")


if __name__ == "__main__":
    main()
