"""Private, versioned file-job interface. No network or shell execution.

The supervisor owns and reaps one process group. Analysis (including hashing)
runs in a separate worker; encoding runs directly under the supervisor. The
supervisor checks cancellation and parent death even while NumPy/FFmpeg is busy.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
import traceback
import uuid

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from faxto_analyzer import __version__

PROTOCOL = 1
HELPER_VERSION = "0.1.0"
DEFAULT_SETTINGS = {"hop_seconds": 0.02, "fft_size": 2048}


def atomic_json(path: Path, value: dict) -> None:
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with temporary.open("x", encoding="utf-8") as out:
            json.dump(value, out, ensure_ascii=False, allow_nan=False)
            out.write("\n")
            out.flush()
            os.fsync(out.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read_json(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected a JSON object: {path.name}")
    return data


def status(job: Path, request: dict, stage: str, **extra) -> None:
    atomic_json(job / "status.json", {"protocol": PROTOCOL, "job_id": request["job_id"],
                                      "stage": stage, **extra})


def cache_key(source: Path, sha256: str, settings: dict, numpy_version: str) -> str:
    identity = {"path": str(source.resolve()), "sha256": sha256, "settings": settings,
                "analyzer": __version__, "schema": "0.1.0", "helper": HELPER_VERSION,
                "numpy": numpy_version}
    return hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()


def analyze(request: dict, job: Path) -> dict:
    import numpy as np
    from faxto_analyzer.analyze import analyze_wav
    from faxto_analyzer.validate import validate_manifest

    source = Path(request["wav"]).resolve(strict=True)
    settings = request.get("settings", DEFAULT_SETTINGS)
    if settings != DEFAULT_SETTINGS:
        raise ValueError("Unsupported analysis settings for protocol 1")
    status(job, request, "Copying and checking audio")
    staging = job / "analysis.partial"
    staging.mkdir()
    (staging / "source").mkdir()
    snapshot = staging / "source" / source.name
    before = source.stat()
    shutil.copyfile(source, snapshot)
    sha256 = digest(snapshot)
    after = source.stat()
    if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino) or digest(source) != sha256:
        raise ValueError("The WAV changed during copying; select it again when it is finished saving")
    cache = Path(request["cache_dir"])
    cache.mkdir(parents=True, exist_ok=True)
    key = cache_key(source, sha256, settings, np.__version__)
    destination = cache / key
    if destination.exists():
        manifest = read_json(destination / "song_manifest.json")
        validate_manifest(manifest)
        if manifest["source"]["sha256"] != sha256 or digest(destination / "source" / source.name) != sha256:
            raise ValueError("Cached audio is damaged; remove this cache entry and analyze again")
        shutil.rmtree(staging)
    else:
        status(job, request, "Analyzing musical features")
        manifest = analyze_wav(snapshot, **settings)
        validate_manifest(manifest)
        if manifest["source"]["sha256"] != sha256:
            raise ValueError("Audio snapshot changed during analysis")
        atomic_json(staging / "song_manifest.json", manifest)
        atomic_json(staging / "identity.json", {"original_wav": str(source), "cache_key": key,
                                               "numpy": np.__version__, "helper": HELPER_VERSION})
        # Both directories are under user://, so publication is one filesystem rename.
        try:
            staging.rename(destination)
        except FileExistsError:
            # Another app instance may have completed the identical immutable job.
            existing = read_json(destination / "song_manifest.json")
            if existing != manifest or digest(destination / "source" / source.name) != sha256:
                raise ValueError("Conflicting cache publication")
            shutil.rmtree(staging)
    return {"manifest": str(destination / "song_manifest.json"),
            "wav": str(destination / "source" / source.name), "original_wav": str(source),
            "cache_key": key, "analyzer_version": __version__, "numpy_version": np.__version__}


def ffmpeg_path(request: dict) -> Path:
    if getattr(sys, "frozen", False):
        # Contents/Helpers/analyzer.app/Contents/MacOS/faxto-helper
        # -> Contents/Helpers/ffmpeg/bin/ffmpeg
        return Path(sys.executable).resolve().parents[3] / "ffmpeg" / "bin" / "ffmpeg"
    path = request.get("dev_ffmpeg") or shutil.which("ffmpeg")
    if not path:
        raise FileNotFoundError("Development FFmpeg was not found")
    return Path(path).resolve(strict=True)


def encoding_command(request: dict, temporary: Path) -> list[str]:
    start, end, fps = (float(request[k]) for k in ("start", "end", "fps"))
    if not all(math.isfinite(x) for x in (start, end, fps)) or not (0 <= start < end and 0 < fps <= 120):
        raise ValueError("Invalid export interval or frame rate")
    expected = math.ceil((end - start) * fps - 1e-9)
    frames = Path(request["frames"])
    if expected != int(request["frame_count"]) or expected < 1:
        raise ValueError("Frame count does not match the requested interval")
    if any(not (frames / f"frame_{i:06d}.png").is_file() for i in range(expected)):
        raise ValueError("The PNG sequence is incomplete")
    encoder = "h264_videotoolbox" if sys.platform == "darwin" else "libx264"
    # Only the development/Linux test path uses x264. It is never redistributed.
    codec = ["-c:v", encoder, "-pix_fmt", "yuv420p"]
    if encoder == "h264_videotoolbox":
        codec += ["-allow_sw", "1", "-b:v", "16M"]
    else:
        codec += ["-crf", "18"]
    return [str(ffmpeg_path(request)), "-nostdin", "-n", "-hide_banner", "-loglevel", "info",
            "-framerate", str(fps), "-start_number", "0", "-i", str(frames / "frame_%06d.png"),
            "-ss", str(start), "-i", request["wav"], "-map", "0:v:0", "-map", "1:a:0",
            *codec, "-c:a", "aac", "-b:a", "192k", "-t", str(end - start),
            "-movflags", "+faststart", "-f", "mp4", str(temporary)]


def stop_child(child: subprocess.Popen) -> None:
    if child.poll() is None:
        try:
            os.killpg(child.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            child.wait(timeout=1.5)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
    child.wait(timeout=2)


def supervise(request_path: Path) -> int:
    job = request_path.resolve().parent
    request = read_json(request_path)
    if request.get("protocol") != PROTOCOL or not isinstance(request.get("job_id"), str):
        raise ValueError("Unsupported or malformed helper request")
    if not isinstance(request.get("parent_pid"), int) or request["parent_pid"] <= 1:
        raise ValueError("A live application parent PID is required")
    child = None
    temporary = None
    result = {"protocol": PROTOCOL, "job_id": request["job_id"], "helper_version": HELPER_VERSION}
    interrupted = False

    def signal_cancel(_signum, _frame):
        nonlocal interrupted
        interrupted = True

    signal.signal(signal.SIGTERM, signal_cancel)
    signal.signal(signal.SIGINT, signal_cancel)

    def cancelled() -> bool:
        if interrupted or (job / "cancel").exists():
            return True
        try:
            os.kill(request["parent_pid"], 0)
        except ProcessLookupError:
            return True
        return False

    with (job / "diagnostics.log").open("w", encoding="utf-8") as log:
        try:
            print(json.dumps({"helper": HELPER_VERSION, "analyzer": __version__,
                              "python": sys.version, "request": request}, ensure_ascii=False), file=log, flush=True)
            if cancelled():
                result["state"] = "cancelled"
            else:
                if request["operation"] == "analyze":
                    command = [sys.executable]
                    if not getattr(sys, "frozen", False):
                        command.append(str(Path(__file__).resolve()))
                    command += ["--worker", str(request_path.resolve())]
                    status(job, request, "Starting analyzer")
                elif request["operation"] == "encode":
                    temporary = Path(request["frames"]) / (".video-" + uuid.uuid4().hex + ".partial.mp4")
                    command = encoding_command(request, temporary)
                    status(job, request, "Encoding video with audio")
                else:
                    raise ValueError("Unknown operation")
                environment = dict(os.environ)
                # PyInstaller changes DYLD_LIBRARY_PATH on some platforms; do not
                # let its Python libraries contaminate the independent encoder.
                if request["operation"] == "encode":
                    for key in ("DYLD_LIBRARY_PATH", "DYLD_FRAMEWORK_PATH", "LD_LIBRARY_PATH"):
                        environment.pop(key, None)
                child = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                         cwd=job, env=environment, start_new_session=True)
                atomic_json(job / "child.json", {"pid": child.pid})
                while child.poll() is None and not cancelled():
                    time.sleep(0.05)
                if cancelled():
                    stop_child(child)
                    result["state"] = "cancelled"
                elif child.returncode != 0:
                    raise RuntimeError(f"{request['operation']} exited with code {child.returncode}; see diagnostics")
                elif request["operation"] == "analyze":
                    result.update(read_json(job / "worker.json"))
                    result["state"] = "complete"
                else:
                    if not temporary.is_file() or temporary.stat().st_size == 0:
                        raise RuntimeError("Encoder returned no video")
                    destination = Path(request["frames"]) / "FaXto Visualizer.mp4"
                    # link is atomic and refuses to replace an existing file.
                    os.link(temporary, destination)
                    result.update(state="complete", video=str(destination))
        except Exception as exc:
            traceback.print_exc(file=log)
            result.update(state="failed", error=str(exc))
        finally:
            if child is not None:
                stop_child(child)
            if temporary is not None:
                temporary.unlink(missing_ok=True)
            shutil.rmtree(job / "analysis.partial", ignore_errors=True)
        atomic_json(job / "result.json", result)
    return 0 if result["state"] == "complete" else (2 if result["state"] == "cancelled" else 1)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job", type=Path)
    parser.add_argument("--worker", type=Path)
    parser.add_argument("--version", action="store_true")
    args = parser.parse_args()
    if args.version:
        print(json.dumps({"protocol": PROTOCOL, "helper": HELPER_VERSION, "analyzer": __version__}))
        return 0
    if args.worker:
        request = read_json(args.worker)
        atomic_json(args.worker.parent / "worker.json", analyze(request, args.worker.parent))
        return 0
    if args.job:
        return supervise(args.job)
    parser.error("--job is required")


if __name__ == "__main__":
    raise SystemExit(main())
