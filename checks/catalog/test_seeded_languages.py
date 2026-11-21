import io
import json
import re
import shutil
import string
import tempfile
import unittest
from collections import Counter
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from gen3tl.web import snapshotstore as snapshot_store, editorsnapshot
from gen3tl.cli import main as cli
from gen3tl.build import keyboard
from gen3tl.build.release import build_names
from gen3tl.catalog.catalog import load_catalog
from gen3tl.check.entrycheck import UNVERIFIED
from gen3tl.check.fillsources import Evaluator, graph
from gen3tl.build.font import FontTable
from gen3tl.lang.langpack import LangPack
from gen3tl.catalog.po import read
from gen3tl.catalog import keys
from gen3tl.catalog.extract import load
from gen3tl.profile.profile import Profile
from gen3tl.project import Registry
from gen3tl.core.rom import Rom

from rom_support import needs_rom, rom_path
from project_fixture import ENGLISH, UNBOUND, copy_aliases, shared_profiles

CODES = ("es", "de", "fr")


PROFILE = "unbound-2.1.1.1"


@needs_rom
class OpenedProjectTest(unittest.TestCase):
    """The es, de and fr projects at translation stage."""

    @classmethod
    def setUpClass(cls):
        cls.enterClassContext(shared_profiles())

    def test_policies_compute_declared_slots_and_name_remaining_estimates(self):
        raw = Profile.by_name(PROFILE)
        registry = Registry.load(UNBOUND)
        slots = raw["policy_slots"]
        russian = registry.resolve(raw, "ru").effective(raw)
        for code in CODES:
            with self.subTest(code=code):
                project = registry.resolve(raw, code)
                profile = project.effective(raw)
                self.assertEqual((project.stage, profile.stage), ("translation", "translation"))
                layout = profile["layout"]
                slots = profile["policy_slots"]   # entries by inventory id, as the layout
                self.assertTrue(set(slots["window_width"]) <= layout["window_width"].keys())
                sources = layout["slot_source"]
                self.assertTrue(set(slots["placeholders"]) <= layout["placeholders"].keys() | sources.keys())
                marks = profile["policy_unverified"]
                self.assertEqual(set(marks), {"window_width", "placeholders", "code_fill",
                                              "table_windows", "table_window"})
                for section, names in marks.items():
                    self.assertTrue(set(names) <= set(slots[section]), section)
                self.assertNotIn("PLAYER", marks["placeholders"])
                self.assertIn("STR_VAR_1", marks["placeholders"])
                self.assertFalse(set(marks["placeholders"]) & sources.keys())
                snapshot = snapshot_store.load(project.snapshot)
                metrics = snapshot["fonts"]
                widths = metrics[raw["font_style"]["style"]]["widths"]
                pack = LangPack.load(code)
                typed = {c for k, row in profile["keyboard"]["rows"].items() if "_keys_" in k for c in row} - {" "}
                widest = max(widths[pack.chars[c]] for c in typed | set(string.ascii_letters))
                catalog = load_catalog(project.catalog, profile=profile, english=False)
                inv, _, _, facts = editorsnapshot.inputs(snapshot, catalog, profile)
                measure, cm, _ = editorsnapshot.measures(profile, code, metrics)
                resolved = graph(profile, inv, catalog, alphabet=facts["fill_alphabet"])
                evaluator = Evaluator(resolved, catalog, measure, cm, facts["fill_fragments"])
                self.assertEqual(evaluator.result(sources["PLAYER"])["width"], 7 * widest)
                for token, source in sources.items():
                    self.assertEqual(evaluator.result(source)["state"], "computed", token)
                if widest == 6:
                    for section in ("window_width", "placeholders"):
                        recorded = set(slots[section]) - (sources.keys() if section == "placeholders" else set())
                        self.assertEqual({k: layout[section][k] for k in recorded},
                                         {k: russian["layout"][section][k] for k in recorded})
                self.assertEqual(profile["qa"]["optional_tokens"], ["{PK}", "{MN}"])
                self.assertEqual(profile["graphics"]["edit"], [])

    def test_catalogs_hold_every_source_with_empty_targets(self):
        raw = Profile.by_name(PROFILE)
        registry = Registry.load(UNBOUND)
        source = {e.msgctxt: (path.relative_to(UNBOUND / "translation/ru/po").as_posix(), e.msgid)
                  for path in sorted((UNBOUND / "translation/ru/po").rglob("*.po")) for e in read(path)[1]}
        for code in CODES:
            with self.subTest(code=code):
                project = registry.resolve(raw, code)
                seen = {}
                for path in sorted(project.catalog.rglob("*.po")):
                    header, entries = read(path)
                    self.assertEqual((header["Language"], header["Project-Id-Version"]), (code, raw.name))
                    for e in entries:
                        self.assertEqual((e.msgstr, e.flags), ("", []), e.msgctxt)
                        seen[e.msgctxt] = (path.relative_to(project.catalog).as_posix(), e.msgid)
                self.assertEqual(seen, source)

    def test_no_rom_editor_data_checks_translations_and_marks_estimates(self):
        raw = Profile.by_name(PROFILE)
        registry = Registry.load(UNBOUND)
        aliases = keys.for_profile(raw)
        source_ids = {aliases.entry_id(e.msgctxt) for path in sorted((UNBOUND / "translation/ru/po").rglob("*.po"))
                      for e in read(path)[1]}
        samples = {"es": "Nombre", "de": "Name", "fr": "Nom"}
        with tempfile.TemporaryDirectory() as tmp, patch.object(
                Profile, "load_rom", side_effect=AssertionError("ROM access forbidden")):
            for code in CODES:
                with self.subTest(code=code):
                    project = registry.resolve(raw, code)
                    out = Path(tmp) / f"{code}.json"
                    with redirect_stdout(io.StringIO()) as output:
                        result = cli.main(["--project-root", str(UNBOUND), "--profile", str(raw.path), "--lang", code,
                                           "web", "data", "--no-rom", "--out", str(out)])
                    self.assertIn(result, (0, None))
                    doc = json.loads(out.read_text())
                    rows = [re.split(r" {2,}", row) for row in output.getvalue().splitlines()]
                    self.assertEqual([row for row in rows if row[0] == "status"], [["status", "written"]])
                    for heading, counts in (("state", Counter(e["status"] for e in doc["entries"])),
                                            ("reach", Counter(e["reach"]["class"] for e in doc["entries"]))):
                        start = rows.index([heading, "entries"]) + 1
                        self.assertEqual(rows[start:start + len(counts)],
                                         [[value, str(count)] for value, count in sorted(counts.items())])
                    self.assertNotIn("stage", doc)
                    marks = project.effective(raw)["policy_unverified"]
                    key = aliases.key   # the document names entries by key
                    self.assertEqual(doc["unverified"], {**marks, "window_width": [key(x) for x in marks["window_width"]]})
                    self.assertEqual(doc["check_rules"]["optional_tokens"], ["{PK}", "{MN}"])
                    entries = {aliases.entry_id(e["id"]): e for e in doc["entries"]}
                    self.assertEqual(set(entries), source_ids)
                    self.assertEqual({e["status"] for e in entries.values()}, {"untranslated", "approved", "nothing"})
                    guessed, known = entries["s0A4C61A"], entries["s1F81E44"]
                    self.assertTrue(guessed["window"]["sources"]["width"]["unverified"])
                    self.assertNotIn("unverified", known["window"]["sources"]["width"])
                    snapshot = snapshot_store.load(project.snapshot)
                    checker = editorsnapshot.checker(doc, snapshot["fonts"], doc["check_rules"], "0.0.0")
                    self.assertEqual(checker.check(known, samples[code])["problems"], [])
                    wide = [p["message"] for p in checker.check(guessed, "Ab " * 20)["problems"]]
                    self.assertTrue(wide and all(m.endswith(UNVERIFIED) for m in wide if "line too wide" in m), wide)
                    # typography reads the English the page takes from the ROM
                    self.assertEqual(checker.check(known, "No...")["unavailable"], ["typography", "glossary"])
                    text = {**known, "source_text": load(ENGLISH)[known["id"]].msgid}
                    dots = [p["message"] for p in checker.check(text, "No...")["problems"]]
                    self.assertEqual(dots, ["typography: three dots: use the ellipsis character …"])

    def test_empty_catalogs_build_verified_keyboards_without_font_edits(self):
        raw = Profile.by_name(PROFILE)
        base = raw.load_rom(rom_path())
        fonts = FontTable.from_profile(raw)
        inventory = json.loads((UNBOUND / "build/inventory.json").read_text())
        source = {e["id"]: e for e in inventory["entries"]}
        registry = Registry.load(UNBOUND)
        inventory_bytes = (UNBOUND / "build/inventory.json").read_bytes()
        source_bytes = (UNBOUND / "build/catalog.pot").read_bytes()
        for code in CODES:
            with self.subTest(code=code), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                project = registry.resolve(raw, code)
                shutil.copytree(project.translation, root / "translation")
                (root / "projects.toml").write_text(
                    f'[defaults]\nprofile = "{raw.name}"\nlanguage = "{code}"\n\n[[project]]\n'
                    f'profile = "{raw.name}"\nlanguage = "{code}"\nroot = "."\npolicy = "translation/policy.toml"\n',
                    encoding="utf-8")
                copy_aliases(root)
                (root / "build").mkdir()
                (root / "build/inventory.json").write_bytes(inventory_bytes)
                (root / "build/catalog.pot").write_bytes(source_bytes)
                args = ["--rom", str(rom_path()), "--project-root", str(root), "--profile", str(raw.path), "--lang", code]
                with redirect_stdout(io.StringIO()) as output:
                    self.assertEqual(cli.main(args + ["build", "rom"]), 0)
                report = output.getvalue()
                self.assertIn("verified     passed", report)
                profile = Registry.load(root).resolve(raw, code).effective(raw)
                entry_id = keys.for_profile(raw).entry_id   # the catalog names entries by key
                entries = {entry_id(e.msgctxt): e for path in (root / "translation/po").rglob("*.po")
                           for e in read(path)[1]}
                owned = {sid for sid in keyboard.owned_entries(profile) if sid in entries}
                report_doc = (root / "build" / "build-report.md").read_text(encoding="utf-8")
                self.assertIn(f"| catalog: untranslated | {len(entries) - len(owned)} |", report_doc)
                self.assertIn(f"| catalog: included | {len(owned)} |", report_doc)
                self.assertIn(f"| catalog: approved | {len(owned)} |", report_doc)
                self.assertNotIn("| catalog: translated |", report_doc)
                stem = build_names(raw, code, root / "translation/release.toml").output
                self.assertEqual(stem, f"Pokemon Unbound 2.1.1.1 [{code.upper()} v0.0.0 by gen3tl]")
                built = Rom.load(root / "build" / f"{stem}.gba")
                metadata = json.loads((root / "build" / f"{stem}.project.json").read_text())
                self.assertNotIn("stage", metadata)
                kb = profile["keyboard"]; pack = LangPack.load(code); cm = pack.charmap()
                self.assertEqual(pack.base_problems(base, fonts), [])
                self.assertEqual(keyboard.verify(built, kb, keyboard.plan(kb, base, built)), [])
                for font in fonts:
                    self.assertEqual(font.all_bytes(base), font.all_bytes(built))
                english = load(root / "build" / "catalog.pot")
                for key, sid in kb["row_bindings"].items():
                    entry = source[sid]
                    self.assertEqual(english[entries[sid].msgctxt].msgid, entry["text"])
                    if entry["kind"] == "fixed":
                        self.assertEqual(built.read(entry["offset"], entry["length"]), cm.encode(kb["rows"][key], False))
                    else:
                        target = built.ptr_at(entry["refs"][0]["at"])
                        self.assertEqual(cm.decode(built.data, target)[0], kb["rows"][key])
