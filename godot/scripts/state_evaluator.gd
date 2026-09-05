class_name StateEvaluator
extends RefCounted

static func frame_time(frame_index: int, fps: float) -> float:
	return float(frame_index) / fps

static func evaluate(features: FeatureTimeline, song_time: float, previous_time: float, seed_value: int, parameters: Dictionary) -> Dictionary:
	var t := clampf(song_time, 0.0, features.duration)
	var intensity := features.value("rms", t)
	var impact := features.value("onset_strength", t)
	var centroid := features.value("spectral_centroid_hz", t)
	var rng := RandomNumberGenerator.new()
	rng.seed = hash("%s:%0.6f" % [seed_value, t])
	return {
		"song_time": t,
		"delta_time": maxf(0.0, t - previous_time),
		"normalized_progress": t / features.duration,
		"feature_values": {"rms": intensity, "centroid_hz": centroid, "onset_strength": impact},
		"musical_state": {"beat_phase": features.event_phase("beats", t), "recent_onset": features.event_occurred("onsets", previous_time, t), "song_progress": t / features.duration},
		"expressive_state": {"intensity": intensity, "impact": impact, "brightness": clampf(centroid / 8000.0, 0.0, 1.0), "openness": 1.0 - intensity},
		"scene_parameters": parameters,
		"deterministic_seed": seed_value,
		"seeded_variation": rng.randf()
	}

