"""Editor manifests use registry membership independently of library profiles."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from gen3tl.profile import profile
from gen3tl.project import registry_scope
from gen3tl.web.editordata import write_languages


class ManifestRegistryScopeTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.output = self.root / "output"
        self.registry = self.root / "projects.toml"
        self.registry.write_text(
            '[defaults]\nprofile = "selected"\nlanguage = "xx"\n'
            '[[project]]\nprofile = "selected"\nlanguage = "xx"\nroot = "."\npolicy = "policy.toml"\n',
            encoding="utf-8")
        self.paths = []
        for name in ("selected", "unregistered"):
            path = self.root / (name + ".toml")
            path.write_text(f'[rom]\nname = "{name}"\nsha1 = "' + '0' * 40 + '"\n', encoding="utf-8")
            self.paths.append(path)
        for name in ("selected", "unregistered", "unknown"):
            path = self.output / name / "xx" / "index.json"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({"profile": name, "language": "xx", "list": []}), encoding="utf-8")
        self.enterContext(registry_scope(self.root))
        self.enterContext(patch.object(profile, "profile_paths", return_value=self.paths))

    def test_registry_excludes_known_and_unknown_unregistered_data(self):
        for paths in (self.paths, self.paths[:1], []):
            with self.subTest(library=[path.stem for path in paths]), \
                    patch.object(profile, "profile_paths", return_value=paths):
                document = write_languages(self.output)
                self.assertEqual({row["profile"] for row in document["languages"]}, {"selected", "site"})
                self.assertEqual({row["id"] for row in document["profiles"]}, {"selected", "site"})
                self.assertEqual(json.loads((self.output / "languages.json").read_text()), document)
                registry = json.loads((self.output / "registry.json").read_text())
                self.assertEqual({row["id"] for row in registry["games"]}, {"selected"})
        self.assertTrue((self.output / "unknown/xx/index.json").is_file())
        self.assertTrue((self.output / "unregistered/xx/index.json").is_file())

    def test_absent_registry_preserves_all_discovered_data(self):
        self.registry.unlink()
        document = write_languages(self.output)
        expected = {"selected", "unregistered", "unknown", "site"}
        self.assertEqual({row["profile"] for row in document["languages"]}, expected)
        self.assertEqual({row["id"] for row in document["profiles"]}, expected)
        registry = json.loads((self.output / "registry.json").read_text())
        self.assertEqual({row["id"] for row in registry["games"]}, expected - {"site"})

    def test_empty_registry_lists_only_the_site_catalog(self):
        self.registry.write_text("", encoding="utf-8")
        document = write_languages(self.output)
        self.assertEqual({row["profile"] for row in document["languages"]}, {"site"})
        self.assertEqual({row["id"] for row in document["profiles"]}, {"site"})
        registry = json.loads((self.output / "registry.json").read_text())
        self.assertEqual(registry["games"], [])

    def test_only_registered_datasets_are_copied(self):
        datasets = self.root / "datasets"
        for name in ("selected", "unregistered", "unknown"):
            source = datasets / name
            source.mkdir(parents=True)
            (source / "pokedex.json").write_text(json.dumps({"profile": name}), encoding="utf-8")
            (source / "learnsets.json").write_text("{}", encoding="utf-8")
            (source / "sprites").mkdir()
            (source / "sprites/icon.png").write_bytes(b"sprite")
        with patch("gen3tl.data.pokedextexts.dataset_dir", side_effect=lambda name: datasets / name):
            document = write_languages(self.output)
        self.assertEqual({path.name for path in (self.output / "pokedex").iterdir()}, {"selected"})
        for relative in ("pokedex.json", "learnsets.json", "sprites/icon.png"):
            self.assertEqual((self.output / "pokedex/selected" / relative).read_bytes(),
                             (datasets / "selected" / relative).read_bytes())
        selected = next(row for row in document["profiles"] if row["id"] == "selected")
        self.assertEqual(selected["pokedex"], "pokedex/selected/pokedex.json")
