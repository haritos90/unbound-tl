from test_roots import TOOLKIT_ROOT
"""Qa messages checks and fixtures."""

import sys
from pathlib import Path
import tempfile
import unittest

sys.path.insert(0, str(TOOLKIT_ROOT / "src"))

from gen3tl.check import qa
from gen3tl.check.layout import Limit, Measure, check
from gen3tl.catalog.extract import english
from gen3tl.catalog.po import PoEntry, write

import qa_support
from qa_support import PACK, entry, fixed, setUpModule, tabled, tearDownModule


class TrainerBattleWindowTest(unittest.TestCase):
    def test_all_references_need_battle_speech_evidence(self):
        roles = ["defeat", "victory", "intro", "cannot-battle", "after-battle", None]
        entries, rows, uses = [], {}, {}
        for i, role in enumerate(roles):
            sid = f"s{0x100 + i * 0x100:07X}"
            e = entry(sid, "A short speech.")
            e["refs"] = [{"at": i * 4, "kind": "script:trainerbattle"}]
            entries.append(e)
            rows[sid] = (Path("a.po"), PoEntry(sid, e["text"], ""))
            uses[sid] = {"uses": [{"at": i * 4, "trainer_role": role}]}
        prof = {"layout": {"dialogue_width": 208, "battle_width": 222, "prompt_arrow_width": 10,
                           "box_width": {"dialogue": 208, "battle": 222}}}
        limits = qa.compute_limits(prof, {"entries": entries}, rows, Measure(lambda b: 6, {}),
                                   PACK.charmap(), {"strings": uses})
        self.assertEqual([(x.kind, x.width, x.arrow) for x in limits.values()],
                         [("battle", 222, 10)] * 2 + [("dialogue", 208, 10)] * 4)
        e = entries[0]
        evidence = uses[e["id"]]["uses"]
        self.assertTrue(qa.trainer_battle_only(e, evidence))
        self.assertFalse(qa.trainer_battle_only(e, []))
        self.assertFalse(qa.trainer_battle_only(e, [{"trainer_role": "defeat"}]))
        self.assertFalse(qa.trainer_battle_only(e, evidence + [{"at": 0, "trainer_role": "intro"}]))
        for kind in ("script:trainerbattle", "script:message", "aligned"):
            with self.subTest(kind=kind):
                changed = {**e, "refs": e["refs"] + [{"at": 1000, "kind": kind}]}
                self.assertFalse(qa.trainer_battle_only(changed, evidence))


class MessageBoxWindowTest(unittest.TestCase):
    """Message box texts and title centring windows."""

    def limits(self, lay, entries, catalog_texts, overrides=None):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / "a.po", [PoEntry(sid, en, ru) for sid, (en, ru) in catalog_texts.items()], {})
            return qa.compute_limits({"layout": lay}, {"entries": entries}, qa.load_catalog(root),
                                     Measure(lambda b: 6, {}), PACK.charmap(), overrides=overrides)

    def test_runtime_scroll_window_binding(self):
        es = [tabled("s0000100", "A\\nB\\nC", 0x1000)]
        row = {"name": "scroll", "width": 60, "box": "dialogue", "lines": 2,
               "where": "Notice message window",
               "newline_scroll_after": 1, "evidence": "The printer converts later newlines."}
        for lay in ({"table_window": [{**row, "base": 0x1000, "stride": 4, "count": 1}]},
                    {"window_binding": {"s0000100": row}, "window_width": {"s0000100": 60},
                     "window_box": {"s0000100": "dialogue"}, "window_lines": {"s0000100": 2},
                     "window_newline_scroll_after": {"s0000100": 1}}):
            lim = self.limits({"prompt_arrow_width": 10, **lay}, es, {"s0000100": (es[0]["text"], "")})["s0000100"]
            self.assertEqual((lim.width, lim.lines, lim.newline_scroll_after), (60, 2, 1))
            self.assertEqual(lim.consumers[0]["newline_scroll_after"], 1)
            self.assertEqual(lim.consumers[0]["name"], "Notice message window")
            self.assertIn("scroll", lim.consumers[0]["source"]["rule"])
            self.assertIn("converts later newlines", lim.consumers[0]["source"]["evidence"])

    def test_shared_list_and_sign_keep_separate_confirmation(self):
        es = [tabled("s0000100", "Floor", 0x1000)]
        common = {"base": 0x1000, "stride": 4, "count": 1, "fields": [0]}
        lay = {"prompt_arrow_width": 10, "table_window": [
            {**common, "name": "floor-list", "where": "Floor selection list", "width": 80, "lines": 1},
            {**common, "name": "floor-sign", "where": "Floor sign window", "width": 60, "lines": 2,
             "prompt_arrow_width": 10, "evidence": "The sign printer waits with the arrow."},
        ]}
        lim = self.limits(lay, es, {"s0000100": ("Floor", "")})["s0000100"]
        self.assertEqual((lim.width, lim.lines, lim.arrow), (60, 1, 10))
        self.assertEqual([(c["name"], c["arrow_confirmed"]) for c in lim.consumers],
                         [("Floor selection list", False), ("Floor sign window", True)])

    def test_default_arrow_in_every_kind(self):
        from gen3tl.check.layout import arrow_room
        entries = [entry("s0000100", "A"), entry("s0000200", "A"),
                   tabled("s0000300", "A", 0x1000), tabled("s0000400", "A\\nB", 0x2000)]
        entries[1]["category"] = "battle-script"
        fixed = {**entry("s0000500", "A"), "kind": "fixed", "table": "labels", "index": 0}
        entries.append(fixed)
        prof = {"layout": {"prompt_arrow_width": 10},
                "table": [{"name": "labels", "field_length": 20}]}
        catalog = {e["id"]: (Path(e["id"] + ".po"), PoEntry(e["id"], e["text"], "")) for e in entries}
        limits = qa.compute_limits(prof, {"entries": entries}, catalog, Measure(lambda b: 6, {}), PACK.charmap())
        self.assertEqual([l.kind for l in limits.values()], ["dialogue", "battle", "single", "multiline", "field"])
        for lim in limits.values():
            self.assertEqual(arrow_room(lim), lim.width - 10)
            self.assertEqual(lim.consumers[0]["arrow_source"], "default")

    def test_instant_window_refuses_waits_for_single_and_shared_texts(self):
        from gen3tl.check.entrycheck import entry_problems
        m, cm = Measure(lambda b: 1, {}), PACK.charmap()
        ordinary = {"name": "ordinary", "where": "ordinary message window", "base": 0x1000,
                    "stride": 4, "count": 1, "width": 60, "box": "dialogue"}
        instant = {"name": "instant", "where": "instant message window", "base": 0x2000,
                   "stride": 4, "count": 1, "width": 80, "lines": 2, "instant_print": True,
                   "evidence": "The printer runs instantly."}
        for refs in ((0x2000,), (0x1000, 0x2000), (0x1000,)):
            es = [tabled("s0000100", "A", *refs)]
            lim = self.limits({"table_window": [ordinary, instant]}, es, {"s0000100": ("A", "")})["s0000100"]
            self.assertEqual(len(lim.consumers), len(refs))
            for text in ("A\\lB", "A\\pB", "A\\p", "A\\nB", "A"):
                with self.subTest(refs=refs, text=text):
                    _, problems = entry_problems("A", text, lim, m, cm)
                    found = [p for p in problems if "prints instantly" in p]
                    self.assertEqual(bool(found), 0x2000 in refs and ("\\l" in text or "\\p" in text))
                    if found:
                        self.assertEqual(found, ["scroll and page codes are not supported in instant message window: "
                                                 "this window prints instantly and drops the remaining text"])

    def test_instant_window_without_width_keeps_existing_limits(self):
        from gen3tl.profile.schema import load
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp) / "profile.toml"
            file.write_text('[[layout.window]]\nname = "banner"\ninstant_print = true\n'
                            'evidence = "The printer runs instantly."\n'
                            '[[layout.window_strings]]\nstring = "s0000100"\nwindow = "banner"\n')
            lay = load(file)["layout"]
        es = [tabled("s0000100", "A", 0x1000)]
        before = self.limits({}, es, {"s0000100": ("A", "")})["s0000100"]
        after = self.limits(lay, es, {"s0000100": ("A", "")})["s0000100"]
        self.assertEqual((after.width, after.lines, after.kind), (before.width, before.lines, before.kind))
        self.assertTrue(after.consumers[0]["instant_print"])
        self.assertIn("banner", after.consumers[0]["name"])

    def test_shared_consumers_bind_width_and_arrow_separately(self):
        from gen3tl.check.layout import arrow_overflows, arrow_room, check
        m, cm = Measure(lambda b: 1, {}), PACK.charmap()
        es = [tabled("s0000100", "A", 0x1000, 0x2000)]
        first = {"name": "wide", "where": "wide message window", "base": 0x1000, "stride": 4,
                 "count": 1, "width": 224, "box": "dialogue"}
        second = {"name": "narrow", "where": "narrow menu window", "base": 0x2000, "stride": 4,
                  "count": 1, "width": 176, "lines": 2, "evidence": "The printer's arrow was measured."}
        for override, expected in ((None, 166), (0, 214), (60, 116)):
            rule = dict(second)
            if override is not None:
                rule["prompt_arrow_width"] = override
            lim = self.limits({"prompt_arrow_width": 10, "table_window": [first, rule]}, es,
                              {"s0000100": ("A", "")})["s0000100"]
            self.assertEqual((lim.kind, lim.width, arrow_room(lim)), ("multiline", 176, expected))
            self.assertEqual([(c["width"], c["arrow"]) for c in lim.consumers],
                             [(224, 10), (176, 10 if override is None else override)])
            self.assertIn("narrow menu window", check("A" * 177, lim, m, cm)[0])
            message = arrow_overflows("A" * (expected + 1) + "\\pB", lim, m, cm)[0]
            self.assertIn("wide message window" if override == 0 else "narrow menu window", message)
            self.assertFalse(arrow_overflows("A" * expected + "\\lB", lim, m, cm))
            self.assertFalse(arrow_overflows("A" * (expected + 1) + "{PAUSE_UNTIL_PRESS}", lim, m, cm))
            self.assertFalse(arrow_overflows("A" * (expected + 1), lim, m, cm))

    def test_box(self):
        lay = {"box_width": {"dialogue": 208, "battle": 222},
               "table_window": [{"name": "pre", "base": 0x1000, "stride": 8, "count": 2, "fields": [0], "width": 208,
                                 "box": "dialogue"},
                                {"name": "win", "base": 0x1000, "stride": 8, "count": 2, "fields": [4], "width": 222,
                                 "box": "battle"}],
               "window_box": {"s0000300": "battle"}}
        es = [tabled("s0000100", "Hi!", 0x1000), tabled("s0000200", "Bye!\\nNow\\pGo.", 0x100C),
              tabled("s0000300", "Example weather text…", 0x5000), tabled("s0000400", "Plain.", 0x5004)]
        lims = self.limits(lay, es, {e["id"]: (e["text"], "") for e in es})
        self.assertEqual({sid: (l.kind, l.width, l.lines) for sid, l in lims.items() if sid != "s0000400"},
                         {"s0000100": ("dialogue", 208, 2), "s0000200": ("battle", 222, 2),
                          "s0000300": ("battle", 222, 2)})
        self.assertEqual(lims["s0000400"].kind, "single")
        # a single-line English may take two lines in its box
        self.assertEqual(qa.check("Привет!\\nКак дела?", lims["s0000100"], Measure(lambda b: 6, {}), PACK.charmap()),
                         [])
        with self.assertRaises(ValueError):
            self.limits({"window_box": {"s0000100": "sign"}}, es, {"s0000100": ("Hi!", "")})

    def test_measured_field_table_reserves_arrow_room(self):
        from gen3tl.check.entrycheck import entry_problems
        from gen3tl.web.editorcheck import limit_of
        en = "Hi!\\nThere.\\pBye."
        text = "aa\\naaaaa bbb\\pcc"
        es = [tabled("s0000100", en, 0x1000), tabled("s0000200", en, 0x2000)]
        texts = {e["id"]: (en, text) for e in es}
        lay = {"prompt_arrow_width": 12}
        before = self.limits(lay, es, texts)
        self.assertEqual([(x.kind, x.arrow) for x in before.values()], [("multiline", 12)] * 2)
        lay["table_window"] = [{"name": "field-messages", "base": 0x1000, "stride": 4,
                                "count": 1, "fields": [0], "width": 60, "box": "dialogue",
                                "evidence": "The getter feeds the field message printer."}]
        limits = self.limits(lay, es, texts)
        measured = limits["s0000100"]
        self.assertEqual((measured.kind, measured.width, measured.arrow), ("dialogue", 60, 12))
        self.assertEqual((limits["s0000200"].kind, limits["s0000200"].arrow), ("multiline", 12))
        self.assertEqual(measured.sources["width"]["evidence"], lay["table_window"][0]["evidence"])
        for lim in (measured, limit_of(vars(measured))):
            errors = entry_problems(en, text, lim, Measure(lambda b: 6, {}), PACK.charmap())[1]
            self.assertTrue(any("prompt arrow" in message for message in errors), errors)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / "a.po", [PoEntry("s0000100", en, text)], {})
            gate = qa.run({"layout": lay}, {"entries": es}, root, PACK.charmap(),
                          Measure(lambda b: 6, {}), set())
            arrows = [(f.id, f.severity) for f in gate.findings if "prompt arrow" in f.message]
            self.assertEqual(arrows, [("s0000100", "error")])

    def test_centre(self):
        lay = {"table_window": [{"name": "titles", "base": 0x1000, "stride": 4, "count": 3, "fields": [0],
                                 "width": 144, "centre": {"reference": "s0000100", "step": 5}}]}
        es = [tabled("s0000100", "Link Multi Record", 0x1000), tabled("s0000200", "Single Record", 0x1004),
              tabled("s0000300", "Multi", 0x1008)]
        texts = {"s0000100": ("Link Multi Record", "Рекорд мульти"), "s0000200": ("Single Record", "Рекорд"),
                 "s0000300": ("Multi", "")}
        lims = self.limits(lay, es, texts)
        # x = 5 * 7; the untranslated entry counts its English
        self.assertEqual({sid: l.width for sid, l in lims.items()},
                         {"s0000100": 144, "s0000200": 144 - 35, "s0000300": 144 - 40})
        # a batch translation counts; extra characters run off the window
        lims = self.limits(lay, es, texts, overrides={"s0000200": "Рекорд одиночных битв"})
        self.assertEqual(lims["s0000200"].width, 0)


class WindowStyleTest(unittest.TestCase):
    """A window the code draws in another font style ([layout.window_style])."""

    M = Measure(lambda b: 6, {}, styles={"small": lambda b: 5})

    def test_entry_measured_in_its_style(self):
        from gen3tl.check.layout import Limit, check, entry_measure
        cm = PACK.charmap()
        lim = Limit("single", 32, 1, style="small")
        self.assertEqual(entry_measure(self.M, lim).width("Готово", cm), 30)
        self.assertEqual(check("Готово", lim, self.M, cm), [])
        self.assertEqual(check("Поймано", lim, self.M, cm), ["line too wide: 35 > 32 px: 'Поймано'"])
        self.assertTrue(check("Готово", Limit("single", 32, 1), self.M, cm))   # main font: 36 px
        # a style the measure does not know: the main widths
        self.assertEqual(entry_measure(self.M, Limit("single", 32, 1, style="other")).width("Готово", cm), 36)
        # the entry's placeholder widths stay
        lim = Limit("single", 100, 1, style="small", placeholders={"STR_VAR_1": 40})
        self.assertEqual(entry_measure(self.M, lim).width("{STR_VAR_1}а", cm), 45)

    def test_profile_style_reaches_the_limit_and_the_gate(self):
        prof = {"layout": {"window_width": {"s0000100": 32, "s0000200": 32},
                           "window_style": {"s0000100": "small"}}}
        inv = {"entries": [entry("s0000100", "Done"), entry("s0000200", "Done")]}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / "a.po", [PoEntry("s0000100", "Done", "Готово"),        # small: 30 px
                                  PoEntry("s0000200", "Done", "Готово")], {})   # main: 36 px
            lims = qa.compute_limits(prof, inv, qa.load_catalog(root), self.M, PACK.charmap())
            self.assertEqual({sid: (l.width, l.style) for sid, l in lims.items()},
                             {"s0000100": (32, "small"), "s0000200": (32, None)})
            gate = qa.run(prof, inv, root, PACK.charmap(), self.M, set(PACK.glyph_slots()))
            self.assertEqual({f.id for f in gate.findings if f.severity == "error"}, {"s0000200"})


class BoxWidthTest(qa_support.BoxWidthTest, unittest.TestCase):
    def test_box_cap(self):
        boxes = {"dialogue": 208, "sign": 200, "battle": 222}
        self.assertEqual(qa.box_cap(boxes, "dialogue", []), 208)
        self.assertEqual(qa.box_cap(boxes, "dialogue", [{"event": "npc", "box": "sign"}]), 200)
        self.assertEqual(qa.box_cap(boxes, "dialogue", [{"event": "sign", "box": None}]), 200)
        self.assertEqual(qa.box_cap(boxes, "battle", [{"event": "sign", "box": "sign"}]), 222)
        self.assertIsNone(qa.box_cap(boxes, "multiline", []))
        self.assertIsNone(qa.box_cap({}, "dialogue", []))
        self.assertIsNone(qa.box_cap({"sign": 200}, "dialogue", []))

    def test_limits_never_exceed_the_box(self):
        prof = {"layout": {k: v for k, v in self.PROF["layout"].items() if k != "box_width"}}
        # without measured boxes: the English width, if wider than least
        self.assertEqual(self.limits(prof, self.CTX), {
            "s0000100": ("dialogue", 120), "s0000200": ("dialogue", 120), "s0000300": ("dialogue", 60),
            "s0000400": ("battle", 150), "s0000450": ("battle", 108), "s0000500": ("dialogue", 150),
            "s0000600": ("multiline", 150)})
        # the box binds a wider English.
        # a sign takes the sign box; windows are no boxes.
        self.assertEqual(self.limits(self.PROF, self.CTX), {
            "s0000100": ("dialogue", 100), "s0000200": ("dialogue", 90), "s0000300": ("dialogue", 60),
            "s0000400": ("battle", 120), "s0000450": ("battle", 108), "s0000500": ("dialogue", 150),
            "s0000600": ("multiline", 150)})
        # without context no use is a sign: the dialogue box
        self.assertEqual(self.limits(self.PROF)["s0000200"], ("dialogue", 100))

    def test_gate_reports_a_line_over_the_box(self):
        inv = {"entries": self.INV["entries"][:1]}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # one 102 px word fits the English width only
            write(root / "a.po", [PoEntry("s0000100", "A" * 20, "Ж" * 17)], {})
            prof = {"layout": {k: v for k, v in self.PROF["layout"].items() if k != "box_width"}}
            runs = [qa.run(p, inv, root, PACK.charmap(), Measure(lambda b: 6, {}), set(PACK.glyph_slots()))
                    for p in (prof, self.PROF)]
            self.assertEqual([f.message for f in runs[0].findings], [])
            self.assertEqual([(f.id, f.severity, f.message) for f in runs[1].findings],
                             [("s0000100", "error", "line too wide: 102 > 100 px: '" + "Ж" * 17 + "'")])
            # two words: the layout breaks the line inside the box
            write(root / "a.po", [PoEntry("s0000100", "A" * 20, "Жжжжжжжж жжжжжжжж")], {})
            gate = qa.run(self.PROF, inv, root, PACK.charmap(), Measure(lambda b: 6, {}), set(PACK.glyph_slots()))
            self.assertEqual(gate.findings, [])
            # English wider than the box: warning, the original is cut
            gate = qa.run(self.PROF, inv, root, PACK.charmap(), Measure(lambda b: 6, {}), set(PACK.glyph_slots()),
                          source_as_translation=True)
            self.assertEqual([(f.id, f.severity, f.message) for f in gate.findings],
                             [("s0000100", "warning", "line too wide: 120 > 100 px: '" + "A" * 20 + "'")])


class StripPrefixTest(unittest.TestCase):
    """Prefixes the printing code strips are not measured."""

    M = Measure(lambda b: 6, {})
    LAY = {"table_window": [
        {"name": "music", "base": 0x1000, "stride": 4, "count": 3, "fields": [0], "width": 60,
         "strip": [{"reference": "s0000900", "chars": 8}, {"reference": "s0000A00", "chars": 5}]},
        {"name": "list", "base": 0x2000, "stride": 4, "count": 1, "fields": [0], "width": 200}],
        "window_width": {"s0000400": 60}}
    ES = [tabled("s0000100", "Battle! Abc", 0x1000),
          tabled("s0000200", "Battle! Abcd", 0x1004, 0x2000),   # also in a window that strips nothing
          tabled("s0000300", "Battle! X", 0x1008, 0x3000),      # 0x3000: no window measures it
          tabled("s0000400", "Battle! Y", 0x1000),              # its own window_width
          entry("s0000900", "Battle! "), entry("s0000A00", "Team ")]

    def limits(self, team="Бой! ", overrides=None, english=False, lay=None):
        texts = {e["id"]: "" for e in self.ES} | {"s0000900": "Battle! ", "s0000A00": team}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / "a.po", [PoEntry(e["id"], e["text"], texts[e["id"]]) for e in self.ES], {})
            return qa.compute_limits({"layout": lay or self.LAY}, {"entries": self.ES}, qa.load_catalog(root),
                                     self.M, PACK.charmap(), overrides=overrides, english_slots=english)

    def test_check_measures_the_rest(self):
        from gen3tl.check.layout import Limit, check
        cm = PACK.charmap()
        lim = Limit("single", 60, 1, strip=["Battle! ", "Бой! "])
        self.assertEqual(check("Бой! Абвгдежзий", lim, self.M, cm), [])    # 10 x 6 after the prefix
        self.assertEqual(check("Battle! Бой! Абв", lim, self.M, cm), [])   # each in turn
        self.assertEqual(check("Бой! Абвгдежзийк", lim, self.M, cm),
                         ["line too wide: 66 > 60 px: 'Абвгдежзийк' (prefix 'Бой! ' stripped)"])
        # list order, each once; not at the start: whole
        self.assertEqual(check("Бой! Battle! Абв", lim, self.M, cm),
                         ["line too wide: 66 > 60 px: 'Battle! Абв' (prefix 'Бой! ' stripped)"])
        self.assertEqual(check("Абв Бой! Где", lim, self.M, cm), ["line too wide: 72 > 60 px: 'Абв Бой! Где'"])
        # characters and bytes of the whole text
        lim = Limit("single", 60, 1, chars=12, bytes=12, strip=["Бой! "])
        self.assertEqual(check("Бой! Абвгдежз", lim, self.M, cm),
                         ["field overflow: 13 > 12 characters", "in-place overflow: 13 > 12 bytes"])

    def test_window_rule(self):
        lims = self.limits()
        self.assertEqual({sid: lims[sid].strip for sid in ("s0000100", "s0000200", "s0000300", "s0000400")},
                         {"s0000100": ["Battle! ", "Бой! "], "s0000200": None, "s0000300": ["Battle! ", "Бой! "],
                          "s0000400": None})
        self.assertEqual(lims["s0000100"].width, 60)
        # a reference of other length never matches
        self.assertEqual(self.limits(team="Бой ")["s0000100"].strip, ["Battle! "])
        # the batch's translation of a reference, English for English
        self.assertEqual(self.limits(overrides={"s0000A00": "Битва"})["s0000100"].strip, ["Battle! ", "Битва"])
        self.assertEqual(self.limits(english=True)["s0000100"].strip, ["Battle! ", "Team "])
        # no reference in the catalog: nothing stripped
        lay = {"table_window": [dict(self.LAY["table_window"][0], strip=[{"reference": "s0000B00", "chars": 5}])]}
        self.assertIsNone(self.limits(lay=lay)["s0000100"].strip)

    def test_rules_that_differ(self):
        rule = {"name": "a", "base": 0x1000, "stride": 4, "count": 2, "width": 60,
                "strip": [{"reference": "s0000900", "chars": 8}]}
        out = qa.window_strips({"table_window": [rule, dict(rule, name="b", base=0x1004, strip=[])]})
        self.assertEqual(out, {0x1000: (("s0000900", 8),), 0x1004: (), 0x1008: ()})
