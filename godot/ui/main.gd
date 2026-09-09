extends Control

const SignalFieldScene = preload("res://scenes/signal_field.tscn")
var timeline := FeatureTimeline.new()
var audio := AudioStreamPlayer.new()
var visual: SignalField
var status := Label.new()
var details := TextEdit.new()
var time_label := Label.new()
var scrubber := HSlider.new()
var scrubber_dragging := false
var play_button: Button
var cancel_export_button: Button
var conflicting_controls: Array[BaseButton] = []
var selected_wav := ""
var active_wav := ""
var manifest_path := ""
var last_time := 0.0
var seed_value := 42
var parameters := {"deformation": 0.8, "impact_scale": 0.7, "element_count": 28.0}
var parameter_controls: Dictionary = {}
var config_extras: Dictionary = {}
var preferences: Dictionary = {}
var export_directory := ""
var exporting := false
var export_frame_pending := false
var export_frame := 0
var export_fps := 30.0
var export_width := 1280
var export_height := 720
var export_start_time := 0.0
var export_end_time := 0.0
var export_is_test := false
var export_video := CheckBox.new()
var export_target: ExportTarget
var export_epoch := 0
var job := HelperJob.new()
var dialog_open := false
var closing := false
var close_deadline := 0

func _ready() -> void:
	preferences = AppPaths.read_json("user://preferences.json")
	_build_ui()
	get_tree().auto_accept_quit = false
	set_process(true)

func _build_ui() -> void:
	add_child(audio)
	audio.finished.connect(func(): play_button.text = "Play")
	var root := VBoxContainer.new()
	root.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	add_child(root)
	var toolbar := HFlowContainer.new()
	root.add_child(toolbar)
	_action(toolbar, "Open WAV", _open_wav)
	_action(toolbar, "Analyze", _analyze)
	play_button = _action(toolbar, "Play", _toggle_play)
	_action(toolbar, "Save Config", _save_config)
	_action(toolbar, "Load Config", _load_config)
	_action(toolbar, "Test Export (5s)", _choose_test_export)
	_action(toolbar, "Export Full", _choose_export)
	cancel_export_button = _add_button(toolbar, "Cancel", _cancel_operation)
	cancel_export_button.disabled = true
	_add_button(toolbar, "Open Output Folder", _open_output)
	_add_button(toolbar, "Details", func(): details.visible = not details.visible)
	_add_button(toolbar, "Copy Error Details", func(): DisplayServer.clipboard_set(details.text))
	_add_button(toolbar, "Third-party Notices", _show_notices)
	status.text = "Choose a PCM WAV to begin"
	status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	root.add_child(status)
	var body := HSplitContainer.new()
	body.size_flags_vertical = Control.SIZE_EXPAND_FILL
	root.add_child(body)
	var viewport_panel := PanelContainer.new()
	viewport_panel.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	body.add_child(viewport_panel)
	visual = SignalFieldScene.instantiate()
	viewport_panel.add_child(visual)
	var scroll := ScrollContainer.new()
	scroll.custom_minimum_size.x = 220
	body.add_child(scroll)
	var controls := VBoxContainer.new()
	controls.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	scroll.add_child(controls)
	var scene_label := Label.new()
	scene_label.text = "Signal Field"
	controls.add_child(scene_label)
	_add_parameter(controls, "Deformation", "deformation", 0.0, 2.0)
	_add_parameter(controls, "Impact scale", "impact_scale", 0.0, 2.0)
	_add_parameter(controls, "Element count", "element_count", 8.0, 80.0, 1.0)
	_add_button(controls, "Reset Parameters", _reset_parameters)
	export_video.text = "Include MP4 with audio"
	export_video.button_pressed = true
	controls.add_child(export_video)
	var timeline_row := HBoxContainer.new()
	root.add_child(timeline_row)
	scrubber.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	scrubber.step = 0.001
	scrubber.drag_started.connect(_scrub_started)
	scrubber.drag_ended.connect(_scrub_ended)
	scrubber.value_changed.connect(_scrub_preview)
	timeline_row.add_child(scrubber)
	time_label.text = "00:00.000 / 00:00.000"
	timeline_row.add_child(time_label)
	details.editable = false
	details.custom_minimum_size.y = 150
	details.wrap_mode = TextEdit.LINE_WRAPPING_BOUNDARY
	details.visible = false
	root.add_child(details)

func _add_button(parent: Control, text_value: String, callback: Callable) -> Button:
	var button := Button.new()
	button.text = text_value
	button.pressed.connect(callback)
	parent.add_child(button)
	return button

func _action(parent: Control, text_value: String, callback: Callable) -> Button:
	var button := _add_button(parent, text_value, callback)
	conflicting_controls.append(button)
	return button

func _add_parameter(parent: Control, label_text: String, key: String, low: float, high: float, step_value := 0.01) -> void:
	var label := Label.new()
	label.text = label_text
	parent.add_child(label)
	var slider := HSlider.new()
	slider.min_value = low
	slider.max_value = high
	slider.step = step_value
	slider.value = parameters[key]
	slider.value_changed.connect(func(value): parameters[key] = value; _evaluate(scrubber.value))
	parent.add_child(slider)
	parameter_controls[key] = slider

func _busy() -> bool:
	return exporting or job.running() or dialog_open or closing

func _refresh_controls() -> void:
	for control in conflicting_controls: control.disabled = _busy()
	scrubber.editable = not _busy()
	cancel_export_button.disabled = not (exporting or job.running()) or job.cancelling

func _error(message: String, diagnostic := "") -> void:
	status.text = message
	details.text = "FaXto Visualizer %s | Godot %s | %s\n%s\n%s" % [AppPaths.APP_VERSION, Engine.get_version_info().string, OS.get_name(), message, diagnostic]
	details.visible = true
	var log_error := AppPaths.write_json("user://last-error.json", {"details": details.text})
	if log_error != OK: details.text += "\nCould not save error log: " + error_string(log_error)

func _remember(kind: String, directory: String) -> void:
	preferences[kind] = directory
	var error := AppPaths.write_json("user://preferences.json", preferences)
	if error != OK: _error("Could not save recent folders", error_string(error))

func _dialog(mode: FileDialog.FileMode, filters: PackedStringArray, callback: Callable, title: String, kind: String) -> void:
	if _busy(): return
	dialog_open = true
	_refresh_controls()
	var dialog := FileDialog.new()
	dialog.file_mode = mode
	dialog.access = FileDialog.ACCESS_FILESYSTEM
	dialog.filters = filters
	dialog.title = title
	dialog.use_native_dialog = OS.get_name() == "macOS"
	dialog.current_dir = AppPaths.preferred_directory(preferences, kind)
	var accept := func(path: String):
		dialog_open = false
		_refresh_controls()
		_remember(kind, path if mode == FileDialog.FILE_MODE_OPEN_DIR else path.get_base_dir())
		callback.call(path)
		dialog.queue_free()
	dialog.file_selected.connect(accept)
	dialog.dir_selected.connect(accept)
	dialog.canceled.connect(func(): dialog_open = false; _refresh_controls(); dialog.queue_free())
	add_child(dialog)
	dialog.popup_centered_ratio(0.8)

func _open_wav() -> void:
	_dialog(FileDialog.FILE_MODE_OPEN_FILE, PackedStringArray(["*.wav ; WAV audio"]), _wav_selected, "Open Song", "wav")

func _preferred_music_directory() -> String:
	return AppPaths.preferred_directory(preferences, "wav")

func _wav_selected(path: String) -> void:
	if _busy(): return
	selected_wav = path
	status.text = "Selected %s — click Analyze" % path.get_file()

func _analyze() -> void:
	if _busy(): return
	if selected_wav.is_empty(): status.text = "Choose a WAV first"; return
	var error := job.start("analyze", {"wav": selected_wav, "cache_dir": ProjectSettings.globalize_path("user://cache")})
	if not error.is_empty(): _error(error); return
	audio.stream_paused = true
	play_button.text = "Play"
	status.text = "Starting analyzer…"
	_refresh_controls()

func _job_finished(result: Dictionary) -> void:
	_refresh_controls()
	if closing: return
	if result.get("state") == "cancelled":
		status.text = "Cancelled. Previous song remains available." if job.request.operation == "analyze" else "Encoding cancelled. Complete PNG frames remain in the output folder."
		return
	if result.get("state") != "complete":
		var message := str(result.get("error", "Helper operation failed"))
		if job.request.operation == "encode": message += " Complete PNG frames remain in the output folder."
		_error(message, job.diagnostics())
		return
	if job.request.operation == "analyze":
		_load_manifest(str(result.manifest), str(result.wav), str(result.original_wav))
	else:
		status.text = "Video and PNG frames complete — Open Output Folder"
		_write_export_record("complete", {"video": result.video})

func _load_manifest(path: String, wav_path: String, original_path: String) -> void:
	var parsed := AppPaths.read_json(path)
	if parsed.is_empty(): _error("Could not read analysis manifest", path); return
	var next_timeline := FeatureTimeline.new()
	var error := next_timeline.load_manifest(parsed)
	if not error.is_empty(): _error(error, path); return
	var stream := AudioStreamWAV.load_from_file(wav_path)
	if stream == null: _error("The analyzed WAV could not be loaded for playback", wav_path); return
	# Commit the new project state only when both manifest and audio are usable.
	audio.stop()
	audio.stream = stream
	audio.stream_paused = false
	timeline = next_timeline
	active_wav = wav_path
	selected_wav = original_path
	manifest_path = path
	scrubber.max_value = timeline.duration
	scrubber.set_value_no_signal(0.0)
	last_time = 0.0
	play_button.text = "Play"
	status.text = "Ready — %s" % original_path.get_file()
	_evaluate(0.0)

func _toggle_play() -> void:
	if _busy(): return
	if audio.stream == null: status.text = "Analyze a WAV before playback"; return
	if audio.playing: audio.stream_paused = not audio.stream_paused
	else:
		audio.stream_paused = false
		audio.play(scrubber.value)
	play_button.text = "Play" if audio.stream_paused else "Pause"

func _scrub_started() -> void:
	scrubber_dragging = true

func _scrub_preview(value: float) -> void:
	if scrubber_dragging: _evaluate(value)

func _scrub_ended(_changed: bool) -> void:
	scrubber_dragging = false
	if audio.stream != null:
		var was_active := audio.playing and not audio.stream_paused
		audio.play(scrubber.value)
		audio.stream_paused = not was_active
	last_time = scrubber.value
	_evaluate(scrubber.value)

func _process(_delta: float) -> void:
	if job.running():
		status.text = job.stage()
		var result := job.poll()
		if not result.is_empty(): _job_finished(result)
	if closing:
		if not job.running() or Time.get_ticks_msec() >= close_deadline: get_tree().quit()
		return
	if exporting:
		if not export_frame_pending: _export_next_frame()
		return
	if audio.playing and not audio.stream_paused and not scrubber_dragging:
		var current := audio.get_playback_position()
		scrubber.set_value_no_signal(current)
		_evaluate(current)

func _evaluate(song_time: float) -> void:
	if timeline.duration <= 0.0 or visual == null: return
	visual.set_visual_context(StateEvaluator.evaluate(timeline, song_time, last_time, seed_value, parameters))
	time_label.text = "%s / %s" % [_format_time(song_time), _format_time(timeline.duration)]
	last_time = song_time

func _format_time(value: float) -> String:
	return "%02d:%06.3f" % [int(value) / 60, fmod(value, 60.0)]

func _reset_parameters() -> void:
	parameters = {"deformation": 0.8, "impact_scale": 0.7, "element_count": 28.0}
	for key in parameter_controls: parameter_controls[key].value = parameters[key]
	_evaluate(scrubber.value)

func _save_config() -> void:
	_dialog(FileDialog.FILE_MODE_SAVE_FILE, PackedStringArray(["*.json ; Visual config"]), _write_config, "Save Visual Configuration", "config")

func _write_config(path: String) -> void:
	var config := config_extras.duplicate(true)
	config.merge({"schema_version": "0.1.0", "scene": "signal_field", "seed": seed_value, "parameters": parameters, "export": {"width": export_width, "height": export_height, "fps": export_fps}}, true)
	if not config.has("mappings"): config.mappings = {}
	if not config.has("authored_cues"): config.authored_cues = []
	var error := AppPaths.write_json(path, config)
	if error != OK: _error("Could not save configuration", error_string(error)); return
	status.text = "Configuration saved"

func _load_config() -> void:
	_dialog(FileDialog.FILE_MODE_OPEN_FILE, PackedStringArray(["*.json ; Visual config"]), _read_config, "Load Visual Configuration", "config")

func _read_config(path: String) -> void:
	var config := AppPaths.read_json(path)
	if config.get("schema_version") != "0.1.0" or config.get("scene") != "signal_field" or not config.get("parameters", {}) is Dictionary or not config.get("export", {}) is Dictionary:
		_error("Unsupported or malformed visual configuration", path); return
	var next_parameters := parameters.duplicate(true)
	next_parameters.merge(config.get("parameters", {}), true)
	for key in parameter_controls:
		if not _finite_number(next_parameters.get(key)):
			_error("Invalid configuration parameter: " + key); return
	var output: Dictionary = config.get("export", {})
	var width = output.get("width", 1280)
	var height = output.get("height", 720)
	var fps = output.get("fps", 30)
	var seed = config.get("seed", 42)
	if not _finite_number(width) or not _finite_number(height) or not _finite_number(fps) or not _finite_number(seed):
		_error("Configuration dimensions, frame rate and seed must be finite numbers"); return
	if width != floor(width) or height != floor(height) or seed != floor(seed) or width < 1 or height < 1 or width > 8192 or height > 8192 or fps <= 0 or fps > 120:
		_error("Supported exports: 1–8192 pixels per dimension and up to 120 fps; seed must be an integer"); return
	seed_value = int(seed)
	parameters = next_parameters
	config_extras = config.duplicate(true)
	export_width = int(width)
	export_height = int(height)
	export_fps = float(fps)
	for key in parameter_controls: parameter_controls[key].value = parameters[key]
	status.text = "Configuration loaded"
	_evaluate(scrubber.value)

func _finite_number(value: Variant) -> bool:
	return (value is float or value is int) and is_finite(float(value))

func _choose_export() -> void:
	if _busy(): return
	if timeline.duration <= 0.0: status.text = "Analyze a WAV before export"; return
	export_start_time = 0.0
	export_end_time = timeline.duration
	export_is_test = false
	_dialog(FileDialog.FILE_MODE_OPEN_DIR, PackedStringArray(), _start_export, "Choose Export Folder", "export")

func _choose_test_export() -> void:
	if _busy(): return
	if timeline.duration <= 0.0: status.text = "Analyze a WAV before export"; return
	export_start_time = minf(scrubber.value, maxf(0.0, timeline.duration - 0.1))
	export_end_time = minf(timeline.duration, export_start_time + 5.0)
	export_is_test = true
	_dialog(FileDialog.FILE_MODE_OPEN_DIR, PackedStringArray(), _start_export, "Choose Test Export Folder", "export")

func _start_export(path: String) -> void:
	if _busy(): return
	if export_video.button_pressed and (export_width % 2 != 0 or export_height % 2 != 0):
		_error("MP4 requires even dimensions. Use PNG only for this configuration."); return
	if DisplayServer.get_name() == "headless":
		_error("Frame export requires a graphics session; headless launch cannot render frames."); return
	var timestamp := Time.get_datetime_string_from_system().replace(":", "-")
	export_directory = path.path_join("faxto_%s_%s" % [timestamp, AppPaths.token()])
	var error := DirAccess.make_dir_absolute(export_directory)
	if error != OK: _error("Cannot create export folder", error_string(error)); return
	var ignore_file := FileAccess.open(export_directory.path_join(".gdignore"), FileAccess.WRITE)
	if ignore_file == null: _error("Cannot write to export folder", error_string(FileAccess.get_open_error())); return
	ignore_file.store_string("# Generated frames; do not import.\n")
	ignore_file.flush()
	error = ignore_file.get_error()
	ignore_file.close()
	if error != OK: _error("Cannot write export marker", error_string(error)); return
	export_target = ExportTarget.new()
	add_child(export_target)
	export_target.configure(timeline, {"width": export_width, "height": export_height, "fps": export_fps, "start": export_start_time, "end": export_end_time, "seed": seed_value, "parameters": parameters, "wav": active_wav, "video": export_video.button_pressed})
	if not _write_export_record("rendering"): _release_target(); return
	export_frame = 0
	export_epoch += 1
	export_frame_pending = false
	exporting = true
	audio.stop()
	play_button.text = "Play"
	_refresh_controls()

func _cancel_operation() -> void:
	if exporting:
		_write_export_record("cancelled", {"complete_frames": export_frame})
		exporting = false
		export_epoch += 1
		_release_target()
		status.text = "Cancelled. Partial PNG sequence remains in the output folder."
	if job.running():
		var error := job.cancel()
		if not error.is_empty(): _error(error)
	_refresh_controls()

func _release_target() -> void:
	if is_instance_valid(export_target): export_target.queue_free()
	export_target = null
	export_frame_pending = false

func _write_export_record(state: String, extra: Dictionary = {}) -> bool:
	var record := AppPaths.read_json(export_directory.path_join("export.json"))
	if is_instance_valid(export_target): record = export_target.snapshot.duplicate(true)
	record.merge(extra, true)
	record["state"] = state
	var error := AppPaths.write_json(export_directory.path_join("export.json"), record)
	if error != OK: _error("Could not record export status", error_string(error)); return false
	return true

func _export_next_frame() -> void:
	export_frame_pending = true
	var epoch := export_epoch
	if export_frame >= export_target.frame_count:
		var snapshot := export_target.snapshot.duplicate(true)
		exporting = false
		if not _write_export_record("frames_complete", {"complete_frames": export_frame}):
			_release_target(); _refresh_controls(); return
		_release_target()
		if snapshot.video: _assemble_video(snapshot)
		else: status.text = "PNG sequence complete — Open Output Folder"
		_refresh_controls()
		return
	export_target.prepare_frame(export_frame)
	await RenderingServer.frame_post_draw
	if not exporting or epoch != export_epoch: return
	var image := export_target.get_texture().get_image()
	var error := image.save_png(export_directory.path_join("frame_%06d.png" % export_frame))
	if error != OK:
		_write_export_record("failed", {"complete_frames": export_frame})
		exporting = false
		_release_target()
		_refresh_controls()
		_error("Frame export failed. Partial frames remain in the output folder.", error_string(error))
		return
	export_frame += 1
	export_frame_pending = false
	status.text = "Rendering frame %d / %d" % [export_frame, export_target.frame_count]

func _assemble_video(snapshot: Dictionary) -> void:
	var request := {"frames": export_directory, "wav": snapshot.wav, "start": snapshot.start, "end": snapshot.end, "fps": snapshot.fps, "frame_count": export_frame}
	var error := job.start("encode", request)
	if not error.is_empty(): _error(error + " Complete PNG frames remain in the output folder."); return
	status.text = "Encoding video with audio…"

func _open_output() -> void:
	if export_directory.is_empty(): status.text = "Export a sequence first"; return
	var error := OS.shell_open(export_directory)
	if error != OK: _error("Could not open output folder", export_directory + "\n" + error_string(error))

func _show_notices() -> void:
	var path := AppPaths.contents_directory().path_join("Resources/ThirdPartyNotices/NOTICE.txt")
	if OS.has_feature("editor"): path = ProjectSettings.globalize_path("res://../packaging/NOTICE.txt")
	var file := FileAccess.open(path, FileAccess.READ)
	details.text = file.get_as_text() if file != null else "Third-party notices are missing from this application installation."
	details.visible = true

func _notification(what: int) -> void:
	if what == NOTIFICATION_WM_CLOSE_REQUEST:
		_cancel_operation()
		closing = true
		close_deadline = Time.get_ticks_msec() + 5000
		_refresh_controls()

func _exit_tree() -> void:
	# The supervisor also observes parent death (including a force-quit).
	if job.running(): job.cancel()
