"""Fetch official matching binaries/templates and verify upstream SHA-512."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = json.loads((ROOT / "packaging/versions.json").read_text())["godot"]


def fetch(url, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=120) as response, destination.open("wb") as out:
        shutil.copyfileobj(response, out)


def download(output, templates=False):
    base = f"https://github.com/godotengine/godot/releases/download/{VERSION}-stable"
    checksums = output / "SHA512-SUMS.txt"
    fetch(base + "/SHA512-SUMS.txt", checksums)
    suffix = "macos.universal.zip" if sys.platform == "darwin" else "linux.x86_64.zip"
    names = [f"Godot_v{VERSION}-stable_{suffix}"]
    if templates: names.append(f"Godot_v{VERSION}-stable_export_templates.tpz")
    expected = {line.split()[-1].lstrip("*"): line.split()[0] for line in checksums.read_text().splitlines() if line.strip()}
    for name in names:
        archive = output / name
        fetch(base + "/" + name, archive)
        if hashlib.sha512(archive.read_bytes()).hexdigest() != expected[name]:
            raise ValueError(f"Official checksum mismatch: {name}")
        if name.endswith(".tpz"):
            target = Path.home() / "Library/Application Support/Godot/export_templates" / f"{VERSION}.stable"
            with zipfile.ZipFile(archive) as z:
                # Only macOS templates are needed; preserve the upstream bytes.
                for member in ("templates/macos.zip", "templates/version.txt"):
                    target.mkdir(parents=True, exist_ok=True)
                    (target / Path(member).name).write_bytes(z.read(member))
        elif sys.platform == "darwin":
            subprocess.run(["ditto", "-x", "-k", str(archive), str(output)], check=True)
        else:
            with zipfile.ZipFile(archive) as z: z.extractall(output)
    binary = output / ("Godot.app/Contents/MacOS/Godot" if sys.platform == "darwin" else f"Godot_v{VERSION}-stable_linux.x86_64")
    binary.chmod(0o755)
    return binary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("destination", type=Path)
    parser.add_argument("--templates", action="store_true")
    args = parser.parse_args()
    print(download(args.destination.resolve(), args.templates))
