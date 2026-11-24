import json
import shutil
import tempfile
import unittest
from pathlib import Path

from gen3tl.build.font import FontTable
from gen3tl.discover import emission, foundations
from gen3tl.profile import check, schema
from gen3tl.profile.profile import Profile, source_files

from rom_support import needs_rom, rom_path
from project_fixture import UNBOUND

@needs_rom
class ReferenceROMTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profile = Profile.by_name("unbound-2.1.1.1")
        path = rom_path()
        cls.rom = cls.profile.load_rom(path)
        inventory = UNBOUND / "build/inventory.json"
        cls.inventory = json.loads(inventory.read_text()) if inventory.is_file() else None
        cls.result = foundations.run(cls.rom, inventory=cls.inventory)
        cls.language_profiles = {code: cls.profile.for_project(code, UNBOUND)
                                 for code in ("ru", "es", "de", "fr")}

    def test_real_fingerprints_codec_and_five_font_bindings(self):
        selected, = [row for row in self.result.metadata["families"] if row["selected"]]
        self.assertEqual(selected["name"], "firered-cfru")
        self.assertEqual(selected["ratio"], 1)
        self.assertIn("extension", selected["categories"])
        self.assertTrue(selected["functions"]["hidden-ability"])
        self.assertEqual(self.result.metadata["codec"]["candidate"], "gen3-western")
        wanted = [{k: v for k, v in font.items() if k in emission.ROM_FONT_FIELDS} for font in self.profile["font"]]
        self.assertTrue(check.same(self.result.data["font"], wanted))
        actual_tables = FontTable.from_profile(self.result.data)
        reference_tables = FontTable.from_profile(self.profile)
        for actual, expected in zip(actual_tables, reference_tables):
            with self.subTest(font=actual.name):
                self.assertEqual(actual.all_bytes(self.rom), expected.all_bytes(self.rom))
        proofs = [proof for proof in self.result.facts if proof.kind == "font"]
        self.assertEqual(len(proofs), 5)
        self.assertTrue(all(p.evidence.anchors and p.evidence.code_sites and p.source != "overlay" for p in proofs))

    def test_free_slots_equal_current_allocation_and_blank_checks(self):
        self.assertIsNotNone(self.inventory, "generated inventory is required")
        from gen3tl.lang.langinit import _missing_slots
        slots = self.result.metadata["free_slots"]
        count = len(set(slots["candidates"]) - set(slots["used"]))
        current = _missing_slots(self.inventory, [str(index) for index in range(count)])
        self.assertEqual(slots["free"], sorted(current.values()))
        self.assertEqual(slots["status"], "candidate")
        self.assertEqual(slots["inventory_entries"], len(self.inventory["entries"]))
        self.assertIn("not whole-ROM", slots["scope"])
        for table in FontTable.from_profile(self.profile):
            for byte in slots["free"]:
                self.assertTrue(all(value in (0, 3) for row in table.glyph(self.rom, byte) for value in row))

    def test_script_table_and_all_compatibility_differences_are_reported(self):
        self.assertEqual(self.result.data["script"], {"command_table": 0x15F9B4, "command_table_end": 0x15FD08})
        self.assertTrue(self.result.metadata["scripts"]["table_verified"])
        self.assertTrue(self.result.metadata["scripts"]["readers_verified"])
        handlers = self.result.metadata["scripts"]["handlers"]
        counts = {status: sum(handler["status"] == status for handler in handlers)
                  for status in ("fixed", "shape", "variable", "unresolved")}
        self.assertEqual(sum(counts.values()), 213)
        self.assertEqual((counts["fixed"], counts["variable"]), (25, 2))
        self.assertGreaterEqual(counts["fixed"] + counts["shape"], 150)
        differences = self.result.metadata["scripts"]["comparison"]
        self.assertEqual([row["opcode"] for row in differences if row["status"] == "variable"], [0x5C, 0xB6])
        self.assertEqual(sum(row["status"] == "unresolved" for row in differences), counts["unresolved"])
        self.assertEqual([(row["opcode"], row["compatibility_length"], row["discovered_lengths"])
                          for row in differences if row["status"] in ("fixed", "shape")],
                         [(44, 5, [1]), (116, 5, [1]), (148, 3, [1]), (150, 3, [1]),
                          (177, 8, [1]), (179, 3, [5]), (211, 5, [1])])
        self.assertEqual(sum(issue.status == "unresolved" and issue.kind == "script-command"
                             for issue in self.result.issues), counts["unresolved"])
        proof = next(proof for proof in self.result.facts if proof.id == "script")
        self.assertEqual((proof.status, proof.tier), ("verified", "crossref"))
        for status, count in counts.items():
            self.assertEqual(dict(proof.evidence.counts)[status], count)
        self.assertTrue(all(h["assumptions"] and h["assumption_sites"]
                            for h in handlers if h["status"] == "shape"))
        self.assertTrue(all(issue.tier is None for issue in self.result.issues if issue.status == "unresolved"))

    def test_deterministic_profiles_keep_manual_style_and_all_language_policies(self):
        with tempfile.TemporaryDirectory() as temporary:
            outputs = [Path(temporary) / name / self.profile.name for name in ("first", "second")]
            for path in outputs:
                path.mkdir(parents=True)
                for source in schema.overlay_files(self.profile.path):
                    target = path / source.relative_to(self.profile.path)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, target)
                result = emission.write(self.result, path, self.profile.name, self.profile)
                self.assertEqual(result["comparison"]["raw_ROM_fonts_equal"], 5)
                self.assertEqual(result["comparison"]["full_merged_fonts_equal"], 5)
                self.assertEqual(result["comparison"]["retained_presentation_bindings"], [
                    {"font": "small", "field": "style", "value": "unbound-small", "source": "selected overlay configuration"}])
                loaded = Profile.load(path)
                self.assertEqual(loaded["script"]["command_table"], self.result.data["script"]["command_table"])
                self.assertEqual(loaded["script"]["command_table_end"], self.result.data["script"]["command_table_end"])
                self.assertTrue(check.same(loaded.data, self.profile.data))
                for language, expected in self.language_profiles.items():
                    self.assertTrue(check.same(loaded.for_project(language, UNBOUND).data, expected.data))
                checked = check.run(path)
                row = next(row for row in checked.sections if row.name == "font")
                self.assertEqual((row.generated, row.counts["reproduced"], row.counts["extends"]), (5, 4, 1))
                report = (path / "report.md").read_text()
                for binding in result["comparison"]["retained_presentation_bindings"]:
                    self.assertNotIn(binding["value"], report)
                self.assertNotIn("## Structured evidence", report)
                self.assertIn("## Structural discovery", report)
                if self.inventory:
                    self.assertIn("| Inventory digest |", report)
                self.assertLess(len(report.splitlines()), 200)
            for name in ("profile.toml", "discovery.json", "report.md"):
                self.assertEqual((outputs[0] / name).read_bytes(), (outputs[1] / name).read_bytes())
        inputs = source_files(self.profile.path)
        self.assertTrue({"engine.toml", "anchors.toml", "functions.json", "script.json"} <= {path.name for path in inputs})
        for path in inputs:
            if path.parent.name == "firered-cfru":
                self.assertNotRegex(path.read_text(), r"0x[0-9A-Fa-f]{5,}")
