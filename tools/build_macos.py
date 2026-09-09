"""Native developer/CI entry point; never run from the product UI."""
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import plistlib
import shutil
import subprocess
import sys

from build_ffmpeg import build as build_ffmpeg
from download_godot import download, fetch
from inspect_macos_bundle import inspect
from sign_macos import sign

ROOT = Path(__file__).resolve().parents[1]
VERSIONS = json.loads((ROOT / "packaging/versions.json").read_text())


def run(*args, **kwargs):
    subprocess.run([str(a) for a in args], check=True, **kwargs)


def collect_notices(notices):
    shutil.copy2(ROOT / "packaging/NOTICE.txt", notices / "NOTICE.txt")
    for name in ("numpy", "pyinstaller", "pyinstaller-hooks-contrib", "altgraph", "packaging", "setuptools", "macholib"):
        distribution = importlib.metadata.distribution(name)
        for path in distribution.files or []:
            if any(word in str(path).lower() for word in ("license", "copying", "copyright", "notice")):
                source = Path(distribution.locate_file(path))
                if source.is_file():
                    relative = Path(*[p for p in path.parts if p not in ("..", ".")])
                    target = notices / name / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
    fetch(f"https://raw.githubusercontent.com/python/cpython/v{VERSIONS['python']}/LICENSE", notices / "PYTHON-LICENSE.txt")
    fetch(f"https://raw.githubusercontent.com/godotengine/godot/{VERSIONS['godot']}-stable/LICENSE.txt", notices / "GODOT-LICENSE.txt")
    fetch(f"https://raw.githubusercontent.com/godotengine/godot/{VERSIONS['godot']}-stable/COPYRIGHT.txt", notices / "GODOT-COPYRIGHT.txt")


def build():
    if sys.platform != "darwin" or platform.machine() != "arm64":
        raise SystemExit("Build requires a native Apple Silicon macOS machine; this is not a cross-compiler")
    if platform.python_version() != VERSIONS["python"]:
        raise SystemExit(f"Use Python {VERSIONS['python']} for this build")
    for command in ("clang", "make", "gpg", "codesign", "ditto", "otool", "lipo"):
        if not shutil.which(command): raise SystemExit(f"Missing developer build tool: {command}")
    work = ROOT / "build/macos"
    work.mkdir(parents=True, exist_ok=True)
    destination = ROOT / "dist"
    destination.mkdir(exist_ok=True)
    app = destination / "FaXto Visualizer.app"
    if app.exists(): shutil.rmtree(app)
    godot = download(work / "godot", templates=True)
    run(sys.executable, ROOT / "tools/check_godot.py", godot, "--headless", "--editor", "--path", ROOT / "godot", "--import")
    run(sys.executable, ROOT / "tools/check_godot.py", godot, "--headless", "--path", ROOT / "godot", "--export-release", "macOS Apple Silicon", app)
    contents = app / "Contents"
    notices = contents / "Resources/ThirdPartyNotices"
    notices.mkdir(parents=True, exist_ok=True)
    helpers = contents / "Helpers"
    helpers.mkdir(exist_ok=True)
    run(sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir", "--name", "faxto-helper",
        "--target-architecture", "arm64", "--paths", ROOT / "analyzer/src", "--collect-all", "numpy",
        "--distpath", work / "frozen", "--workpath", work / "pyinstaller", "--specpath", work,
        ROOT / "analyzer/src/faxto_analyzer/standalone.py")
    shutil.copytree(work / "frozen/faxto-helper", helpers / "analyzer", symlinks=True)
    build_ffmpeg(helpers / "ffmpeg", work / "ffmpeg", notices / "FFmpeg")
    collect_notices(notices)
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    record = {**VERSIONS, "source_commit": revision, "build_host": platform.mac_ver()[0],
              "python": platform.python_version(), "signing": "ad-hoc", "notarized": False,
              "packages": {d.metadata["Name"]: d.version for d in importlib.metadata.distributions()},
              "gui_smoke": "pending"}
    (contents / "Resources/build-info.json").write_text(json.dumps(record, indent=2) + "\n")
    info_file = contents / "Info.plist"
    info = plistlib.loads(info_file.read_bytes())
    info["LSMinimumSystemVersion"] = VERSIONS["minimum_macos"]
    info["LSArchitecturePriority"] = ["arm64"]
    info_file.write_bytes(plistlib.dumps(info))
    inspection = inspect(app)
    (destination / "bundle-inspection.json").write_text(json.dumps(inspection, indent=2) + "\n")
    sign(app)
    run(sys.executable, ROOT / "tools/package_smoke.py", app)
    # Archives are produced only after packaged-helper and isolation checks pass.
    run("ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", app, destination / "FaXto-Visualizer-arm64-adhoc.zip")
    run("ditto", "-c", "-k", "--keepParent", notices / "FFmpeg", destination / "FFmpeg-corresponding-source.zip")
    shutil.copy2(contents / "Resources/build-info.json", destination / "build-info.json")
    print("Ad-hoc app archive complete. Finder/GPU/perceived sync/Gatekeeper smoke test remains manual.")


if __name__ == "__main__": build()
