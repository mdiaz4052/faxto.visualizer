"""Native packaged-code checks, independent of editor/developer PATH and checkout.

This proves helper and headless integration, not Finder, pixels, or perception.
"""
import json
import math
import os
from pathlib import Path
import plistlib
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import wave
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "analyzer/src"))
from faxto_analyzer.analyze import analyze_wav


def png(path):
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 160, 90, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress((b"\0" + b"\x45\x10\x75" * 160) * 90)) + chunk(b"IEND", b""))


def smoke(app):
    with tempfile.TemporaryDirectory(prefix="FaXto isolated ") as temp:
        isolated = Path(temp)
        moved = isolated / "FaXto Visualizer.app"
        subprocess.run(["ditto", str(app), str(moved)], check=True)
        wav = isolated / "música.wav"
        rate = 16000
        with wave.open(str(wav), "wb") as out:
            out.setnchannels(1); out.setsampwidth(2); out.setframerate(rate)
            out.writeframes(b"".join(struct.pack("<h", int(6000 * math.sin(2 * math.pi * 330 * i / rate))) for i in range(rate * 2)))
        expected = analyze_wav(wav)
        environment = {"PATH": "/usr/bin:/bin", "LANG": "en_US.UTF-8", "TMPDIR": temp}
        # Preserve only the user's existing home and session identity; never alter
        # them. Jobs and caches explicitly use the fresh private directory below.
        for key in ("HOME", "USER", "LOGNAME"):
            if key in os.environ: environment[key] = os.environ[key]
        helper = moved / "Contents/Helpers/analyzer/faxto-helper"
        encoder = moved / "Contents/Helpers/ffmpeg/bin/ffmpeg"
        probe = encoder.with_name("ffprobe")
        frames = isolated / "frames"; frames.mkdir()
        for i in range(5): png(frames / f"frame_{i:06d}.png")
        counter = 0

        def job(operation, **extra):
            nonlocal counter
            counter += 1
            directory = isolated / f"job-{counter}"; directory.mkdir()
            request = {"protocol": 1, "job_id": directory.name, "parent_pid": os.getpid(),
                       "operation": operation, "wav": str(wav), "cache_dir": str(isolated / "fresh-cache"), **extra}
            path = directory / "request.json"; path.write_text(json.dumps(request))
            result = subprocess.run([str(helper), "--job", str(path)], env=environment, cwd=isolated,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=60)
            if not (directory / "result.json").exists(): raise AssertionError(result.stdout)
            data = json.loads((directory / "result.json").read_text())
            if result.returncode and data["state"] != "failed": raise AssertionError((directory / "diagnostics.log").read_text())
            return data, directory

        # Make the entire source checkout unavailable to subprocesses. Restore it
        # even on failure, before producing CI's report.
        hidden = ROOT.with_name(ROOT.name + ".runtime-isolation")
        if hidden.exists(): raise RuntimeError("Isolation destination already exists")
        ROOT.rename(hidden)
        try:
            assert json.loads(subprocess.check_output([str(helper), "--version"], env=environment, cwd=isolated))["protocol"] == 1
            result, log = job("analyze")
            assert result["state"] == "complete", (log / "diagnostics.log").read_text()
            assert json.loads(Path(result["manifest"]).read_text()) == expected, "Frozen analyzer semantics changed"
            assert Path(result["wav"]).read_bytes() == wav.read_bytes()
            cached, _ = job("analyze")
            assert cached["cache_key"] == result["cache_key"]
            invalid = isolated / "invalid.wav"; invalid.write_text("broken")
            assert job("analyze", wav=str(invalid))[0]["state"] == "failed"
            encoders = subprocess.check_output([str(encoder), "-encoders"], env=environment, cwd=isolated, stderr=subprocess.STDOUT, text=True)
            assert "h264_videotoolbox" in encoders and "libx264" not in encoders
            options = {"frames": str(frames), "start": 0.37, "end": 0.78, "fps": 12, "frame_count": 5}
            encoded, log = job("encode", **options)
            assert encoded["state"] == "complete", (log / "diagnostics.log").read_text()
            video = Path(encoded["video"])
            metadata = json.loads(subprocess.check_output([str(probe), "-v", "error", "-show_streams", "-of", "json", str(video)], env=environment, cwd=isolated))
            streams = {s["codec_type"]: s for s in metadata["streams"]}
            assert streams["video"]["codec_name"] == "h264" and streams["audio"]["codec_name"] == "aac"
            assert (streams["video"]["width"], streams["video"]["height"]) == (160, 90)
            assert int(streams["video"]["nb_frames"]) == 5
            assert abs(float(streams["video"]["duration"]) - 0.41) <= 1 / 12
            assert abs(float(streams["audio"]["duration"]) - 0.41) < 0.04
            original = video.read_bytes()
            assert job("encode", **options)[0]["state"] == "failed"
            assert video.read_bytes() == original
            info = plistlib.loads((moved / "Contents/Info.plist").read_bytes())
            launch = subprocess.run([str(moved / "Contents/MacOS" / info["CFBundleExecutable"]), "--headless", "--quit-after", "3"], env=environment, cwd=isolated, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=30)
            assert launch.returncode == 0 and "ERROR:" not in launch.stdout, launch.stdout
        finally:
            hidden.rename(ROOT)
        print("PASS: relocated arm64 bundle, reduced PATH, absent checkout, frozen/development analysis equality,")
        print("fresh explicit cache, repeat/invalid jobs, bundled H.264/AAC encode, dimensions/duration, no-clobber, headless app.")
        print("NOT TESTED: fresh GUI preferences, Finder, GPU rendering, Gatekeeper, perceived sync.")


if __name__ == "__main__": smoke(Path(sys.argv[1]).resolve())
