# Run under a graphics session (xvfb on Linux); never --headless.
extends SceneTree

var failures: Array[String] = []
func _initialize() -> void: call_deferred("run")
func expect(condition: bool, message: String) -> void:
	if not condition: failures.append(message)

func run() -> void:
	var main = load("res://ui/main.tscn").instantiate()
	root.add_child(main)
	await process_frame
	var features := FeatureTimeline.new()
	features.load_manifest({"schema_version": "0.1.0", "source": {"duration_seconds": 2.0}, "curves": [
		{"name": "rms", "sample_interval_seconds": 1.0, "values": [0.3, 0.9]},
		{"name": "onset_strength", "sample_interval_seconds": 1.0, "values": [0.2, 0.7]},
		{"name": "spectral_centroid_hz", "sample_interval_seconds": 1.0, "values": [1000, 5000]}], "events": {"beats": [0.0, 0.5, 1.0]}})
	var target := ExportTarget.new()
	root.add_child(target)
	target.configure(features, {"width": 320, "height": 180, "fps": 12, "start": 0.37, "end": 0.78, "seed": 42, "parameters": {"deformation": 0.8}})
	root.mode = Window.MODE_WINDOWED
	root.size = Vector2i(1280, 720)
	target.prepare_frame(1)
	await RenderingServer.frame_post_draw
	var first := target.get_texture().get_image()
	root.size = Vector2i(800, 600)
	target.prepare_frame(1)
	await RenderingServer.frame_post_draw
	var second := target.get_texture().get_image()
	expect(first.get_size() == Vector2i(320, 180), "exact export resolution")
	expect(first.get_data() == second.get_data(), "composition independent of window size on this renderer")
	expect(first.get_pixel(160, 90) != first.get_pixel(270, 80) or first.get_data().count(0) < first.get_data().size() / 2, "nonempty visual rendering")
	var folder := ProjectSettings.globalize_path("user://render-test-" + AppPaths.token())
	DirAccess.make_dir_absolute(folder)
	main.timeline = features
	main.export_width = 320
	main.export_height = 180
	main.export_fps = 12
	main.export_start_time = 0.37
	main.export_end_time = 0.78
	main.export_video.button_pressed = false
	main._start_export(folder)
	var deadline := Time.get_ticks_msec() + 15000
	while main.exporting and Time.get_ticks_msec() < deadline: await process_frame
	expect(not main.exporting, "frame export finishes")
	var exported: String = main.export_directory
	expect(AppPaths.read_json(exported.path_join("export.json")).get("complete_frames") == 5, "exact sequence frame count")
	expect(FileAccess.file_exists(exported.path_join(".gdignore")), "no importer sidecars")
	var frame := Image.load_from_file(exported.path_join("frame_000001.png"))
	expect(frame.get_size() == Vector2i(320, 180), "written frame dimensions")
	main._start_export(folder)
	main._cancel_operation()
	await process_frame
	expect(not main.exporting and AppPaths.read_json(main.export_directory.path_join("export.json")).get("state") == "cancelled", "frame cancellation records partial state")
	for directory in DirAccess.get_directories_at(folder):
		for file in DirAccess.get_files_at(folder.path_join(directory)): DirAccess.remove_absolute(folder.path_join(directory).path_join(file))
		DirAccess.remove_absolute(folder.path_join(directory))
	DirAccess.remove_absolute(folder)
	target.queue_free()
	main.queue_free()
	await process_frame
	if failures.is_empty(): print("Fixed viewport and PNG export: passed")
	else:
		for failure in failures: push_error(failure)
	quit(0 if failures.is_empty() else 1)
