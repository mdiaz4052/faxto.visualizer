class_name ExportTarget
extends SubViewport

const Scene = preload("res://scenes/signal_field.tscn")
var field: SignalField
var snapshot: Dictionary = {}
var timeline: FeatureTimeline
var frame_count := 0

func configure(features: FeatureTimeline, settings: Dictionary) -> void:
	snapshot = settings.duplicate(true)
	timeline = features
	size = Vector2i(int(snapshot.width), int(snapshot.height))
	disable_3d = true
	render_target_update_mode = SubViewport.UPDATE_DISABLED
	field = Scene.instantiate()
	add_child(field)
	field.set_anchors_and_offsets_preset(Control.PRESET_TOP_LEFT)
	field.position = Vector2.ZERO
	field.size = Vector2(size)
	frame_count = ceili((float(snapshot.end) - float(snapshot.start)) * float(snapshot.fps) - 0.000000001)

func prepare_frame(index: int) -> Dictionary:
	var time := float(snapshot.start) + StateEvaluator.frame_time(index, float(snapshot.fps))
	var previous := float(snapshot.start) if index == 0 else time - 1.0 / float(snapshot.fps)
	var context := StateEvaluator.evaluate(timeline, time, previous, int(snapshot.seed), snapshot.parameters)
	field.set_visual_context(context)
	render_target_update_mode = SubViewport.UPDATE_ONCE
	return context
