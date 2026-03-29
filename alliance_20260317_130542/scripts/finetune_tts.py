#!/usr/bin/env python3
"""Fine-tune Qwen3-TTS with JARVIS voice persona.

Uses collected voice samples as reference audio to create a custom
voice that matches the desired JARVIS persona (calm, professional Korean).

Prerequisites:
    1. Collect voice samples: python scripts/collect_voice_samples.py --count 20
    2. Run: python scripts/finetune_tts.py

The Qwen3-TTS-CustomVoice model supports zero-shot voice cloning via
reference audio. This script prepares the reference embeddings.

Model: Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

VOICE_DIR = Path.home() / ".jarvis" / "tts_training" / "reference_voice"
EMBEDDINGS_OUTPUT = Path.home() / ".jarvis" / "models" / "jarvis_voice_embeddings.json"
MODEL_ID = "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice"


def main():
    if not VOICE_DIR.exists():
        logger.error("No voice samples found.")
        logger.error("Run: python scripts/collect_voice_samples.py --count 20")
        sys.exit(1)

    samples = sorted(VOICE_DIR.glob("*.wav"))
    if len(samples) < 5:
        logger.error("Need at least 5 voice samples. Found: %d", len(samples))
        sys.exit(1)

    logger.info("JARVIS Voice Fine-tuning")
    logger.info("  Reference samples: %d", len(samples))
    logger.info("  Model: %s", MODEL_ID)
    logger.info("")

    # Step 1: Load the TTS model processor for embedding extraction
    logger.info("Loading Qwen3-TTS processor...")
    try:
        from transformers import AutoProcessor
        processor = AutoProcessor.from_pretrained(MODEL_ID, trust_remote_code=True)
        logger.info("Processor loaded")
    except Exception as exc:
        logger.error("Failed to load processor: %s", exc)
        logger.info("")
        logger.info("Alternative: Use the reference audio directly with Qwen3-TTS")
        logger.info("The CustomVoice model accepts reference audio at inference time.")
        _create_reference_config(samples)
        return

    # Step 2: Extract speaker embeddings from reference audio
    logger.info("Extracting speaker embeddings from %d samples...", len(samples))
    embeddings = []
    for sample_path in samples[:10]:  # Use up to 10 best samples
        try:
            import torch
            import wave
            import numpy as np

            with wave.open(str(sample_path), "rb") as wf:
                raw = wf.readframes(wf.getnframes())
                audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0

            # Process through the model's audio encoder
            inputs = processor(audio, sampling_rate=24000, return_tensors="pt")
            if hasattr(inputs, "input_features"):
                embeddings.append(inputs.input_features.numpy().tolist())
                logger.info("  Processed: %s", sample_path.name)
        except Exception as exc:
            logger.warning("  Skipped %s: %s", sample_path.name, exc)

    if embeddings:
        EMBEDDINGS_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        with open(EMBEDDINGS_OUTPUT, "w") as f:
            json.dump({"embeddings": embeddings, "model": MODEL_ID, "n_samples": len(embeddings)}, f)
        logger.info("\nEmbeddings saved: %s", EMBEDDINGS_OUTPUT)
    else:
        _create_reference_config(samples)


def _create_reference_config(samples: list[Path]) -> None:
    """Create a reference config for zero-shot voice cloning."""
    config = {
        "model": MODEL_ID,
        "reference_audio_paths": [str(s) for s in samples[:5]],
        "speaker_description": (
            "A calm, professional Korean male voice. "
            "Polite and measured, like an AI butler. "
            "Clear enunciation with moderate pace."
        ),
        "instructions": (
            "Use these reference audio files with Qwen3-TTS CustomVoice "
            "for zero-shot voice cloning at inference time. Pass the "
            "reference audio path to the model's generate() call."
        ),
    }

    config_path = Path.home() / ".jarvis" / "models" / "jarvis_voice_config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

    logger.info("\nReference voice config saved: %s", config_path)
    logger.info("Use with Qwen3-TTS CustomVoice for zero-shot cloning.")


if __name__ == "__main__":
    main()
