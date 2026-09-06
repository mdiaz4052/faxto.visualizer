from __future__ import annotations

import wave
from pathlib import Path

import numpy as np


def read_pcm_wav(path: str | Path) -> tuple[np.ndarray, int, int]:
    """Return mono float64 samples, sample rate and original channel count."""
    with wave.open(str(path), "rb") as source:
        channels = source.getnchannels()
        width = source.getsampwidth()
        rate = source.getframerate()
        frames = source.getnframes()
        if source.getcomptype() != "NONE" or width not in (1, 2, 3, 4):
            raise ValueError("Only uncompressed 8/16/24/32-bit PCM WAV files are supported")
        raw = source.readframes(frames)
    if width == 1:
        data = (np.frombuffer(raw, dtype=np.uint8).astype(np.float64) - 128.0) / 128.0
    elif width == 2:
        data = np.frombuffer(raw, dtype="<i2").astype(np.float64) / 32768.0
    elif width == 3:
        packed = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3)
        values = packed[:, 0].astype(np.int32) | (packed[:, 1].astype(np.int32) << 8) | (packed[:, 2].astype(np.int32) << 16)
        values = np.where(values & 0x800000, values - 0x1000000, values)
        data = values.astype(np.float64) / 8388608.0
    else:
        data = np.frombuffer(raw, dtype="<i4").astype(np.float64) / 2147483648.0
    if channels < 1 or len(data) % channels:
        raise ValueError("Malformed WAV channel data")
    return data.reshape(-1, channels).mean(axis=1), rate, channels
