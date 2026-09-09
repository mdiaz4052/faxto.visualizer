"""Fail if native code cannot run as arm64 or depends on build-machine paths."""
import json
from pathlib import Path
import plistlib
import re
import subprocess
import sys

MAGICS = {b"\xcf\xfa\xed\xfe", b"\xce\xfa\xed\xfe", b"\xfe\xed\xfa\xcf", b"\xca\xfe\xba\xbe", b"\xca\xfe\xba\xbf"}


def native_files(app):
    for path in sorted(app.rglob("*")):
        if path.is_file() and not path.is_symlink():
            with path.open("rb") as source: magic = source.read(4)
            if magic in MAGICS: yield path


def output(*args):
    return subprocess.check_output([str(x) for x in args], text=True)


def version(value):
    return tuple((list(map(int, value.split("."))) + [0, 0])[:3])


def inspect(app):
    info = plistlib.loads((app / "Contents/Info.plist").read_bytes())
    main = app / "Contents/MacOS" / info["CFBundleExecutable"]
    helper = app / "Contents/Helpers/analyzer/faxto-helper"
    records = []
    for binary in native_files(app):
        architectures = output("lipo", "-archs", binary).strip().split()
        if "arm64" not in architectures: raise ValueError(f"Missing arm64: {binary}")
        commands = output("otool", "-arch", "arm64", "-l", binary)
        minimums = re.findall(r"\bminos\s+([\d.]+)", commands)
        minimums += re.findall(r"LC_VERSION_MIN_MACOSX\s+cmdsize\s+\d+\s+version\s+([\d.]+)", commands)
        if not minimums or any(version(v) > version("15.0") for v in minimums):
            raise ValueError(f"Unsupported minimum macOS for {binary}: {minimums}")
        executable = helper if "Helpers/analyzer/" in str(binary) else main
        if "Helpers/ffmpeg/" in str(binary): executable = app / "Contents/Helpers/ffmpeg/bin/ffmpeg"

        def expand(value):
            return value.replace("@loader_path", str(binary.parent)).replace("@executable_path", str(executable.parent))

        rpaths = re.findall(r"cmd LC_RPATH\s+cmdsize\s+\d+\s+path (.+?) \(offset", commands)
        if executable != binary:
            exe_commands = output("otool", "-arch", "arm64", "-l", executable)
            for rp in re.findall(r"cmd LC_RPATH\s+cmdsize\s+\d+\s+path (.+?) \(offset", exe_commands):
                rpaths.append(rp.replace("@loader_path", str(executable.parent)))
        for rp in rpaths:
            expanded = Path(expand(rp))
            if expanded.is_absolute() and not expanded.resolve().is_relative_to(app.resolve()):
                raise ValueError(f"External runtime search path: {binary}: {rp}")
        deps = []
        for line in output("otool", "-arch", "arm64", "-L", binary).splitlines()[1:]:
            dep = line.strip().split(" (", 1)[0]
            if not dep or dep.endswith(":"): continue
            deps.append(dep)
            if dep.startswith(("/System/Library/", "/usr/lib/")): continue
            if dep.startswith("@rpath/"):
                candidates = [Path(expand(rp)) / dep[len("@rpath/"):] for rp in rpaths]
            else:
                candidates = [Path(expand(dep))]
            if not any(p.is_file() and p.resolve().is_relative_to(app.resolve()) for p in candidates):
                raise ValueError(f"Unresolved/external runtime dependency: {binary}: {dep}")
        records.append({"file": str(binary.relative_to(app)), "architectures": architectures,
                        "minimum_macos": minimums, "dependencies": deps, "rpaths": rpaths})
    if not records or not helper.is_file() or not main.is_file(): raise ValueError("Incomplete app")
    return records


if __name__ == "__main__":
    print(json.dumps(inspect(Path(sys.argv[1]).resolve()), indent=2))
