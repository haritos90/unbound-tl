from pathlib import Path
import json
import shutil
import subprocess
import tempfile
import unittest

from gen3tl.web import editorcheck, editordata
from gen3tl.check import qa
from gen3tl.catalog.catalog import load_catalog
from gen3tl.check.entrycheck import entry_problems
from gen3tl.lang.langpack import load_styles
from gen3tl.check.layout import Measure, entry_measure, line_width
from gen3tl.check.provenance import formatted
from gen3tl.catalog.po import PoEntry, write
from gen3tl.profile.profile import Profile

from test_roots import TOOLKIT_ROOT
from editorcheck_support import INV, PO, PROF, ROM, with_english
from test_roots import PROJECT_ROOT as ROOT

class FontCodeCheckTest(unittest.TestCase):
    """The browser check measures {FONT xx} and {CLEAR_TO} like check batch."""

    @classmethod
    def setUpClass(cls):
        from gen3tl.build.font import font_codes
        fonts = [dict(PROF["font"][0], codes=[1, 2]), dict(PROF["font"][1], codes=[0])]
        cls.prof = Profile({**PROF.data, "font": fonts}, Path("test.toml"))
        packs = load_styles("ru", cls.prof)
        main, small = (packs[s].glyph_slots() for s in ("unbound", "unbound-small"))
        cls.cm = packs["unbound"].charmap()
        widths = {"unbound": lambda b: main[b].width if b in main else ROM[0x100 + b],
                  "unbound-small": lambda b: small[b].width if b in small else ROM[0x400 + b]}
        cls.measure = Measure(widths["unbound"], PROF["layout"]["placeholders"], styles=widths,
                              fonts=font_codes(cls.prof))
        with tempfile.TemporaryDirectory() as tmp:
            for name, es in PO.items():
                write(Path(tmp) / name, es, {})
            catalog = load_catalog(Path(tmp))
        cls.limits = qa.compute_limits(cls.prof, INV, catalog, cls.measure, cls.cm)
        cls.doc = editordata.build("ru", cls.prof, catalog, cls.limits, cls.measure, cls.cm, packs)
        cls.by_id = with_english(cls.doc, catalog)
        latin = editorcheck.latin_widths(cls.doc["fonts"], ROM, cls.doc["rom"]["sha1"])
        cls.checker = editorcheck.Checker({k: v for k, v in cls.doc.items() if k != "entries"}, latin, PROF["qa"])

    def test_codes_in_the_data(self):
        self.assertEqual(self.doc["fonts"]["codes"], {"01": "unbound", "02": "unbound", "00": "unbound-small"})

    def test_same_as_batch_check(self):
        for sid, text in (("s0000200", "Зе{FONT 00}лье"), ("s0000300", "Сум{FONT 02}ка"),
                          ("s0000200", "Зелье{CLEAR_TO 3C}x"), ("s0000200", "Большое зелье{CLEAR_TO 3C} {FONT 00}8")):
            with self.subTest(sid=sid, text=text):
                lim = self.limits[sid]
                laid, probs = entry_problems(self.by_id[sid]["source_text"], text, lim, self.measure, self.cm)
                r = self.checker.check(self.by_id[sid], text)
                self.assertEqual(([p["message"] for p in r["problems"]], r["laid"]), (probs, laid))
                self.assertEqual(r["lines"][0][0]["width"], line_width(text, entry_measure(self.measure, lim), self.cm))
        # the small style after the code: narrower
        w = lambda t: self.checker.check(self.by_id["s0000200"], t)["lines"][0][0]["width"]   # noqa: E731
        self.assertLess(w("Зе{FONT 00}лье"), w("Зелье"))
        self.assertEqual(w("Зелье{CLEAR_TO 3C}x"), 0x3C + 6)
        self.assertTrue(any("before the column {CLEAR_TO 3C}" in formatted(p["message"]) for p in
                            self.checker.check(self.by_id["s0000200"], "Большое зелье{CLEAR_TO 3C}x")["problems"]))

class SpriteFontCheckTest(unittest.TestCase):
    """A sprite font's canvases and pair in the editor data and check."""

    @classmethod
    def setUpClass(cls):
        from test_namepairs import DEX, NAMES, fixed, hud
        tables = [{"name": t, "base": 0x6000 + 0x1000 * n, "stride": 13, "count": 4, "field_offset": 0,
                   "field_length": 13, "windows": [{"style": "unbound", "width": 96, "where": "summary"}]}
                  for n, t in enumerate(("moves", "abilities"))]
        cls.prof = Profile({**PROF.data, "table": PROF["table"] + tables, "sprite_font": [hud()]}, Path("test.toml"))
        inv = {"entries": INV["entries"] + [fixed(t, i, en) for t in ("moves", "abilities") for i, en, _ in NAMES[t]]}
        po = {**PO, "tables/moves.po": [PoEntry(f"moves:{i}", en, tr) for i, en, tr in NAMES["moves"]],
              "tables/abilities.po": [PoEntry(f"abilities:{i}", en, tr) for i, en, tr in NAMES["abilities"]],
              "tables/species.po": [PoEntry(f"species:{i}", en, tr) for i, en, tr in NAMES["species"]]}
        packs = load_styles("ru", cls.prof)
        main = packs["unbound"].glyph_slots()
        cls.cm = packs["unbound"].charmap()
        cls.measure = Measure(lambda b: main[b].width if b in main else ROM[0x100 + b], PROF["layout"]["placeholders"])
        from gen3tl.web.editorfonts import sprite_measures
        cls.measures = {n: (m, cls.cm) for n, m in sprite_measures(cls.prof, "ru").items()}
        with tempfile.TemporaryDirectory() as tmp:
            for name, es in po.items():
                write(Path(tmp) / name, es, {})
            catalog = load_catalog(Path(tmp))
        cls.limits = qa.compute_limits(cls.prof, inv, catalog, cls.measure, cls.cm)
        cls.windows = qa.Windows(cls.prof, inv, cls.measures)
        cls.doc = editordata.build("ru", cls.prof, catalog, cls.limits, cls.measure, cls.cm, packs,
                                   windows=cls.windows, pokedex=DEX)
        cls.by_id = with_english(cls.doc, catalog)
        latin = editorcheck.latin_widths(cls.doc["fonts"], ROM, cls.doc["rom"]["sha1"])
        cls.checker = editorcheck.Checker({k: v for k, v in cls.doc.items() if k != "entries"}, latin, PROF["qa"])
        cls.hud = cls.measures["dexnav-hud"][0]

    def test_the_data_carries_the_measure_the_canvas_and_the_pair(self):
        self.assertEqual(self.doc["fonts"]["sprites"], {"dexnav-hud": self.hud.data()})
        self.assertEqual((len(self.hud.table), len(self.hud.steps)), (256, 256))
        w = self.by_id["moves:2"]["window"]
        self.assertEqual(w["other"], [{"font": "dexnav-hud", "sprite": True, "width": 64, "where": "HUD move",
                                       "suffix": "/"}])
        self.assertEqual(w["pair"], {"font": "dexnav-hud", "width": 111, "where": "HUD before the eye icon",
                                     "suffix": "/", "partner": {
                                         "id": "abilities:1", "text": "Ледяные чешуйки",
                                         "width": self.hud.width("Ледяные чешуйки", self.cm),
                                         "species": {"id": "species:1", "text": "Сил"}}})
        self.assertEqual(self.by_id["abilities:2"]["window"]["pair"]["partner"]["text"], "Ошарашивание/")
        self.assertNotIn("pair", self.by_id["moves:3"]["window"])   # not a move the HUD shows
        self.assertNotIn("pair", self.by_id["species:1"]["window"])

    def test_same_as_batch_check(self):
        for sid, text in (("moves:2", "Ошарашивание"), ("moves:2", "Испуг"), ("moves:1", "Затрещина по полной"),
                          ("abilities:1", "Ледяные чешуйки"), ("abilities:1", "Чешуя"), ("moves:3", "Режущий удар")):
            with self.subTest(sid=sid, text=text):
                e = self.by_id[sid]
                laid, probs = entry_problems(e["source_text"], text, self.limits[sid], self.measure, self.cm,
                                             windows=self.windows.other(sid), measures=self.measures,
                                             pair=e["window"].get("pair"))
                r = self.checker.check(e, text)
                self.assertEqual(([p["message"] for p in r["problems"]], r["laid"]), (probs, laid))

    def test_the_canvas_and_the_pair_of_a_name(self):
        own = self.hud.width("Ошарашивание/", self.cm)
        partner = self.hud.width("Ледяные чешуйки", self.cm)
        line = self.hud.shared   # the last outline column
        r = self.checker.check(self.by_id["moves:2"], "Ошарашивание")
        self.assertEqual(r["others"], [{"font": "dexnav-hud", "where": "HUD move", "width": 64, "value": own,
                                        "over": False, "shadow": False}])
        self.assertEqual(r["pair"], {"value": own + partner + line, "width": 111, "where": "HUD before the eye icon",
                                     "partner": self.by_id["moves:2"]["window"]["pair"]["partner"]})
        self.assertGreater(own + partner + line, 111)
        self.assertEqual([formatted(p["message"]) for p in r["problems"]],
                         [f"pair too wide: {own + partner + line} > 111 px in HUD before the eye icon (dexnav-hud) "
                          f"with «Ледяные чешуйки» abilities:1, {partner} px, outline 1 px, for «Сил» species:1"])
        short = self.checker.check(self.by_id["moves:2"], "Испуг")
        self.assertEqual((short["problems"], short["pair"]["value"]),
                         ([], self.hud.width("Испуг/", self.cm) + partner + line))
        wide = "Затрещина по полной"
        n = self.hud.width(wide + "/", self.cm)
        self.assertIn(f"line too wide: {n} > 64 px in HUD move (dexnav-hud)",
                      [formatted(p["message"]) for p in self.checker.check(self.by_id["moves:1"], wide)["problems"]])
        partner_move = self.hud.width("Ошарашивание/", self.cm)
        self.assertIn(f"pair too wide: {partner_move + partner + line} > 111 px in HUD before the eye icon "
                      f"(dexnav-hud) with «Ошарашивание/» moves:2, {partner_move} px, outline 1 px, for «Сил» species:1",
                      [formatted(p["message"])
                       for p in self.checker.check(self.by_id["abilities:1"], "Ледяные чешуйки")["problems"]])
        self.assertNotIn("others", self.checker.check(self.by_id["s0000100"], "Привет"))
        self.assertNotIn("pair", self.checker.check(self.by_id["moves:2"], "中"))   # not encodable

    @unittest.skipUnless(shutil.which("node"), "no node")
    def test_the_browser_check_measures_the_glyph_drafts(self):
        """The page's drafts over the data (fonts.draftFonts) reach the check (check.checkDoc)."""
        from gen3tl.web.editorfonts import art_rows
        pack = load_styles("ru", self.prof)["unbound"]
        sheet = next(s for s in self.doc["font_sheets"]["sheets"] if s["kind"] == "sprite")
        sha = next(g for g in sheet["glyphs"] if g["char"] == "ш")
        drafts = [{"style": "unbound", "code": f"{pack.chars['ш']:02X}", "width": pack.glyphs["ш"].width + 1,
                   "rows": [r + "_" for r in art_rows(pack.glyphs["ш"], 0, 14)]},
                  {"style": sheet["style"], "code": sha["code"], "width": len(sheet["art"][str(sha["tile"])][0]) + 1,
                   "rows": [r + "_" for r in sheet["art"][str(sha["tile"])]]}]
        script = ("import fs from 'node:fs';\n"
                  f"import {{ checkDoc }} from '{(TOOLKIT_ROOT / 'web/js/check.js').as_uri()}';\n"
                  f"import {{ draftFonts }} from '{(TOOLKIT_ROOT / 'web/js/fonts.js').as_uri()}';\n"
                  "const { index, drafts } = JSON.parse(fs.readFileSync(0, 'utf8'));\n"
                  "process.stdout.write(checkDoc(draftFonts(index, drafts)));\n")
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "doc.mjs").write_text(script, encoding="utf-8")
            index = {k: v for k, v in self.doc.items() if k != "entries"}
            run = subprocess.run(["node", str(Path(tmp) / "doc.mjs")], input=json.dumps({"index": index, "drafts": drafts}),
                                 capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(run.returncode, 0, run.stderr[-2000:])
        latin = editorcheck.latin_widths(self.doc["fonts"], ROM, self.doc["rom"]["sha1"])
        drawn = editorcheck.Checker(run.stdout, latin, PROF["qa"])
        e = self.by_id["moves:2"]
        before, after = self.checker.check(e, "Ошарашивание"), drawn.check(e, "Ошарашивание")
        # ш twice adds a column in each font
        self.assertEqual(after["lines"][0][0]["width"], before["lines"][0][0]["width"] + 2)
        self.assertEqual(after["others"][0]["value"], before["others"][0]["value"] + 2)
        self.assertEqual(after["pair"]["value"], before["pair"]["value"] + 2)

    def test_the_problems_reach_the_list(self):
        problems = editordata.data_problems(self.doc, self.checker)
        self.assertTrue(any(formatted(p["message"]).startswith("pair too wide") for p in problems["moves:2"]))
        self.assertTrue(any(formatted(p["message"]).startswith("pair too wide") for p in problems["abilities:1"]))
        self.assertFalse(any(formatted(p["message"]).startswith("pair too wide") for p in problems["moves:3"]))
