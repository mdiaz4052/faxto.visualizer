class_name FeatureTimeline
extends RefCounted

var duration := 0.0
var curves: Dictionary = {}
var events: Dictionary = {}

func load_manifest(manifest: Dictionary) -> String:
	if manifest.get("schema_version") != "0.1.0":
		return "Unsupported manifest schema version"
	if not manifest.has("source") or not manifest.has("curves") or not manifest.has("events"):
		return "Malformed manifest: required fields are missing"
	duration = float(manifest.source.get("duration_seconds", 0.0))
	if duration <= 0.0:
		return "Malformed manifest: duration must be positive"
	curves.clear()
	for curve in manifest.curves:
		if not curve.has("name") or not curve.has("values") or float(curve.get("sample_interval_seconds", 0.0)) <= 0.0:
			return "Malformed feature curve"
		curves[curve.name] = curve
	events = manifest.events
	return ""

func value(name: String, song_time: float) -> float:
	if not curves.has(name): return 0.0
	var curve: Dictionary = curves[name]
	var values: Array = curve.values
	if values.is_empty(): return 0.0
	var position := maxf(0.0, song_time) / float(curve.sample_interval_seconds)
	var left := mini(int(floor(position)), values.size() - 1)
	var right := mini(left + 1, values.size() - 1)
	return lerpf(float(values[left]), float(values[right]), position - floor(position))

func previous_event(kind: String, song_time: float) -> Variant:
	var found: Variant = null
	for event_time in events.get(kind, []):
		if float(event_time) > song_time: break
		found = float(event_time)
	return found

func next_event(kind: String, song_time: float) -> Variant:
	for event_time in events.get(kind, []):
		if float(event_time) >= song_time: return float(event_time)
	return null

func event_occurred(kind: String, start_exclusive: float, end_inclusive: float) -> bool:
	for event_time in events.get(kind, []):
		var t := float(event_time)
		if t > start_exclusive and t <= end_inclusive: return true
	return false

func event_phase(kind: String, song_time: float) -> float:
	var previous = previous_event(kind, song_time)
	var upcoming = next_event(kind, song_time + 0.000000001)
	if previous == null or upcoming == null or upcoming <= previous: return 0.0
	return clampf((song_time - previous) / (upcoming - previous), 0.0, 1.0)

