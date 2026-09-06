from __future__ import annotations

import hashlib
import math
from pathlib import Path

import numpy as np

from . import __version__
from .wav import read_pcm_wav

SCHEMA_VERSION = "0.1.0"


def _normalize(values: np.ndarray) -> np.ndarray:
    high = float(np.percentile(values, 95)) if values.size else 0.0
    return np.clip(values / high, 0.0, 1.0) if high > 1e-12 else np.zeros_like(values)


def analyze_wav(path: str | Path, hop_seconds: float = 0.02, fft_size: int = 2048) -> dict:
    path = Path(path)
    samples, sample_rate, channels = read_pcm_wav(path)
    if samples.size == 0:
        raise ValueError("WAV contains no audio frames")
    hop = max(1, round(sample_rate * hop_seconds))
    fft_size = max(256, int(fft_size))
    window = np.hanning(fft_size)
    freqs = np.fft.rfftfreq(fft_size, 1.0 / sample_rate)
    times, rms, centroid, low, mid, high, flux = [], [], [], [], [], [], []
    previous_spectrum = np.zeros(freqs.size)
    for start in range(0, samples.size, hop):
        frame = np.zeros(fft_size)
        available = samples[start : start + fft_size]
        frame[: available.size] = available
        magnitude = np.abs(np.fft.rfft(frame * window))
        power = magnitude * magnitude
        total = float(magnitude.sum())
        times.append(start / sample_rate)
        rms.append(float(np.sqrt(np.mean(available * available))) if available.size else 0.0)
        centroid.append(float(np.dot(freqs, magnitude) / total) if total > 1e-12 else 0.0)
        low.append(float(power[freqs < 250].sum()))
        mid.append(float(power[(freqs >= 250) & (freqs < 4000)].sum()))
        high.append(float(power[freqs >= 4000].sum()))
        flux.append(float(np.maximum(0.0, magnitude - previous_spectrum).sum()))
        previous_spectrum = magnitude

    arrays = {"rms": np.asarray(rms), "low_energy": np.asarray(low), "mid_energy": np.asarray(mid),
              "high_energy": np.asarray(high), "spectral_centroid_hz": np.asarray(centroid),
              "onset_strength": np.asarray(flux)}
    normalized = {name: _normalize(values) for name, values in arrays.items() if name != "spectral_centroid_hz"}
    onset_curve = normalized["onset_strength"]
    median = float(np.median(onset_curve))
    threshold = median + 1.5 * float(np.median(np.abs(onset_curve - median)))
    onset_indices = [i for i in range(1, len(onset_curve) - 1)
                     if onset_curve[i] >= max(0.15, threshold) and onset_curve[i] > onset_curve[i - 1] and onset_curve[i] >= onset_curve[i + 1]]
    onsets = [times[i] for i in onset_indices]
    intervals = np.diff(onsets)
    plausible = intervals[(intervals >= 0.25) & (intervals <= 1.5)]
    tempo = float(60.0 / np.median(plausible)) if plausible.size >= 3 else None
    beats = []
    if tempo:
        period = 60.0 / tempo
        anchor = onsets[0] if onsets else 0.0
        beats = [anchor + i * period for i in range(max(0, math.floor((samples.size / sample_rate - anchor) / period) + 1))]
    curves = []
    for name, values in arrays.items():
        output = values if name == "spectral_centroid_hz" else normalized[name]
        curves.append({"name": name, "source_id": "master", "unit": "Hz" if name == "spectral_centroid_hz" else "normalized",
                       "sample_interval_seconds": hop / sample_rate, "values": [round(float(x), 8) for x in output]})
    duration = samples.size / sample_rate
    return {"schema_version": SCHEMA_VERSION, "analyzer": {"name": "faxto-analyzer", "version": __version__},
            "source": {"id": "master", "filename": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                       "duration_seconds": duration, "sample_rate_hz": sample_rate, "channel_count": channels},
            "analysis_settings": {"hop_seconds_requested": hop_seconds, "hop_samples": hop, "fft_size": fft_size},
            "estimates": {"tempo_bpm": tempo, "tempo_confidence": 0.35 if tempo else 0.0,
                          "tonal_center": None, "tonal_center_confidence": 0.0},
            "events": {"beats": beats, "onsets": onsets, "downbeats": []}, "curves": curves,
            "structure": {"sections": [], "recurrences": [], "manual_annotations": []}}
