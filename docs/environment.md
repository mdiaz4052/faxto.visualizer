# Phase 0 environment

Implemented and analyzer-tested with:

- Python 3.12.13
- NumPy 2.3.5
- FFmpeg 6.1.1
- Godot 4.7.2 headless import and contract tests in CI

The Godot project targets Godot 4.7.2 and the compatibility renderer. CI imports the complete project and runs logical-state contract tests with the official headless Linux build. Interactive playback synchronization and video frame capture still require a short macOS smoke test because headless CI cannot judge perceived audiovisual timing or desktop file-dialog behavior.

Use the regular Godot build. The `.NET` edition exists for C# projects and is not required because FaXto Visualizer uses GDScript.

`analyzer/requirements-lock.txt` reproduces the tested DSP dependency. `pyproject.toml` permits compatible NumPy 2.x updates for ordinary development.

The GUI's **Setup Analyzer** action creates a private virtual environment in Godot's per-user application-data directory and installs the pinned requirements there. It does not alter the system Python environment. Python 3 itself must already exist; missing Python is reported in the interface.
