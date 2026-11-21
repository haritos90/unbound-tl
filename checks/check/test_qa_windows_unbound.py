import tempfile
import unittest
from pathlib import Path
from unittest import mock

from gen3tl.check import qa
from gen3tl.lang.langpack import LangPack
from gen3tl.check.layout import Measure, check
from gen3tl.catalog.po import PoEntry, write

from rom_support import source_text, needs_rom, rom_path
from test_roots import PROJECT_ROOT as ROOT
import qa_support
from project_fixture import unbound
from qa_support import PACK, batch_messages, batch_project, setUpModule, tearDownModule

@needs_rom
class BoxWidthRegressionTest(unittest.TestCase):
    """Measured windows reject overflow that source-derived limits permit."""

    SIGN_LINE = "1234 " * 6 + "12345"
    RU = {"s1F6F1F9": SIGN_LINE + "\\nс уровнем допуска {COLOR 06}{STR_VAR_1}"
                      "{COLOR 02}.",
          "s1F6F244": "Чтобы открыть дверь, нужна Карта-ключ\\nс уровнем допуска {COLOR 06}{STR_VAR_1}"
                      "{COLOR 02}.\\pОткрыть?",
          "s08B84E0": "{B_ATK_NAME_WITH_PREFIX}: талант {B_ATK_ABILITY}!\\nПротивник от волнения не ест ягоды!"}

    @classmethod
    def setUpClass(cls):
        import copy

        from gen3tl.discover import inventory as inv_mod
        from gen3tl.build.font import FontTable
        from gen3tl.discover.context import build_context
        from gen3tl.profile.profile import Profile
        prof = unbound()
        rom = prof.load_rom(rom_path())
        inv = inv_mod.load(ROOT / "build" / "inventory.json")
        cls.ctx = build_context(rom, prof, inv)
        font = FontTable.from_profile(prof)[0]
        pack = LangPack.load("ru", prof["font_style"]["style"])
        slots = pack.glyph_slots(rom, font)
        cls.cm = pack.charmap()
        cls.m = Measure(lambda b: slots[b].width if b in slots else font.width(rom, b),
                        prof.get("layout", {}).get("placeholders", {}))
        by_id = {e["id"]: e for e in inv["entries"]}
        catalog = {sid: (Path("maps/shadow-base.po"), PoEntry(sid, by_id[sid]["text"], ru))
                   for sid, ru in cls.RU.items()}
        cls.boxes = prof["layout"]["box_width"]
        before = copy.deepcopy(prof.data)
        del before["layout"]["box_width"]
        cls.old = qa.compute_limits(before, inv, catalog, cls.m, cls.cm, cls.ctx, rom=rom)
        cls.new = qa.compute_limits(prof, inv, catalog, cls.m, cls.cm, cls.ctx, rom=rom)

    def test_measured_boxes(self):
        self.assertEqual(self.boxes, {"dialogue": 208, "sign": 208, "battle": 222})

    def test_limits_drop_to_the_box(self):
        self.assertEqual({sid: (lim.kind, lim.width) for sid, lim in self.old.items()},
                         {"s1F6F1F9": ("dialogue", 213), "s1F6F244": ("dialogue", 213), "s08B84E0": ("battle", 356)})
        self.assertEqual({sid: (lim.kind, lim.width) for sid, lim in self.new.items()},
                         {"s1F6F1F9": ("dialogue", 208), "s1F6F244": ("dialogue", 208), "s08B84E0": ("battle", 222)})
        uses = self.ctx["strings"]["s1F6F1F9"]["uses"]
        self.assertTrue(uses and all(u["event"] == "sign" for u in uses))

    def test_sign_line_over_the_box_is_rewrapped(self):
        from gen3tl.check.layout import check, entry_measure, layout, lines_of, paragraphs
        text, old, new = self.RU["s1F6F1F9"], self.old["s1F6F1F9"], self.new["s1F6F1F9"]
        line = self.SIGN_LINE
        self.assertEqual(self.m.width(line, self.cm), 210)
        self.assertLess(new.width, 210)
        self.assertLessEqual(210, old.width)
        # without box widths: the line fits and overruns the box
        self.assertEqual(layout(text, old, self.m, self.cm), text)
        self.assertEqual(check(text, old, self.m, self.cm), [])
        # with box widths: too wide as written; the layout rewraps
        self.assertEqual(check(text, new, self.m, self.cm), ["line too wide: 210 > 208 px: " + repr(line)])
        laid = layout(text, new, self.m, self.cm)
        self.assertEqual(check(laid, new, self.m, self.cm), [])
        me = entry_measure(self.m, new)
        self.assertTrue(all(me.width(l, self.cm) <= 208 for par in paragraphs(laid) for l in lines_of(par)))


@needs_rom
class MissionLogWindowTest(unittest.TestCase):
    """The profile's Mission Log window: 200 px, 3 lines."""

    LINES = {"s1EE55DE": 3,   # type 0
             "s1F073B6": 3,   # type 1, stage list
             "s1F06B1D": 2,   # type 2, No Survivors
             "s1F07E7E": 2,   # type 2, count 300
             "s1F0921E": 2,   # type 2, count 1000000
             "s1EEDAA2": 3,   # type 3
             "s1EF155B": 2,   # type 4
             "s1EF1910": 3,   # type-4 hint
             "s1FAFEE7": 3,   # Too Much TV hint
             "s1F563ED": 3,   # main story
             "s1F560DA": 3,   # reward waits
             "s1F85B56": 3}   # special hint

    @classmethod
    def setUpClass(cls):
        from gen3tl.discover import inventory as inv_mod
        from gen3tl.profile.profile import Profile
        prof = unbound()
        rom = prof.load_rom(rom_path())
        inv = inv_mod.load(ROOT / "build" / "inventory.json")
        by_id = {e["id"]: e for e in inv["entries"]}
        catalog = {sid: (Path("system/missions.po"), PoEntry(sid, by_id[sid]["text"], "")) for sid in cls.LINES}
        cls.limits = qa.compute_limits(prof, inv, catalog, Measure(lambda b: 6, {}), PACK.charmap(), rom=rom)
        rules = [r for r in prof["layout"]["record_window"] if r["name"] == "mission-log"]
        ats = {at for at, _, _ in qa.window_texts({"record_window": rules}, rom)}
        cls.reached = {e["id"] for e in inv["entries"] if any(r["at"] in ats for r in e["refs"])}

    def test_limits(self):
        self.assertEqual({sid: (l.kind, l.width, l.lines) for sid, l in self.limits.items()},
                         {sid: ("multiline", 200, n) for sid, n in self.LINES.items()})

    def test_the_records_reach_every_description_and_hint(self):
        self.assertEqual(len(self.reached), 559)

    def test_counts_take_the_digits_of_their_record(self):
        # 6 px per digit; FD 02 is {STR_VAR_1}
        self.assertEqual({sid: self.limits[sid].placeholders for sid in ("s1EEDAA2", "s1F07E7E", "s1F0921E")},
                         {"s1EEDAA2": {"B_COPY_VAR_1": 6}, "s1F07E7E": {"B_COPY_VAR_1": 18},
                          "s1F0921E": {"STR_VAR_1": 42}})


@needs_rom
class MoveDescriptionWindowTest(unittest.TestCase):
    """Move-description windows: the narrowest window binds."""

    LIMITS = {"s048305C": (118, 5),   # Tackle: summary and relearner
              "s0486EBE": (118, 4),   # Focus Punch: also TM01 in the TM Case
              "s0EB8D15": (142, 4),   # a description only TM items point at
              "s0A3BE9D": (118, 4)}   # Infestation, TM100 in the TM mart

    @classmethod
    def setUpClass(cls):
        from gen3tl.discover import inventory as inv_mod
        from gen3tl.profile.profile import Profile
        prof = unbound()
        rom = prof.load_rom(rom_path())
        inv = inv_mod.load(ROOT / "build" / "inventory.json")
        by_id = {e["id"]: e for e in inv["entries"]}
        catalog = {sid: (Path("system/moves.po"), PoEntry(sid, by_id[sid]["text"], "")) for sid in cls.LIMITS}
        cls.limits = qa.compute_limits(prof, inv, catalog, Measure(lambda b: 6, {}), PACK.charmap(), rom=rom)
        cls.rules = {t["name"]: t for t in prof["layout"]["table_window"]}

        def shown(*names):
            ats = {at for at, _, _ in qa.window_texts({"table_window": [cls.rules[n] for n in names]})}
            return {e["id"] for e in inv["entries"] if any(r["at"] in ats for r in e["refs"])}
        cls.moves = shown("move-descriptions-summary")
        cls.tms = shown("tm-descriptions", "tm-descriptions-2")
        cls.mart = shown("tm-move-descriptions")   # the TM mart prints these

    def test_measured_windows(self):
        self.assertEqual({n: (self.rules[n]["width"], self.rules[n]["lines"]) for n in
                          ("move-descriptions-summary", "move-descriptions-relearner", "tm-descriptions",
                           "tm-descriptions-2")},
                         {"move-descriptions-summary": (118, 6), "move-descriptions-relearner": (119, 5),
                          "tm-descriptions": (142, 4), "tm-descriptions-2": (142, 4)})

    def test_limits(self):
        self.assertEqual({sid: (l.kind, l.width, l.lines) for sid, l in self.limits.items()},
                         {sid: ("multiline", w, n) for sid, (w, n) in self.LIMITS.items()})

    def test_strings_shown(self):
        self.assertEqual((len(self.moves), len(self.tms), len(self.tms - self.moves)), (767, 128, 11))
        self.assertEqual((len(self.mart), len(self.mart - self.moves)), (128, 0))   # all summary texts too


@needs_rom
class TypeNameWindowTest(unittest.TestCase):
    """The types_short window: 64 px, 7-byte field."""

    NAMES = {"types_short:0": ("Normal", "Обычный", ["field overflow: 7 > 6 characters"]),
             "types_short:1": ("Fight", "Боевой", []),
             "types_short:17": ("Dark", "Тёмный", [])}

    def test_limits_and_full_names(self):
        from gen3tl.discover import inventory as inv_mod
        from gen3tl.check.layout import check
        from gen3tl.profile.profile import Profile
        prof = unbound()
        inv = inv_mod.load(ROOT / "build" / "inventory.json")
        catalog = {sid: (Path("tables/types_short.po"), PoEntry(sid, en, ""))
                   for sid, (en, _, _) in self.NAMES.items()}
        m, cm = Measure(lambda b: 6, {}), PACK.charmap()
        lims = qa.compute_limits(prof, inv, catalog, m, cm, rom=prof.load_rom(rom_path()))
        self.assertEqual({sid: (l.kind, l.width, l.chars) for sid, l in lims.items()},
                         {sid: ("field", 64, 6) for sid in self.NAMES})
        self.assertEqual({sid: check(ru, lims[sid], m, cm) for sid, (_, ru, _) in self.NAMES.items()},
                         {sid: probs for sid, (_, _, probs) in self.NAMES.items()})

    def test_types_table(self):
        """The main types table, 60 px of room in its narrowest host line."""
        from gen3tl.discover import inventory as inv_mod
        from gen3tl.check.layout import check
        from gen3tl.profile.profile import Profile
        prof = unbound()
        inv = inv_mod.load(ROOT / "build" / "inventory.json")
        names = {"types:1": ("Fight", "Боевой"), "types:17": ("Dark", "Тёмный")}
        catalog = {sid: (Path("tables/types.po"), PoEntry(sid, en, "")) for sid, (en, _) in names.items()}
        m, cm = Measure(lambda b: 6, {}), PACK.charmap()
        lims = qa.compute_limits(prof, inv, catalog, m, cm, rom=prof.load_rom(rom_path()))
        self.assertEqual({sid: (l.kind, l.width, l.chars) for sid, l in lims.items()},
                         {sid: ("field", 60, 6) for sid in names})
        self.assertEqual({sid: check(ru, lims[sid], m, cm) for sid, (_, ru) in names.items()},
                         {sid: [] for sid in names})

    def test_union_room_list(self):
        """Items 1-16 of the wanted-type list take its 64 px; Exit, shared, does not."""
        from gen3tl.discover import inventory as inv_mod
        from gen3tl.profile.profile import Profile
        prof = unbound()
        inv = inv_mod.load(ROOT / "build" / "inventory.json")
        names = {"s024F1A7": "FIGHT", "s024F217": "DARK", "s0459360": "Exit"}
        catalog = {sid: (Path("system/table-0456E7C.po"), PoEntry(sid, en, "")) for sid, en in names.items()}
        lims = qa.compute_limits(prof, inv, catalog, Measure(lambda b: 6, {}), PACK.charmap(), rom=prof.load_rom(rom_path()))
        self.assertEqual(lims["s024F1A7"].width, 64)
        self.assertEqual(lims["s024F217"].width, 64)
        self.assertNotEqual(lims["s0459360"].width, 64)


@needs_rom
class RegionWindowTest(unittest.TestCase):
    """Windows of the 0A40000 region texts."""

    # id -> (kind, width, lines, chars, style)
    LIMITS = {
        "s0A4AB8E": ("battle", 222, 2, None, None),           # battle string loader
        "s0A4C88B": ("battle", 222, 2, None, None),           # team label, window 0
        "s0A4E664": ("battle", 222, 2, None, None),           # slide table 0xA6D2C8
        "s0A4C5F6": ("single", 115, 1, 15, None),             # status word, 16-byte buffer
        "s0A4E0C3": ("dialogue", 224, 2, None, None),         # party limit table
        "s0A4D0BF": ("dialogue", 224, 2, None, None),         # boot warning
        "s0A4D8A4": ("dialogue", 238, 5, None, None),        # whiteout window
        "s0A4C86D": ("multiline", 110, 2, None, None),        # raid catch prompt
        "s0A4E474": ("multiline", 80, 3, None, "unbound-small"),
        "s0A4CB72": ("single", 128, 1, None, "unbound-small"),
        "s0A4E4BF": ("single", 76, 1, None, None),            # start menu
    }

    def test_limits(self):
        from gen3tl.discover import inventory as inv_mod
        from gen3tl.profile.profile import Profile
        prof = unbound()
        inv = inv_mod.load(ROOT / "build" / "inventory.json")
        by_id = {e["id"]: e for e in inv["entries"]}
        catalog = {sid: (Path("system/region-0A40000.po"), PoEntry(sid, by_id[sid]["text"], ""))
                   for sid in self.LIMITS}
        lims = qa.compute_limits(prof, inv, catalog, Measure(lambda b: 6, {}), PACK.charmap(), rom=prof.load_rom(rom_path()))
        self.assertEqual({sid: (l.kind, l.width, l.lines, l.chars, l.style) for sid, l in lims.items()},
                         self.LIMITS)


@needs_rom
class FormCategoryCharsTest(unittest.TestCase):
    """The Pokedex page copies at most 11 characters of a category."""

    SID = "s166A8E1"   # High King, table 0x1A3544C

    def setUp(self):
        import json
        import os

        from gen3tl.discover import inventory as inv_mod
        inv = inv_mod.load(ROOT / "build" / "inventory.json")
        e = next(x for x in inv["entries"] if x["id"] == self.SID)
        self.assertEqual(e["text"], source_text('s166A8E1'))
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.cwd = os.getcwd()
        os.chdir(self.root)
        project = batch_project(self.root)
        (self.root / "build").mkdir()
        (self.root / "build" / "inventory.json").write_text(json.dumps({"profile": inv["profile"], "rom_sha1": inv["rom_sha1"], "entries": [e]}), encoding="utf-8")
        write(self.root / "po" / "a.po", [PoEntry(self.SID, e["text"], "")],
              {"Project-Id-Version": "unbound-2.1.1.1", "Language": "ru"})
        project.translation.mkdir(parents=True)
        project.release.write_text('version = "0.1.0"\n', encoding="utf-8")
        self.batch = project.batches / "t"
        self.batch.mkdir(parents=True)
        (self.batch / "source.json").write_text(json.dumps([{"id": self.SID, "source_text": e["text"]}]),
                                                encoding="utf-8")

    def tearDown(self):
        import os
        os.chdir(self.cwd)
        self.tmp.cleanup()

    def check(self, ru: str) -> tuple[int, list[str]]:
        import json

        from gen3tl.__main__ import main
        (self.batch / "translation.json").write_text(json.dumps({self.SID: ru}, ensure_ascii=False),
                                                     encoding="utf-8")
        with mock.patch("builtins.print") as out:
            code = main(["--rom", str(rom_path()), "check", "batch", "t", "--po-root", "po"])
        return code, batch_messages(out)

    def test_twelve_characters_fit_the_width_not_the_limit(self):
        # the game font's width passes; only the characters fail
        code, lines = self.check("Король высот")
        self.assertEqual((code, [l for l in lines if l.startswith(self.SID)]),
                         (1, [f"{self.SID}: field overflow: 12 > 11 characters"]))
        code, lines = self.check("Король горы")
        self.assertEqual(code, 0, lines)


@needs_rom
class LabelWindowTest(qa_support.LabelWindowTest):
    pass
