#!/usr/bin/env python3
"""Collect wake word training samples for "헤이 자비스" custom model.

Records multiple utterances of the wake word for OpenWakeWord training.
Each sample is saved as a 16kHz mono WAV file.

Usage:
    python scripts/collect_wake_word_samples.py --count 50

The script will prompt you to say "헤이 자비스" for each sample,
with a short pause between recordings. Samples are saved to:
    ~/.jarvis/wake_word_training/positive/
"""
from __future__ import annotations

import argparse
import os
import sys
import time
import wave
from pathlib import Path

SAMPLE_RATE = 16000
CHANNELS = 1
SAMPLE_WIDTH = 2  # 16-bit
RECORD_SECONDS = 2.0  # Each wake word sample duration
OUTPUT_DIR = Path.home() / ".jarvis" / "wake_word_training"


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
    """Save raw PCM data as a WAV file."""
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(SAMPLE_WIDTH)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(audio_data)


def list_input_devices() -> None:
    """List available input devices."""
    import pyaudio
    pa = pyaudio.PyAudio()
    print("\n사용 가능한 입력 장치:")
    for i in range(pa.get_device_count()):
        info = pa.get_device_info_by_index(i)
        if info["maxInputChannels"] > 0:
            print(f"  [{i}] {info['name']}")
    pa.terminate()


def main():
    parser = argparse.ArgumentParser(description="Wake word sample collection")
    parser.add_argument("--count", type=int, default=50, help="Number of samples to collect")
    parser.add_argument("--device", type=int, default=None, help="Input device index")
    parser.add_argument("--negative", action="store_true", help="Collect negative (non-wake-word) samples")
    parser.add_argument("--list-devices", action="store_true", help="List input devices and exit")
    args = parser.parse_args()

    if args.list_devices:
        list_input_devices()
        return

    category = "negative" if args.negative else "positive"
    output_dir = OUTPUT_DIR / category
    output_dir.mkdir(parents=True, exist_ok=True)

    existing = len(list(output_dir.glob("*.wav")))
    print(f"\n{'헤이 자비스' if not args.negative else '일반 대화'} 음성 샘플 수집")
    print(f"  저장 위치: {output_dir}")
    print(f"  기존 샘플: {existing}개")
    print(f"  수집 목표: {args.count}개")
    print(f"  녹음 시간: {RECORD_SECONDS}초/샘플")
    print()

    if not args.negative:
        print("  📢 각 녹음 시 '헤이 자비스'라고 말해주세요.")
    else:
        print("  📢 각 녹음 시 아무 말이나 해주세요 (wake word 제외).")
    print("  Enter를 누르면 녹음 시작, Ctrl+C로 종료")
    print()

    collected = 0
    try:
        while collected < args.count:
            input(f"  [{collected + 1}/{args.count}] Enter를 누르면 녹음 시작...")
            print("    🎙 녹음 중...", end="", flush=True)
            audio = record_sample(args.device, RECORD_SECONDS)
            sample_path = output_dir / f"sample_{existing + collected:04d}.wav"
            save_wav(sample_path, audio)
            print(f" ✓ 저장: {sample_path.name}")
            collected += 1
    except KeyboardInterrupt:
        print(f"\n\n  수집 완료: {collected}개 샘플")

    total = len(list(output_dir.glob("*.wav")))
    print(f"\n  총 {category} 샘플: {total}개")
    print(f"  학습에 필요한 최소 샘플: positive 50+, negative 200+")

    if total >= 50 and category == "positive":
        print(f"\n  ✅ 학습 준비 완료! 다음 단계:")
        print(f"     python scripts/train_wake_word.py")


if __name__ == "__main__":
    main()
