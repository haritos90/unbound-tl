from test_roots import PROJECT_ROOT, TOOLKIT_ROOT
"""The project of this repository pins the toolkit of the same checkout."""

import sys
import unittest
from pathlib import Path

ROOT = PROJECT_ROOT
sys.path.insert(0, str(TOOLKIT_ROOT / "src"))

from gen3tl import __version__  # noqa: E402
from gen3tl.project import MANIFEST, Manifest  # noqa: E402


class ToolkitPinTest(unittest.TestCase):
    # a checkout only warns of another pin
    def test_the_pin_equals_the_toolkit_version(self):
        self.assertEqual(Manifest.read(ROOT / MANIFEST).toolkit, __version__)


if __name__ == "__main__":
    unittest.main()
