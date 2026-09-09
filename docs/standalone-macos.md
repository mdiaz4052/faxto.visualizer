# Standalone macOS application — Phase 0.1

This milestone preserves Godot 4.7.2, the Compatibility renderer, the analyzer's
DSP, Signal Field, and the 0.1.0 manifest/configuration formats. The app embeds
Godot itself; there is no second UI framework. A successful CI artifact is an
**Apple Silicon / arm64, macOS 15.0+ internal test build**. Older macOS releases
and Intel Macs are not advertised. GUI acceptance remains separate from build
and headless/helper checks.

## Use the application

Download the `FaXto-Visualizer-arm64-adhoc` artifact from the successful
**Standalone macOS arm64** Actions run for the PR's latest commit. Unzip the
outer artifact, then `FaXto-Visualizer-arm64-adhoc.zip`. Move **FaXto Visualizer.app**
to Applications or another folder and launch it from Finder. The app requires no
Godot editor, external Python/NumPy/FFmpeg, source checkout, Terminal, or network
connection. The archive also contains build/dependency records and FFmpeg source.

This is ad-hoc signed, **not Developer ID signed or notarized**. Gatekeeper may
block a downloaded test build. For a build you intentionally trust, macOS may
provide **System Settings → Privacy & Security → Open Anyway** after the first
attempt. Do not disable Gatekeeper globally. If macOS does not offer a per-app
exception, stop and report the displayed message; Developer ID distribution is
the remaining delivery path. Ad-hoc signing is not a claim of Gatekeeper approval.

1. Choose **Open WAV**, then **Analyze**. The first music folder preference is
   Documents/My music, when present; later choices are remembered.
2. Play/pause, drag the timeline, and adjust Signal Field parameters.
3. Save or load existing 0.1.0 visual configurations. Authored cues and mappings
   are retained. Configured dimensions and frame rate now govern export.
4. Choose **Test Export (5s)** at the current timeline position or **Export Full**.
   **Include MP4 with audio** is on by default; turn it off for PNG only.
5. Use **Cancel** during analysis, frame rendering, or encoding. **Details**
   and **Copy Error Details** retain selectable diagnostic text.
6. **Open Output Folder** opens the most recent output, including complete PNG
   frames after an encoding failure. Every export gets its own uniquely named
   folder. Its `export.json` distinguishes partial from complete sequences.

MP4 H.264 requires even dimensions. PNG-only export also supports odd dimensions.
This milestone accepts 1–8192 pixels per dimension and up to 120 fps; high
resolutions remain subject to available graphics memory. Video is H.264 via
Apple VideoToolbox at a requested 16 Mb/s and AAC at 192 kb/s. If the platform
encoder is unavailable, encoding reports failure and retains the frames; it
never reports a substitute codec/container as successful.

## Storage and compatibility

The project name and default Godot user-data setting are deliberately unchanged.
On macOS, the existing default is
`~/Library/Application Support/Godot/app_userdata/FaXto Visualizer`.
No source audio or user configuration is moved, overwritten, or deleted.
Old basename-only manifests and the old developer virtual environment can remain
in place. Old manifests are not trusted as a content cache: analyze the WAV once
to create the new verified cache. No migration of the old Python environment is
needed by the standalone product.

New data beneath the same application-data directory:

- `preferences.json`: recent WAV/config/export folders.
- `cache/<SHA-256>/`: complete manifest, identity record, and private audio copy.
- `jobs/<random ID>/`: immutable request, stage/result files, and local diagnostics.
- `last-error.json`: the latest complete diagnostic text.

Hashing and copying happen outside the UI thread. Identity includes original
absolute path, audio content, analyzer/helper/schema versions, NumPy version,
and analysis settings. Identical filenames in different folders are independent.
Playback and export use the same immutable audio snapshot that was analyzed;
subsequent edits/moves of the original WAV cannot silently change that song.
Audio snapshots consume disk space. Cache/job cleanup is manual in this phase;
quit the app first and remove only those subdirectories if desired. The app can
rebuild them from the original WAV. Replacing the `.app` leaves this data and
user-selected configurations/output intact. Logs contain local paths and are
never uploaded automatically.

## Helper ownership and cancellation

`AppPaths` locates `Contents/Helpers/analyzer/faxto-helper` relative to the running
executable in every exported build, including debug exports. It never searches
PATH or the repository in release mode. Editor-only development can use the
repo `.venv`, the old `user://analyzer-environment`, or `FAXTO_ANALYZER_PYTHON`.
The release GUI has no Setup Analyzer/install button.

Protocol 1 uses private job directories and atomic JSON files. Godot owns one
nonblocking supervisor. The supervisor starts and owns a process group for
NumPy analysis or FFmpeg and polls cancellation and parent death every 50 ms.
It sends TERM, then KILL after 1.5 s if required, and waits to reap its child.
The app requests cancellation on close and keeps processing events for up to
five seconds; the supervisor also detects application force-quit. No blocking
`OS.execute` or UI-thread join is used. Conflicting actions are disabled, and
job IDs reject stale results. Completion is accepted only after successful
helper exit. Failed/cancelled analysis leaves the previous valid song available.

Analysis publishes a complete cache directory by rename; encoding writes a
private `.partial.mp4` then publishes via an atomic, no-clobber hard link.
Incomplete results are never loaded as completed work. The output filesystem
must support hard links (normal APFS does). On a filesystem that does not, the
app reports encoding publication failure, preserves PNGs, and removes the
unpublished temporary video. Use a local APFS folder for MP4 export.

## Rendering and timing

`ExportTarget` is a fixed-size `SubViewport` containing the unchanged Signal
Field scene. Preview and export use the existing `StateEvaluator`; export
snapshots parameters, seed, audio, interval, dimensions, and fps. No application
screenshot, viewport crop, or post-capture resizing is involved.

For [start, end), timestamps are `start + frame_index/fps`. The sequence has
`ceil((end-start)*fps)` frames (with a tiny floating-boundary tolerance). The
last frame samples within the interval; MP4 uses the requested duration, with
container/frame-rate quantization up to one frame. Audio is trimmed from the
same nonzero start. Logical state is deterministic; identical GPU pixels across
different hardware are not promised.

## Repeatable developer build

Build on native Apple Silicon macOS 15 with Xcode Command Line Tools, Python
3.13.15, and GnuPG available. Only developer/CI machines need these commands:

```sh
python3.13 -m venv .venv
.venv/bin/python -m pip install -r analyzer/requirements-lock.txt -r packaging/requirements-lock.txt
.venv/bin/python tools/build_macos.py
```

Python 3.13.15 is used because GitHub provides current native macOS binaries
for that series; 3.12.14 is not available there. CI tests both 3.12.14 and
3.13.15 with unchanged NumPy 2.3.5 and DSP, and compares frozen/unfrozen
results within the native build.

Pins are in `packaging/versions.json` and both requirements locks. The builder
enables the ETC2/ASTC import format required by Godot’s arm64 export validator
(the selected renderer and Signal Field drawing remain unchanged),
fetches matching official Godot binary/templates and verifies their upstream
SHA-512 manifest. Official macOS templates contain a universal engine executable;
the builder explicitly thins it to arm64 before adding the arm64-only helpers
and checking every native dependency. The delivered app is not universal. FFmpeg 8.0.1 source is SHA-256 pinned and its upstream detached
signature is checked against the pinned release-key fingerprint. The builder
compiles a controlled, shared-library LGPL-only FFmpeg with autodetection,
network, GPL, and nonfree components disabled. It fixes relative install names,
collects notices/source/configuration records, freezes the analyzer with
PyInstaller one-directory mode, checks every native binary for arm64, deployment
target, and library closure, then signs nested code and the app ad hoc.

The build runs a relocated-copy smoke test with developer environment variables
removed, PATH limited to system tools, fresh explicit job/cache directories,
and the entire checkout temporarily unavailable. It compares frozen and
unfrozen analyzer results and exercises the actual bundled encoder. The outer
archive is created with `ditto` to preserve symlinks, executable permissions,
and the `.app` structure. Failed packaging/isolation checks produce no release
archive. `build-info.json` records exact head, versions, packages, and signing.

The macOS workflow checks `uname -m` rather than trusting a runner label and
checks out the exact PR head. Its token is read-only; it has no signing secrets.
Linux CI additionally renders a short sequence under Xvfb. Headless tests do
not stand in for a macOS desktop/GPU session.

## Signing and corresponding source

Full bundled notices are under `Contents/Resources/ThirdPartyNotices`; the app
shows the overview through **Third-party Notices**. FFmpeg's complete unmodified
source, signature, configure arguments, and build script are included in the app
and `FFmpeg-corresponding-source.zip`. Shared libraries are replaceable; no
proprietary project objects are linked into FFmpeg. Distribution obligations
are based on this controlled build, not a developer-installed FFmpeg. No
license is assigned to FaXto's own project or music by these changes.

A local maintainer with a Developer ID certificate in an approved keychain can
sign the tested bundle using `tools/sign_macos.py APP --identity IDENTITY`.
With a previously configured `notarytool` keychain profile, add
`--notary-profile PROFILE`. The script signs inner Mach-O files, then frameworks,
then the outer bundle with the hardened runtime, submits an archive, requires
Accepted, and staples/validates the ticket. Re-create the delivery ZIP after
signing/stapling. Update the external build record to identify the signed
artifact; do not edit a signed app in place. This credentialed path is opt-in
and is never run on untrusted PRs. No secrets belong in chat, source, or logs.

## GUI acceptance checklist

On Miguel's Mac, using only Finder and the app: launch, open/analyze a WAV,
play/pause/scrub, adjust parameters, save/load an existing config, resize the
window, export five seconds with audio starting away from zero, cancel an
operation, close, and reopen. Confirm perceived sync, readable dialogs/errors,
folder access, and Gatekeeper behavior. Record this separately from local
unit tests, native helper checks, and the existence of a built archive.
