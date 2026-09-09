class_name AppPaths
extends RefCounted

const APP_VERSION := "0.1.0"

static func contents_directory() -> String:
	return OS.get_executable_path().get_base_dir().get_base_dir()

static func helper_command() -> Dictionary:
	if not OS.has_feature("editor"):
		var bundled := contents_directory().path_join("Helpers/analyzer/faxto-helper")
		return {"executable": bundled, "arguments": PackedStringArray()}
	var python := OS.get_environment("FAXTO_ANALYZER_PYTHON")
	if python.is_empty():
		python = ProjectSettings.globalize_path("res://../.venv/bin/python3")
	if not FileAccess.file_exists(python):
		python = ProjectSettings.globalize_path("user://analyzer-environment/bin/python3")
	if not FileAccess.file_exists(python):
		python = find_command("python3")
	return {"executable": python, "arguments": PackedStringArray([ProjectSettings.globalize_path("res://../analyzer/src/faxto_analyzer/standalone.py")])}

static func find_command(command: String) -> String:
	for directory in OS.get_environment("PATH").split(":", false):
		var candidate := directory.path_join(command)
		if FileAccess.file_exists(candidate): return candidate
	return ""

static func token() -> String:
	return Crypto.new().generate_random_bytes(16).hex_encode()

static func write_json(path: String, value: Dictionary) -> Error:
	var temporary := path + "." + token() + ".tmp"
	var file := FileAccess.open(temporary, FileAccess.WRITE)
	if file == null: return FileAccess.get_open_error()
	file.store_string(JSON.stringify(value, "  ") + "\n")
	file.flush()
	var error := file.get_error()
	file.close()
	if error == OK: error = DirAccess.rename_absolute(temporary, path)
	if error != OK: DirAccess.remove_absolute(temporary)
	return error

static func read_json(path: String) -> Dictionary:
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null: return {}
	var parsed = JSON.parse_string(file.get_as_text())
	return parsed if parsed is Dictionary else {}

static func preferred_directory(preferences: Dictionary, kind: String) -> String:
	var recent := str(preferences.get(kind, ""))
	if DirAccess.dir_exists_absolute(recent): return recent
	var documents := OS.get_system_dir(OS.SYSTEM_DIR_DOCUMENTS)
	var music := documents.path_join("My music")
	if kind == "wav" and DirAccess.dir_exists_absolute(music): return music
	return documents if DirAccess.dir_exists_absolute(documents) else OS.get_system_dir(OS.SYSTEM_DIR_DESKTOP)
