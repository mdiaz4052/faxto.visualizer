extends SceneTree

const MainScene = preload("res://ui/main.tscn")
var failures: Array[String] = []

func _initialize() -> void:
	call_deferred("run")

func expect(condition: bool, message: String) -> void:
	if not condition: failures.append(message)

func run() -> void:
	var main = MainScene.instantiate()
	root.add_child(main)
	await process_frame
	var folder := ProjectSettings.globalize_path("user://test-" + AppPaths.token())
	expect(DirAccess.make_dir_absolute(folder) == OK, "private test folder")
	var path := folder.path_join("legacy.json")
	var legacy := {"schema_version": "0.1.0", "scene": "signal_field", "seed": 91, "parameters": {"deformation": 1.2, "impact_scale": 0.2, "element_count": 40}, "mappings": {"future": 1}, "authored_cues": [{"time": 1}], "export": {"width": 640, "height": 360, "fps": 24}}
	legacy = JSON.parse_string(JSON.stringify(legacy))
	AppPaths.write_json(path, legacy)
	main._read_config(path)
	expect(main.seed_value == 91 and main.export_width == 640 and main.export_fps == 24, "legacy config and export settings load")
	main._write_config(path)
	var restored := AppPaths.read_json(path)
	expect(restored.mappings == legacy.mappings and restored.authored_cues == legacy.authored_cues, "config preserves authored/future data")
	AppPaths.write_json(path, {"schema_version": "0.1.0", "scene": "signal_field", "parameters": {"deformation": "bad"}})
	main._read_config(path)
	expect(main.seed_value == 91, "invalid config preserves valid state")
	var helper := HelperJob.new()
	var missing_command := AppPaths.helper_command()
	expect(not str(missing_command.executable).is_empty(), "development helper path resolves")
	helper.id = "current"
	helper.directory = folder
	AppPaths.write_json(folder.path_join("result.json"), {"protocol": 1, "job_id": "stale", "state": "complete"})
	helper.pid = OS.create_process("/usr/bin/true", PackedStringArray())
	while OS.is_process_running(helper.pid): await process_frame
	expect(helper.poll().get("state") == "failed", "stale helper completion rejected")
	main.job.pid = 2147483646
	main.selected_wav = "original.wav"
	main._wav_selected("wrong.wav")
	expect(main.selected_wav == "original.wav", "busy selection cannot replace immutable request")
	main.job.pid = -1
	var features := FeatureTimeline.new()
	features.load_manifest({"schema_version": "0.1.0", "source": {"duration_seconds": 2.0}, "curves": [{"name": "rms", "sample_interval_seconds": 1.0, "values": [0.2, 0.8]}], "events": {"beats": [0.0, 0.5, 1.0]}})
	var target := ExportTarget.new()
	root.add_child(target)
	var params := {"deformation": 0.8}
	target.configure(features, {"width": 640, "height": 360, "fps": 12, "start": 0.37, "end": 0.78, "seed": 42, "parameters": params})
	params.deformation = 99
	var actual := target.prepare_frame(1)
	var expected := StateEvaluator.evaluate(features, 0.37 + 1.0 / 12, 0.37, 42, {"deformation": 0.8})
	expect(actual == expected, "export shares timestamp/state semantics and freezes parameters")
	expect(target.frame_count == 5 and target.size == Vector2i(640, 360), "partial final frame and fixed dimensions")
	target.queue_free()
	main.queue_free()
	await process_frame
	for file in DirAccess.get_files_at(folder): DirAccess.remove_absolute(folder.path_join(file))
	DirAccess.remove_absolute(folder)
	if failures.is_empty(): print("Godot standalone contracts: passed")
	else:
		for failure in failures: push_error(failure)
	quit(0 if failures.is_empty() else 1)
