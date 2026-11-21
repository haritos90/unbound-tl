import io
import os
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from gen3tl.cli import main as cli

from rom_support import needs_rom, rom_path
from project_fixture import UNBOUND


def build_files():
    """The files under the project's build/ with their size and modification time."""
    files = {}
    for top, _, names in os.walk(UNBOUND / "build"):
        for name in names:
            stat = os.lstat(Path(top, name))
            files[Path(top, name)] = (stat.st_size, stat.st_mtime_ns)
    return files


@needs_rom
class GoldenRomTest(unittest.TestCase):
    def test_generated_outputs_match_manifest(self):
        before = build_files()
        output = io.StringIO()
        with redirect_stdout(output), redirect_stderr(output):
            code = cli.main(["--project-root", str(UNBOUND), "--lang", "ru",
                             "--rom", str(rom_path()), "verify", "golden"])
        self.assertEqual(code, 0, output.getvalue())
        self.assertIn("verified", output.getvalue())
        self.assertEqual(build_files(), before)   # the gate generates in its own directory
