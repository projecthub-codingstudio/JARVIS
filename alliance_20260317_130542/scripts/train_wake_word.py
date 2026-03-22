#!/usr/bin/env python3
"""Train a custom "헤이 자비스" wake word model using OpenWakeWord.

Prerequisites:
    1. Collect samples: python scripts/collect_wake_word_samples.py --count 50
    2. Collect negatives: python scripts/collect_wake_word_samples.py --negative --count 200
    3. Run this script: python scripts/train_wake_word.py

The trained model is saved to: ~/.jarvis/models/hey_jarvis_ko.onnx

Training approach:
    - Uses collected positive/negative WAV samples
    - Extracts Mel spectrogram features (matching OpenWakeWord's pipeline)
    - Trains a small CNN classifier
    - Exports to ONNX for integration with OpenWakeWord
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

import numpy as np

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

TRAINING_DIR = Path.home() / ".jarvis" / "wake_word_training"
MODEL_OUTPUT = Path.home() / ".jarvis" / "models" / "hey_jarvis_ko.onnx"
SAMPLE_RATE = 16000
N_MELS = 32
HOP_LENGTH = 160  # 10ms frames
WIN_LENGTH = 400  # 25ms window


def load_samples(sample_dir: Path) -> list[np.ndarray]:
    """Load WAV files as numpy arrays."""
    import wave
    samples = []
    for wav_path in sorted(sample_dir.glob("*.wav")):
        with wave.open(str(wav_path), "rb") as wf:
            raw = wf.readframes(wf.getnframes())
            arr = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
            samples.append(arr)
    return samples


def extract_features(audio: np.ndarray) -> np.ndarray:
    """Extract mel spectrogram features from audio."""
    target_len = SAMPLE_RATE * 2
    if len(audio) > target_len:
        audio = audio[:target_len]
    elif len(audio) < target_len:
        audio = np.pad(audio, (0, target_len - len(audio)))

    n_frames = (len(audio) - WIN_LENGTH) // HOP_LENGTH + 1
    frames = np.zeros((n_frames, WIN_LENGTH))
    for i in range(n_frames):
        start = i * HOP_LENGTH
        frames[i] = audio[start:start + WIN_LENGTH] * np.hanning(WIN_LENGTH)

    spectrum = np.abs(np.fft.rfft(frames, n=512))

    n_fft_bins = spectrum.shape[1]
    mel_filter = np.zeros((N_MELS, n_fft_bins))
    freqs = np.linspace(0, SAMPLE_RATE / 2, n_fft_bins)
    mel_freqs = np.linspace(0, 2595 * np.log10(1 + SAMPLE_RATE / 2 / 700), N_MELS + 2)
    mel_freqs = 700 * (10 ** (mel_freqs / 2595) - 1)

    for i in range(N_MELS):
        lower = mel_freqs[i]
        center = mel_freqs[i + 1]
        upper = mel_freqs[i + 2]
        for j, f in enumerate(freqs):
            if lower <= f <= center:
                mel_filter[i, j] = (f - lower) / max(center - lower, 1e-8)
            elif center < f <= upper:
                mel_filter[i, j] = (upper - f) / max(upper - center, 1e-8)

    mel_spec = np.dot(spectrum, mel_filter.T)
    mel_spec = np.log(mel_spec + 1e-8)
    return mel_spec.astype(np.float32)


def train_model(positive_features: list[np.ndarray], negative_features: list[np.ndarray]):
    """Train a simple classifier and export to ONNX."""
    import torch
    import torch.nn as nn
    import torch.optim as optim

    X_pos = np.stack(positive_features)
    X_neg = np.stack(negative_features[:len(positive_features) * 4])
    X = np.concatenate([X_pos, X_neg])
    y = np.concatenate([np.ones(len(X_pos)), np.zeros(len(X_neg))])

    idx = np.random.permutation(len(X))
    X, y = X[idx], y[idx]

    X_tensor = torch.FloatTensor(X).unsqueeze(1)
    y_tensor = torch.FloatTensor(y)

    class WakeWordCNN(nn.Module):
        def __init__(self):
            super().__init__()
            self.conv = nn.Sequential(
                nn.Conv2d(1, 16, 3, padding=1), nn.ReLU(), nn.MaxPool2d(2),
                nn.Conv2d(16, 32, 3, padding=1), nn.ReLU(), nn.MaxPool2d(2),
                nn.Conv2d(32, 64, 3, padding=1), nn.ReLU(), nn.AdaptiveAvgPool2d(1),
            )
            self.fc = nn.Sequential(
                nn.Linear(64, 32), nn.ReLU(), nn.Dropout(0.3),
                nn.Linear(32, 1), nn.Sigmoid(),
            )

        def forward(self, x):
            x = self.conv(x)
            x = x.view(x.size(0), -1)
            return self.fc(x).squeeze(-1)

    model = WakeWordCNN()
    optimizer = optim.Adam(model.parameters(), lr=0.001)
    criterion = nn.BCELoss()

    logger.info("Training on %d positive + %d negative samples...", len(X_pos), len(X_neg))
    for epoch in range(50):
        model.train()
        optimizer.zero_grad()
        output = model(X_tensor)
        loss = criterion(output, y_tensor)
        loss.backward()
        optimizer.step()

        if (epoch + 1) % 10 == 0:
            model.eval()
            with torch.no_grad():
                preds = (model(X_tensor) > 0.5).float()
                acc = (preds == y_tensor).float().mean()
                logger.info("  Epoch %d/50: loss=%.4f, acc=%.3f", epoch + 1, loss.item(), acc.item())

    MODEL_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    dummy = torch.randn(1, 1, X.shape[1], X.shape[2])
    torch.onnx.export(
        model, dummy, str(MODEL_OUTPUT),
        input_names=["audio_features"],
        output_names=["wake_probability"],
        dynamic_axes={"audio_features": {0: "batch"}},
    )
    logger.info("\nModel saved: %s", MODEL_OUTPUT)


def main():
    pos_dir = TRAINING_DIR / "positive"
    neg_dir = TRAINING_DIR / "negative"

    if not pos_dir.exists() or not list(pos_dir.glob("*.wav")):
        logger.error("No positive samples found in %s", pos_dir)
        logger.error("Run: python scripts/collect_wake_word_samples.py --count 50")
        sys.exit(1)

    pos_samples = load_samples(pos_dir)
    neg_samples = load_samples(neg_dir) if neg_dir.exists() else []

    logger.info("Positive samples: %d", len(pos_samples))
    logger.info("Negative samples: %d", len(neg_samples))

    if len(pos_samples) < 20:
        logger.warning("Minimum 20 positive samples recommended.")

    logger.info("\nExtracting features...")
    pos_features = [extract_features(s) for s in pos_samples]
    neg_features = [extract_features(s) for s in neg_samples] if neg_samples else []

    if not neg_features:
        logger.info("Generating synthetic negative samples from noise...")
        rng = np.random.default_rng(42)
        for _ in range(100):
            noise = rng.standard_normal(SAMPLE_RATE * 2).astype(np.float32) * 0.01
            neg_features.append(extract_features(noise))

    train_model(pos_features, neg_features)


if __name__ == "__main__":
    main()
