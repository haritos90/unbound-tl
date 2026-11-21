from test_roots import TOOLKIT_ROOT
"""Qa tables checks and fixtures."""

import sys
from pathlib import Path
import tempfile
import unittest

sys.path.insert(0, str(TOOLKIT_ROOT / "src"))

from gen3tl.check import qa
from gen3tl.check.layout import Measure, check
from gen3tl.catalog.po import PoEntry, write

import qa_support
from qa_support import PACK, fixed, setUpModule, tabled, tearDownModule


class TableWindowTest(qa_support.TableWindowTest, unittest.TestCase):
    def test_loaded_window_spacing_measures_icons_and_overrides_kind(self):
        from gen3tl.profile.profile import Profile
        from gen3tl.check.layout import entry_measure, line_width
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "profile.toml"
            path.write_text('''[layout.icon_letter_spacing]
single = 1
[[layout.table_window]]
name = "descriptions"
base = 4096
stride = 4
count = 2
width = 30
letter_spacing = 2
evidence = "The printer stores two pixels of spacing."
[[layout.table_window]]
name = "hints"
base = 8192
stride = 4
count = 2
width = 28
letter_spacing = 0
evidence = "The printer stores zero spacing."
''')
            prof = Profile.load(path)
            inv = {"entries": [tabled("s0000100", "a{F8 00}{F8 03}", 0x1000),
                               tabled("s0000200", "a{F8 00}", 0x2000),
                               tabled("s0000300", "a{F8 00}", 0x1004, 0x2004),
                               tabled("s0000400", "a{F8 00}", 0x3000)]}
            catalog = {e["id"]: (root / "a.po", PoEntry(e["id"], e["text"], "")) for e in inv["entries"]}
            measure = Measure(lambda b: 6, {"F8 00": 8, "F8 03": 16})
            limits = qa.compute_limits(prof, inv, catalog, measure, PACK.charmap())
        self.assertEqual([limits[e["id"]].icon_spacing for e in inv["entries"]], [2, 0, 2, 1])
        self.assertEqual(limits["s0000300"].width, 28)
        self.assertEqual(line_width("a{F8 00}{F8 03}", entry_measure(measure, limits["s0000100"]),
                                    PACK.charmap()), 34)
        self.assertEqual(limits["s0000100"].sources["icon_spacing"]["evidence"],
                         "The printer stores two pixels of spacing.")

    def test_invalid_window_spacing(self):
        for spacing in (-1, 256, 1.5, True, "2"):
            with self.subTest(spacing=spacing), self.assertRaisesRegex(ValueError, "letter_spacing"):
                qa.window_icon_spacings({"table_window": [dict(self.PROF["layout"]["table_window"][0],
                                                              letter_spacing=spacing)]})

    def test_limits(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / "system" / "a.po", [PoEntry(x["id"], x["text"], "") for x in self.INV["entries"]], {})
            from gen3tl.catalog.catalog import load_catalog
            lim = qa.compute_limits(self.PROF, self.INV, load_catalog(root), Measure(lambda b: 6, {}),
                                    PACK.charmap())
        self.assertEqual({sid: (l.kind, l.width, l.lines) for sid, l in lim.items()}, {
            "s0000100": ("single", 30, 1), "s0000200": ("single", 30, 1), "s0000300": ("single", 60, 1),
            "s0000400": ("single", 30, 1), "s0000500": ("single", 24, 1), "s0000600": ("single", 36, 1)})

    def test_gate_reports_a_line_over_the_window(self):
        inv = {"entries": self.INV["entries"][:2]}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / "system" / "a.po", [PoEntry("s0000100", "Ab", "Абвгд"),        # 30 px: fits
                                             PoEntry("s0000200", "Abc", "Абвгде")], {})  # 36 px
            gate = qa.run(self.PROF, inv, root, PACK.charmap(), Measure(lambda b: 6, {}), set(PACK.glyph_slots()))
        self.assertEqual([(f.id, f.severity, f.message) for f in gate.findings],
                         [("s0000200", "error", "line too wide: 36 > 30 px: 'Абвгде'")])

    def test_english_over_the_window_is_a_warning(self):
        # the original overflows the window too.
        # warning for English, error for an equally wide translation.
        inv = {"entries": [tabled("s0000100", "Ab", 0x1000), tabled("s0000200", "Abcdef", 0x1008)]}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / "system" / "a.po", [PoEntry("s0000100", "Ab", "Аб"),
                                             PoEntry("s0000200", "Abcdef", "Абвгде")], {})   # both 36 px
            runs = {mode: qa.run(self.PROF, inv, root, PACK.charmap(), Measure(lambda b: 6, {}),
                                 set(PACK.glyph_slots()), source_as_translation=mode) for mode in (True, False)}
        self.assertEqual([(f.id, f.severity, f.message) for f in runs[True].findings],
                         [("s0000200", "warning", "line too wide: 36 > 30 px: 'Abcdef'")])
        self.assertEqual(runs[True].errors, 0)
        self.assertEqual([(f.id, f.severity, f.message) for f in runs[False].findings],
                         [("s0000200", "error", "line too wide: 36 > 30 px: 'Абвгде'")])

    def test_window_lines_make_a_fixed_window_text(self):
        # a table_window with lines
        prof = {"layout": {"table_window": [dict(self.PROF["layout"]["table_window"][0], lines=3)]}}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / "system" / "a.po", [PoEntry("s0000100", "Ab", "")], {})
            from gen3tl.catalog.catalog import load_catalog
            lim = qa.compute_limits(prof, {"entries": [tabled("s0000100", "Ab", 0x1000)]}, load_catalog(root),
                                    Measure(lambda b: 6, {}), PACK.charmap())["s0000100"]
        self.assertEqual((lim.kind, lim.width, lim.lines), ("multiline", 30, 3))

    def test_window_chars_limit_the_characters(self):
        # the printing code copies 11 characters; 12 fit the width
        cats = {"name": "cats", "base": 0x3000, "stride": 8, "count": 2, "fields": [4], "width": 111, "chars": 11}
        prof = {"layout": {"table_window": [cats, dict(cats, name="few", count=1, chars=9)]}}
        inv = {"entries": [tabled("s0000100", "Ab", 0x3004), tabled("s0000200", "Abc", 0x300C),
                           tabled("s0000300", "Abcd", 0x1000)]}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / "system" / "a.po", [PoEntry("s0000100", "Ab", "Абвгд"),            # 5: fits the least
                                             PoEntry("s0000200", "Abc", "Абвгдежзийкл"),     # 12, 72 px
                                             PoEntry("s0000300", "Abcd", "Абвг")], {})       # no rule
            from gen3tl.catalog.catalog import load_catalog
            lim = qa.compute_limits(prof, inv, load_catalog(root), Measure(lambda b: 6, {}), PACK.charmap())
            gate = qa.run(prof, inv, root, PACK.charmap(), Measure(lambda b: 6, {}), set(PACK.glyph_slots()))
        self.assertEqual({sid: (l.width, l.chars) for sid, l in lim.items() if sid != "s0000300"},
                         {"s0000100": (111, 9), "s0000200": (111, 11)})
        self.assertIsNone(lim["s0000300"].chars)
        self.assertEqual([(f.id, f.severity, f.message) for f in gate.findings],
                         [("s0000200", "error", "field overflow: 12 > 11 characters")])


class TrailingSpaceWidthTest(unittest.TestCase):
    """The English width behind a limit leaves out trailing spaces."""

    # descriptions: widest 36 px, padded 78 px.
    # labels: widest 18 px, padded 60 px; leading spaces count.
    INV = {"entries": [tabled("s0000100", "Abcdef\\nAb", 0x2000),
                       tabled("s0000200", "Abcd\\nAbc          ", 0x2004),
                       tabled("s0000300", "Abc", 0x1000),
                       tabled("s0000400", "Ab        ", 0x1004),
                       tabled("s0000500", "   Ab", 0x3000)]}

    def test_padding_does_not_widen_the_table(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / "system" / "a.po", [PoEntry(x["id"], x["text"], "") for x in self.INV["entries"]], {})
            from gen3tl.catalog.catalog import load_catalog
            lim = qa.compute_limits({}, self.INV, load_catalog(root), Measure(lambda b: 6, {}), PACK.charmap())
        self.assertEqual({sid: (l.kind, l.width, l.lines) for sid, l in lim.items()}, {
            "s0000100": ("multiline", 36, 2), "s0000200": ("multiline", 36, 2), "s0000300": ("single", 18, 1),
            "s0000400": ("single", 18, 1), "s0000500": ("single", 30, 1)})

    def test_gate_reports_a_line_as_wide_as_the_padding(self):
        inv = {"entries": self.INV["entries"][:2]}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / "system" / "a.po", [PoEntry("s0000100", "Abcdef\\nAb", "Абвгде\\nАб"),           # 36 px
                                             PoEntry("s0000200", "Abcd\\nAbc          ", "Аб\\nАбвгдежз")],  # 48 px
                  {})
            gate = qa.run({}, inv, root, PACK.charmap(), Measure(lambda b: 6, {}), set(PACK.glyph_slots()))
        self.assertEqual([(f.id, f.severity, f.message) for f in gate.findings],
                         [("s0000200", "error", "line too wide: 48 > 36 px: 'Абвгдежз'")])


def mission_rom():
    """Mission Log style records: pointer table, typed sub-records."""
    from gen3tl.core.rom import Rom
    data = bytearray(0x1000)

    def ptr(at, off):
        data[at:at + 4] = (0x08000000 + off).to_bytes(4, "little")
    for i, rec in enumerate([0x200, 0x300, 0x400, 0x500]):
        ptr(0x100 + 4 * i, rec)
    data[0x20B] = 0
    ptr(0x20C, 0x800)
    data[0x30B] = 2
    ptr(0x30C, 0x310)
    data[0x314:0x318] = (300).to_bytes(4, "little")   # the type-2 count target
    ptr(0x318, 0x810)
    data[0x40B] = 4
    ptr(0x40C, 0x410)
    ptr(0x410, 0x820)
    for k, flag in enumerate([1, 2]):
        e = 0x414 + 16 * k
        ptr(e, 0x830)
        ptr(e + 4, 0x840 + 16 * k)
        data[e + 8:e + 10] = flag.to_bytes(2, "little")
    data[0x50B] = 1
    ptr(0x50C, 0x510)
    ptr(0x510, 0x860)
    ptr(0x514, 0x870)
    return Rom(data)


class RecordWindowTest(unittest.TestCase):
    """Mission Log texts in their measured window ([[layout.record_window]])."""

    RULE = {"name": "log", "table": 0x100, "count": 5, "type_at": 0xB, "width": 120, "lines": 3, "texts": [
        {"types": [0], "path": [0xC]},
        {"types": [1], "path": [0xC, 0], "stride": 4},
        {"types": [2], "path": [0xC, 8], "lines": 2},
        {"types": [4], "path": [0xC, 0], "lines": 2},
        {"types": [4], "path": [0xC, 4], "stride": 16, "field": 4, "end": 8}]}
    PROF = {"layout": {"record_window": [RULE]}}
    # s0000400 is no window text; English sets run width
    INV = {"entries": [tabled("s0000100", "Beat all the leaders\\nin the marathon!", 0x20C),
                       tabled("s0000200", "Heal at the Centers\\nthree hundred times.", 0x318),
                       tabled("s0000300", "Found on Route 5.", 0x418),
                       tabled("s0000400", "Abcdefghij abcdefghij abcdefgh\\nAb", 0x900)]}
    # 49 characters: 2 lines at 180 px, 3 at 120
    HEAL = "Полечиться в Центрах покемонов\\nтриста раз за день."

    def limits(self, prof, ru=None):
        from gen3tl.catalog.catalog import load_catalog
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / "system" / "a.po", [PoEntry(x["id"], x["text"], (ru or {}).get(x["id"], ""))
                                             for x in self.INV["entries"]], {})
            return qa.compute_limits(prof, self.INV, load_catalog(root), Measure(lambda b: 6, {}), PACK.charmap(),
                                     rom=mission_rom())

    def test_walk(self):
        self.assertEqual(sorted(qa.window_texts(self.PROF["layout"], mission_rom())), [
            (0x20C, 120, 3), (0x318, 120, 2), (0x410, 120, 2), (0x418, 120, 3), (0x428, 120, 3),
            (0x510, 120, 3), (0x514, 120, 3)])

    def test_rules_need_the_rom(self):
        with self.assertRaises(ValueError):
            qa.window_texts(self.PROF["layout"])

    def test_limits(self):
        old, new = self.limits({"layout": {}}), self.limits(self.PROF)
        self.assertEqual({sid: (l.kind, l.width, l.lines) for sid, l in old.items()}, {
            "s0000100": ("multiline", 180, 2), "s0000200": ("multiline", 180, 2), "s0000300": ("single", 102, 1),
            "s0000400": ("multiline", 180, 2)})
        self.assertEqual({sid: (l.kind, l.width, l.lines) for sid, l in new.items()}, {
            "s0000100": ("multiline", 120, 3), "s0000200": ("multiline", 120, 2), "s0000300": ("multiline", 120, 3),
            "s0000400": ("multiline", 180, 2)})

    def test_description_over_the_window(self):
        # fits the English run width, not the window
        from gen3tl.check.layout import check, layout
        cm, m = PACK.charmap(), Measure(lambda b: 6, {})
        old = self.limits({"layout": {}})["s0000200"]
        new = self.limits(self.PROF)["s0000200"]
        self.assertEqual(check(layout(self.HEAL, old, m, cm), old, m, cm), [])
        self.assertEqual(check(layout(self.HEAL, new, m, cm), new, m, cm), ["too many lines: 3 > 2"])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / "system" / "a.po", [PoEntry(x["id"], x["text"], self.HEAL if x["id"] == "s0000200" else "")
                                             for x in self.INV["entries"]], {})
            gate = qa.run(self.PROF, self.INV, root, cm, m, set(PACK.glyph_slots()), rom=mission_rom())
        self.assertEqual([(f.id, f.severity, f.message) for f in gate.findings],
                         [("s0000200", "error", "too many lines: 3 > 2")])

    def test_count_takes_the_digits_of_its_record(self):
        # target 300 fills {B_COPY_VAR_1}: 3 digits, 18 px
        from gen3tl.catalog.catalog import load_catalog
        from gen3tl.check.layout import check, dropped_breaks, layout
        number = {"slots": ["STR_VAR_1", "B_COPY_VAR_1"], "path": [0xC, 4], "bytes": 4}
        with_number = dict(self.RULE, texts=[{"types": [2], "path": [0xC, 8], "lines": 2, "number": number}])
        without = dict(self.RULE, texts=[{"types": [2], "path": [0xC, 8], "lines": 2}])
        self.assertEqual(qa.record_numbers({"record_window": [with_number]}, mission_rom()),
                         {0x318: {"STR_VAR_1": 300, "B_COPY_VAR_1": 300}})
        inv = {"entries": [tabled("s0000200", "Heal {B_COPY_VAR_1} times\\nat the Centers.", 0x318)]}
        text = "Полечиться {B_COPY_VAR_1} раз\\nв Центрах."   # line 1: 90 px and the count
        cm, m = PACK.charmap(), Measure(lambda b: 6, {})
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / "system" / "a.po", [PoEntry("s0000200", inv["entries"][0]["text"], text)], {})
            old, new = (qa.compute_limits({"layout": {"record_window": [r]}}, inv, load_catalog(root), m, cm,
                                          rom=mission_rom())["s0000200"] for r in (without, with_number))
        self.assertEqual((old.placeholders, new.placeholders), (None, {"B_COPY_VAR_1": 18}))
        self.assertEqual(check(layout(text, old, m, cm), old, m, cm), ["too many lines: 3 > 2"])
        self.assertEqual(layout(text, new, m, cm), text)
        self.assertEqual(check(text, new, m, cm) + dropped_breaks(text, new, m, cm), [])


class WindowsTest(unittest.TestCase):
    """Name-table windows per font style."""

    def test_main_and_other_style(self):
        prof = {"layout": {}, "font_style": {"style": "main"},
                "table": [{"name": "names", "field_length": 11, "windows": [
                    {"style": "main", "width": 30, "where": "summary"},
                    {"style": "small", "width": 20, "where": "health box", "entries": {"names:1": 25}}]}]}
        inv = {"entries": [fixed("names:0", "Abc"), fixed("names:1", "Abcd"), fixed("names:2", "Ab")]}
        main = Measure(lambda b: 6, {})
        small = Measure(lambda b: 5, {})
        cm = PACK.charmap()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / "tables" / "names.po", [PoEntry("names:0", "Abc", "Абвг"),      # small 20: fits
                                                 PoEntry("names:1", "Abcd", "Абвгд"),    # small 25: entry override
                                                 PoEntry("names:2", "Ab", "Абвгде")], {})  # main 36 > 30, small 30 > 20
            w = qa.Windows(prof, inv, {"small": (small, cm)})
            self.assertEqual(w.width("names:1", "small"), 25)
            gate = qa.run(prof, inv, root, cm, main, set(PACK.glyph_slots()), windows=w)
            errs = sorted((f.id, f.message) for f in gate.findings if f.severity == "error")
            self.assertEqual([i for i, _ in errs], ["names:2", "names:2"])
            self.assertTrue(any("in health box (small)" in m for _, m in errs))
            self.assertTrue(any("36 > 30" in m for _, m in errs))


class TableWindowIndexesTest(unittest.TestCase):
    def test_indexes_select_records(self):
        # a scattered subset of a pointer table
        tw = {"name": "t", "base": 0x100, "stride": 4, "count": 10, "indexes": [2, 7], "fields": [0],
              "width": 142, "lines": 4}
        self.assertEqual(qa.table_window_positions(tw), [0x108, 0x11C])
        self.assertEqual([at for at, *_ in qa.window_rules({"table_window": [tw]})], [0x108, 0x11C])
        every = {k: v for k, v in tw.items() if k != "indexes"}
        self.assertEqual(len(qa.table_window_positions(every)), 10)
        with self.assertRaises(ValueError):
            qa.table_window_positions({**tw, "indexes": [10]})
