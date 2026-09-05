# Determinism

Export time is exactly `frame_index / fps`. Preview time comes from `AudioStreamPlayer.get_playback_position()` and is passed through the same state evaluator.

Feature curves use clamped linear interpolation. Event intervals are `(previous_frame_time, current_frame_time]`, preventing an event on a frame boundary from firing twice. Beat phase is the normalized position between surrounding beats.

Random variation must be a pure function of seed and quantized logical time (or another stable event identity). State repeatability—not cross-GPU pixel hashes—is the correctness contract. The same manifest, visual config, seed, timestamp and code version produces equivalent logical state.

