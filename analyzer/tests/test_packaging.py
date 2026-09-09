"""Mach-O dependency parsing regression from the native bundle inspection."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from inspect_macos_bundle import loaded_libraries


class PackagingTests(unittest.TestCase):
    def test_dylib_identity_is_not_a_dependency(self):
        commands = """Load command 0
          cmd LC_ID_DYLIB
      cmdsize 48
         name @rpath/Python (offset 24)
Load command 1
          cmd LC_LOAD_DYLIB
      cmdsize 56
         name /usr/lib/libSystem.B.dylib (offset 24)
Load command 2
          cmd LC_LOAD_WEAK_DYLIB
      cmdsize 56
         name @rpath/libexample.dylib (offset 24)
"""
        self.assertEqual(loaded_libraries(commands), ["/usr/lib/libSystem.B.dylib", "@rpath/libexample.dylib"])

    def test_external_load_and_reexport_are_still_inspected(self):
        commands = """          cmd LC_LOAD_DYLIB
      cmdsize 80
         name /opt/homebrew/lib/external.dylib (offset 24)
          cmd LC_REEXPORT_DYLIB
      cmdsize 56
         name @rpath/reexport.dylib (offset 24)
"""
        self.assertEqual(loaded_libraries(commands), ["/opt/homebrew/lib/external.dylib", "@rpath/reexport.dylib"])
