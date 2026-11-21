from test_roots import TOOLKIT_ROOT
"""Termbase unbound checks and fixtures."""

import sys
from pathlib import Path
import shutil
import tempfile
import unittest

sys.path.insert(0, str(TOOLKIT_ROOT / "src"))

from gen3tl.lang import termbase as tb

from project_fixture import UNBOUND, needs_unbound
from termbase_support import setUpModule


class SaveTest(unittest.TestCase):
    @needs_unbound
    def test_the_glossary_is_in_the_writer_form(self):
        # no-change write is byte-identical
        path = UNBOUND / "translation/ru/glossary.tsv"
        with tempfile.TemporaryDirectory() as tmp:
            # Structured references resolve beside the glossary.
            for folder in ("notes", "research"):
                if (path.parent / folder).is_dir():
                    shutil.copytree(path.parent / folder, Path(tmp) / folder)
            g = Path(tmp) / "g.tsv"
            tb.save(g, tb.load(path))
            self.assertEqual(g.read_bytes(), path.read_bytes())
