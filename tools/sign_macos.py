"""Sign nested code in order; optional notarization uses an existing keychain profile."""
import argparse
import json
from pathlib import Path
import plistlib
import subprocess
import tempfile

from inspect_macos_bundle import native_files


def run(*args):
    subprocess.run([str(a) for a in args], check=True)


def sign(app, identity="-", profile=None):
    if profile and identity == "-": raise ValueError("Notarization requires a Developer ID identity")
    flags = ["--force", "--sign", identity]
    if identity != "-": flags += ["--options", "runtime", "--timestamp"]
    else: flags += ["--timestamp=none"]
    with tempfile.TemporaryDirectory() as temp:
        entitlements = Path(temp) / "godot.plist"
        entitlements.write_bytes(plistlib.dumps({"com.apple.security.cs.allow-jit": True}))
        for binary in sorted(native_files(app), key=lambda p: len(p.parts), reverse=True):
            extra = ["--entitlements", str(entitlements)] if binary.parent == app / "Contents/MacOS" else []
            run("codesign", *flags, *extra, binary)
        for framework in sorted(app.rglob("*.framework"), key=lambda p: len(p.parts), reverse=True):
            if not framework.is_symlink(): run("codesign", *flags, framework)
        run("codesign", *flags, "--entitlements", entitlements, app)
        run("codesign", "--verify", "--deep", "--strict", "--verbose=2", app)
        if profile:
            archive = Path(temp) / "FaXto-Notarization.zip"
            run("ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", app, archive)
            response = subprocess.check_output(["xcrun", "notarytool", "submit", str(archive), "--keychain-profile", profile, "--wait", "--output-format", "json"], text=True)
            result = json.loads(response)
            if result.get("status") != "Accepted": raise RuntimeError("Notarization was not accepted")
            run("xcrun", "stapler", "staple", app)
            run("xcrun", "stapler", "validate", app)
            run("spctl", "--assess", "--type", "execute", "--verbose=2", app)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("app", type=Path)
    parser.add_argument("--identity", default="-")
    parser.add_argument("--notary-profile")
    args = parser.parse_args()
    sign(args.app.resolve(), args.identity, args.notary_profile)
