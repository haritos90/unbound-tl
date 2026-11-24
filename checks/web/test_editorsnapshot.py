import copy
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from gen3tl.cli import main as cli
from gen3tl.web import editordata, editorsnapshot as snapshot
from gen3tl.check import qa, rules
from gen3tl.check.provenance import formatted
from gen3tl.catalog.catalog import load_catalog
from gen3tl.web.editorcheck import Checker, latin_cells, latin_widths
from gen3tl.build.font import FontTable
from gen3tl.lang.langpack import load_styles
from gen3tl.catalog.po import PoEntry, write
from gen3tl.catalog.source import digest
from gen3tl.profile.profile import Profile
from gen3tl.core.rom import Rom

from project_fixture import UNBOUND, literal, needs_unbound, with_profile_notes, write_policy
from editordata_support import CTX, INV, PO, PROF, REACH

class SnapshotTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.po = self.root / "translation/po"
        for name, entries in PO.items():
            write(self.po / name, copy.deepcopy(entries), {"Project-Id-Version": "test", "Language": "ru"})
        self.catalog = load_catalog(self.po)
        self.prof = Profile(copy.deepcopy(PROF.data), self.root / "test.toml")
        self.rom = Rom(bytes(0x14000))
        for font in FontTable.from_profile(self.prof):
            self.rom.data[font.widths:font.widths + font.count] = bytes([6]) * font.count
        self.rom.data[0xF000:0xF004] = (0x0800F100).to_bytes(4, "little")
        self.rom.data[0xF100:0xF104] = (0x08000100).to_bytes(4, "little")
        self.rom.data[0xF104:0xF108] = (1234).to_bytes(4, "little")
        self.prof.data["layout"]["record_window"] = [{
            "name": "record", "table": 0xF000, "count": 1, "width": 77, "lines": 2,
            "texts": [{"path": [0], "number": {"path": [4], "slots": ["STR_VAR_1"]}}]}]
        self.prof.data["rom"]["sha1"] = self.rom.sha1()
        self.identity = {"profile": self.prof.name, "rom_sha1": self.prof.sha1}
        self.inv = {**copy.deepcopy(INV), **self.identity}
        self.inv["entries"][0]["refs"].append({"at": 0xF100, "kind": "table"})
        self.ctx = {**copy.deepcopy(CTX), **self.identity}
        self.reach = {**copy.deepcopy(REACH), **self.identity}
        self.doc = snapshot.extract(self.prof, "ru", self.rom, self.inv, self.ctx, self.reach,
                                    self.catalog, self.po)

    def validate(self, doc=None):
        snapshot.validate(self.doc if doc is None else doc, self.prof, "ru", self.catalog, self.po)

    def data(self, offline):
        measure, cm, measures = snapshot.measures(self.prof, "ru", self.doc["fonts"])
        if offline:
            inv, ctx, reach, facts = snapshot.inputs(self.doc, self.catalog, self.prof)
            limits = qa.compute_limits(self.prof, inv, self.catalog, measure, cm, ctx, facts=facts)
        else:
            inv, reach = self.inv, self.reach
            limits = qa.compute_limits(self.prof, inv, self.catalog, measure, cm, self.ctx, rom=self.rom)
        return editordata.build("ru", self.prof, self.catalog, limits, measure, cm,
                               load_styles("ru", self.prof), notes=self.doc["notes"],
                               windows=qa.Windows(self.prof, inv, measures), reach=reach,
                               rules=rules.profile_rules(self.prof, inv, self.catalog, limits),
                               fill_facts=self.doc["records"])

    def test_snapshot_reconstructs_record_windows_and_all_editor_fields(self):
        self.assertEqual(self.data(True), self.data(False))
        inv, ctx, reach, facts = snapshot.inputs(self.doc, self.catalog, self.prof)
        self.assertEqual(facts["windows"][0][:3], (0xF100, 77, 2))
        self.assertEqual(facts["numbers"], {0xF100: {"STR_VAR_1": 1234}})
        self.assertNotIn("pixels", json.dumps(self.doc))
        self.assertNotIn("palette", json.dumps(self.doc))
        self.assertNotIn("text", self.doc["inventory"][0])
        self.assertEqual(self.doc["inventory"][0]["source_sha256"], digest(self.inv["entries"][0]["text"]))


    def test_snapshot_preserves_measured_message_arrow(self):
        language = self.doc["language"]
        lay = self.prof.data["layout"]
        lay.pop("record_window")
        lay["prompt_arrow_width"] = 10
        lay["table_window"] = [{"name": "field-messages", "base": 0xF100, "stride": 4,
                                "count": 1, "fields": [0], "width": 70, "box": "dialogue",
                                "evidence": "The getter feeds the field message printer."}]
        self.doc = snapshot.extract(self.prof, language, self.rom, self.inv, self.ctx, self.reach,
                                    self.catalog, self.po)
        self.assertEqual(self.data(True), self.data(False))
        inv, ctx, _, facts = snapshot.inputs(self.doc, self.catalog, self.prof)
        measure, cm, _ = snapshot.measures(self.prof, language, self.doc["fonts"])
        limits = qa.compute_limits(self.prof, inv, self.catalog, measure, cm, ctx, facts=facts)
        lim = limits[self.inv["entries"][0]["id"]]
        self.assertEqual((lim.kind, lim.width, lim.arrow), ("dialogue", 70, 10))

    def test_snapshot_preserves_record_arrow_override(self):
        self.prof.data["layout"]["prompt_arrow_width"] = 10
        rule = self.prof.data["layout"]["record_window"][0]
        rule.update(prompt_arrow_width=0, evidence="The bitmap printer has no waiting state.")
        self.doc = snapshot.extract(self.prof, "ru", self.rom, self.inv, self.ctx, self.reach, self.catalog, self.po)
        self.assertEqual(self.data(True), self.data(False))
        entry = next(e for e in self.data(True)["entries"] if e["id"] == self.inv["entries"][0]["id"])
        record = next(c for c in entry["window"]["consumers"] if c["name"] == "record")
        self.assertEqual((record["arrow"], record["arrow_source"]), (0, "declared"))

    def test_snapshot_preserves_runtime_scroll_binding(self):
        self.prof.data["layout"]["prompt_arrow_width"] = 10
        rule = self.prof.data["layout"]["record_window"][0]
        rule.update(newline_scroll_after=1, evidence="The printer converts later newlines.")
        self.doc = snapshot.extract(self.prof, self.doc["language"], self.rom, self.inv, self.ctx, self.reach, self.catalog, self.po)
        self.assertEqual(self.data(True), self.data(False))
        entry = next(e for e in self.data(True)["entries"] if e["id"] == self.inv["entries"][0]["id"])
        record = next(c for c in entry["window"]["consumers"] if c["name"] == "record")
        self.assertEqual(record["newline_scroll_after"], 1)
        self.assertEqual(entry["window"]["newline_scroll_after"], 1)

    def test_snapshot_preserves_instant_record_consumer(self):
        rule = self.prof.data["layout"]["record_window"][0]
        rule.update(instant_print=True, evidence="The printer runs instantly.")
        self.doc = snapshot.extract(self.prof, self.doc["language"], self.rom, self.inv, self.ctx, self.reach,
                                    self.catalog, self.po)
        self.assertEqual(self.data(True), self.data(False))
        entry = next(e for e in self.data(True)["entries"] if e["id"] == self.inv["entries"][0]["id"])
        record = next(c for c in entry["window"]["consumers"] if c["name"] == "record")
        self.assertTrue(record["instant_print"])

    def test_bound_notes_survive_snapshot_and_editor_exports(self):
        evidence = "Measured window.\nVerified buffer."
        self.prof.data["layout"]["record_window"][0]["evidence"] = evidence
        self.prof.data["layout"]["window_width"].pop("s0000300")
        self.prof.data["layout"]["table_window"] = [
            {"base": 0x310, "count": 1, "stride": 4, "width": 76, "evidence": evidence}]
        self.prof.data["table"][0]["windows"][0].update(strict=True, chars=9, evidence=evidence)
        original = copy.deepcopy(self.prof.data)
        for status in ("unreviewed", "accepted"):
            with self.subTest(status=status):
                self.prof.data = with_profile_notes(original, status)
                self.doc = snapshot.extract(self.prof, "ru", self.rom, self.inv, self.ctx, self.reach,
                                            self.catalog, self.po)
                restored = json.loads(json.dumps(self.doc))
                self.validate(restored)
                sources = restored["source"]
                for sid, dimension in (("s0000100", "width"), ("s0000300", "width"),
                                       ("species:1", "chars")):
                    self.assertEqual(sources[sid][5]["sources"][dimension][2],
                                     evidence, sid)
                self.assertEqual(self.data(True), self.data(False))
                malformed = copy.deepcopy(restored)
                malformed["inventory"][0]["length"] = True
                with self.assertRaisesRegex(ValueError, "invalid measurement snapshot value"):
                    self.validate(malformed)
                malformed = copy.deepcopy(restored)
                malformed["source"]["species:1"][5]["sources"]["chars"][2] = []
                with self.assertRaisesRegex(ValueError, "invalid measurement snapshot value"):
                    self.validate(malformed)


    def test_snapshot_window_references_retain_site_language_descriptions(self):
        rule = self.prof.data["layout"]["record_window"][0]
        rule.update(where="mission list", evidence="WindowTemplate at 0xF000")
        labels = self.root / "profile-labels.po"
        label = PoEntry("layout.record_window[name=record].where", "mission list", "список заданий")
        write(labels, [label], {})
        self.enterContext(patch.object(editordata, "profile_label_inputs", return_value={"ru": labels}))
        self.doc = snapshot.extract(self.prof, "ru", self.rom, self.inv, self.ctx, self.reach,
                                    self.catalog, self.po)
        self.validate()
        self.assertEqual(self.doc["records"]["windows"][0][3:], ["record_window", 0])
        self.assertIn("mission list", formatted(self.doc["source"]["s0000100"][5]["sources"]["width"][1]))
        _, _, _, facts = snapshot.inputs(self.doc, self.catalog, self.prof)
        self.assertNotIn("where_ru", facts["windows"][0][3])
        offline = self.data(True)
        self.assertEqual(offline, self.data(False))
        self.assertEqual(offline["where_texts"]["mission list"], {"ru": "список заданий"})
        entry = next(e for e in offline["entries"] if e["id"] == "s0000100")
        self.assertEqual(entry["window"]["sources"]["width"]["evidence"], "WindowTemplate at 0xF000")
        label.msgstr = "перечень заданий"
        write(labels, [label], {})
        self.validate()
        self.assertEqual(self.data(True)["where_texts"]["mission list"]["ru"], "перечень заданий")


    def test_code_fill_originals_are_typed_and_match_live_measurements(self):
        import hashlib

        raw = b"\xbb\xbb\xff"
        self.rom.write(0xF200, raw)
        self.prof.data["rom"]["sha1"] = self.rom.sha1()
        for document in (self.inv, self.ctx, self.reach):
            document["rom_sha1"] = self.prof.sha1
        self.prof.data["layout"]["code_fill"] = [{"ids": ["s0000100"], "evidence": "actual font2",
            "slots": {"STR_VAR_1": {"strings": ["s0000200"], "font": "font0", "originals": [
                {"id": "s000F200", "length": 3, "sha256": hashlib.sha256(raw).hexdigest()}]}}}]
        self.prof.data = with_profile_notes(self.prof.data)
        self.doc = snapshot.extract(self.prof, "ru", self.rom, self.inv, self.ctx, self.reach,
                                    self.catalog, self.po)
        fact = self.doc["records"]["code_originals"]["s000F200"]
        self.assertEqual((fact["width"], fact["glyph_counts"]), (12, [[187, 2]]))
        offline, live = self.data(True), self.data(False)
        self.assertEqual(offline, live)
        host = next(entry for entry in offline["entries"] if entry["id"] == "s0000100")
        self.assertTrue(any("one of 2 source strings, measured at their widest rendering" in formatted(rule["text"])
                            for rule in host["rules"]))
        for value in ({}, {"length": "3"}, {"glyph_counts": [[187, 1]]}, {"width": 13}):
            bad = copy.deepcopy(self.doc)
            if value:
                bad["records"]["code_originals"]["s000F200"].update(value)
            else:
                bad["records"]["code_originals"] = {}
            bad["facts_sha256"] = snapshot.digest({k: v for k, v in bad.items() if k != "facts_sha256"})
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.validate(bad)

    def test_trainer_roles_retain_all_reference_evidence(self):
        sid = "s0000300"
        uses = [{"event": "npc", "box": "trainer", "at": 1234, "trainer_role": "defeat"},
                {"event": "npc", "box": "autoclose", "at": 5678, "trainer_role": None}]
        self.ctx["strings"][sid] = {"uses": uses}
        self.doc = snapshot.extract(self.prof, "ru", self.rom, self.inv, self.ctx, self.reach,
                                    self.catalog, self.po)
        self.assertEqual(self.doc["context"][sid]["uses"], uses)
        _, ctx, _, _ = snapshot.inputs(self.doc, self.catalog, self.prof)
        self.assertEqual(ctx["strings"][sid]["uses"], uses)
        self.assertEqual(self.data(True), self.data(False))


    def test_participant_evidence_survives_key_only_export(self):
        from gen3tl.discover.maps import gender_source, identity_context
        from gen3tl.catalog.po import KEY_ONLY, SOURCE_FIELD, read
        identity = identity_context("You had one job.")
        identity["speaker"]["sources"] = [gender_source("sprite", "male", 7, "object table")]
        identity["addressee"]["sources"] = [gender_source("trainer", "female", "9 / 5", "scene trace")]
        identity = with_profile_notes(identity)
        self.ctx["strings"]["s0000100"]["identity"] = identity
        doc = snapshot.extract(self.prof, "ru", self.rom, self.inv, self.ctx, self.reach,
                               self.catalog, self.po)
        saved = doc["source"]["s0000100"][5]["context"]["identity"]
        self.assertEqual(saved["addressee"], identity["addressee"])
        self.assertIn(identity["speaker"]["sources"][0], saved["speaker"]["sources"])
        for path in self.po.rglob("*.po"):
            header, entries = read(path)
            write(path, entries, {**header, SOURCE_FIELD: KEY_ONLY})
        catalog = load_catalog(self.po, source={}, english=False)
        inv, ctx, reach, facts = snapshot.inputs(doc, catalog, self.prof)
        measure, cm, measurements = snapshot.measures(self.prof, "ru", doc["fonts"])
        limits = qa.compute_limits(self.prof, inv, catalog, measure, cm, ctx, facts=facts)
        data = editordata.build("ru", self.prof, catalog, limits, measure, cm,
                                load_styles("ru", self.prof), source=doc["source"], contexts=ctx, fill_facts=facts)
        exported = next(e for e in data["entries"] if e["id"] == "s0000100")["context"]["identity"]
        self.assertEqual(exported, saved)

    def test_translation_edits_recalculate_inserted_word_widths(self):
        self.doc["records"]["numbers"] = {}
        self.prof.data["layout"]["record_window"][0]["texts"][0].pop("number")
        self.doc["configuration_sha256"] = snapshot.configuration(self.prof)
        self.doc["facts_sha256"] = snapshot.digest({k: v for k, v in self.doc.items() if k != "facts_sha256"})
        before = self.data(True)
        self.catalog["s0000200"][1].msgstr = "Суперзелье"
        self.validate()
        after = self.data(True)
        old = next(e for e in before["entries"] if e["id"] == "s0000100")
        new = next(e for e in after["entries"] if e["id"] == "s0000100")
        self.assertNotEqual(old["window"]["placeholders"], new["window"]["placeholders"])
        self.assertEqual(after, self.data(False))

    def test_original_and_copied_glyph_checks_match_user_rom(self):
        doc = self.data(True)
        old = Checker(doc, latin_widths(doc["fonts"], bytes(self.rom.data), self.prof.sha1),
                      {}, "1.2.3", latin_cells(doc["fonts"], bytes(self.rom.data)))
        new = snapshot.checker(doc, self.doc["fonts"], {}, "1.2.3")
        for style in doc["fonts"]["styles"]:
            left, right = old.measures[style][0], new.measures[style][0]
            for code in range(512):
                self.assertEqual(left.glyph_width(code), right.glyph_width(code))
                self.assertEqual(left.shadow_end(code), right.shadow_end(code))
        for entry in doc["entries"]:
            text = entry["translation"] or self.catalog[entry["id"]][1].msgid
            self.assertEqual(old.check(entry, text), new.check(entry, text))

    def test_centred_titles_recalculate_after_translation_edits(self):
        self.prof.data["layout"]["window_width"].pop("s0000300")
        self.prof.data["layout"]["table_window"] = [{
            "base": 0x310, "count": 1, "stride": 4, "width": 76,
            "centre": {"reference": "s0000400", "step": 6}}]
        self.catalog["s0000400"][1].msgstr = "Зелье"
        self.doc = snapshot.extract(self.prof, "ru", self.rom, self.inv, self.ctx, self.reach,
                                    self.catalog, self.po)
        before = next(e["window"]["width"] for e in self.data(True)["entries"] if e["id"] == "s0000300")
        self.catalog["s0000300"][1].msgstr = "Сум"
        self.validate()
        after = self.data(True)
        width = next(e["window"]["width"] for e in after["entries"] if e["id"] == "s0000300")
        self.assertEqual(width, before - 12)
        self.assertEqual(after, self.data(False))

    def test_keyboard_columns_and_interior_prefixes_are_semantic_facts(self):
        self.prof.data["keyboard"] = {"base_pages": 1, "table": [
            {"name": "columns", "base": 0xF200, "entry": 1},
            {"name": "column_x", "base": 0xF210, "entry": 8},
            {"name": "keys", "base": 0x5000, "entry": 22}]}
        self.rom.data[0xF200] = 10
        self.rom.data[0xF210:0xF218] = bytes(range(0, 80, 10))
        self.rom.data[0xF300:0xF304] = (0x08000601).to_bytes(4, "little")
        self.prof.data["strings"] = {"interior": [{"id": "s0000600", "offset": 1, "pointer": 0xF300,
                                                  "evidence": "fixture prefix"}]}
        self.prof.data = with_profile_notes(self.prof.data)
        self.prof.data["rom"]["sha1"] = self.rom.sha1()
        for document in (self.inv, self.ctx, self.reach):
            document["rom_sha1"] = self.prof.sha1
        self.doc = snapshot.extract(self.prof, "ru", self.rom, self.inv, self.ctx, self.reach,
                                    self.catalog, self.po)
        self.assertEqual(self.doc["records"]["keys"], {"species:1": 10})
        self.assertEqual(self.doc["records"]["heads"], {"s0000600": "s"})
        self.assertEqual(self.doc["records"]["cursor"], [list(range(0, 80, 10))])
        self.assertEqual(self.data(True), self.data(False))


    def test_version_token_uses_current_release_without_snapshot_refresh(self):
        doc = self.data(True)
        entry = next(e for e in doc["entries"] if e["id"] == "s0000300")
        text = "Версия @VERSION@"
        checker = snapshot.checker(doc, self.doc["fonts"], {}, "12.34.56")
        actual = checker.check(entry, text)
        self.assertEqual(actual, checker.check(entry, "Версия 12.34.56"))
        self.assertNotIn("@VERSION@", actual["laid"])
        self.validate()


    def test_cli_builds_without_rom_or_build_analyses(self):
        self.prof.path.write_text("\n".join(f"{key} = {literal(value)}" for key, value in self.prof.data.items()))
        write_policy(self.root, self.prof)
        (self.root / "projects.toml").write_text(
            '[defaults]\nprofile="test"\nlanguage="ru"\n[[project]]\nprofile="test"\nlanguage="ru"\n'
            'root="."\npolicy="policy.toml"\n')
        from gen3tl.project import Registry
        selected = Registry.load(self.root).projects[0].effective(self.prof)
        self.doc = snapshot.extract(selected, "ru", self.rom, self.inv, self.ctx, self.reach, self.catalog, self.po)
        snapshot.write(self.root / "translation/editor-inputs.json", self.doc)
        (self.root / "translation/release.toml").write_text('version="1.2.3"\n')
        self.assertFalse((self.root / "build").exists())
        self.assertFalse((self.root / "rom").exists())
        args = ["--project-root", str(self.root), "--profile", str(self.prof.path),
                "web", "data", "--no-rom"]
        with patch.object(Profile, "load_rom", side_effect=AssertionError("ROM access forbidden")):
            with redirect_stdout(io.StringIO()):
                self.assertIsNone(cli.main(args))
                self.assertIsNone(cli.main(args + ["--split"]))
                staged = self.root / "build/stage/view"
                self.assertIsNone(cli.main(args + ["--split", "--language-only", "--out", str(staged)]))
        doc = json.loads((self.root / "build/editor/ru.json").read_text())
        self.assertEqual(doc["version"], "1.2.3")
        self.assertEqual(len(doc["entries"]), len(self.catalog))
        index = json.loads((self.root / "build/editor/test/ru/index.json").read_text())
        self.assertEqual(index["version"], "1.2.3")
        self.assertEqual(json.loads((staged / "index.json").read_text()), index)
        self.assertEqual(sorted(staged.parent.iterdir()), [staged.parent / "shared", staged])

    def test_incomplete_source_table_preserves_snapshot_and_offline_exports(self):
        self.prof.data["layout"].update(
            fill_source={"player": {"label": "Player name", "font": "font0", "value": {"table": "species"},
                                    "evidence": "Verified name table"}},
            slot_source={"PLAYER": "player"})
        self.doc = snapshot.extract(self.prof, "ru", self.rom, self.inv, self.ctx, self.reach,
                                    self.catalog, self.po)
        live, offline = self.data(False), self.data(True)
        self.assertEqual(live, offline)
        detail = live["entries"][0]["window"]["slot_details"]["PLAYER"]
        self.assertEqual((detail["width"], detail["state"]), (42, "recorded"))
        self.assertIn("incomplete table", detail["unavailable"])
        self.test_cli_builds_without_rom_or_build_analyses()


@needs_unbound
class CommittedSnapshotTest(unittest.TestCase):
    """The editor refuses a snapshot older than the profile."""

    def test_window_descriptions_are_available_across_language_projects(self):
        from gen3tl.catalog import keys
        from gen3tl.catalog.po import read
        from gen3tl.project import Registry

        project = Registry.load(UNBOUND).resolve("unbound-2.1.1.1", "ru")
        _, entries = read(project.profile_labels)
        expected = {entry.msgid: entry.msgstr for entry in entries}

        def descriptions(value):
            if isinstance(value, dict):
                if "where" in value:
                    yield value
                for child in value.values():
                    yield from descriptions(child)
            elif isinstance(value, list):
                for child in value:
                    yield from descriptions(child)

        for code in ("ru", "es", "de", "fr"):
            prof = Profile.by_name("unbound-2.1.1.1").for_project(code, UNBOUND)
            texts = editordata.where_texts(prof, keys.for_profile(prof))
            for section in ("layout", "table", "sprite_font"):
                for fact in descriptions(prof.get(section, {})):
                    with self.subTest(language=code, where=fact["where"]):
                        self.assertNotIn("where_ru", fact)
                        self.assertNotEqual(expected[fact["where"]], fact["where"])
                        self.assertEqual(texts[fact["where"]]["ru"], expected[fact["where"]])
                        self.assertFalse({"es", "de", "fr"} & texts[fact["where"]].keys())

    def test_fill_source_labels_are_available_across_language_projects(self):
        from gen3tl.catalog import keys
        from gen3tl.catalog.po import read
        from gen3tl.profile.schema import key_text
        from gen3tl.project import Registry

        project = Registry.load(UNBOUND).resolve("unbound-2.1.1.1", "ru")
        _, entries = read(project.profile_labels)
        expected = {entry.msgctxt: entry for entry in entries}
        for code in ("ru", "es", "de", "fr"):
            prof = Profile.by_name("unbound-2.1.1.1").for_project(code, UNBOUND)
            texts = editordata.where_texts(prof, keys.for_profile(prof))
            sources = prof["layout"]["fill_source"]
            self.assertIn("Frostbite-curing berry", [source["label"] for source in sources.values()])
            for name, source in sources.items():
                entry = expected[f"layout.fill_source.{key_text(name)}.label"]
                with self.subTest(language=code, label=source["label"]):
                    self.assertEqual(entry.msgid, source["label"])
                    self.assertNotEqual(entry.msgstr, entry.msgid)
                    self.assertEqual(texts[source["label"]], {"ru": entry.msgstr})

    def test_committed_snapshot_matches_the_profile(self):
        root = UNBOUND
        paths = sorted((root / "source" / "snapshot").glob("*.snapshot.json"))
        self.assertTrue(paths)
        for path in paths:
            doc = snapshot.load(path)
            self.assertEqual(path.name, f"{doc['language']}.snapshot.json")
            prof = Profile.by_name(doc["profile"]).for_project(doc["language"], root)
            self.assertEqual(doc["configuration_sha256"], snapshot.configuration(prof),
                             f"{path.relative_to(root)} is older than the profile: run "
                             f"PYTHONPATH=src python3 -m gen3tl web snapshot --lang {doc['language']}")
