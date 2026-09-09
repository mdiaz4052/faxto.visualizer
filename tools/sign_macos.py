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
        app_bundles = [*app.rglob("*.app"), app]
        main_executables = set()
        for bundle in app_bundles:
            info = plistlib.loads((bundle / "Contents/Info.plist").read_bytes())
            main_executables.add(bundle / "Contents/MacOS" / info["CFBundleExecutable"])
        for binary in sorted(native_files(app), key=lambda p: len(p.parts), reverse=True):
            # Signing a bundle's main executable also signs its enclosing bundle;
            # defer it until all nested code/frameworks are complete.
            if binary not in main_executables:
                run("codesign", *flags, binary)
        for framework in sorted(app.rglob("*.framework"), key=lambda p: len(p.parts), reverse=True):
            if not framework.is_symlink(): run("codesign", *flags, framework)
        for bundle in sorted(app_bundles, key=lambda p: len(p.parts), reverse=True):
            extra = ["--entitlements", str(entitlements)] if bundle == app else []
            run("codesign", *flags, *extra, bundle)
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
