from test_roots import TOOLKIT_ROOT
"""Qa fills checks and fixtures."""

import sys
from pathlib import Path
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(TOOLKIT_ROOT / "src"))

from gen3tl.check import qa
from gen3tl.check.layout import Measure
from gen3tl.check.provenance import formatted
from gen3tl.catalog.po import KEY_ONLY, SOURCE_FIELD, PoEntry, write

from qa_support import PACK, entry, fixed, scripted, setUpModule, slot, tabled, tearDownModule


class SlotWidthTest(unittest.TestCase):
    """Placeholder widths per entry and slot, 6 px per glyph."""

    PROF = {"layout": {"dialogue_width": 100, "label_min_width": 60, "buffer_tables": {"item": "items"}},
            "table": [{"name": "items", "base": 0x5000, "stride": 4, "count": 3, "field_length": 10}]}
    INV = {"entries": [
        scripted("s0000100", "A {STR_VAR_1}."), scripted("s0000200", "B {STR_VAR_1}."),
        scripted("s0000300", "C {STR_VAR_1}."), scripted("s0000400", "D {STR_VAR_1}."),
        scripted("s0000500", "E {STR_VAR_1}."), scripted("s0000600", "F {STR_VAR_1}."),
        scripted("s0000700", "G {STR_VAR_1}."), scripted("s0000800", "H {STR_VAR_1}."),
        scripted("s0000900", "Word", "script:bufferstring"), scripted("s0000A00", "Long word", "script:bufferstring"),
        scripted("s0000B00", "Old English", "script:bufferstring"),
        fixed("items:0", "Ab", "items"), fixed("items:1", "Abcdef", "items"), fixed("items:2", "Abc", "items")]}
    CTX = {"strings": {
        "s0000100": slot(("string", "s0000900")),            # a word of the catalog: its translation
        "s0000200": slot(("item", None)),                    # a variable: the widest item name
        "s0000300": slot(("item", 0)),                       # the item the script names
        "s0000400": slot(("number", 1234), ("number", None)),
        "s0000500": {"slot_refs": {"unwalked": 1, "code": 0}},   # nothing known: the profile width
        "s0000600": slot(("string", "s0000900"), uses=2, unfilled=1),   # a path without a value
        "s0000700": slot(("nickname", None)),                # a name the player types
        "s0000800": slot(("string", "s0000B00"), ("string", "s0000A00")),
        "s0000900": {"fills": [["s0000100", "{STR_VAR_1}"], ["s0000600", "{STR_VAR_1}"]]},
        "s0000A00": {"fills": [["s0000800", "{STR_VAR_1}"]]},
        "s0000B00": {"fills": [["s0000800", "{STR_VAR_1}"]]}}}

    def catalog(self, root, host="Икс {STR_VAR_1}"):
        tr = {"s0000900": "Слово", "s0000A00": "Очень длинное слово", "items:0": "Абв", "items:1": "Абвгдеёж",
              "s0000800": host}
        write(root / "a.po", [PoEntry(x["id"], x["text"], tr.get(x["id"], "")) for x in self.INV["entries"]], {})
        from gen3tl.catalog.catalog import load_catalog
        return load_catalog(root)

    def test_widths_and_sources(self):
        m = Measure(lambda b: 6, {"STR_VAR_1": 60})
        with tempfile.TemporaryDirectory() as tmp:
            sw = qa.slot_widths(self.PROF, self.INV, self.CTX, self.catalog(Path(tmp)), m, PACK.charmap())
        got = {sid: (w["STR_VAR_1"].translated, w["STR_VAR_1"].source_width, w["STR_VAR_1"].known) for sid, w in sw.items()}
        self.assertEqual(got, {
            "s0000100": (30, 24, "script"),      # Слово / Word
            "s0000200": (48, 36, "script"),      # widest Russian Абвгдеёж, widest English Abcdef
            "s0000300": (18, 12, "script"),      # Абв / Ab
            "s0000400": (30, 30, "script"),      # five digits of a variable beat 1234
            "s0000500": (60, 60, "profile"),
            "s0000600": (60, 24, "partly"),      # at least the profile width
            "s0000700": (60, 60, "profile"),
            "s0000800": (114, 66, "script")})    # Очень длинное слово; the English Old English
        self.assertIn("s0000900 'Слово'", formatted(sw["s0000100"]["STR_VAR_1"].source))
        self.assertIn("widest of table items: items:1 'Абвгдеёж'", formatted(sw["s0000200"]["STR_VAR_1"].source))
        self.assertIn("number of up to 5 digits", formatted(sw["s0000400"]["STR_VAR_1"].source))
        self.assertIn("profile width (no fill known; 1 script references not walked)",
                      formatted(sw["s0000500"]["STR_VAR_1"].source))
        self.assertIn("1 of 2 walked paths set no value", formatted(sw["s0000600"]["STR_VAR_1"].source))
        self.assertIn("nickname", formatted(sw["s0000700"]["STR_VAR_1"].source))
        self.assertNotIn("unverified", formatted(sw["s0000500"]["STR_VAR_1"].source))
        with tempfile.TemporaryDirectory() as tmp:
            guessed = qa.slot_widths({**self.PROF, "policy_unverified": {"placeholders": ["STR_VAR_1"]}}, self.INV,
                                     self.CTX, self.catalog(Path(tmp)), m, PACK.charmap())
        self.assertIn("profile width, unverified estimate (no fill known", formatted(guessed["s0000500"]["STR_VAR_1"].source))
        self.assertIn("profile width, unverified estimate, above", formatted(guessed["s0000600"]["STR_VAR_1"].source))
        self.assertEqual(formatted(guessed["s0000100"]["STR_VAR_1"].source), formatted(sw["s0000100"]["STR_VAR_1"].source))
        # a batch's own translation of a word replaces the catalog's
        with tempfile.TemporaryDirectory() as tmp:
            sw = qa.slot_widths(self.PROF, self.INV, self.CTX, self.catalog(Path(tmp)), m, PACK.charmap(),
                                {"s0000900": "Словечко"})
        self.assertEqual(sw["s0000100"]["STR_VAR_1"].translated, 48)

    def test_limits_measure_the_english_with_its_insertions(self):
        m = Measure(lambda b: 6, {"STR_VAR_1": 60})
        with tempfile.TemporaryDirectory() as tmp:
            cat = self.catalog(Path(tmp))
            old = qa.compute_limits(self.PROF, self.INV, cat, m, PACK.charmap())
            new = qa.compute_limits(self.PROF, self.INV, cat, m, PACK.charmap(), self.CTX)
        # 18 px of text; slot 60 px, 66 wide
        self.assertEqual((old["s0000800"].width, old["s0000800"].placeholders), (100, None))
        self.assertEqual((new["s0000800"].width, new["s0000800"].placeholders), (100, {"STR_VAR_1": 114}))
        # an inserted word inside a sentence uses the host window
        self.assertEqual((old["s0000900"].kind, old["s0000900"].width, old["s0000900"].host), ("single", 60, None))
        self.assertEqual((new["s0000900"].width, new["s0000900"].host), (100, "s0000100"))
        self.assertEqual((new["s0000A00"].width, new["s0000A00"].host), (100, "s0000800"))

    def test_fill_keeps_its_confirmed_arrow_when_using_host_width(self):
        prof = {**self.PROF, "layout": {**self.PROF["layout"], "prompt_arrow_width": 10,
                                       "window_prompt_arrow_width": {"s0000900": 10}}}
        with tempfile.TemporaryDirectory() as tmp:
            limits = qa.compute_limits(prof, self.INV, self.catalog(Path(tmp)),
                                       Measure(lambda b: 6, {"STR_VAR_1": 60}), PACK.charmap(), self.CTX)
        confirmed = limits["s0000900"].consumers[0]
        unknown = limits["s0000A00"].consumers[0]
        self.assertEqual((confirmed["width"], confirmed["arrow"], confirmed["arrow_confirmed"]),
                         (100, 10, True))
        self.assertEqual((unknown["width"], unknown["arrow"], unknown["arrow_confirmed"]),
                         (100, 10, False))

    def test_without_the_english_the_snapshot_rows_give_the_same_limits_and_findings(self):
        from gen3tl.catalog import extract
        from gen3tl.catalog.catalog import load_catalog
        from gen3tl.catalog.po import KEY_ONLY, SOURCE_FIELD
        from gen3tl.web.editorsnapshot import source_rows
        m = Measure(lambda b: 6, {"STR_VAR_1": 60})
        fields = ("kind", "width", "lines", "chars", "bytes", "keys", "style", "placeholders", "source_lines", "strip",
                  "head", "host", "target", "sentence_break", "arrow")
        with tempfile.TemporaryDirectory() as tmp:
            full, keyed = Path(tmp) / "full", Path(tmp) / "keyed"
            cat = self.catalog(full, host="Икс")
            rows = source_rows(cat, qa.compute_limits(self.PROF, self.INV, cat, m, PACK.charmap(), self.CTX,
                                                      english_slots=True), lambda b: 6)
            write(keyed / "a.po", [e for _, e in cat.values()], {SOURCE_FIELD: KEY_ONLY})
            without = load_catalog(keyed, source={}, english=False)
            self.assertTrue(all(e.keyed and e.msgid == e.msgctxt for _, e in without.values()))
            inv = {"entries": [{**e, "text": ""} for e in self.INV["entries"]]}   # the snapshot's inventory
            limits = qa.compute_limits(self.PROF, self.INV, cat, m, PACK.charmap(), self.CTX)
            facts = qa.compute_limits(self.PROF, inv, without, m, PACK.charmap(), self.CTX, source=rows)
            self.assertEqual({sid: [getattr(lim, f) for f in fields] for sid, lim in facts.items()},
                             {sid: [getattr(lim, f) for f in fields] for sid, lim in limits.items()})
            # the gate finds the same
            gate = qa.run(self.PROF, self.INV, full, PACK.charmap(), m, set(PACK.glyph_slots()), ctx=self.CTX)
            with mock.patch.object(extract, "path", return_value=Path(tmp) / "missing.pot"):
                on_rows = qa.run(self.PROF, inv, keyed, PACK.charmap(), m, set(PACK.glyph_slots()), ctx=self.CTX,
                                 source=rows)
        # host without its token; the word exceeds the host window
        self.assertEqual([(f.id, f.message[:22]) for f in gate.findings],
                         [("s0000800", "placeholders differ: m"), ("s0000A00", "line too wide: 114 > 1")])
        self.assertEqual([(f.id, f.severity, f.message) for f in on_rows.findings],
                         [(f.id, f.severity, f.message) for f in gate.findings])

    def test_a_word_with_a_display_of_its_own_keeps_its_limit(self):
        # only a buffered word takes its host's window
        inv = {"entries": [dict(e, refs=list(e["refs"])) for e in self.INV["entries"]]}
        word = next(e for e in inv["entries"] if e["id"] == "s0000B00")
        word["refs"].append({"at": 0x20, "kind": "table"})
        m = Measure(lambda b: 6, {"STR_VAR_1": 60})
        with tempfile.TemporaryDirectory() as tmp:
            new = qa.compute_limits(self.PROF, inv, self.catalog(Path(tmp)), m, PACK.charmap(), self.CTX)
        self.assertEqual((new["s0000B00"].width, new["s0000B00"].host), (66, None))   # its English
        self.assertEqual((new["s0000A00"].width, new["s0000A00"].host), (100, "s0000800"))

    def test_gate_reports_the_overflow_with_the_inserted_word(self):
        m = Measure(lambda b: 6, {"STR_VAR_1": 60})
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.catalog(root)
            before = qa.run(self.PROF, self.INV, root, PACK.charmap(), m, set(PACK.glyph_slots()))
            after = qa.run(self.PROF, self.INV, root, PACK.charmap(), m, set(PACK.glyph_slots()), ctx=self.CTX)
        def errors(gate):
            return sorted((f.id, f.message) for f in gate.findings if f.severity == "error")
        # with its own English width, 114 px fails 60 px
        self.assertEqual(errors(before), [("s0000A00", "line too wide: 114 > 60 px: 'Очень длинное слово'")])
        # the word alone exceeds the 100 px host window
        self.assertEqual(errors(after), [
            ("s0000800", "line too wide: 114 > 100 px: '{STR_VAR_1}' with {STR_VAR_1} = 114 px "
                         "(s0000A00 'Очень длинное слово')"),
            ("s0000A00", "line too wide: 114 > 100 px: 'Очень длинное слово'")])
        # fits with the profile width, not with the word
        self.assertIn(("s0000800", "line wider than the window with the inserted words: box 1: 138 > 100 px: "
                                   "'Икс {STR_VAR_1}' with {STR_VAR_1} = 114 px (s0000A00 'Очень длинное слово'); "
                                   "the build re-wraps the box"),
                      [(f.id, f.message) for f in after.findings if f.severity == "warning"])


class CodeFillTest(unittest.TestCase):
    """A code-filled placeholder takes its real width by id or pointer table."""

    PROF = {"layout": {
        "code_fill": [
            {"ids": ["s0000100", "s0000500"], "slots": {"STR_VAR_1": {"digits": 1}}, "where": "count",
             "evidence": "test"},
            {"base": 0x1000, "stride": 4, "count": 2, "slots": {"STR_VAR_1": {"digits": 3}, "STR_VAR_2": {"width": 30}},
             "where": "table", "evidence": "test"}],
        "window_width": {"s0000100": 60}}}
    INV = {"entries": [
        tabled("s0000100", "{STR_VAR_1} PLAYERS", 0x2000),
        tabled("s0000200", "{STR_VAR_1}/{STR_VAR_2}", 0x1004),
        tabled("s0000300", "{STR_VAR_2}!", 0x1008),          # past the table's count
        scripted("s0000400", "{STR_VAR_1} left"),            # no rule
        tabled("s0000500", "{STR_VAR_1} and {STR_VAR_3}", 0x1000)]}   # both rules: the widest
    M = Measure(lambda b: 6, {"STR_VAR_1": 60, "STR_VAR_2": 60, "STR_VAR_3": 60})

    def limits(self, root, ctx=None, tr=None):
        write(root / "a.po", [PoEntry(x["id"], x["text"], (tr or {}).get(x["id"], "")) for x in self.INV["entries"]],
              {})
        from gen3tl.catalog.catalog import load_catalog
        return qa.compute_limits(self.PROF, self.INV, load_catalog(root), self.M, PACK.charmap(), ctx)

    def test_widths_and_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            lim = self.limits(Path(tmp))
        self.assertEqual({sid: l.placeholders for sid, l in lim.items()}, {
            "s0000100": {"STR_VAR_1": 6}, "s0000200": {"STR_VAR_1": 18, "STR_VAR_2": 30}, "s0000300": None,
            "s0000400": None, "s0000500": {"STR_VAR_1": 18}})
        texts = {sid: {name: formatted(source) for name, source in (l.slot_sources or {}).items()} for sid, l in lim.items()}
        self.assertEqual(texts["s0000100"], {"STR_VAR_1": "number of 1 digit, count"})
        self.assertEqual(texts["s0000200"], {"STR_VAR_1": "number of 3 digits, table", "STR_VAR_2": "30 px, table"})
        # widest English of the run measured with them.
        # 18 + 30 + 60, not 60 + 30 + 60.
        self.assertEqual({sid: lim[sid].width for sid in ("s0000200", "s0000300", "s0000500")},
                         {"s0000200": 108, "s0000300": 108, "s0000500": 108})

    def test_over_the_widths_of_the_scripts(self):
        ctx = {"strings": {"s0000100": slot(("number", 12345)), "s0000400": slot(("number", 12345))}}
        with tempfile.TemporaryDirectory() as tmp:
            lim = self.limits(Path(tmp), ctx)
        self.assertEqual((lim["s0000100"].placeholders, lim["s0000400"].placeholders),
                         ({"STR_VAR_1": 6}, {"STR_VAR_1": 30}))

    def test_gate(self):
        tr = {"s0000100": "Игроков: {STR_VAR_1}",     # 54 + 6: fits the 60 px window
              "s0000200": "{STR_VAR_1} из {STR_VAR_2}"}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.limits(root, tr=tr)
            gate = qa.run(self.PROF, self.INV, root, PACK.charmap(), self.M, set(PACK.glyph_slots()))
            ok = [(f.id, f.message) for f in gate.findings]
            write(root / "a.po", [PoEntry("s0000100", "{STR_VAR_1} PLAYERS", "Игроков всего: {STR_VAR_1}")], {})
            gate = qa.run(self.PROF, self.INV, root, PACK.charmap(), self.M, set(PACK.glyph_slots()))
        self.assertEqual(ok, [])
        self.assertEqual([(f.id, f.message) for f in gate.findings],
                         [("s0000100", "line too wide: 96 > 60 px: 'Игроков всего: {STR_VAR_1}' with "
                                       "{STR_VAR_1} = 6 px (number of 1 digit, count)")])

    def test_refused_rules(self):
        for rule in ({"ids": ["s0000100"], "slots": {"STR_VAR_1": {"digits": 1}}},
                     {"ids": ["s0000100"], "slots": {"STR_VAR_1": {"digits": 1, "width": 6}}, "evidence": "x"},
                     {"ids": ["s0000100"], "slots": {"STR_VAR_1": {}}, "evidence": "x"}):
            with self.subTest(rule=rule), self.assertRaises(ValueError):
                qa.code_fills({"code_fill": [rule]})


class ControlOnlyFillTest(unittest.TestCase):
    def test_zero_width_is_limited_to_verified_hosts(self):
        from gen3tl.check import layout

        token = "{FD 07}"
        text = f"AAAA{token} BBBB"
        inv = {"entries": [scripted(f"s{at:07X}", text) for at in (0x100, 0x200, 0x300)]}
        prof = {"layout": {"window_width": {e["id"]: 60 for e in inv["entries"]}, "code_fill": [
            {"ids": ["s0000100"], "slots": {"FD 07": {"width": 0}},
             "where": "colour reset", "evidence": "buffer holds COLOR only"},
            {"ids": ["s0000300"], "slots": {"FD 07": {"width": 24}},
             "where": "inserted name", "evidence": "buffer holds a name"}]}}
        measure = Measure(lambda b: 6, {})
        cm = PACK.charmap()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write(root / "a.po", [PoEntry(e["id"], text, text) for e in inv["entries"]], {})
            from gen3tl.catalog.catalog import load_catalog
            rows = load_catalog(root)
            ru = qa.compute_limits(prof, inv, rows, measure, cm)
            en = qa.compute_limits(prof, inv, rows, measure, cm, english_slots=True)
        for limits in (ru, en):
            self.assertEqual(limits["s0000100"].placeholders, {"FD 07": 0})
            self.assertIsNone(limits["s0000200"].placeholders)
            self.assertEqual(limits["s0000300"].placeholders, {"FD 07": 24})
            widths = [layout.entry_measure(measure, limits[e["id"]]).width(token, cm)
                      for e in inv["entries"]]
            self.assertEqual(widths, [0, 60, 24])
            self.assertEqual(layout.layout(text, limits["s0000100"], measure, cm), text)
            self.assertEqual(layout.check(text, limits["s0000100"], measure, cm), [])
            self.assertNotEqual(layout.layout(text, limits["s0000200"], measure, cm), text)


class CodeFillEnglishTest(unittest.TestCase):
    """A code-fill width may carry the English fill width."""

    PROF = {"layout": {"code_fill": [
        {"ids": ["s0000100"], "slots": {"B_TRAINER1_NAME": {"width": 66, "source_width": 67}}, "where": "name",
         "evidence": "test"}]}}

    def limit(self, root, english_slots=False):
        e = entry("s0000100", "{B_TRAINER1_NAME} " + "a" * 24)
        e.update(category="battle-script", mode="battle", refs=[{"at": 0x10, "kind": "script:setword"}])
        write(root / "a.po", [PoEntry("s0000100", e["text"], "")], {})
        from gen3tl.catalog.catalog import load_catalog
        return qa.compute_limits(self.PROF, {"entries": [e]}, load_catalog(root), Measure(lambda b: 6, {}),
                                 PACK.charmap(), english_slots=english_slots)["s0000100"]

    def test_widths(self):
        with tempfile.TemporaryDirectory() as tmp:
            ru, en = self.limit(Path(tmp)), self.limit(Path(tmp), english_slots=True)
        # English: 67 + 6 + 24 * 6 = 217 px
        self.assertEqual((ru.width, ru.placeholders, en.placeholders),
                         (217, {"B_TRAINER1_NAME": 66}, {"B_TRAINER1_NAME": 67}))
        self.assertEqual({name: formatted(source) for name, source in ru.slot_sources.items()},
                         {"B_TRAINER1_NAME": "66 px, English 67 px, name"})

    def test_refused_rules(self):
        for s in ({"source_width": 67}, {"digits": 2, "source_width": 12}):
            with self.subTest(slot=s), self.assertRaises(ValueError):
                qa.code_fills({"code_fill": [{"ids": ["s0000100"], "slots": {"B_TRAINER1_NAME": s},
                                              "evidence": "x"}]})
