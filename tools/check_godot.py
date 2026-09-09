"""Godot can log a script error and still return zero; make CI fail explicitly."""
import subprocess
import sys

process = subprocess.run(sys.argv[1:], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=180)
print(process.stdout)
failed = process.returncode != 0 or any(term in process.stdout for term in ("SCRIPT ERROR", "Parse Error", "Failed to load", "ERROR:"))
raise SystemExit(1 if failed else 0)
