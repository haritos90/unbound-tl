import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from gen3tl.catalog.po import PoEntry, write
from gen3tl.web import sitecatalog

from project_fixture import UNBOUND

class ToolkitSiteSubmissionTest(unittest.TestCase):
    """A site catalog submission in a toolkit tree: no projects.toml, web/i18n under the root."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        (self.root / ".git").mkdir()
        self.i18n = self.root / "web" / "i18n"
        self.i18n.mkdir(parents=True)
        self.site = self.i18n / "xx.po"
        write(self.site, [PoEntry("site:Patch", "Patch", "Патч", extracted=["index.html"]),
                          PoEntry("site:Loading {game}…", "Loading {game}…", "", extracted=["js/pick.js"]),
                          PoEntry("site:Home", "Home", "Дом", extracted=["index.html"])],
              {"Project-Id-Version": "site", "Language": "xx", "Content-Type": "text/plain; charset=UTF-8"})
        self.before = self.site.read_bytes()
        hook = patch.object(sitecatalog, "CATALOGS", self.i18n)
        hook.start()
        self.addCleanup(hook.stop)


    def test_web_import_of_a_pack_export_without_a_project_reaches_the_pack_check(self):
        from gen3tl.__main__ import main
        export = self.root / "pack-export.json"
        export.write_text(json.dumps({"profile": "unbound-2.1.1.1", "language": "ru", "entries": [],
                                      "pictures": [], "terms": [], "glyphs": [{"style": "unbound", "char": "Б"}]}),
                          encoding="utf-8")
        previous = os.getcwd()
        os.chdir(self.root)
        try:
            with contextlib.redirect_stdout(io.StringIO()) as log:
                status = main(["--profile", str(UNBOUND / "profile"), "--lang", "ru", "web", "import",
                               str(export), "--dry-run"])
        finally:
            os.chdir(previous)
        self.assertEqual(status, 1)
        self.assertIn("each glyph needs style, char or slot, width, rows and base", log.getvalue())
