from pathlib import Path
import json
import tempfile
import unittest

from gen3tl.web import editordata
from gen3tl.lang import language
from gen3tl.project import registry_scope

from project_fixture import CATALOG_STAGE, SAMPLE
import editordata_support
from editordata_support import TOOLKIT, entry, games_only, setUpModule
from test_roots import TOOLKIT_ROOT as ROOT
from editorstore_support import decoded

class SplitTest(editordata_support.SplitTest, unittest.TestCase):
    def setUp(self):
        self.enterContext(language.use(self.doc["language"]))
        self.enterContext(registry_scope(Path(self.enterContext(tempfile.TemporaryDirectory()))))


    def test_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "ru"
            (out / "entries").mkdir(parents=True)
            (out / "entries" / "99.json").write_text("{}", encoding="utf-8")   # a stale chunk
            (out / "fonts").mkdir()
            (out / "fonts" / "stale.txt").write_text("", encoding="utf-8")
            editordata.write_split(out, self.index, self.chunks)
            self.assertEqual(sorted(p.name for p in (out / "entries").iterdir()), ["0.json", "1.json", "2.json", "3.json"])
            # the art files of the font sheets beside the index
            self.assertEqual(sorted(p.name for p in (out / "fonts").iterdir()), ["unbound-small.txt", "unbound.txt"])
            for style, entry in self.index["font_sheets"]["styles"].items():
                self.assertEqual((out / entry["art"]["path"]).read_bytes(),
                                 (ROOT / entry["art"]["source"]).read_bytes())
            data = decoded(out)
            self.assertEqual({**data["index"], "progress": None}, {**self.index, "progress": None})
            self.assertEqual(data["chunks"][1], self.chunks[1])
            with registry_scope(Path(tmp)):   # no registry: every toolkit profile
                doc = editordata.write_languages(Path(tmp), toolkit=TOOLKIT)
            self.assertEqual(doc["schema"], editordata.SCHEMA)
            self.assertEqual(doc["toolkit"], TOOLKIT)
            self.assertEqual(doc["bundle"], "gen3tl-check.zip")
            self.assertEqual(games_only(doc["languages"]), [
                {"code": "ru", "index": "ru/index.json", "profile": "test", "entries": 9,
                 "progress": editordata.progress_of(self.index["list"])}])
            self.assertEqual(sum(doc["languages"][0]["progress"].values()), 9)
            profiles = {p["id"]: p for p in doc["profiles"]}
            self.assertEqual(profiles["test"]["support"], "legacy")
            self.assertEqual(profiles[SAMPLE]["support"], "catalog")
            self.assertEqual(len(profiles[SAMPLE]["sha1"]), 40)
            self.assertEqual(json.loads((Path(tmp) / "languages.json").read_text(encoding="utf-8")), doc)
            # the site registry
            registry = json.loads((Path(tmp) / "registry.json").read_text(encoding="utf-8"))
            self.assertEqual(registry, editordata.registry_of(doc))
            games = {g["id"]: g for g in registry["games"]}
            self.assertEqual(games["test"], {"id": "test", "name": "test", "stage": "legacy",
                                             "engine": "unspecified", "languages": ["ru"], "data": "./"})
            self.assertEqual(games[SAMPLE]["stage"], "catalog")
            self.assertEqual(registry["games"][0]["id"], "test")
            self.assertEqual(registry["default"], "test")


    def test_manifest_isolates_projects(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for profile in ("first", "second"):
                index = dict(self.index, profile=profile)
                editordata.write_split(root / profile / "ru", index, self.chunks)
            doc = editordata.write_languages(root)
            self.assertEqual([(p["profile"], p["code"], p["index"]) for p in games_only(doc["languages"])], [
                ("first", "ru", "first/ru/index.json"), ("second", "ru", "second/ru/index.json")])
            editordata.write_split(root / "ru", dict(self.index, profile="first"), self.chunks)
            with self.assertRaisesRegex(ValueError, "duplicate editor project"):
                editordata.write_languages(root)


    def test_a_registered_project_lists_only_its_games(self):
        """The toolkit's other profiles, their editor data and datasets stay out of a project's manifest."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "data"
            for profile in (SAMPLE, "unbound-2.1.1.1", "test"):
                editordata.write_split(root / profile / "ru", dict(self.index, profile=profile), self.chunks)
            with registry_scope(CATALOG_STAGE):
                doc = editordata.write_languages(root, toolkit=TOOLKIT)
            self.assertEqual([x["profile"] for x in games_only(doc["languages"])], [SAMPLE])
            self.assertEqual(sorted(p["id"] for p in doc["profiles"]), sorted([SAMPLE, "site"]))
            self.assertFalse((root / "pokedex").exists())
            registry = json.loads((root / "registry.json").read_text(encoding="utf-8"))
            self.assertEqual(sorted(g["id"] for g in registry["games"]), [SAMPLE])
            with registry_scope(Path(tmp)):   # no registry: the toolkit's own site
                doc = editordata.write_languages(root, toolkit=TOOLKIT)
            self.assertEqual([x["profile"] for x in games_only(doc["languages"])], [SAMPLE, "test", "unbound-2.1.1.1"])
            self.assertLessEqual({SAMPLE, "unbound-2.1.1.1"}, {p["id"] for p in doc["profiles"]})
