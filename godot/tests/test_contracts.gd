extends SceneTree

const MainScript = preload("res://ui/main.gd")
const MainScene = preload("res://ui/main.tscn")

var failures: Array[String] = []

func _init() -> void:
	var timeline := FeatureTimeline.new()
	var error := timeline.load_manifest(_fixture_manifest())
	_expect(error.is_empty(), "fixture manifest loads")
	_expect(is_equal_approx(timeline.value("rms", 0.5), 0.5), "continuous values interpolate linearly")
	_expect(is_equal_approx(timeline.value("rms", -2.0), 0.0), "feature lookup clamps before the first sample")
	_expect(is_equal_approx(timeline.value("rms", 4.0), 1.0), "feature lookup clamps after the last sample")
	_expect(timeline.previous_event("beats", 0.75) == 0.5, "previous event lookup")
	_expect(timeline.next_event("beats", 0.75) == 1.0, "next event lookup")
	_expect(is_equal_approx(timeline.event_phase("beats", 0.75), 0.5), "beat phase calculation")
	_expect(timeline.event_occurred("beats", 0.49, 0.5), "event interval includes its right boundary")
	_expect(not timeline.event_occurred("beats", 0.5, 0.6), "event interval excludes its left boundary")
	_expect(is_equal_approx(StateEvaluator.frame_time(30, 30.0), 1.0), "frame index converts to deterministic time")
	var first := StateEvaluator.evaluate(timeline, 0.75, 0.5, 42, {"deformation": 0.8})
	var repeated := StateEvaluator.evaluate(timeline, 0.75, 0.5, 42, {"deformation": 0.8})
	var alternate := StateEvaluator.evaluate(timeline, 0.75, 0.5, 43, {"deformation": 0.8})
	_expect(first == repeated, "repeated logical evaluation is deterministic")
	_expect(first.seeded_variation != alternate.seeded_variation, "seed changes deterministic variation")
	_expect(MainScript != null, "main GUI script parses")
	_expect(MainScene != null, "main GUI scene resource loads")
	if failures.is_empty():
		print("Godot Phase 0 contracts: all checks passed")
		quit(0)
	else:
		for failure in failures:
			push_error(failure)
		quit(1)

func _expect(condition: bool, label: String) -> void:
	if not condition:
		failures.append(label)

func _fixture_manifest() -> Dictionary:
	return {
		"schema_version": "0.1.0",
		"source": {"duration_seconds": 1.0},
		"curves": [
			{"name": "rms", "sample_interval_seconds": 1.0, "values": [0.0, 1.0]},
			{"name": "onset_strength", "sample_interval_seconds": 1.0, "values": [0.25, 0.75]},
			{"name": "spectral_centroid_hz", "sample_interval_seconds": 1.0, "values": [1000.0, 5000.0]}
		],
		"events": {"beats": [0.0, 0.5, 1.0], "onsets": [0.5], "downbeats": []}
	}
