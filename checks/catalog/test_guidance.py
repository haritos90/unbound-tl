import copy
import tempfile
import unittest
from pathlib import Path

from gen3tl import TOOLKIT_ROOT
from gen3tl.catalog import draftcatalog, guidance, source, keys
from gen3tl.core import notes as structured
from gen3tl.web import editordata, editorsnapshot, snapshotstore as snapshot_store
from gen3tl.core.charmap import Charmap
from gen3tl.check.layout import Measure
from gen3tl.catalog.po import PoEntry
from gen3tl.profile.profile import Profile

from rom_support import needs_rom, rom_path
from project_fixture import UNBOUND

class GuidanceTest(unittest.TestCase):
    def setUp(self):
        self.source_text = "{PLAYER} found an item!"
        self.note = {"id": "s1", "source_sha256": source.digest(self.source_text),
                     "text": "PLAYER names the finder, not the item.",
                     "evidence": "The acquisition script fills PLAYER."}
        self.profile = Profile({"rom": {"sha1": "a" * 40}, "layout": {}, "font": [],
                                "translator_notes": [self.note]}, Path("example.toml"))
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.notes_path = Path(temporary.name) / "notes.toml"

    def catalog(self, translation=""):
        return {"s1": (Path("a.po"), PoEntry("s1", self.source_text, translation,
                    translator=["source: Current wording reference"])),
                "s2": (Path("a.po"), PoEntry("s2", "Another message"))}

    def structured_note(self):
        return {"id": "finder-placeholder", "subject": {"kind": "entry", "id": "s1"},
                "scope": {"kind": "shared"},
                "binding": {"kind": "entry", "id": "s1", "source_sha256": self.note["source_sha256"]},
                "guidance": [self.note["text"]], "status": "unreviewed",
                "evidence": [{"method": self.note["evidence"], "verification": "recorded"}]}

    def set_structured(self, rows):
        guidance.write_notes(self.notes_path, {"schema": structured.SCHEMA, "note": rows})
        self.profile.notes_path = self.notes_path

    def documents(self, lang, catalog):
        manifest = {"profile": self.profile.name, "language": lang, "rom_sha1": self.profile.sha1,
                    "source_sha256": draftcatalog.source_digest(e for _, e in catalog.values())}
        return [editordata.build(lang, self.profile, catalog, {}, Measure(lambda _: 6, {}),
                                 Charmap(), {}, toolkit="1.0.0"),
                draftcatalog.editor_data(self.profile, lang, catalog, manifest)]

    def test_languages_and_editor_paths_share_guidance_only(self):
        for lang, translation in (("fr", "Objet trouvé"), ("es", "Objeto encontrado"), ("de", "")):
            with self.subTest(language=lang):
                for doc in self.documents(lang, self.catalog(translation)):
                    entry, other = doc["entries"]
                    self.assertEqual(entry["translator_notes"], [{"text": self.note["text"],
                                                                "evidence": self.note["evidence"]}])
                    self.assertEqual(entry["translation"], translation)
                    self.assertEqual(entry["note"], "Current wording reference")
                    self.assertEqual(other["translator_notes"], [])
                    self.assertEqual(other["note"], "")

    def test_changed_source_is_rejected_in_both_editor_paths(self):
        catalog = self.catalog()
        catalog["s1"][1].msgid = "A different source"
        with self.assertRaisesRegex(ValueError, "s1: translator note source differs"):
            editordata.build("fr", self.profile, catalog, {}, Measure(lambda _: 6, {}), Charmap(), {})
        manifest = {"profile": self.profile.name, "language": "fr", "rom_sha1": self.profile.sha1,
                    "source_sha256": draftcatalog.source_digest(e for _, e in catalog.values())}
        with self.assertRaisesRegex(ValueError, "s1: translator note source differs"):
            draftcatalog.editor_data(self.profile, "fr", catalog, manifest)


    def test_updates_are_live_without_invalidating_measurements(self):
        previous = editorsnapshot.configuration(self.profile)
        self.note["text"] = "Updated explanation"
        for doc in self.documents("fr", self.catalog()):
            self.assertEqual(doc["entries"][0]["translator_notes"][0]["text"], "Updated explanation")
        self.assertEqual(editorsnapshot.configuration(self.profile), previous)


    def test_structured_notes_change_only_editor_guidance(self):
        row = self.structured_note()
        languages = sorted(path.parent.name for path in (TOOLKIT_ROOT / "assets/lang").glob("*/language.json"))
        self.assertTrue(languages)
        for language in languages:
            with self.subTest(language=language):
                self.profile.data["translator_notes"] = [self.note]
                self.profile.notes_path = None
                catalog = self.catalog("Translated item")
                original = copy.deepcopy(catalog)
                configuration = editorsnapshot.configuration(self.profile)
                before = self.documents(language, catalog)
                self.set_structured([row])
                after = self.documents(language, catalog)
                for old, new in zip(before, after):
                    # a migrated entry carries note records, not projections
                    self.assertNotIn("translator_notes", new["entries"][0])
                    new["entries"][0]["translator_notes"] = old["entries"][0]["translator_notes"]
                    # the editor data also exposes the structured note itself
                    self.assertEqual(new["entries"][0].pop("note_ids"), [row["id"]])
                    self.assertEqual([note["id"] for note in new["notes"]["note"]], [row["id"]])
                    new["notes"] = old["notes"]
                    self.assertEqual(new, old)
                self.assertEqual(catalog, original)
                self.assertEqual(editorsnapshot.configuration(self.profile), configuration)


    def test_structured_source_digests_reject_stale_catalogs(self):
        row = self.structured_note()
        self.set_structured([row])
        catalog = self.catalog()
        catalog["s1"][1].msgid = "Changed source"
        with self.assertRaisesRegex(ValueError, "s1: translator note source differs"):
            self.documents("zz", catalog)
        manifest = {"profile": self.profile.name, "language": "zz", "rom_sha1": self.profile.sha1,
                    "source_sha256": draftcatalog.source_digest(e for _, e in catalog.values())}
        with self.assertRaisesRegex(ValueError, "source differs"):
            draftcatalog.editor_data(self.profile, "zz", catalog, manifest)
        catalog["s1"][1].msgid = "s1"
        catalog["s1"][1].keyed = True
        for digests in (None, {"s1": self.note["source_sha256"]}):
            self.assertEqual(guidance.entry_notes(self.profile, catalog, digests)["s1"][0]["text"],
                             row["guidance"][0])
        for digests in ({}, {"s1": source.digest("Changed source")}):
            with self.subTest(digests=digests), self.assertRaisesRegex(ValueError, "source differs"):
                guidance.entry_notes(self.profile, catalog, digests)
        partial = {"s2": (Path("a.po"), PoEntry("s2", self.source_text))}
        self.assertEqual(guidance.entry_notes(self.profile, partial), {})


    def test_language_policy_retains_shared_notes(self):
        from gen3tl.project import Registry
        original = Profile.by_name("unbound-2.1.1.1")
        registry = Registry.load(UNBOUND)
        shared = registry.resolve(original, "ru").notes
        self.assertTrue(shared.is_file())
        for language in ("ru", "es", "de", "fr"):
            selected = registry.resolve(original, language).effective(original)
            self.assertEqual(selected.notes_path, shared)
            self.assertEqual(guidance.profile_rows(selected), guidance.read_notes(shared))
            self.assertNotIn("translator_notes", selected.data)


    @needs_rom
    def test_shared_note_english_is_recovered_from_the_original_rom(self):
        from gen3tl.catalog.catalog import load_catalog
        from gen3tl.project import Registry

        original = Profile.by_name("unbound-2.1.1.1")
        registry = Registry.load(UNBOUND)
        rom = original.load_rom(rom_path())
        for language in ("ru", "es", "de", "fr"):
            project = registry.resolve(original, language)
            selected = project.effective(original)
            catalog = load_catalog(project.catalog, selected)
            notes = guidance.entry_notes(selected, catalog)
            catalog = {sid: row for sid, row in catalog.items() if sid in notes}
            snapshot = snapshot_store.load(project.snapshot)
            rows = editordata.source_data(selected, catalog, {"entries": snapshot["inventory"]}, snapshot)
            texts, missing = source.read(bytes(rom.data), rows["rows"])
            with self.subTest(language=language):
                self.assertEqual(missing, [])
                # proposed notes are not yet guidance
                bindings = [note.get("binding", note) for note in guidance.profile_rows(selected)
                            if note.get("status", "accepted") in ("unreviewed", "accepted")]
                aliases = keys.for_profile(selected)
                bound_keys = [aliases.key(aliases.entry_id(binding["id"])) for binding in bindings]
                self.assertEqual(len(texts), len(set(bound_keys)))
                for key, binding in zip(bound_keys, bindings):
                    self.assertEqual(source.digest(texts[key]), binding["source_sha256"])
