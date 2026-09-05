import json
import math
import sys
import tempfile
import unittest
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from faxto_analyzer.analyze import analyze_wav
from faxto_analyzer.contracts import FeatureTimeline, evaluate_state, frame_time
from faxto_analyzer.validate import ManifestError, validate_manifest


def write_fixture(path: Path, seconds=2.0, rate=8000):
    t = np.arange(round(seconds * rate)) / rate
    signal = 0.25 * np.sin(2 * np.pi * 220 * t)
    signal += ((t % 0.5) < 0.015) * 0.7
    pcm = np.clip(signal, -1, 1)
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1); out.setsampwidth(2); out.setframerate(rate)
        out.writeframes((pcm * 32767).astype("<i2").tobytes())


class Phase0Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.wav = Path(self.temp.name) / "synthetic.wav"
        write_fixture(self.wav)
        self.manifest = analyze_wav(self.wav)

    def tearDown(self): self.temp.cleanup()

    def test_analyzer_output_validates(self):
        validate_manifest(self.manifest)
        self.assertEqual({c["name"] for c in self.manifest["curves"]}, {"rms", "low_energy", "mid_energy", "high_energy", "spectral_centroid_hz", "onset_strength"})
        self.assertTrue(self.manifest["events"]["onsets"])

    def test_malformed_manifest_rejected(self):
        broken = json.loads(json.dumps(self.manifest)); del broken["source"]
        with self.assertRaises(ManifestError): validate_manifest(broken)

    def test_interpolation_and_clamping(self):
        timeline = FeatureTimeline(self.manifest)
        curve = timeline.curves["rms"]
        expected = (curve["values"][0] + curve["values"][1]) / 2
        self.assertAlmostEqual(timeline.value("rms", curve["sample_interval_seconds"] / 2), expected)
        self.assertEqual(timeline.value("rms", -1), curve["values"][0])
        self.assertEqual(timeline.value("rms", 99), curve["values"][-1])

    def test_event_lookup_and_phase(self):
        timeline = FeatureTimeline(self.manifest); timeline.events["beats"] = [0.0, 0.5, 1.0]
        self.assertEqual(timeline.previous_event("beats", 0.75), 0.5)
        self.assertEqual(timeline.next_event("beats", 0.75), 1.0)
        self.assertAlmostEqual(timeline.phase("beats", 0.75), 0.5)
        self.assertTrue(timeline.occurred("beats", 0.49, 0.5))
        self.assertFalse(timeline.occurred("beats", 0.5, 0.6))

    def test_frame_time_and_repeatability(self):
        self.assertEqual(frame_time(30, 30), 1.0)
        timeline = FeatureTimeline(self.manifest)
        self.assertEqual(evaluate_state(timeline, 0.731, 42), evaluate_state(timeline, 0.731, 42))
        self.assertNotEqual(evaluate_state(timeline, 0.731, 42).seeded_variation, evaluate_state(timeline, 0.731, 43).seeded_variation)

    def test_basic_project_configuration(self):
        config = {"schema_version": "0.1.0", "scene": "signal_field", "seed": 42,
                  "parameters": {"deformation": 0.8}, "export": {"width": 1280, "height": 720, "fps": 30}}
        self.assertEqual(json.loads(json.dumps(config))["scene"], "signal_field")


if __name__ == "__main__": unittest.main()
