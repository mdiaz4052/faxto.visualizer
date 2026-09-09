"""Controlled LGPL-only, dynamically linked Apple Silicon FFmpeg build."""
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile

from download_godot import fetch

ROOT = Path(__file__).resolve().parents[1]
VERSIONS_FILE = ROOT / "packaging/versions.json"
if not VERSIONS_FILE.is_file(): VERSIONS_FILE = Path(__file__).with_name("versions.json")
VERSIONS = json.loads(VERSIONS_FILE.read_text())


def run(*args, **kwargs):
    return subprocess.run([str(a) for a in args], check=True, **kwargs)


def _build_native(destination, work, notices):
    if sys.platform != "darwin" or platform.machine() != "arm64":
        raise RuntimeError("FFmpeg product builds require native Apple Silicon macOS")
    work.mkdir(parents=True, exist_ok=True)
    notices.mkdir(parents=True, exist_ok=True)
    version = VERSIONS["ffmpeg"]
    archive = work / f"ffmpeg-{version}.tar.xz"
    fetch(f"https://ffmpeg.org/releases/{archive.name}", archive)
    if hashlib.sha256(archive.read_bytes()).hexdigest() != VERSIONS["ffmpeg_sha256"]:
        raise ValueError("FFmpeg source checksum mismatch")
    signature = Path(str(archive) + ".asc")
    key = work / "ffmpeg-devel.asc"
    fetch(f"https://ffmpeg.org/releases/{signature.name}", signature)
    fetch("https://ffmpeg.org/ffmpeg-devel.asc", key)
    key_info = subprocess.check_output(["gpg", "--show-keys", "--with-colons", str(key)], text=True)
    primary_fingerprint = next(line.split(":")[9] for line in key_info.splitlines() if line.startswith("fpr:"))
    if primary_fingerprint != VERSIONS["ffmpeg_signing_fingerprint"]:
        raise ValueError("Unexpected FFmpeg signing key")
    # Detached public-key verification needs no signing agent/socket. A long
    # macOS temporary path can exceed the agent socket path limit.
    keyring = work / "release-key.gpg"
    run("gpg", "--batch", "--yes", "--dearmor", "--output", keyring, key)
    run("gpgv", "--keyring", keyring, signature, archive)
    with tarfile.open(archive) as tar: tar.extractall(work, filter="data")
    source = work / f"ffmpeg-{version}"
    # Disable autodetection so Homebrew and changing runner packages cannot alter
    # the license/dependency closure. Shared libraries are replaceable.
    args = [f"--prefix={destination}", "--arch=arm64", "--target-os=darwin",
            "--cc=clang", "--disable-autodetect", "--disable-gpl", "--disable-nonfree",
            "--disable-version3", "--enable-shared", "--disable-static", "--disable-doc",
            "--disable-debug", "--disable-network", "--disable-everything",
            "--enable-ffmpeg", "--enable-ffprobe", "--enable-avcodec", "--enable-avformat",
            "--enable-avfilter", "--enable-swscale", "--enable-swresample",
            "--enable-videotoolbox", "--enable-audiotoolbox", "--enable-zlib",
            "--enable-encoder=h264_videotoolbox,aac", "--enable-decoder=png,h264,aac,pcm_u8,pcm_s16le,pcm_s24le,pcm_s32le,pcm_f32le",
            "--enable-parser=png,h264,aac", "--enable-demuxer=image2,wav,mov",
            "--enable-muxer=mp4,mov,null,wav", "--enable-protocol=file,pipe",
            "--enable-filter=scale,format,aformat,aresample,anull,null",
            "--extra-cflags=-mmacosx-version-min=15.0", "--extra-ldflags=-mmacosx-version-min=15.0"]
    environment = {**os.environ, "MACOSX_DEPLOYMENT_TARGET": "15.0"}
    run(source / "configure", *args, cwd=source, env=environment)
    run("make", "-j", "3", cwd=source)
    run("make", "install", cwd=source)
    # Resolve every FFmpeg reference through the shipped library directory.
    binaries = list((destination / "bin").iterdir()) + [p for p in (destination / "lib").glob("*.dylib") if not p.is_symlink()]
    for binary in binaries:
        deps = subprocess.check_output(["otool", "-L", str(binary)], text=True)
        if binary.suffix == ".dylib":
            run("install_name_tool", "-id", "@rpath/" + binary.name, binary)
        for line in deps.splitlines()[1:]:
            dependency = line.strip().split(" (", 1)[0]
            if dependency.startswith(str(destination)):
                run("install_name_tool", "-change", dependency, "@rpath/" + Path(dependency).name, binary)
        rpath = "@loader_path/../lib" if binary.parent.name == "bin" else "@loader_path"
        run("install_name_tool", "-add_rpath", rpath, binary)
    for binary in binaries:
        run("codesign", "--force", "--sign", "-", binary)
    config = subprocess.check_output([str(destination / "bin/ffmpeg"), "-buildconf"], stderr=subprocess.STDOUT, text=True)
    # Configure's license statement is also checked, not inferred from flags.
    license_text = subprocess.check_output([str(destination / "bin/ffmpeg"), "-L"], stderr=subprocess.STDOUT, text=True)
    normalized_license = " ".join(license_text.split())
    if "GNU Lesser General Public License" not in normalized_license or "version 2.1" not in normalized_license or "--enable-gpl" in config or "--enable-nonfree" in config:
        raise RuntimeError("Unexpected FFmpeg license configuration: " + license_text)
    (notices / "buildconf.txt").write_text(config)
    (notices / "configure-arguments.json").write_text(json.dumps(args, indent=2) + "\n")
    (notices / "toolchain.txt").write_text(subprocess.check_output(["clang", "--version"], text=True) + subprocess.check_output(["xcodebuild", "-version"], text=True))
    for path in (archive, signature, key, source / "COPYING.LGPLv2.1", source / "LICENSE.md", Path(__file__), Path(__file__).with_name("download_godot.py"), VERSIONS_FILE):
        shutil.copy2(path, notices / path.name)
    # The complete source includes development headers; the product keeps only
    # executables and dylibs under its code-signing runtime directories.
    return destination


def build(destination, work, notices):
    # FFmpeg's generated linker flags do not quote spaces in install-name paths.
    # Compile under a private space-free prefix, rewrite install names, then copy
    # the closed runtime into the user-facing application bundle.
    work.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="faxto-ffmpeg-") as temporary:
        build_root = Path(temporary)
        if " " in str(build_root): raise RuntimeError("FFmpeg build temporary path must not contain spaces")
        prefix = _build_native(build_root / "prefix", build_root / "source", notices)
        destination.mkdir(parents=True, exist_ok=True)
        shutil.copytree(prefix / "bin", destination / "bin", symlinks=True)
        shutil.copytree(prefix / "lib", destination / "lib", symlinks=True,
                        ignore=shutil.ignore_patterns("pkgconfig", "*.a"))
    return destination


if __name__ == "__main__":
    if len(sys.argv) != 4: raise SystemExit("build_ffmpeg.py DESTINATION WORK NOTICES")
    build(*(Path(p).resolve() for p in sys.argv[1:]))
