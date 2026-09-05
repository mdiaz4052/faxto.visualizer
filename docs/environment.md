# Phase 0 environment

Implemented and analyzer-tested with:

- Python 3.12.13
- NumPy 2.3.5
- FFmpeg 6.1.1

The Godot project targets Godot 4.3+ syntax and the compatibility renderer. No Godot binary was available in the implementation environment, so editor import, GUI interaction, playback synchronization, and video frame capture require a smoke test in Godot before Phase 0 can be declared complete. This is an explicit validation gap, not a claim of completion.

`analyzer/requirements-lock.txt` reproduces the tested DSP dependency. `pyproject.toml` permits compatible NumPy 2.x updates for ordinary development.
