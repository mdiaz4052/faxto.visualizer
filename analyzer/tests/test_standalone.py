import json
import math
import os
from pathlib import Path
import shutil
import signal
import struct
import subprocess
import sys
import tempfile
import time
import unittest
import wave
import zlib

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from faxto_analyzer.analyze import analyze_wav
from faxto_analyzer.standalone import atomic_json, cache_key, DEFAULT_SETTINGS
from test_phase0 import write_fixture

HELPER = Path(__file__).resolve().parents[1] / "src/faxto_analyzer/standalone.py"


def wait_for(predicate, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("Timed out waiting for child process state")


def png(path, width=160, height=90):
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    row = b"\0" + b"\x45\x10\x75" * width
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(row * height)) + chunk(b"IEND", b""))


class StandaloneTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.wav = self.root / "Música con espacios.wav"
        write_fixture(self.wav)
        self.children = []
        self.next_job = 0

    def tearDown(self):
        for child, job in self.children:
            if child.poll() is None:
                (job / "cancel").touch()
                child.wait(timeout=5)
        self.temp.cleanup()

    def start(self, **values):
        self.next_job += 1
        job = self.root / f"job-{self.next_job}"
        job.mkdir()
        request = {"protocol": 1, "job_id": job.name, "parent_pid": os.getpid(),
                   "operation": "analyze", "wav": str(self.wav), "cache_dir": str(self.root / "cache"), **values}
        atomic_json(job / "request.json", request)
        child = subprocess.Popen([sys.executable, str(HELPER), "--job", str(job / "request.json")],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.children.append((child, job))
        return child, job

    def complete(self, **values):
        child, job = self.start(**values)
        code = child.wait(timeout=20)
        result = json.loads((job / "result.json").read_text())
        return code, result, job

    def test_analysis_matches_original_and_publishes_atomic_snapshot(self):
        code, result, job = self.complete()
        self.assertEqual(code, 0, (job / "diagnostics.log").read_text())
        self.assertEqual(result["state"], "complete")
        self.assertEqual(json.loads(Path(result["manifest"]).read_text()), analyze_wav(self.wav))
        self.assertEqual(Path(result["wav"]).read_bytes(), self.wav.read_bytes())
        self.assertFalse((job / "analysis.partial").exists())
        self.assertFalse(list(self.root.rglob("*.tmp")))

    def test_repeated_jobs_cache_and_changed_content(self):
        _, first, _ = self.complete()
        _, second, _ = self.complete()
        self.assertEqual(first["cache_key"], second["cache_key"])
        write_fixture(self.wav, seconds=1)
        _, third, _ = self.complete()
        self.assertNotEqual(first["cache_key"], third["cache_key"])
        self.assertNotEqual(Path(first["wav"]).read_bytes(), self.wav.read_bytes())

    def test_same_basename_in_different_directories(self):
        folder = self.root / "other"; folder.mkdir()
        other = folder / self.wav.name
        shutil.copyfile(self.wav, other)
        _, first, _ = self.complete()
        _, second, _ = self.complete(wav=str(other))
        self.assertNotEqual(first["cache_key"], second["cache_key"])

    def test_cache_invalidation_settings_and_version(self):
        key = cache_key(self.wav, "abc", DEFAULT_SETTINGS, "2.3.5")
        self.assertNotEqual(key, cache_key(self.wav, "abc", {"fft_size": 4096}, "2.3.5"))
        self.assertNotEqual(key, cache_key(self.wav, "abc", DEFAULT_SETTINGS, "2.3.6"))

    def test_invalid_and_moved_audio_recover(self):
        self.wav.write_bytes(b"not a WAV")
        code, result, job = self.complete()
        self.assertEqual(code, 1)
        self.assertEqual(result["state"], "failed")
        self.assertIn("Traceback", (job / "diagnostics.log").read_text())
        self.assertFalse(list((self.root / "cache").glob("*/song_manifest.json")))
        self.wav.unlink()
        self.assertEqual(self.complete()[1]["state"], "failed")
        write_fixture(self.wav)
        self.assertEqual(self.complete()[1]["state"], "complete")

    def test_inaccessible_cache_is_recoverable(self):
        cache = self.root / "not-a-directory"
        cache.write_text("existing file")
        self.assertEqual(self.complete(cache_dir=str(cache))[1]["state"], "failed")
        self.assertEqual(cache.read_text(), "existing file")

    def test_cancel_during_analysis_reaps_worker(self):
        write_fixture(self.wav, seconds=240)
        child, job = self.start()
        wait_for(lambda: (job / "status.json").exists() and json.loads((job / "status.json").read_text())["stage"] == "Analyzing musical features")
        worker = json.loads((job / "child.json").read_text())["pid"]
        (job / "cancel").touch()
        self.assertEqual(child.wait(timeout=5), 2)
        self.assertEqual(json.loads((job / "result.json").read_text())["state"], "cancelled")
        with self.assertRaises(ProcessLookupError): os.kill(worker, 0)
        self.assertFalse((job / "analysis.partial").exists())

    def encoding_request(self, **extra):
        frames = self.root / "frames"; frames.mkdir(exist_ok=True)
        for i in range(5): png(frames / f"frame_{i:06d}.png")
        return {"operation": "encode", "frames": str(frames), "start": 0.37, "end": 0.78,
                "fps": 12, "frame_count": 5, **extra}

    def test_missing_encoder_and_launch_failure_preserve_frames(self):
        bad = self.root / "not-executable"; bad.write_text("not a program")
        for path in (self.root / "missing", bad):
            code, result, _ = self.complete(**self.encoding_request(dev_ffmpeg=str(path)))
            self.assertEqual(code, 1)
            self.assertEqual(result["state"], "failed")
            self.assertEqual(len(list((self.root / "frames").glob("frame_*.png"))), 5)
            self.assertFalse(list((self.root / "frames").glob("*.mp4")))

    def slow_encoder(self):
        script = self.root / "encoder"
        script.write_text(f"#!{sys.executable}\nimport time\ntime.sleep(60)\n")
        script.chmod(0o755)
        return self.encoding_request(dev_ffmpeg=str(script))

    def test_encoding_cancellation_reaps_child(self):
        child, job = self.start(**self.slow_encoder())
        wait_for(lambda: (job / "child.json").exists())
        encoder = json.loads((job / "child.json").read_text())["pid"]
        (job / "cancel").touch()
        self.assertEqual(child.wait(timeout=5), 2)
        with self.assertRaises(ProcessLookupError): os.kill(encoder, 0)
        self.assertEqual(len(list((self.root / "frames").glob("frame_*.png"))), 5)

    def test_parent_exit_cancels_and_reaps_encoder(self):
        parent = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
        try:
            child, job = self.start(**self.slow_encoder(), parent_pid=parent.pid)
            wait_for(lambda: (job / "child.json").exists())
            encoder = json.loads((job / "child.json").read_text())["pid"]
            parent.terminate(); parent.wait(timeout=5)
            self.assertEqual(child.wait(timeout=5), 2)
            with self.assertRaises(ProcessLookupError): os.kill(encoder, 0)
        finally:
            if parent.poll() is None: parent.kill(); parent.wait()

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "Development encoder not available")
    def test_real_video_audio_offset_duration_and_no_clobber(self):
        rate = 8000
        t = np.arange(rate * 2) / rate
        samples = np.sin(2 * np.pi * np.where(t < 0.3, 220, 880) * t) * 0.2
        with wave.open(str(self.wav), "wb") as out:
            out.setnchannels(1); out.setsampwidth(2); out.setframerate(rate)
            out.writeframes((samples * 32767).astype("<i2").tobytes())
        code, result, job = self.complete(**self.encoding_request())
        self.assertEqual(code, 0, (job / "diagnostics.log").read_text())
        video = Path(result["video"])
        probe = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(video)]))
        streams = {s["codec_type"]: s for s in probe["streams"]}
        self.assertEqual((streams["video"]["width"], streams["video"]["height"]), (160, 90))
        self.assertEqual(int(streams["video"]["nb_frames"]), 5)
        self.assertAlmostEqual(float(streams["video"]["duration"]), 0.41, delta=1 / 12)
        self.assertAlmostEqual(float(streams["audio"]["duration"]), 0.41, delta=0.04)
        decoded = subprocess.check_output(["ffmpeg", "-v", "error", "-i", str(video), "-map", "0:a", "-f", "f32le", "-ac", "1", "-ar", str(rate), "-"])
        data = np.frombuffer(decoded, dtype="<f4")[:round(0.3 * rate)]
        peak = np.argmax(abs(np.fft.rfft(data * np.hanning(len(data))))) * rate / len(data)
        self.assertAlmostEqual(peak, 880, delta=10)
        original = video.read_bytes()
        self.assertEqual(self.complete(**self.encoding_request())[1]["state"], "failed")
        self.assertEqual(video.read_bytes(), original)
        self.assertFalse(list(video.parent.glob("*.partial.mp4")))


if __name__ == "__main__": unittest.main()
