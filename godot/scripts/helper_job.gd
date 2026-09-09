class_name HelperJob
extends RefCounted

var pid := -1
var id := ""
var directory := ""
var request: Dictionary = {}
var cancelling := false

func running() -> bool:
	return pid > 0

func start(operation: String, values: Dictionary) -> String:
	if running(): return "Another operation is still running"
	var command := AppPaths.helper_command()
	if str(command.executable).is_empty() or not FileAccess.file_exists(command.executable):
		return "Analyzer helper is missing. Reinstall the complete application." if not OS.has_feature("editor") else "Development Python is missing; see docs/standalone-macos.md."
	id = AppPaths.token()
	directory = ProjectSettings.globalize_path("user://jobs").path_join(id)
	var error := DirAccess.make_dir_recursive_absolute(directory)
	if error != OK: return "Cannot create job folder: " + error_string(error)
	request = values.duplicate(true)
	request.merge({"protocol": 1, "job_id": id, "operation": operation, "parent_pid": OS.get_process_id()}, true)
	error = AppPaths.write_json(directory.path_join("request.json"), request)
	if error != OK: return "Cannot write job request: " + error_string(error)
	var arguments: PackedStringArray = command.arguments
	arguments.append_array(PackedStringArray(["--job", directory.path_join("request.json")]))
	pid = OS.create_process(command.executable, arguments, false)
	cancelling = false
	if pid <= 0:
		pid = -1
		return "Could not launch the analyzer helper. Check the complete app installation and permissions."
	return ""

func stage() -> String:
	if cancelling: return "Cancelling…"
	var current := AppPaths.read_json(directory.path_join("status.json"))
	return str(current.get("stage", "Starting helper…")) if current.get("job_id", id) == id else "Starting helper…"

func poll() -> Dictionary:
	if not running() or OS.is_process_running(pid): return {}
	var code := OS.get_process_exit_code(pid)
	pid = -1
	var result := AppPaths.read_json(directory.path_join("result.json"))
	if result.get("protocol") != 1 or result.get("job_id") != id:
		return {"state": "failed", "error": "Helper exited without a valid result (exit %s)." % code}
	if cancelling: return {"state": "cancelled"}
	if result.get("state") == "complete" and code != 0:
		return {"state": "failed", "error": "Helper result disagrees with exit code %s." % code}
	return result

func cancel() -> String:
	if not running(): return ""
	var file := FileAccess.open(directory.path_join("cancel"), FileAccess.WRITE)
	if file == null: return "Could not write cancellation request: " + error_string(FileAccess.get_open_error())
	file.close()
	cancelling = true
	return ""

func diagnostics() -> String:
	var path := directory.path_join("diagnostics.log")
	var file := FileAccess.open(path, FileAccess.READ)
	return (file.get_as_text() if file != null else "No helper log was produced.") + "\nJob folder: " + directory
