import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest

from gen3tl import TOOLKIT_ROOT
from gen3tl.cli.web import site_assemble
from gen3tl.web import sitecatalog, sitepreview

from test_roots import PROJECT_ROOT

WEB = TOOLKIT_ROOT / "web"

class SitePreviewTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data = self.root / "data"
        self.data.mkdir()
        (self.data / "languages.json").write_text(json.dumps({"bundle": "check.zip", "profiles": [], "languages": []}))

    def assemble(self, name, base=None):
        out = self.root / name
        args = SimpleNamespace(data=self.data, out=out, public_base=base)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = site_assemble(args)
        self.assertEqual(result, 0, output.getvalue())
        return out


    def test_assembled_picture_passes_the_publication_guard(self):
        script = PROJECT_ROOT / ".github" / "scripts" / "site-check.py"
        if not script.is_file():
            self.skipTest("publication guard is absent from this checkout")
        out = self.assemble("published", "https://site.test")
        result = subprocess.run([sys.executable, str(script), str(out)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("verified     passed", result.stdout)


    def test_catalog_sync_and_seed_keep_preview_guidance(self):
        keys = {text for row in sitepreview.translated(WEB).values() for text in row.values()}
        other = {text for row in sitepreview.definitions(WEB).values() for text in row.values()} - keys
        self.assertTrue(keys and other)
        for path in sitecatalog.catalogs().values():
            entries = {entry.msgid: entry for entry in sitecatalog.load(path)}
            for key in keys:
                self.assertIn(key, entries)
                self.assertTrue(any(note.startswith("Link preview ") for note in entries[key].extracted), key)
            for key in other & set(entries):
                self.assertFalse(any(note.startswith("Link preview ") for note in entries[key].extracted), key)
        path = sitecatalog.seed("xx", self.root / "i18n")
        entries = sitecatalog.load(path)
        self.assertTrue(all(any(note.startswith("Link preview ") for note in entry.extracted)
                            for entry in entries if entry.msgid in keys))
        sitecatalog.sync(path.parent)
        self.assertEqual(sitecatalog.load(path), entries)
