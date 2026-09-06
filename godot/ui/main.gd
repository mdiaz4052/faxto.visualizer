extends Control

const SignalFieldScene = preload("res://scenes/signal_field.tscn")
var timeline := FeatureTimeline.new()
var audio := AudioStreamPlayer.new()
var visual: SignalField
var status := Label.new()
var time_label := Label.new()
var scrubber := HSlider.new()
var play_button := Button.new()
var analyze_button := Button.new()
var selected_wav := ""
var manifest_path := ""
var last_time := 0.0
var seed_value := 42
var parameters := {"deformation": 0.8, "impact_scale": 0.7, "element_count": 28.0}
var parameter_controls: Dictionary = {}
var export_directory := ""
var exporting := false
var export_frame_pending := false
var export_frame := 0
var export_fps := 30.0
var analysis_thread: Thread

func _ready() -> void:
	_build_ui()
	set_process(true)

func _build_ui() -> void:
	add_child(audio)
	var root := VBoxContainer.new(); root.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT); add_child(root)
	var toolbar := HBoxContainer.new(); root.add_child(toolbar)
	_add_button(toolbar, "Open WAV", _open_wav)
	analyze_button = _add_button(toolbar, "Analyze", _analyze)
	play_button = _add_button(toolbar, "Play", _toggle_play)
	var scene_choice := OptionButton.new(); scene_choice.add_item("Signal Field"); scene_choice.tooltip_text = "Scene preset"; toolbar.add_child(scene_choice)
	_add_button(toolbar, "Save Config", _save_config)
	_add_button(toolbar, "Load Config", _load_config)
	_add_button(toolbar, "Export", _choose_export)
	status.text = "Choose a PCM WAV to begin"; status.size_flags_horizontal = Control.SIZE_EXPAND_FILL; toolbar.add_child(status)
	var body := HSplitContainer.new(); body.size_flags_vertical = Control.SIZE_EXPAND_FILL; root.add_child(body)
	var viewport_panel := PanelContainer.new(); viewport_panel.size_flags_horizontal = Control.SIZE_EXPAND_FILL; body.add_child(viewport_panel)
	visual = SignalFieldScene.instantiate(); viewport_panel.add_child(visual)
	var controls := VBoxContainer.new(); controls.custom_minimum_size.x = 260; body.add_child(controls)
	_add_parameter(controls, "Deformation", "deformation", 0.0, 2.0)
	_add_parameter(controls, "Impact scale", "impact_scale", 0.0, 2.0)
	_add_parameter(controls, "Element count", "element_count", 8.0, 80.0, 1.0)
	_add_button(controls, "Reset Parameters", _reset_parameters)
	var timeline_row := HBoxContainer.new(); root.add_child(timeline_row)
	scrubber.size_flags_horizontal = Control.SIZE_EXPAND_FILL; scrubber.step = 0.001; scrubber.drag_ended.connect(_scrub_ended); timeline_row.add_child(scrubber)
	time_label.text = "00:00.000 / 00:00.000"; timeline_row.add_child(time_label)

func _add_button(parent: Control, text_value: String, callback: Callable) -> Button:
	var button := Button.new(); button.text = text_value; button.pressed.connect(callback); parent.add_child(button); return button

func _add_parameter(parent: Control, label_text: String, key: String, low: float, high: float, step_value := 0.01) -> void:
	var label := Label.new(); label.text = label_text; parent.add_child(label)
	var slider := HSlider.new(); slider.min_value = low; slider.max_value = high; slider.step = step_value; slider.value = parameters[key]
	slider.value_changed.connect(func(value): parameters[key] = value); parent.add_child(slider); parameter_controls[key] = slider

func _dialog(mode: FileDialog.FileMode, filters: PackedStringArray, callback: Callable, title: String) -> void:
	var dialog := FileDialog.new(); dialog.file_mode = mode; dialog.access = FileDialog.ACCESS_FILESYSTEM; dialog.filters = filters; dialog.title = title
	dialog.file_selected.connect(func(path): callback.call(path); dialog.queue_free())
	dialog.dir_selected.connect(func(path): callback.call(path); dialog.queue_free())
	dialog.canceled.connect(dialog.queue_free); add_child(dialog); dialog.popup_centered_ratio(0.8)

func _open_wav() -> void: _dialog(FileDialog.FILE_MODE_OPEN_FILE, PackedStringArray(["*.wav ; WAV audio"]), _wav_selected, "Open Song")
func _wav_selected(path: String) -> void: selected_wav = path; status.text = "Selected %s — click Analyze" % path.get_file()

func _analyze() -> void:
	if selected_wav.is_empty(): status.text = "Choose a WAV first"; return
	status.text = "Analyzing…"
	analyze_button.disabled = true
	manifest_path = "user://%s.song_manifest.json" % selected_wav.get_file().get_basename()
	var python := _find_command("python3")
	if python.is_empty():
		status.text = "Python 3 was not found. Install Python before analyzing audio."
		analyze_button.disabled = false
		return
	var cli := ProjectSettings.globalize_path("res://../analyzer/src/faxto_analyzer/cli.py")
	analysis_thread = Thread.new()
	analysis_thread.start(_run_analysis.bind(python, cli, selected_wav, ProjectSettings.globalize_path(manifest_path)))

func _run_analysis(python: String, cli: String, wav_path: String, output_path: String) -> void:
	var output: Array[String] = []
	var code := OS.execute(python, PackedStringArray([cli, wav_path, "--output", output_path]), output, true)
	call_deferred("_analysis_finished", code, output)

func _analysis_finished(code: int, output: Array[String]) -> void:
	if analysis_thread != null:
		analysis_thread.wait_to_finish()
		analysis_thread = null
	analyze_button.disabled = false
	if code != 0:
		status.text = "Analysis failed: %s" % " ".join(output)
		return
	_load_manifest(manifest_path)

func _load_manifest(path: String) -> void:
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null: status.text = "Could not read manifest"; return
	var parsed = JSON.parse_string(file.get_as_text())
	if typeof(parsed) != TYPE_DICTIONARY: status.text = "Malformed manifest JSON"; return
	var error := timeline.load_manifest(parsed)
	if not error.is_empty(): status.text = error; return
	scrubber.max_value = timeline.duration
	var stream = AudioStreamWAV.load_from_file(selected_wav)
	if stream == null: status.text = "The analyzed WAV could not be loaded for playback"; return
	audio.stream = stream; status.text = "Ready — %s" % selected_wav.get_file(); _evaluate(0.0)

func _toggle_play() -> void:
	if audio.stream == null: status.text = "Analyze a WAV before playback"; return
	if audio.playing: audio.stream_paused = not audio.stream_paused
	else: audio.play(scrubber.value)
	play_button.text = "Play" if audio.stream_paused else "Pause"

func _scrub_ended(_changed: bool) -> void:
	if audio.stream != null:
		var was_active := audio.playing and not audio.stream_paused
		audio.play(scrubber.value); audio.stream_paused = not was_active
	last_time = scrubber.value; _evaluate(scrubber.value)

func _process(_delta: float) -> void:
	if exporting:
		if not export_frame_pending:
			_export_next_frame()
		return
	if audio.playing and not audio.stream_paused:
		var current := audio.get_playback_position(); scrubber.set_value_no_signal(current); _evaluate(current)

func _evaluate(song_time: float) -> void:
	if timeline.duration <= 0.0: return
	visual.set_visual_context(StateEvaluator.evaluate(timeline, song_time, last_time, seed_value, parameters))
	time_label.text = "%s / %s" % [_format_time(song_time), _format_time(timeline.duration)]; last_time = song_time

func _format_time(value: float) -> String: return "%02d:%06.3f" % [int(value) / 60, fmod(value, 60.0)]

func _find_command(command: String) -> String:
	var separator := ";" if OS.get_name() == "Windows" else ":"
	for directory in OS.get_environment("PATH").split(separator, false):
		var candidate := directory.path_join(command)
		if FileAccess.file_exists(candidate):
			return candidate
		if OS.get_name() == "Windows" and FileAccess.file_exists(candidate + ".exe"):
			return candidate + ".exe"
	return ""

func _reset_parameters() -> void:
	parameters = {"deformation": 0.8, "impact_scale": 0.7, "element_count": 28.0}
	for key in parameter_controls: parameter_controls[key].value = parameters[key]

func _save_config() -> void: _dialog(FileDialog.FILE_MODE_SAVE_FILE, PackedStringArray(["*.json ; Visual config"]), _write_config, "Save Visual Configuration")
func _write_config(path: String) -> void:
	var config := {"schema_version": "0.1.0", "scene": "signal_field", "seed": seed_value, "parameters": parameters, "mappings": {}, "authored_cues": [], "export": {"width": 1280, "height": 720, "fps": export_fps}}
	var file := FileAccess.open(path, FileAccess.WRITE); file.store_string(JSON.stringify(config, "  ") + "\n"); status.text = "Configuration saved"

func _load_config() -> void: _dialog(FileDialog.FILE_MODE_OPEN_FILE, PackedStringArray(["*.json ; Visual config"]), _read_config, "Load Visual Configuration")
func _read_config(path: String) -> void:
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null:
		status.text = "Could not read visual configuration"
		return
	var config = JSON.parse_string(file.get_as_text())
	if typeof(config) != TYPE_DICTIONARY or config.get("schema_version") != "0.1.0" or config.get("scene") != "signal_field": status.text = "Unsupported or malformed visual configuration"; return
	seed_value = int(config.get("seed", 42)); parameters.merge(config.get("parameters", {}), true)
	for key in parameter_controls:
		if parameters.has(key):
			parameter_controls[key].value = parameters[key]
	status.text = "Configuration loaded"; _evaluate(scrubber.value)

func _choose_export() -> void:
	if timeline.duration <= 0.0: status.text = "Analyze a WAV before export"; return
	_dialog(FileDialog.FILE_MODE_OPEN_DIR, PackedStringArray(), _start_export, "Choose Export Folder")

func _start_export(path: String) -> void:
	export_directory = path.path_join("faxto_frames"); DirAccess.make_dir_recursive_absolute(export_directory)
	export_frame = 0; export_frame_pending = false; exporting = true; audio.stop(); status.text = "Exporting deterministic frames…"

func _export_next_frame() -> void:
	export_frame_pending = true
	var t := StateEvaluator.frame_time(export_frame, export_fps)
	if t > timeline.duration:
		exporting = false
		export_frame_pending = false
		_assemble_video()
		return
	_evaluate(t); await RenderingServer.frame_post_draw
	var image := get_viewport().get_texture().get_image()
	var error := image.save_png(export_directory.path_join("frame_%06d.png" % export_frame))
	if error != OK:
		exporting = false
		export_frame_pending = false
		status.text = "Frame export failed: %s" % error_string(error)
		return
	export_frame += 1
	export_frame_pending = false
	status.text = "Exporting frame %d" % export_frame

func _exit_tree() -> void:
	if analysis_thread != null:
		analysis_thread.wait_to_finish()

func _assemble_video() -> void:
	var ffmpeg := _find_command("ffmpeg")
	if ffmpeg.is_empty(): status.text = "Frames exported. FFmpeg was not found, so video assembly was skipped."; return
	var output_path := export_directory.get_base_dir().path_join("faxto_visualizer.mp4")
	var args := PackedStringArray(["-y", "-framerate", str(export_fps), "-i", export_directory.path_join("frame_%06d.png"), "-i", selected_wav, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", output_path])
	var output: Array[String] = []
	var code := OS.execute(ffmpeg, args, output, true)
	status.text = "Export complete: %s" % output_path if code == 0 else "Frames exported, but FFmpeg assembly failed: %s" % " ".join(output)
