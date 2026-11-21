import tempfile
import unittest
from pathlib import Path
from unittest import mock

from gen3tl.check import qa
from gen3tl.lang.langpack import LangPack
from gen3tl.check.layout import Limit, Measure, check
from gen3tl.catalog.extract import english
from gen3tl.catalog.po import PoEntry, write

from rom_support import source_text, needs_rom, rom_path
from test_roots import PROJECT_ROOT as ROOT
import qa_support
from project_fixture import ENGLISH, unbound
from qa_support import BoxWidthTest, PACK, TableWindowTest, batch_messages, entry, fixed, scripted, setUpModule, slot, tabled, tearDownModule

@needs_rom
class TrainerNameFillTest(unittest.TestCase):
    """Battle text measures inserted trainer names at the widest name."""

    TOKENS = ("B_TRAINER1_NAME", "FD 2F", "FD 33")

    @classmethod
    def setUpClass(cls):
        from gen3tl.discover import inventory as inv_mod
        from gen3tl.build.font import FontTable
        from gen3tl.profile.profile import Profile
        cls.prof = unbound()
        cls.rom = cls.prof.load_rom(rom_path())
        cls.inv = inv_mod.load(ROOT / "build" / "inventory.json")
        font = FontTable.from_profile(cls.prof)[0]
        pack = LangPack.load("ru", cls.prof["font_style"]["style"])
        slots = pack.glyph_slots(cls.rom, font)
        cls.cm = pack.charmap()
        cls.m = Measure(lambda b: slots[b].width if b in slots else font.width(cls.rom, b),
                        cls.prof["layout"]["placeholders"])

    def test_widths_are_the_widest_names(self):
        from gen3tl.catalog.po import read
        po = ROOT / "translation" / "ru" / "po" / "tables" / "trainer_names.po"
        names = read(po)[1]
        english(names, ENGLISH)
        ru = max((self.m.width(e.msgstr, self.cm), e.msgstr) for e in names if e.msgstr.strip() and not e.fuzzy)
        en = max((self.m.width(e.msgid, self.cm), e.msgid) for e in names if e.msgid.strip())
        self.assertEqual((ru, en), ((66, "Рей и Тайра"), (67, "Bryce & Mag")))
        rules = [r for r in self.prof["layout"]["code_fill"] if set(r["slots"]) & set(self.TOKENS)]
        self.assertEqual({t: (s["width"], s["source_width"]) for r in rules for t, s in r["slots"].items()},
                         dict.fromkeys(self.TOKENS, (66, 67)))
        self.assertEqual({t: self.m.ph.get(t) for t in self.TOKENS}, dict.fromkeys(self.TOKENS, 66))

    def test_every_host_measures_them(self):
        hosts = {e["id"]: e for e in self.inv["entries"]
                 if e["mode"] == "battle" and any("{%s}" % t in e["text"] for t in self.TOKENS)}
        self.assertEqual(len(hosts), 34)
        ids = list(hosts) + ["s1F56BEB"]   # the raid partner, field {FD 07}
        by_id = {e["id"]: e for e in self.inv["entries"]}
        catalog = {sid: (Path("battle.po"), PoEntry(sid, by_id[sid]["text"], "")) for sid in ids}
        ru = qa.compute_limits(self.prof, self.inv, catalog, self.m, self.cm, rom=self.rom)
        en = qa.compute_limits(self.prof, self.inv, catalog, self.m, self.cm, english_slots=True, rom=self.rom)
        for sid, e in hosts.items():
            want = [t for t in self.TOKENS if "{%s}" % t in e["text"]]
            with self.subTest(sid=sid):
                self.assertEqual({t: (ru[sid].placeholders or {}).get(t) for t in want}, dict.fromkeys(want, 66))
                self.assertEqual({t: (en[sid].placeholders or {}).get(t) for t in want}, dict.fromkeys(want, 67))
        self.assertEqual(ru["s1F56BEB"].placeholders, {"FD 07": 60})


@needs_rom
class TrainerClassFillTest(unittest.TestCase):
    """{FD 2E} and {FD 32} take their class from the class helper."""

    WIDTHS = {"FD 2E": (88, 117), "FD 32": (72, 87)}
    setUpClass = TrainerNameFillTest.__dict__["setUpClass"]   # the same measure

    def test_class_helper_calls(self):
        def bl(at):   # target of the THUMB BL at a ROM offset
            hi, lo = self.rom.u16(at) & 0x7FF, self.rom.u16(at + 2) & 0x7FF
            return 0x08000000 + at + 4 + ((hi - 0x800 if hi & 0x400 else hi) << 12) + (lo << 1)
        # switch of BattleStringExpandPlaceholders: FD 1C, 2E, 32
        cases = {n: 0x089BD0D0 + 2 * self.rom.u16(0x9BD0D0 + 2 * n) for n in (0x1C, 0x2E, 0x32)}
        self.assertEqual(cases, {0x1C: 0x089BD484, 0x2E: 0x089BD7BC, 0x32: 0x089BD916})
        self.assertEqual((bl(0x9BD498), bl(0x9BD926)), (0x089BCEF8, 0x089BCEF8))

    def test_widths_are_the_widest_classes(self):
        from gen3tl.catalog.po import read
        po = ROOT / "translation" / "ru" / "po" / "tables" / "trainer_classes.po"
        names = read(po)[1]
        english(names, ENGLISH)
        names = [e for e in names if e.msgid.strip()]
        fixed = [e for e in names if e.msgctxt.startswith("table:trainer_classes/")]
        self.assertEqual((len(names), len(fixed)), (106, 97))
        self.assertEqual(max(self.m.width(e.msgstr, self.cm) for e in names if not e.fuzzy), 107)
        en = max((self.m.width(e.msgid, self.cm), e.msgid) for e in names)
        en_fixed = max(self.m.width(e.msgid, self.cm) for e in fixed)
        self.assertEqual((en, en_fixed, self.m.width(source_text('s0A4CAC1'), self.cm)),
                         ((117, source_text('s1FA1EF5')), 72, 87))
        rules = [r for r in self.prof["layout"]["code_fill"] if set(r["slots"]) & set(self.WIDTHS)]
        self.assertEqual({t: (s["width"], s["source_width"]) for r in rules for t, s in r["slots"].items()}, self.WIDTHS)
        ph = self.prof["layout"]["placeholders"]
        self.assertEqual({t: self.m.ph.get(t) for t in self.WIDTHS}, {t: w[0] for t, w in self.WIDTHS.items()})
        self.assertEqual((ph["B_TRAINER1_CLASS"], "B_TRAINER2_CLASS" in ph), (88, False))

    def test_every_host_measures_them(self):
        hosts = {e["id"]: e for e in self.inv["entries"]
                 if e["mode"] == "battle" and any("{%s}" % t in e["text"] for t in self.WIDTHS)}
        self.assertEqual(len(hosts), 13)
        catalog = {sid: (Path("battle.po"), PoEntry(sid, e["text"], "")) for sid, e in hosts.items()}
        ru = qa.compute_limits(self.prof, self.inv, catalog, self.m, self.cm, rom=self.rom)
        en = qa.compute_limits(self.prof, self.inv, catalog, self.m, self.cm, english_slots=True, rom=self.rom)
        for sid, e in hosts.items():
            want = [t for t in self.WIDTHS if "{%s}" % t in e["text"]]
            with self.subTest(sid=sid):
                self.assertEqual({t: (ru[sid].placeholders or {}).get(t) for t in want},
                                 {t: self.WIDTHS[t][0] for t in want})
                self.assertEqual({t: (en[sid].placeholders or {}).get(t) for t in want},
                                 {t: self.WIDTHS[t][1] for t in want})


@needs_rom
class TradeOfferFillTest(unittest.TestCase):
    """The Union Room trade offer measures F7 fields at their producers."""

    setUpClass = TrainerNameFillTest.__dict__["setUpClass"]   # the same measure
    SID = "s0457D44"

    def limit(self, text):
        entry = next(e for e in self.inv["entries"] if e["id"] == self.SID)
        catalog = {self.SID: (Path("system.po"), PoEntry(self.SID, entry["text"], text))}
        return qa.compute_limits(self.prof, self.inv, catalog, self.m, self.cm, rom=self.rom)[self.SID]

    def test_producer_bounds_reject_the_unwrapped_full_word(self):
        unwrapped = ("Вам предлагают обменять\\nвыставленного покемона\\p{F7 01} (уровень {F7 00}) "
                     "на покемона\\n{F7 03} (уровень {F7 02}).\\pПринять это предложение?")
        lim = self.limit(unwrapped)
        self.assertEqual(lim.placeholders, {"F7 00": 18, "F7 01": 60, "F7 02": 18, "F7 03": 60})
        self.assertTrue(any("212 > 208" in p for p in check(unwrapped, lim, self.m, self.cm)))


@needs_rom
class LimitSourceTest(unittest.TestCase):
    """Where each limit comes from (Limit.sources). Every glyph is 6 px."""

    def limits(self, prof, inv, ctx=None, tags=None):
        from gen3tl.catalog.catalog import load_catalog
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / "system" / "a.po", [PoEntry(x["id"], x["text"], "", extracted=(tags or {}).get(x["id"], []))
                                             for x in inv["entries"]], {})
            catalog = load_catalog(root)
            return qa.compute_limits(prof, inv, catalog, Measure(lambda b: 6, {}), PACK.charmap(), ctx), catalog

    @staticmethod
    def src(lim, field="width"):
        s = lim.sources[field]
        return s["kind"], s["rule"]

    def test_measured_windows_and_the_english(self):
        lims, _ = self.limits(TableWindowTest.PROF, TableWindowTest.INV)
        self.assertEqual({sid: self.src(l) for sid, l in lims.items()}, {
            "s0000100": ("measured", "[[layout.table_window]] descs"),
            "s0000200": ("measured", "[[layout.table_window]] descs"),
            "s0000300": ("source", "the English: its widest line"),   # past the table: its own run
            "s0000400": ("measured", "[[layout.table_window]] descs"),
            "s0000500": ("measured", "[[layout.table_window]] other"),    # the narrower of two
            "s0000600": ("source", "the English: its widest line")})
        self.assertEqual(lims["s0000100"].sources["lines"]["kind"], "source")   # a single-line English
        # a shorter string of the run: the run's widest English
        inv = {"entries": [tabled("s0000700", "Ab", 0x3000), tabled("s0000800", "Abcdef", 0x3004)]}
        lims, _ = self.limits({"layout": {}}, inv)
        self.assertEqual((lims["s0000700"].width, self.src(lims["s0000700"])),
                         (36, ("source", "the English: the widest line of its pointer-table run")))

    def test_message_boxes_and_profile_widths(self):
        lims, _ = self.limits(BoxWidthTest.PROF, BoxWidthTest.INV, BoxWidthTest.CTX)
        self.assertEqual({sid: self.src(l) for sid, l in lims.items()}, {
            "s0000100": ("measured", "[layout.box_width] dialogue: the message box, measured in game"),
            "s0000200": ("measured", "[layout.box_width] sign: the message box, measured in game"),
            "s0000300": ("profile", "[layout] dialogue_width"),
            "s0000400": ("measured", "[layout.box_width] battle: the message box, measured in game"),
            "s0000450": ("source", "the English: its widest line"),     # 108 px: wider than 60, inside 120
            "s0000500": ("measured", "[layout.window_width] s0000500: measured in game"),
            "s0000600": ("source", "the English: its widest line")})
        self.assertEqual(self.src(lims["s0000100"], "lines"), ("measured", "two lines per message box"))
        self.assertEqual(self.src(lims["s0000600"], "lines"), ("source", "the English: its line count"))

    def test_window_evidence_field_bytes_and_host(self):
        prof = {"layout": {"dialogue_width": 100, "label_min_width": 30,
                           "table_window": [{"name": "descs", "base": 0x1000, "stride": 4, "count": 1, "width": 50,
                                             "where": "bag", "evidence": "ruler in the bag", "chars": 8}]},
                "table": [{"name": "names", "base": 0x5000, "stride": 11, "count": 2, "field_length": 11,
                           "evidence": "names at stride 11",
                           "windows": [{"style": "unbound", "width": 60, "where": "summary", "evidence": "Талонфлейм"}]},
                          {"name": "keys", "base": 0x6000, "stride": 8, "count": 1, "field_length": 8,
                           "terminated": False}],
                "font_style": {"style": "unbound"}}
        vmsg = entry("s0000300", "Wait")
        vmsg.update(flags=["in-place-only"], refs=[{"at": 0x10, "kind": "script:vmessage"}])
        inv = {"entries": [tabled("s0000100", "Ab", 0x1000), fixed("names:1", "Ivysaur"), fixed("keys:0", "abc", "keys"),
                           vmsg, scripted("s0000400", "Take {STR_VAR_1}."),
                           scripted("s0000500", "Potion", "script:bufferstring")]}
        ctx = {"strings": {"s0000400": slot(("string", "s0000500")), "s0000500": {"fills": [["s0000400", "{STR_VAR_1}"]]}}}
        lims, _ = self.limits(prof, inv, ctx)
        s = lims["s0000100"].sources
        self.assertEqual((s["width"], s["chars"]["rule"]), (
            {"kind": "measured", "rule": "[[layout.table_window]] descs: bag", "evidence": "ruler in the bag"},
            "[[layout.table_window]] descs: bag"))
        s = lims["names:1"].sources
        self.assertEqual((s["width"]["rule"], s["width"]["evidence"], s["chars"]["rule"]),
                         ("[[table]] names window: summary", "Талонфлейм",
                          "[[table]] names: a field of 11 bytes with the terminator"))
        kind, rule = self.src(lims["keys:0"])
        self.assertEqual(kind, "source")
        self.assertRegex(rule, r"^the English: the widest line of .*/system/a\.po$")
        self.assertEqual(lims["keys:0"].sources["chars"]["rule"], "[[table]] keys: a field of 8 bytes")
        self.assertEqual(self.src(lims["s0000300"], "bytes"), (
            "measured", "in place: its 5 bytes with the terminator, a reference the build cannot rewrite "
                        "(script:vmessage)"))
        # a declared table-base field binds
        member = entry("s0000700", "Lum")
        member.update(length=7, flags=["in-place-only"], refs=[{"at": 0x20, "kind": "table-base"}])
        decl = {"pointers": [0x20], "id": "s0000700", "stride": 0x1C, "count": 1, "evidence": "berries",
                "length": 7, "length_evidence": "name[7]"}
        tl, _ = self.limits({"layout": {}, "strings": {"table_base": [decl]}}, {"entries": [member]})
        self.assertEqual((tl["s0000700"].bytes, tl["s0000700"].sources["bytes"]), (6, {
            "kind": "measured", "rule": "[[strings.table_base]] s0000700: in place in its 7-byte field "
                                        "with the terminator", "evidence": "name[7]"}))
        # an inserted word takes the source of its host's window
        self.assertEqual(lims["s0000500"].host, "s0000400")
        self.assertEqual(self.src(lims["s0000500"]),
                         ("profile", "the window of s0000400, which inserts it: [layout] dialogue_width"))

    def test_box_binding(self):
        boxes = {"dialogue": 208, "sign": 200, "battle": 222}
        self.assertEqual(qa.box_binding(boxes, "dialogue", [{"event": "sign", "box": None}]), ("sign", 200))
        self.assertEqual(qa.box_binding(boxes, "battle", []), ("battle", 222))
        self.assertIsNone(qa.box_binding(boxes, "single", []))

    def test_window_rules(self):
        lay = TableWindowTest.PROF["layout"]
        self.assertEqual([(at, w, n, r["name"]) for at, w, n, r in qa.window_rules(lay)][:2],
                         [(0x1000, 30, None, "descs"), (0x1004, 30, None, "descs")])
        self.assertEqual(qa.window_texts(lay), [(at, w, n) for at, w, n, _ in qa.window_rules(lay)])

    def test_unmeasured_report(self):
        inv = {"entries": TableWindowTest.INV["entries"] + [fixed("keys:0", "abc", "keys")]}
        prof = {**TableWindowTest.PROF, "table": [{"name": "keys", "base": 0x6000, "stride": 8, "count": 1,
                                                   "field_length": 8}]}
        lims, catalog = self.limits(prof, inv, tags={"s0000600": ["reach: never shown (review: no caller)"]})
        lims["keys:0"].keys = 8   # a keyboard row: the keys bind
        text, n = qa.unmeasured_report(catalog, lims)
        self.assertEqual(n, 1)
        self.assertIn("/system/a.po | 1 | 0 |", text)
        self.assertIn("| s0000300 | single | 60 | 1 | the English: its widest line | Abcdefghij |", text)
        self.assertIn("1 more entries tagged never shown are left out", text)
        self.assertNotIn("keys:0", text)


@needs_rom
class InsertedTitleRegressionTest(unittest.TestCase):
    """s1F8D540 inserts the Frontier titles into the 208 px box."""

    IDS = ["s1F8D540", "s1F8DD26", "s1F8BED5", "s1F8D227", "s1F9BDDD", "s1F8DD33", "s1F8BEE7", "s1F8DD36",
           "s1F8BEEB"]
    RU = {"s1F8D540": "Поздравляем с серией побед, претендент!\\p{STR_VAR_1} передаёт: {STR_VAR_2} в восторге "
                      "от вас.\\p{STR_VAR_3} видит ваше мастерство - вот {STR_VAR_2} и бросает вызов!\\p"
                      "{STR_VAR_1} ждёт. Готовы сразиться?",
          "s1F8BED5": "Инспектор манежа", "s1F8DD26": "Башенный магнат", "s1F8DD33": "он", "s1F8BEE7": "она",
          "s1F8DD36": "Он", "s1F8BEEB": "Она"}

    @classmethod
    def setUpClass(cls):
        from gen3tl.discover import inventory as inv_mod
        from gen3tl.build.font import FontTable
        from gen3tl.discover.context import build_context
        from gen3tl.profile.profile import Profile
        cls.prof = unbound()
        rom = cls.prof.load_rom(rom_path())
        cls.rom = rom   # the record rules read it
        cls.inv = inv_mod.load(ROOT / "build" / "inventory.json")
        cls.ctx = build_context(rom, cls.prof, cls.inv)
        font = FontTable.from_profile(cls.prof)[0]
        pack = LangPack.load("ru", cls.prof["font_style"]["style"])
        slots = pack.glyph_slots(rom, font)
        cls.cm = pack.charmap()
        cls.m = Measure(lambda b: slots[b].width if b in slots else font.width(rom, b),
                        cls.prof.get("layout", {}).get("placeholders", {}))
        by_id = {e["id"]: e for e in cls.inv["entries"]}
        cls.catalog = {sid: (Path("maps/battle-circus.po"), PoEntry(sid, by_id[sid]["text"], cls.RU.get(sid, "")))
                       for sid in cls.IDS}

    def test_titles_reach_the_slot_and_box_4_is_broken(self):
        from gen3tl.check.layout import check, entry_measure, layout, lines_of, paragraphs, slot_rewraps
        rec = self.ctx["strings"]["s1F8D540"]["slots"]
        self.assertEqual({f[1] for f in rec["{STR_VAR_1}"]["fills"]}, {"s1F8DD26", "s1F8BED5", "s1F8D227", "s1F9BDDD"})
        self.assertEqual({f[1] for f in rec["{STR_VAR_2}"]["fills"]}, {"s1F8DD33", "s1F8BEE7"})
        self.assertEqual({f[1] for f in rec["{STR_VAR_3}"]["fills"]}, {"s1F8DD36", "s1F8BEEB"})
        text = self.RU["s1F8D540"]
        old = qa.compute_limits(self.prof, self.inv, self.catalog, self.m, self.cm, rom=self.rom)["s1F8D540"]
        lim = qa.compute_limits(self.prof, self.inv, self.catalog, self.m, self.cm, self.ctx, rom=self.rom)["s1F8D540"]
        # without context: 208 px box, 60 px per slot.
        # box 4 stays on one line.
        self.assertEqual(old.width, 208)
        self.assertEqual(check(layout(text, old, self.m, self.cm), old, self.m, self.cm), [])
        self.assertEqual(paragraphs(layout(text, old, self.m, self.cm))[3], "{STR_VAR_1} ждёт. Готовы сразиться?")
        # with context: the 208 px box and the title's width
        self.assertEqual(lim.width, 208)
        self.assertEqual(lim.placeholders["STR_VAR_1"], self.m.width("Инспектор манежа", self.cm))
        self.assertEqual(lim.placeholders["STR_VAR_1"], 95)
        self.assertIn("s1F8BED5 'Инспектор манежа'", lim.slot_sources["STR_VAR_1"])
        real = entry_measure(self.m, lim)
        self.assertEqual(real.width("{STR_VAR_1} ждёт. Готовы сразиться?", self.cm), 237)
        laid = layout(text, lim, self.m, self.cm)
        self.assertEqual(check(laid, lim, self.m, self.cm), [])
        self.assertTrue(all(real.width(l, self.cm) <= 208 for par in paragraphs(laid) for l in lines_of(par)))
        self.assertEqual(lines_of(paragraphs(laid)[3]), ["{STR_VAR_1} ждёт.", "Готовы сразиться?"])
        warn = slot_rewraps(text, lim, self.m, self.cm)
        self.assertTrue(any("box 4: 237 > 208 px" in w and "s1F8BED5 'Инспектор манежа'" in w for w in warn))
        # kept on one line as built; reported with slot value
        probs = check(text, qa.Limit("single", lim.width, 1, placeholders=lim.placeholders,
                                     slot_sources=lim.slot_sources), self.m, self.cm)
        self.assertIn("line too wide: 237 > 208 px: '{STR_VAR_1} ждёт. Готовы сразиться?' with {STR_VAR_1} = "
                      "95 px (s1F8BED5 'Инспектор манежа')", probs)

    def test_preposition_moves_down_with_its_word(self):
        # a short preposition joins the next word
        from gen3tl.check.layout import layout, lines_of, paragraphs
        lim = qa.compute_limits(self.prof, self.inv, self.catalog, self.m, self.cm, self.ctx, rom=self.rom)["s1F8D540"]
        self.assertEqual(lim.source_lines, [2, 2, 2, 2])
        text = self.RU["s1F8D540"]
        self.assertEqual(lines_of(paragraphs(layout(text, lim, self.m, self.cm, keep=False))[1]),
                         ["{STR_VAR_1} передаёт: {STR_VAR_2} в", "восторге от вас."])
        self.assertEqual(lines_of(paragraphs(layout(text, lim, self.m, self.cm))[1]),
                         ["{STR_VAR_1} передаёт: {STR_VAR_2}", "в восторге от вас."])

    def test_title_takes_the_width_of_its_host_sentence(self):
        old = qa.compute_limits(self.prof, self.inv, self.catalog, self.m, self.cm, rom=self.rom)["s1F8BED5"]
        lim = qa.compute_limits(self.prof, self.inv, self.catalog, self.m, self.cm, self.ctx, rom=self.rom)["s1F8BED5"]
        self.assertEqual((old.kind, old.width), ("single", 92))   # the English Circus Ringmaster
        self.assertEqual((lim.kind, lim.width, lim.host), ("single", 208, "s1F8D540"))
        self.assertEqual(qa.check("Инспектор манежа", lim, self.m, self.cm), [])


@needs_rom
class BattlePrefixWidthTest(unittest.TestCase):
    """Prefixed battle names measured with the «Противник» and «Дикий покемон» prefixes."""

    @classmethod
    def setUpClass(cls):
        from gen3tl.build.font import FontTable
        from gen3tl.profile.profile import Profile
        prof = unbound()
        rom = prof.load_rom(rom_path())
        font = FontTable.from_profile(prof)[0]
        pack = LangPack.load("ru", prof["font_style"]["style"])
        slots = pack.glyph_slots(rom, font)
        cls.cm = pack.charmap()
        cls.m = Measure(lambda b: slots[b].width if b in slots else font.width(rom, b),
                        prof.get("layout", {}).get("placeholders", {}))

    def test_token_holds_the_widest_prefixed_name(self):
        widest = max(self.m.width(p + "Хелиоптайл", self.cm)
                     for p in ("Противник ", "Дикий покемон ", "Покемон Теней "))
        for tok in ("B_ATK_NAME_WITH_PREFIX", "B_DEF_NAME_WITH_PREFIX", "B_SCR_ACTIVE_NAME_WITH_PREFIX"):
            self.assertEqual(self.m.width("{" + tok + "}", self.cm), widest, tok)

    def test_battle_line_with_the_widest_name(self):
        from gen3tl.check.layout import Limit, check, layout
        lim = Limit("battle", 208, 2)
        line = "{B_DEF_NAME_WITH_PREFIX} теряет боевую способность!"
        laid = layout(line, lim, self.m, self.cm)
        self.assertEqual(check(laid, lim, self.m, self.cm), [])
        self.assertEqual(laid.count("\\n"), 1)


@needs_rom
class FrontierRecordFillTest(qa_support.LabelWindowTest):
    """The frontier record texts take the widest tier name and format."""

    REST = ("\\pБоёв в серии: {COLOR 06}{FD 0B}{COLOR 08}.\\pБои шли на уровне {COLOR 06}{STR_VAR_3}{COLOR 08},"
            "\\nа {COLOR 06}инверсные битвы{COLOR 08}\\lбыли {COLOR 06}{FD 07}{COLOR 08}.\\pВ боях участвовали:"
            "\\n-{COLOR 06}{FD 08}{COLOR 08}\\l-{COLOR 06}{FD 09}{COLOR 08}\\l-{COLOR 06}{FD 0A}{COLOR 08}")
    RECORD = ("{COLOR 06}{FD 0C}{COLOR 08} рекорд установлен\\nв категории\\l{COLOR 06}{STR_VAR_1}{COLOR 08},"
              "\\lвид боя -\\l{COLOR 06}{STR_VAR_2}{COLOR 08}." + REST)
    CASES = {
        "s1F8E9AE": (208, None, RECORD, True),
        "s1F8C8FD": (208, None, "Вид боя с этим тренером - {COLOR 06}{FD 08}{COLOR 02}, категория - "
                                "{COLOR 06}{FD 07}{COLOR 02}.\\pУровень команды - {COLOR 06}{FD 09}{COLOR 02}, "
                                "инверсные битвы {COLOR 06}{FD 0B}{COLOR 02}.\\pДинамаксировать покемонов также "
                                "{COLOR 06}{FD 0C}{COLOR 02}.\\pВыберите для боя команду из {COLOR 06}{FD 0A}"
                                "{COLOR 02} покемонов.", True),
    }
    MESSAGES = []

    def test_fills(self):
        from gen3tl.discover import inventory as inv_mod
        from gen3tl.profile.profile import Profile
        prof = unbound()
        lims = qa.compute_limits(prof, inv_mod.load(Path("build/inventory.json")), qa.load_catalog(Path("po")),
                                 Measure(lambda b: 6, {}), PACK.charmap(), rom=prof.load_rom(rom_path()))
        self.assertEqual({sid: lims[sid].placeholders for sid in self.CASES},
                         {"s1F8E9AE": {"STR_VAR_1": 155, "STR_VAR_2": 150},
                          "s1F8C8FD": {"FD 07": 155, "FD 08": 150}})

    def test_layout(self):
        """RECORD breaks fit the widest names; approved slots do not."""
        import json

        from gen3tl.__main__ import main
        old = ("{COLOR 06}{FD 0C}{COLOR 08} рекорд установлен\\nв категории {COLOR 06}{STR_VAR_1}{COLOR 08},"
               "\\lвид боя - {COLOR 06}{STR_VAR_2}{COLOR 08}." + self.REST)
        seen = []
        for text in (self.RECORD, old):
            (self.batch / "translation.json").write_text(json.dumps(
                {"s1F8E9AE": text, "s1F8C8FD": self.CASES["s1F8C8FD"][2]}, ensure_ascii=False), encoding="utf-8")
            with mock.patch("builtins.print") as out:
                main(["--rom", str(rom_path()), "check", "batch", "t", "--po-root", "po"])
            seen.append([message for message in batch_messages(out) if message.startswith("s1F")])
        self.assertEqual(seen[0], ["s1F8C8FD: box 1 wraps to 4 lines, the English box has 3 (warning)",
                                   "s1F8E9AE: box 1 wraps to 5 lines, the English box has 3 (warning)",
                                   "s1F8E9AE: box 3 wraps to 3 lines, the English box has 2 (warning)"])
        for m in ("box 1: 230 > 208 px: 'в категории {COLOR 06}{STR_VAR_1}{COLOR ' with {STR_VAR_1} = 155 px",
                  "box 1: 215 > 208 px: 'вид боя - {COLOR 06}{STR_VAR_2}{COLOR 08' with {STR_VAR_2} = 150 px"):
            self.assertTrue(any("line wider than the window with the inserted words: " + m in l for l in seen[1]),
                            seen[1])

    def test_rom_fills(self):
        """The code that copies the names, and the widest Russian names of the catalog."""
        import json

        from gen3tl.profile.profile import Profile
        prof = unbound()
        rom = prof.load_rom(rom_path())
        # gSpecials 0x6E and 0x70
        self.assertEqual((rom.u32(0x15FF18), rom.u32(0x15FF20)), (0x089E874D, 0x089E8989))
        # tier getter: names by tier, doubles for tiers 10, 2
        self.assertEqual([rom.u32(a) for a in (0x9E6DB4, 0x9E6DB8, 0x9E6DBC, 0x9E6DC0)],
                         [0x08A6B6E8, 0x08A441E7, 0x08A4414E, 0x08A4419A])
        # special 0x6E formats; special 0x70 buffers
        self.assertEqual((rom.u32(0x9E8834), rom.u32(0x9E8B94), rom.u32(0x9E8B98)),
                         (0x08A6B768, 0x02022BC4, 0x02022BE4))
        inv = {e["offset"]: e["id"] for e in json.loads((ROOT / "build" / "inventory.json")
                                                        .read_text(encoding="utf-8"))["entries"]}
        tiers = {inv[rom.ptr_at(0xA6B700 + 4 * k)] for k in range(26)} | {"s0A441E7", "s0A4414E", "s0A4419A"}
        formats = {inv[rom.ptr_at(0xA6B768 + 4 * k)] for k in range(7)}
        # the widest Russian names, as the fills of both rules
        from gen3tl.build.font import FontTable
        font = FontTable.from_profile(prof)[0]
        slots = PACK.glyph_slots(rom, font)
        m = Measure(lambda b: slots[b].width if b in slots else font.width(rom, b), {})
        cat = qa.load_catalog(ROOT / "translation" / "ru" / "po", source=ENGLISH)
        widest = [max(m.width(cat[s][1].msgstr, PACK.charmap()) for s in ids) for ids in (tiers, formats)]
        rules = [r for r in prof["layout"]["code_fill"] if set(r.get("ids", [])) & set(self.CASES)]
        self.assertEqual(sorted(tuple(s["width"] for s in r["slots"].values()) for r in rules),
                         [tuple(widest)] * 2)
