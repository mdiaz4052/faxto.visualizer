from dataclasses import dataclass
from bisect import bisect_left, bisect_right
import math
import random


class FeatureTimeline:
    def __init__(self, manifest: dict):
        self.duration = float(manifest["source"]["duration_seconds"])
        self.curves = {curve["name"]: curve for curve in manifest["curves"]}
        self.events = manifest["events"]

    def value(self, name: str, time_seconds: float) -> float:
        curve, values = self.curves[name], self.curves[name]["values"]
        if not values:
            return 0.0
        position = max(0.0, time_seconds) / curve["sample_interval_seconds"]
        left = min(int(math.floor(position)), len(values) - 1)
        right = min(left + 1, len(values) - 1)
        fraction = position - math.floor(position)
        return float(values[left] + (values[right] - values[left]) * fraction)

    def previous_event(self, kind: str, time_seconds: float) -> float | None:
        events = self.events[kind]
        index = bisect_right(events, time_seconds) - 1
        return events[index] if index >= 0 else None

    def next_event(self, kind: str, time_seconds: float) -> float | None:
        events = self.events[kind]
        index = bisect_left(events, time_seconds)
        return events[index] if index < len(events) else None

    def occurred(self, kind: str, start: float, end: float) -> bool:
        events = self.events[kind]
        return bisect_right(events, start) < bisect_right(events, end)

    def phase(self, kind: str, time_seconds: float) -> float:
        previous = self.previous_event(kind, time_seconds)
        upcoming = self.next_event(kind, time_seconds + 1e-12)
        if previous is None or upcoming is None or upcoming <= previous:
            return 0.0
        return max(0.0, min(1.0, (time_seconds - previous) / (upcoming - previous)))


def frame_time(frame_index: int, fps: float) -> float:
    if frame_index < 0 or fps <= 0:
        raise ValueError("frame_index must be nonnegative and fps positive")
    return frame_index / fps


@dataclass(frozen=True)
class LogicalState:
    song_time: float
    progress: float
    intensity: float
    impact: float
    brightness: float
    openness: float
    seeded_variation: float


def evaluate_state(features: FeatureTimeline, song_time: float, seed: int) -> LogicalState:
    t = max(0.0, min(song_time, features.duration))
    rms = features.value("rms", t)
    impact = features.value("onset_strength", t)
    centroid = features.value("spectral_centroid_hz", t)
    rng = random.Random(f"{seed}:{round(t, 6)}")
    return LogicalState(t, t / features.duration, rms, impact, min(1.0, centroid / 8000.0), max(0.0, 1.0 - rms), rng.random())
