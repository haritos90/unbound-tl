import copy
import tempfile
import unittest
from pathlib import Path

from gen3tl.build import spritefont as S
from gen3tl.catalog.po import PoEntry, write
from gen3tl.check import namepairs, qa
from gen3tl.check.entrycheck import pair_problems, window_problems, window_widths
from gen3tl.check.layout import Measure
from gen3tl.lang.langpack import LangPack
from gen3tl.profile.profile import Profile
from gen3tl.web.editorfonts import BlankBase, sprite_measures

from rom_support import needs_rom
from project_fixture import UNBOUND, unbound

REAL = Profile.by_name("unbound-2.1.1.1")

PACK = LangPack.load("ru", "unbound")

CM = PACK.charmap()

WINDOWS = [{"table": "moves", "width": 64, "suffix": "/", "where": "HUD move"},
           {"table": "abilities", "width": 64, "where": "HUD ability"}]

RULE = {"width": 111, "where": "HUD before the eye icon", "encounters": ["land", "water"],
        "learnsets": ["level_up", "egg"], "evidence": "A move and an ability share one line."}

def hud(**keys) -> dict:
    """The profile's HUD sprite font, its windows and pair replaced."""
    entry = copy.deepcopy(REAL["sprite_font"][0])
    entry.update({"windows": copy.deepcopy(WINDOWS), "pair": copy.deepcopy(RULE), **keys})
    return entry

def table(name, base, count=4):
    return {"name": name, "base": base, "stride": 13, "count": count, "field_offset": 0, "field_length": 13}

def fixed(name, index, text):
    return {"id": f"{name}:{index}", "offset": 0x1000 * (1 + len(name)) + 13 * index, "length": 13,
            "kind": "fixed", "category": f"table:{name}", "mode": "field", "text": text, "table": name,
            "index": index, "refs": [], "flags": []}

PROF = {"layout": {"dialogue_width": 208},
        "table": [table("moves", 0x7000), table("abilities", 0x9000), table("species", 0x8000)],
        "sprite_font": [hud()]}

NAMES = {
    "moves": [(1, "Pound", "Затрещина"), (2, "Fake Out", "Ошарашивание"), (3, "Cut", "Режущий удар")],
    "abilities": [(1, "Ice Scales", "Ледяные чешуйки"), (2, "Stench", "Зловоние")],
    "species": [(1, "Seel", "Сил"), (2, "Magikarp", "Мэджикарп"), (3, "Seel Form", "Сил-форма")],
}

INV = {"entries": [fixed(t, i, en) for t, rows in NAMES.items() for i, en, _ in rows]}

DEX = {
    "species": [
        {"slot": 1, "name": "species:1", "abilities": [1, 2], "learnset_species": 1,
         "learnset": [{"method": 0, "move": 1}, {"method": 2, "move": 2}, {"method": 1, "move": 3}]},
        {"slot": 2, "name": "species:2", "abilities": [1], "learnset_species": 2,
         "learnset": [{"method": 0, "move": 2}]},
        {"slot": 3, "name": "species:3", "abilities": [2], "learnset_species": 1,
         "learnset": [{"method": 0, "move": 1}]},
    ],
    "moves": [{"id": i, "name": f"moves:{i}"} for i, _, _ in NAMES["moves"]],
    "abilities": [{"id": i, "name": f"abilities:{i}"} for i, _, _ in NAMES["abilities"]],
    "encounters": [{"species": 1, "method": "land"}, {"species": 2, "method": "fishing"},
                   {"species": 3, "method": "water"}],
}

def measures(prof=PROF) -> dict:
    return {name: (m, CM) for name, m in sprite_measures(prof, "ru").items()}

def texts(translated=True) -> dict[str, str]:
    return {f"{t}:{i}": tr if translated else en for t, rows in NAMES.items() for i, en, tr in rows}

class SpriteMeasureTest(unittest.TestCase):
    """The cursor's travel: the advance per byte, or each byte's step where a pack tile is drawn."""


    def test_the_plan_measures_as_the_routine_steps(self):
        font = S.from_profile(REAL)[0]
        plan = S.plan(font, BlankBase(), LangPack.load("ru", font.style, rows=font.cell_rows, top=0))
        m = S.measure(plan)
        for text in ("Uproar/", "Skill Link", "Шум и гам/", "Мозаичные глаза", "Z-Атака 3"):
            with self.subTest(text=text):
                data = CM.encode(text, terminate=False)
                self.assertEqual(m.width(text, CM), S.text_width(plan, data) - font.shared)
        self.assertEqual(m.width("Skill Link", CM), 40)   # 4 px a byte, the space too
        self.assertEqual(m.width("А Б", CM) - m.width("АБ", CM), plan.advances[CM.encode(" ", terminate=False)[0]])
        self.assertEqual(sprite_measures(REAL, "ru")[font.name].data(), m.data())

class SpriteWindowTest(unittest.TestCase):
    """A sprite font's canvases join the tables they name and measure each name with its suffix."""

    def test_the_canvases_join_their_tables(self):
        windows = qa.Windows(PROF, INV, measures())
        self.assertEqual(windows.other("moves:2"), [{"font": "dexnav-hud", "sprite": True, "width": 64,
                                                     "where": "HUD move", "suffix": "/"}])
        self.assertEqual(windows.other("abilities:1"), [{"font": "dexnav-hud", "sprite": True, "width": 64,
                                                         "where": "HUD ability"}])
        self.assertEqual(windows.other("species:1"), [])
        self.assertIsNone(windows.width("moves:2", None))
        self.assertEqual(PROF["table"][0].get("windows"), None)   # the profile stays as it is
        with self.assertRaisesRegex(ValueError, "no \\[\\[table\\]\\] moves"):
            qa.Windows({"sprite_font": PROF["sprite_font"]}, INV)

    def test_a_name_too_wide_for_its_canvas(self):
        windows, m = qa.Windows(PROF, INV, measures()), measures()["dexnav-hud"][0]
        long = "Ошарашивание до упаду"
        self.assertEqual(windows.problems("moves:2", "Ошарашивание"), [])
        n = m.width(long + "/", CM)
        self.assertGreater(n, 64)
        self.assertEqual(windows.problems("moves:2", long), [f"line too wide: {n} > 64 px in HUD move (dexnav-hud)"])
        self.assertEqual(window_widths(long, windows.other("moves:2"), windows.measures),
                         [{"font": "dexnav-hud", "where": "HUD move", "width": 64, "value": n, "over": True,
                           "shadow": False}])
        self.assertEqual(window_problems(long, windows.other("moves:2"), {}), [])   # no measure, no check
        style = {"dexnav-hud": (Measure(lambda b: 9, {}), CM)}
        self.assertEqual(window_problems(long, windows.other("moves:2"), style), [])   # not a sprite measure

    def test_profile_declares_the_canvases_and_the_pair(self):
        font = S.from_profile(REAL)[0]
        self.assertEqual([(w.table, w.width, w.suffix) for w in font.windows], [("moves", 64, "/"), ("abilities", 64, "")])
        self.assertEqual((font.pair.width, font.pair.encounters, font.pair.learnsets),
                         (111, ["land", "water"], ["level_up", "egg"]))

class PairTest(unittest.TestCase):
    """The widest pair of every species the encounters meet, and of every name."""

    def test_species_names(self):
        rule = S.from_profile(PROF)[0].pair
        self.assertEqual(namepairs.species_names(DEX, rule), [("species:1", [1, 2], [1, 2]),
                                                              ("species:3", [1, 2], [2])])

    def test_widest_pairs_and_partners(self):
        m = measures()["dexnav-hud"][0]
        w = {sid: m.width(t + ("/" if sid.startswith("moves") else ""), CM) for sid, t in texts().items()}
        [res] = namepairs.results(PROF, texts(), measures(), DEX)
        self.assertEqual((res.font, res.width, res.where, res.suffix),
                         ("dexnav-hud", 111, "HUD before the eye icon", {"moves": "/", "abilities": ""}))
        widest = res.widest["species:1"]
        self.assertEqual((widest.first.id, widest.second.id, widest.width),
                         ("moves:2", "abilities:1", w["moves:2"] + w["abilities:1"] + m.shared))
        self.assertEqual(m.shared, 1)   # the last outline column counts
        self.assertEqual(widest.first.text, "Ошарашивание/")
        self.assertGreater(widest.width, 111)
        self.assertEqual([p.species for p in res.over()], ["species:1"])
        self.assertEqual(res.widest["species:3"].second.id, "abilities:2")
        self.assertEqual(res.names["abilities:2"].first.id, "moves:2")
        self.assertNotIn("moves:3", res.names)   # a TM move, not shown
        self.assertEqual(namepairs.partner(res, "moves:1", lambda x: "key:" + x), {
            "font": "dexnav-hud", "width": 111, "where": "HUD before the eye icon", "suffix": "/",
            "partner": {"id": "key:abilities:1", "text": "Ледяные чешуйки", "width": w["abilities:1"],
                        "species": {"id": "key:species:1", "text": "Сил"}}})
        self.assertEqual(namepairs.partner(res, "abilities:1")["partner"]["text"], "Ошарашивание/")
        self.assertIsNone(namepairs.partner(res, "species:1"))
        self.assertEqual(namepairs.results(PROF, texts(), {}, DEX), [])   # no measure
        self.assertEqual(namepairs.results(PROF, texts(), measures(), None), [])   # no dataset
        self.assertEqual(namepairs.results({}, texts(), measures(), DEX), [])   # no sprite font

    def test_the_editor_problem_names_the_partner(self):
        [res] = namepairs.results(PROF, texts(), measures(), DEX)
        pair = namepairs.partner(res, "moves:2")
        n = res.names["moves:2"].width
        self.assertEqual(pair_problems("Ошарашивание", pair, measures()),
                         [f"pair too wide: {n} > 111 px in HUD before the eye icon (dexnav-hud) with "
                          f"«Ледяные чешуйки» abilities:1, {pair['partner']['width']} px, outline 1 px, "
                          f"for «Сил» species:1"])
        self.assertEqual(pair_problems("Удар", pair, measures()), [])
        self.assertEqual(pair_problems("Ошарашивание", None, measures()), [])
        self.assertEqual(pair_problems("Ошарашивание", pair, {}), [])

    def test_rule_needs_both_windows_and_known_methods(self):
        for keys, error in (({"windows": WINDOWS[:1]}, "pair needs the windows of moves and abilities"),
                            ({"pair": {**RULE, "learnsets": ["level_up", "trade"]}}, "pair learnsets name"),
                            ({"pair": {**RULE, "encounters": []}}, "pair encounters must list"),
                            ({"pair": {k: v for k, v in RULE.items() if k != "evidence"}}, "pair needs exactly"),
                            ({"windows": WINDOWS + WINDOWS[:1]}, "one window per table"),
                            ({"windows": [{"table": "moves", "width": 64}]}, "a window needs table, width"),
                            ({"windows": [{**WINDOWS[0], "width": 0}]}, "width must be an integer")):
            with self.subTest(error=error), self.assertRaisesRegex(S.SpriteFontError, error):
                S.parse(hud(**keys))
        entry = hud()
        del entry["pair"], entry["windows"]
        self.assertEqual((S.parse(entry).windows, S.parse(entry).pair), ([], None))

class QaPairTest(unittest.TestCase):
    """QA reports each species whose widest pair runs past the width, named by the species."""

    def run_qa(self, **kw):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for t, rows in NAMES.items():
                write(root / "tables" / f"{t}.po", [PoEntry(f"{t}:{i}", en, tr) for i, en, tr in rows], {})
            return qa.run(PROF, INV, root, CM, Measure(lambda b: 6, {}), set(PACK.glyph_slots()),
                          windows=qa.Windows(PROF, INV, measures()), **kw)

    def test_one_finding_per_species_past_the_width(self):
        [res] = namepairs.results(PROF, texts(), measures(), DEX)
        gate = self.run_qa(pokedex=DEX)
        pairs = [f for f in gate.findings if f.message.startswith("pair too wide")]
        self.assertEqual([(f.id, f.severity) for f in pairs], [("species:1", "error")])
        self.assertTrue(pairs[0].file.endswith("species.po"))
        self.assertEqual(pairs[0].message, namepairs.message(res, res.widest["species:1"]))
        self.assertRegex(pairs[0].message, r"^pair too wide: \d+ > 111 px in HUD before the eye icon \(dexnav-hud\): "
                                           r"«Ошарашивание/» moves:2, \d+ px, and «Ледяные чешуйки» abilities:1, "
                                           r"\d+ px, outline 1 px, for «Сил»$")
        self.assertIn("| error | pair too wide | 1 |", qa.report(gate))

    def test_without_a_dataset_or_with_the_english(self):
        self.assertFalse(any(f.message.startswith("pair") for f in self.run_qa().findings))
        gate = self.run_qa(pokedex=DEX, source_as_translation=True)
        self.assertFalse(any(f.message.startswith("pair") for f in gate.findings))   # the English fits


@needs_rom
class RepositoryPairTest(unittest.TestCase):
    """Every species name past the width carries a pair past it."""

    def test_species_and_names_agree(self):
        from gen3tl.catalog.catalog import load_catalog
        prof = unbound()
        catalog = load_catalog(UNBOUND / "translation/ru/po", prof)
        shown = {sid: e.msgstr or e.msgid for sid, (_, e) in catalog.items()}
        [res] = namepairs.results(prof, shown, measures(prof), namepairs.dataset(prof))
        self.assertGreater(len(res.widest), 300)
        over = res.over()
        past = {sid for sid, p in res.names.items() if p.width > res.width}
        self.assertLessEqual({n.id for p in over for n in (p.first, p.second)}, past)
        for sid in past:
            pair = res.names[sid]
            with self.subTest(sid=sid):
                self.assertIn(pair.species, {p.species for p in over})
                self.assertGreaterEqual(res.widest[pair.species].width, pair.width)
