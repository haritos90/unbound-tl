from pathlib import Path
import unittest
import tempfile
from unittest import mock

from gen3tl.check import qa
from gen3tl.check.layout import Measure
from gen3tl.check.provenance import formatted
from gen3tl.catalog.extract import english
from gen3tl.catalog.po import PoEntry, write

from rom_support import source_text, needs_rom, rom_path
from project_fixture import unbound
from qa_support import PACK, scripted, setUpModule, tearDownModule, batch_messages, batch_project
from test_roots import PROJECT_ROOT as ROOT

class QaGateTest(unittest.TestCase):
    def test_profile_centres_the_start_menu_labels(self):
        # start menu labels, centred in the 80 px window
        from gen3tl.profile.profile import Profile
        add = qa.addable_tokens(unbound()["qa"])
        ids = ["s041627D", "s04162A2", "s041629D", "s0A4E4B8", "s0A4E4BF", "s0A4E4D7", "s0A4E4E4", "s0A4E4EC",
               "s0A4E4F6"]
        for sid in ids:
            rule = add.get(sid, {}).get("{CLEAR_TO}", {})
            self.assertEqual((rule.get("window"), rule.get("x")), (80, 4), sid)
        self.assertNotIn("s0A4E4CB", add)   # Costume Box fills the window

    def test_profile_marks_the_mining_results(self):
        # s1F8220B and s1F8221D, the article slot of the mining results
        from gen3tl.profile.profile import Profile
        drop = qa.droppable_tokens(unbound()["qa"])
        self.assertEqual({sid: drop.get(sid) for sid in ("s1F8220B", "s1F8221D")},
                         {"s1F8220B": {"{B_COPY_VAR_2}"}, "s1F8221D": {"{B_COPY_VAR_2}"}})

class ControlOnlyFillTest(unittest.TestCase):
    def test_profile_names_only_verified_colour_hosts(self):
        from gen3tl.profile.profile import Profile

        prof = unbound()
        rules = [r for r in prof["layout"]["code_fill"]
                 if "s1F99574" in r.get("ids", []) and "FD 07" in r["slots"]]
        self.assertEqual(len(rules), 1)
        rule = rules[0]
        self.assertEqual(set(rule["ids"]), {
            "s1F90F9C", "s1F91096", "s1F911A0", "s1F91296", "s1F921A0", "s1F921DE", "s1F9221F",
            "s1F922E7", "s1F9231D", "s1F9952A", "s1F9954C", "s1F99574", "s1F995D1", "s1F9B245"})
        self.assertEqual(rule["slots"], {"FD 07": {"width": 0}, "B_PLAYER_MON2_NAME": {"width": 0}})
        fills = qa.code_fills(prof["layout"])
        known = qa.fill_slots("s1F99574", "{FD 07}", {"refs": []}, fills, 6)
        alias = qa.fill_slots("s1F90F9C", "{B_PLAYER_MON2_NAME}", {"refs": []}, fills, 6)
        self.assertEqual((known["FD 07"].translated, known["FD 07"].source_width), (0, 0))
        self.assertEqual(alias["B_PLAYER_MON2_NAME"].translated, 0)
        self.assertEqual(qa.fill_slots("s1F56BEB", "{FD 07}", {"refs": []}, fills, 6)["FD 07"].translated, 60)
        self.assertEqual(qa.fill_slots("s1F8C8FD", "{FD 07}", {"refs": []}, fills, 6)["FD 07"].translated, 155)
        self.assertNotIn("unverified", formatted(qa.fill_slots("s1F8C8FD", "{FD 07}", {"refs": []}, fills, 6)["FD 07"].source))
        guessed = qa.fill_slots("s1F8C8FD", "{FD 07}", {"refs": []}, fills, 6, estimates=frozenset({"fill-19"}))
        self.assertIn("155 px, unverified estimate", formatted(guessed["FD 07"].source))

class FrontierPurchaseFillTest(unittest.TestCase):
    def test_numeric_fill_overrides_stale_scripted_words(self):
        from gen3tl.profile.profile import Profile

        prof = unbound()
        text = "{STR_VAR_1} items cost {STR_VAR_2}{FD 07}."
        ids = ("s1F99574", "s0000100")
        inv = {"entries": [scripted(sid, text) for sid in ids]
               + [scripted("s0000200", "BP.")]}
        rules = [r for r in prof["layout"]["code_fill"] if "s1F99574" in r.get("ids", [])]
        prof = {"layout": {"code_fill": rules, "window_width": {sid: 208 for sid in ids}}}
        ctx = {"strings": {sid: {"slots": {
            "{STR_VAR_1}": {"fills": [["number", None]], "uses": 1, "unfilled": 0},
            "{STR_VAR_2}": {"fills": [["string", "s0000200"]], "uses": 1, "unfilled": 0}},
            "slot_refs": {"unwalked": 0, "code": 0}} for sid in ids}}
        rows = {e["id"]: (Path("a.po"), PoEntry(e["id"], e["text"], e["text"]))
                for e in inv["entries"]}
        for english in (False, True):
            limits = qa.compute_limits(prof, inv, rows, Measure(lambda b: 6, {}), PACK.charmap(),
                                       ctx, english_slots=english)
            self.assertEqual(limits[ids[0]].placeholders,
                             {"STR_VAR_1": 18, "STR_VAR_2": 30, "FD 07": 0})
            self.assertEqual(limits[ids[1]].placeholders, {"STR_VAR_1": 30, "STR_VAR_2": 18})
            self.assertIn("number of 3 digits", formatted(limits[ids[0]].slot_sources["STR_VAR_1"]))
            self.assertIn("number of 5 digits", formatted(limits[ids[0]].slot_sources["STR_VAR_2"]))


@needs_rom
class BatchCheckTypographyTest(unittest.TestCase):
    """check batch and check qa judge s1EDD100 alike."""


    def setUp(self):
        import json
        import os

        from gen3tl.discover import inventory as inv_mod
        inv = inv_mod.load(ROOT / "build" / "inventory.json")
        e = next(x for x in inv["entries"] if x["id"] == "s1EDD100")
        self.VROOM = source_text("s1EDD100")
        self.assertEqual(e["text"], self.VROOM)
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.cwd = os.getcwd()
        os.chdir(self.root)
        project = batch_project(self.root)
        (self.root / "build").mkdir()
        (self.root / "build" / "inventory.json").write_text(json.dumps({"profile": inv["profile"], "rom_sha1": inv["rom_sha1"], "entries": [e]}), encoding="utf-8")
        write(self.root / "po" / "a.po", [PoEntry("s1EDD100", self.VROOM, "")],
              {"Project-Id-Version": "unbound-2.1.1.1", "Language": "ru"})
        project.translation.mkdir(parents=True)
        project.release.write_text('version = "0.1.0"\n', encoding="utf-8")
        self.batch = project.batches / "t"
        self.batch.mkdir(parents=True)
        (self.batch / "source.json").write_text(json.dumps([{"id": "s1EDD100", "source_text": self.VROOM}]),
                                                encoding="utf-8")

    def tearDown(self):
        import os
        os.chdir(self.cwd)
        self.tmp.cleanup()

    def check(self, ru: str) -> tuple[int, list[str]]:
        import json

        from gen3tl.__main__ import main
        (self.batch / "translation.json").write_text(json.dumps({"s1EDD100": ru}, ensure_ascii=False),
                                                     encoding="utf-8")
        with mock.patch("builtins.print") as out:
            code = main(["--rom", str(rom_path()), "check", "batch", "t", "--po-root", "po"])
        return code, batch_messages(out)

    def test_typography(self):
        code, lines = self.check("  ВРУМ   ВРУМ\\pЧёрный Ферроторн!")
        self.assertEqual(code, 0, lines)
        self.assertFalse([l for l in lines if "typography" in l])
        code, lines = self.check("  ВРУМ   ВРУМ\\pЧёрный  Ферроторн!")
        self.assertEqual(code, 1)
        self.assertIn("s1EDD100: typography: double space", lines)
        code, lines = self.check("  ВРУМ   ВРУМ\\pЧёрный Ферроторн..." )
        self.assertIn("s1EDD100: typography: three dots: use the ellipsis character …", lines)

    def test_explicit_draft_states_reach_batch_checks(self):
        self.assertEqual(self.check({"translation": "", "state": "original"}), self.check(self.VROOM))
        self.assertEqual(self.check({"translation": "", "state": "empty"}), self.check(""))
        self.assertEqual(self.check({"translation": self.VROOM, "state": "text"}), self.check(self.VROOM))

    def test_never_shown_marker(self):
        # the catalog tag is a marker line and a count
        code, lines = self.check("  ВРУМ   ВРУМ\\pЧёрный Ферроторн!")
        self.assertEqual(lines[-4:], ["checked      1 entries", "errors       0 errors",
                                      "warnings     0 warnings", "never        0 entries"])
        tag = "reach: never shown (review: no caller)"
        write(self.root / "po" / "a.po", [PoEntry("s1EDD100", self.VROOM, "", extracted=[tag])],
              {"Project-Id-Version": "unbound-2.1.1.1", "Language": "ru"})
        code, lines = self.check("  ВРУМ   ВРУМ\\pЧёрный Ферроторн!")
        self.assertEqual(code, 0, lines)
        self.assertEqual(lines[-5:], [f"s1EDD100: {tag}", "checked      1 entries", "errors       0 errors",
                                      "warnings     0 warnings", "never        1 entries"])
        code, lines = self.check("  ВРУМ   ВРУМ\\pЧёрный  Ферроторн!")
        self.assertEqual(code, 1)
        self.assertEqual(lines[-7:], [f"s1EDD100: {tag}", "s1EDD100: typography: double space",
                                      "checked      1 entries", "errors       1 errors",
                                      "warnings     0 warnings", "never        1 entries",
                                      "result       failed: typography: double space"])


@needs_rom
class BatchCheckUnmeasuredTest(unittest.TestCase):
    """check batch marks a problem against an English-derived limit."""

    SID = "s044941B"

    def setUp(self):
        import json
        import os

        from gen3tl.discover import inventory as inv_mod
        inv = inv_mod.load(ROOT / "build" / "inventory.json")
        e = next(x for x in inv["entries"] if x["id"] == self.SID)
        self.source_text = e["text"]
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.cwd = os.getcwd()
        os.chdir(self.root)
        project = batch_project(self.root)
        (self.root / "build").mkdir()
        (self.root / "build" / "inventory.json").write_text(json.dumps({"profile": inv["profile"], "rom_sha1": inv["rom_sha1"], "entries": [e]}), encoding="utf-8")
        write(self.root / "po" / "a.po", [PoEntry(self.SID, self.source_text, "")],
              {"Project-Id-Version": "unbound-2.1.1.1", "Language": "ru"})
        project.translation.mkdir(parents=True)
        project.release.write_text('version = "0.1.0"\n', encoding="utf-8")
        self.batch = project.batches / "t"
        self.batch.mkdir(parents=True)
        (self.batch / "source.json").write_text(json.dumps([{"id": self.SID, "source_text": self.source_text}]),
                                                encoding="utf-8")

    def check(self, ru: str) -> tuple[int, list[str]]:
        import json

        from gen3tl.__main__ import main
        (self.batch / "translation.json").write_text(json.dumps({self.SID: ru}, ensure_ascii=False),
                                                     encoding="utf-8")
        with mock.patch("builtins.print") as out:
            code = main(["--rom", str(rom_path()), "check", "batch", "t", "--po-root", "po"])
        return code, batch_messages(out)

    def tearDown(self):
        import os
        os.chdir(self.cwd)
        self.tmp.cleanup()

    def test_unmeasured_mark(self):
        code, lines = self.check("Ж" * 50)
        self.assertEqual(code, 1)
        wide = [l for l in lines if l.startswith(f"{self.SID}: line too wide: ")]
        self.assertTrue(wide and all(l.endswith(" [unmeasured limit: the English width]") for l in wide), lines)
