import unittest

from gen3tl.catalog.po import KEY_ONLY, SOURCE_FIELD, read
from gen3tl.profile.profile import Profile
from gen3tl.project import Manifest, Registry
from gen3tl.catalog import guidance
from gen3tl.catalog.catalog import load_catalog

from rom_support import needs_rom
from project_fixture import UNBOUND

class RepositoryProjectTest(unittest.TestCase):
    """The tracked game project is consistent with its catalogs."""

    def test_every_language_is_a_folder_of_the_game_project(self):
        manifest = Manifest.read(UNBOUND / "project.toml")
        registry = Registry.load(UNBOUND)
        profile = Profile.by_name(manifest.profile)
        self.assertEqual(profile.sha1, manifest.rom_sha1)
        for code in manifest.languages:
            project = registry.resolve(manifest.profile, code)
            self.assertTrue(project.game)
            self.assertTrue(project.catalog.is_dir(), code)
            self.assertTrue(project.policy.is_file(), code)
            self.assertTrue(project.snapshot.is_file(), code)
        self.assertNotIn("translator_notes", profile.data)

    def test_every_catalog_holds_its_entries_by_key(self):
        manifest = Manifest.read(UNBOUND / "project.toml")
        registry = Registry.load(UNBOUND)
        keys = None
        for code in manifest.languages:
            catalog = {}
            for path in registry.resolve(manifest.profile, code).catalog.rglob("*.po"):
                header, entries = read(path)
                self.assertEqual(header.get(SOURCE_FIELD), KEY_ONLY, path)
                catalog.update((e.msgctxt, e.msgid) for e in entries)
            self.assertTrue(all(key == english for key, english in catalog.items()), code)
            keys = keys or set(catalog)
            self.assertEqual(set(catalog), keys, code)
        self.assertFalse((UNBOUND / "source/catalog.pot").exists())


    @needs_rom
    def test_the_english_source_catalog_and_notes_match_the_default_catalog(self):
        manifest = Manifest.read(UNBOUND / "project.toml")
        project = Registry.load(UNBOUND).resolve(manifest.profile, manifest.default_language)
        _, template = read(UNBOUND / "build/catalog.pot")
        self.assertTrue(all(not e.msgstr for e in template))
        selected = project.effective(Profile.by_name(manifest.profile))
        catalog = load_catalog(project.catalog, selected, UNBOUND / "build/catalog.pot")
        self.assertEqual({e.msgctxt for e in template}, {e.msgctxt for _, e in catalog.values()})
        notes = guidance.entry_notes(selected, catalog)
        # proposed notes are not yet guidance
        active = [n for n in guidance.read_notes(project.notes) if n.get("status", "accepted") in ("unreviewed", "accepted")]
        self.assertEqual(len(notes), len(active))
