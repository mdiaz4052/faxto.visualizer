# Architecture

## Decision: Godot + Python + FFmpeg

Phase 0 retains the proposed stack. Python/NumPy provides inspectable song-wide DSP, Godot 4 provides the creative GUI/scene/shader environment, and FFmpeg assembles deterministic image sequences with source audio. The boundary is a versioned JSON manifest, so analyzer and renderer can evolve independently.

## Layers

1. **Measurement:** analyzer-owned RMS, band energy, centroid, onset strength and estimated events. Estimates carry confidence and are not asserted as musical truth.
2. **Musical state:** time, progress, beat phase, nearby events and structural location.
3. **Expressive state:** explicitly subjective channels such as intensity, impact, brightness and openness.
4. **Visual context:** immutable inputs passed to a scene for a timestamp, parameters and seed.
5. **Behavior/scene:** a scene interprets context through pulse, compression, accumulation, rupture or other reusable behaviors.
6. **Renderer:** preview and export provide different clocks to the same evaluation path.

This avoids direct FFT-to-object coupling. A measured onset can become `impact`; Signal Field may express it as compression, while a future scene can express the same channel as erasure, a step, or delayed accumulation.

Manifests use a `source_id` on every curve. Phase 0 creates only `master`, but the contract can add vocal/drum/bass sources without changing scene code.

## Dependency direction

Scenes depend on `VisualContext`, never analyzer implementation details. Artistic configuration is separate from measurement data. No scene may mutate the manifest.

