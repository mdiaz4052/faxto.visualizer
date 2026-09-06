class_name SignalField
extends Control

var context: Dictionary = {}

func set_visual_context(value: Dictionary) -> void:
	context = value
	queue_redraw()

func _draw() -> void:
	var size := get_rect().size
	draw_rect(Rect2(Vector2.ZERO, size), Color("08070f"))
	if context.is_empty():
		draw_string(ThemeDB.fallback_font, size * 0.5 - Vector2(85, 0), "OPEN AND ANALYZE A WAV", HORIZONTAL_ALIGNMENT_LEFT, -1, 14, Color("8e849e"))
		return
	var expression: Dictionary = context.expressive_state
	var params: Dictionary = context.scene_parameters
	var intensity := float(expression.intensity)
	var impact := float(expression.impact)
	var brightness := float(expression.brightness)
	var openness := float(expression.openness)
	var progress := float(context.normalized_progress)
	var deformation := float(params.get("deformation", 0.8))
	var scale_strength := float(params.get("impact_scale", 0.7))
	var count := int(params.get("element_count", 28.0))
	var center := size * Vector2(0.5 + 0.12 * sin(progress * TAU), 0.5)
	for i in range(count):
		var ratio := float(i + 1) / count
		var phase := ratio * TAU * 3.0 + float(context.song_time) * (0.15 + brightness)
		var radius := ratio * minf(size.x, size.y) * 0.47
		var warp := Vector2(cos(phase * 1.7), sin(phase * 1.3)) * deformation * intensity * 45.0
		var point := center + Vector2(cos(phase), sin(phase)) * radius + warp
		var logical_jitter := (float(context.seeded_variation) - 0.5) * 5.0
		var circle_radius := 2.0 + ratio * 10.0 + impact * scale_strength * 25.0 + logical_jitter
		var color := Color.from_hsv(fmod(0.72 + progress * 0.18 + ratio * 0.1, 1.0), 0.35 + brightness * 0.5, 0.4 + intensity * 0.55, 0.28 + openness * 0.35)
		draw_circle(point, maxf(1.0, circle_radius), color, false, 1.5)
	# Negative space is active: quiet passages reveal a slowly rotating aperture.
	var aperture := openness * minf(size.x, size.y) * 0.18
	draw_circle(center, aperture, Color("08070f"))

