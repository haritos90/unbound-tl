import json
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from gen3tl.catalog import catalog, draftcatalog, entrynotes, po
from gen3tl.catalog.source import digest
from gen3tl.core import notes as structured
from gen3tl.lang import language
from gen3tl.web import editordata
from gen3tl.core.charmap import Charmap
from gen3tl.check.layout import Measure
from gen3tl.profile.profile import Profile

from editorstore_support import decoded

class SourceNoteTest(unittest.TestCase):


    def test_verified_and_draft_editor_data_share_note_form(self):
        profile = Profile({"rom": {"sha1": "a" * 40}, "layout": {}, "font": []}, Path("example.toml"))
        entry = po.PoEntry("s1", "Hello", "Bonjour", translator=["General remark", "source: Official game", "source: glossary:example"])
        rows = {"s1": (Path("translation/po/a.po"), entry)}
        measure = Measure(lambda b: 6, {})
        verified = editordata.build("fr", profile, rows, {}, measure, Charmap(), {}, toolkit="1.0.0")
        manifest = {"profile": profile.name, "language": "fr", "rom_sha1": profile.sha1,
                    "source_sha256": draftcatalog.source_digest([entry])}
        draft = draftcatalog.editor_data(profile, "fr", rows, manifest)
        for document in (verified, draft):
            self.assertEqual(document["entries"][0]["note"], "Official game\nglossary:example")
            self.assertNotIn("General remark", document["entries"][0]["note"])
        entry.source_note = "Current provenance"
        refreshed = draftcatalog.editor_data(profile, "fr", rows, manifest)
        self.assertEqual(refreshed["entries"][0]["note"], "Current provenance")

class StructuredSourceNoteTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.enterContext(language.use(language.Language("fixture", {}, self.root)))
        self.po_root = self.root / "po"
        self.file = self.po_root / "maps" / "one.po"
        self.code = language.current().code
        self.header = {"Language": self.code, "Project-Id-Version": "example"}
        self.note_path = entrynotes.path(self.po_root)
        self.addCleanup(entrynotes.invalidate, self.note_path)
        self.note = {"id": "note:entry-one", "subject": {"kind": "entry", "id": "s1"},
                     "scope": {"kind": "language", "language": self.code},
                     "binding": {"kind": "entry", "id": "s1", "source_sha256": digest("Hello")},
                     "reason": ["Recorded wording rationale."], "status": "unreviewed",
                     "sources": [{"kind": "project", "name": "Reference", "address": "reference:key",
                                  "verification": "recorded", "locator": "section 2"}]}
        self.entry = po.PoEntry("s1", "Hello", "Old", translator=["General remark"], flags=["c-format"])
        po.write(self.file, [self.entry], self.header)
        self.store_notes()

    def store_notes(self, *notes):
        structured.write_notes(self.note_path, {"schema": structured.SCHEMA, "note": list(notes) or [self.note]})


    def test_editor_views_refresh_notes_and_preserve_translation_fields(self):
        profile = Profile({"rom": {"sha1": "a" * 40}, "layout": {}, "font": []}, Path("example.toml"))
        rows = catalog.load_catalog(self.po_root)
        manifest = {"profile": profile.name, "language": self.code, "rom_sha1": profile.sha1,
                    "source_sha256": draftcatalog.source_digest([self.entry])}
        self.note["reason"] = ["Updated after catalog loading."]
        self.store_notes()
        verified = editordata.build(self.code, profile, rows, {}, Measure(lambda b: 6, {}), Charmap(), {})
        draft = draftcatalog.editor_data(profile, self.code, rows, manifest)
        for document in (verified, draft):
            entry = document["entries"][0]
            self.assertNotIn("note", entry)
            self.assertEqual(document["notes"]["note"][0]["reason"], ["Updated after catalog loading."])
            self.assertEqual((entry["translation"], entry["flags"]), ("Old", ["c-format"]))


class EditorNoteCollectionTest(unittest.TestCase):
    def setUp(self):
        from gen3tl.catalog import guidance
        from gen3tl.build.graphics import graphics_text
        from gen3tl.check import rules
        from gen3tl.lang.termbase import Term
        from gen3tl.profile import schema

        from project_fixture import literal

        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.enterContext(language.use(language.Language("fixture", {}, self.root)))
        self.folder = self.root / "locale"
        self.code = language.current().code
        self.records = []

        def note(nid, kind, target, shared=False, **fields):
            subject = {"kind": kind, "id": target}
            row = {"id": nid, "subject": subject,
                   "scope": {"kind": "shared"} if shared else {"kind": "language", "language": self.code},
                   "status": "unreviewed", "facts": [f"Recorded {kind} fact."], **fields}
            if kind in ("entry", "graphic", "profile_fact"):
                row["binding"] = dict(subject)
            if kind == "entry":
                row["binding"]["source_sha256"] = digest("Hello")
            self.records.append(row)
            return row

        shared = note("entry-shared", "entry", "s1", True)
        wording = note("entry-wording", "entry", "s1", status="proposed",
                       author="contributor", created="2026-11-11",
                       sources=[{"kind": "project", "name": "Reference", "address": "ref:one",
                                 "verification": "recorded", "quote": "Exact quotation."}])
        term = note("term-note", "term", "term:one", status="needs_review")
        research = note("research-note", "research", "record:one", status="superseded")
        profile = note("profile-note", "profile_fact", "rom.size", True,
                       evidence=[{"method": "measurement", "verification": "recorded",
                                  "locations": [{"kind": "rom_offset", "value": 256}]}])
        profile["binding"].update(value_sha256=schema.value_digest(4096), field="evidence")
        artwork = note("art-note", "graphic", "picture", True)
        layout = note("layout-note", "graphic", "picture", status="accepted")
        rule = note("rule-note", "wording_rule", "rule:one")
        self.rule_rows = [{"id": "rule:one", "ids": ["s1"], "notes": [rule]}]
        self.terms = [Term("term:one", "item", "Hello", "Hello", note_ids=(term["id"],),
                           note_records=(term,), notes="Existing term projection.")]
        self.terms.append(Term("term:legacy", "item", "Goodbye", "Goodbye", notes="Legacy term note."))
        self.shared_path = self.root / "shared.toml"
        guidance.write_notes(self.shared_path, [shared, {"id": "s2", "source_sha256": digest("Goodbye"),
                                                       "text": "Legacy guidance.", "evidence": "Recorded proof."}])
        for name, rows in (("notes/entries.toml", [wording]), ("notes/terms.toml", [term]),
                           ("notes/graphics.toml", [layout]), ("research/example.notes.toml", [research])):
            structured.write_notes(self.folder / name, {"schema": structured.SCHEMA, "note": rows})
        rules.write_list(self.folder / "rules.toml", self.rule_rows, code=self.code)
        self.graphic_path = self.root / "graphics.toml"
        self.graphic_path.write_text(graphics_text([
            {"id": "picture", "reason": "", "notes_schema": structured.SCHEMA, "notes": [artwork]},
            {"id": "legacy-picture", "reason": "Legacy artwork note."}], {}), encoding="utf-8")
        profile_path = self.root / "profile-facts"
        profile_path.mkdir()
        (profile_path / "profile.toml").write_text('[discovery]\nschema = 1\n')
        (profile_path / "overlay.toml").write_text(
            'rom = {sha1 = "' + "a" * 40 + '", size = 4096}\n[[fact]]\nid = "rom.size"\n'
            'notes_schema = "3.0.0"\n[[fact.notes]]\n' +
            "\n".join(f"{key} = {literal(value)}" for key, value in profile.items()), encoding="utf-8")
        self.prof = Profile.load(profile_path)
        self.prof.data["font"] = []
        self.prof.notes_path = self.shared_path
        self.prof._project_root = self.root
        self.prof.data["graphics"] = {"inventory": "graphics.toml"}
        self.catalog = {sid: (self.folder / "po" / "one.po", po.PoEntry(sid, text, text))
                        for sid, text in (("s1", "Hello"), ("s2", "Goodbye"))}
        self.catalog["s2"][1].source_note = "Legacy source note."

    def build(self):
        from gen3tl.check.rules import wording_rules
        return editordata.build(self.code, self.prof, self.catalog, {}, Measure(lambda b: 6, {}),
                                Charmap(), {}, self.terms, note_root=self.folder,
                                wording=wording_rules(self.rule_rows, self.catalog), wording_rows=self.rule_rows,
                                toolkit="1.0.0")

    def test_all_kinds_keep_complete_records_and_legacy_views(self):
        before = {sid: (entry.msgid, entry.msgstr, list(entry.flags))
                  for sid, (_, entry) in self.catalog.items()}
        doc = self.build()
        self.assertEqual({row["id"]: row for row in doc["notes"]["note"]},
                         {row["id"]: row for row in self.records})
        structured.validate(doc["notes"])
        first, legacy = doc["entries"]
        self.assertEqual(first["note_ids"], ["entry-shared", "entry-wording", "rule-note"])
        self.assertNotIn("note", first)
        self.assertNotIn("translator_notes", first)
        self.assertEqual(legacy["note"], "Legacy source note.")
        self.assertEqual(legacy["translator_notes"], [{"text": "Legacy guidance.", "evidence": "Recorded proof."}])
        self.assertEqual(doc["glossary"]["term:legacy"]["notes"], "Legacy term note.")
        self.assertEqual(doc["glossary"]["term:one"]["note_ids"], ["term-note"])
        graphic, old_graphic = doc["graphics"]["inventory"]
        self.assertEqual(graphic["note_ids"], ["art-note", "layout-note"])
        self.assertNotIn("reason", graphic)
        self.assertEqual(old_graphic["reason"], "Legacy artwork note.")
        tdata = editordata.terms_data(self.terms, doc, self.catalog)
        self.assertEqual(tdata["terms"][0]["note_ids"], ["term-note"])
        self.assertNotIn("notes", tdata["terms"][0])
        self.assertEqual(tdata["terms"][1]["notes"], "Legacy term note.")
        self.assertNotIn("notes", doc["glossary"]["term:one"])
        index, chunks = editordata.split(doc, None, {}, terms=tdata)
        out = self.root / "view"
        editordata.write_split(out, index, chunks, tdata)
        self.assertEqual(decoded(out)["index"]["notes"], doc["notes"])
        self.assertEqual({sid: (entry.msgid, entry.msgstr, list(entry.flags))
                          for sid, (_, entry) in self.catalog.items()}, before)


    def test_staged_catalog_reads_its_note_copy_once(self):
        staged = self.root / "staged" / "po"
        structured.write_notes(entrynotes.path(staged), {"schema": structured.SCHEMA, "note": [self.records[1]]})
        self.catalog = {sid: (staged / "one.po", entry) for sid, (_, entry) in self.catalog.items()}
        doc = self.build()
        self.assertEqual([row["id"] for row in doc["notes"]["note"]].count("entry-wording"), 1)

    def test_entry_projections_follow_independent_note_sources(self):
        from gen3tl.catalog import guidance
        shared, wording = self.records[:2]
        for shared_notes, source_notes in ((True, False), (False, True), (False, False)):
            with self.subTest(shared=shared_notes, source=source_notes):
                guidance.write_notes(self.shared_path, [shared] if shared_notes else [
                    {"id": "s1", "source_sha256": digest("Hello"),
                     "text": "Legacy instruction.", "evidence": "Legacy evidence."}])
                structured.write_notes(self.folder / "notes/entries.toml", {
                    "schema": structured.SCHEMA, "note": [wording] if source_notes else []})
                self.catalog["s1"] = self.folder / "po/one.po", po.PoEntry("s1", "Hello", "Hello")
                if not source_notes:
                    self.catalog["s1"][1].source_note = "Legacy wording."
                manifest = {"profile": self.prof.name, "language": self.code, "rom_sha1": self.prof.sha1,
                            "source_sha256": draftcatalog.source_digest(e for _, e in self.catalog.values())}
                for doc in (self.build(), draftcatalog.editor_data(
                        self.prof, self.code, self.catalog, manifest, note_root=self.folder)):
                    entry = doc["entries"][0]
                    self.assertEqual("note" in entry, not source_notes)
                    self.assertEqual("translator_notes" in entry, not shared_notes)
                    if not source_notes:
                        self.assertEqual(entry["note"], "Legacy wording.")
                    if not shared_notes:
                        self.assertEqual(entry["translator_notes"][0]["text"], "Legacy instruction.")


    def test_note_identity_scope_and_inactive_bindings_are_checked(self):
        path = self.folder / "research" / "example.notes.toml"
        original = path.read_bytes()
        for change, message in (({"id": "term-note"}, "duplicate note"),
                                ({"scope": {"kind": "language", "language": "xy"}}, "expected research")):
            with self.subTest(change=change):
                row = {**self.records[3], **change}
                structured.write_notes(path, {"schema": structured.SCHEMA, "note": [row]})
                with self.assertRaisesRegex(ValueError, message):
                    self.build()
                path.write_bytes(original)
        row = deepcopy(self.records[1])
        row["binding"]["source_sha256"] = "0" * 64
        structured.write_notes(self.folder / "notes" / "entries.toml", {"schema": structured.SCHEMA, "note": [row]})
        with self.assertRaisesRegex(ValueError, "differs from catalog English"):
            self.build()
