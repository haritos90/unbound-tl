import unittest
import re
from pathlib import Path

import gen3tl
from gen3tl.profile.profile import Profile
from gen3tl.profile import schema
from gen3tl.catalog.catalog import load_catalog
from gen3tl.discover.reach import origin
from gen3tl.catalog import guidance
from gen3tl.check import qa
from gen3tl.lang.langpack import LangPack
from gen3tl.check.layout import Limit, Measure, check, entry_measure

from rom_support import source_text, needs_rom, rom_path
from test_roots import PROJECT_ROOT
from project_fixture import UNBOUND, unbound

class EngineFamilyFactsTest(unittest.TestCase):

    def test_instance_keeps_addresses_and_hack_specific_geometry(self):
        prof = Profile.by_name("unbound-2.1.1.1")
        sources = schema.read(prof.path)
        raw = sources.overlay
        self.assertEqual(sources.family_file.parent.name, "firered-cfru")
        for before, merged in zip(raw["font"], prof["font"]):
            self.assertNotIn("count", before)
            self.assertNotIn("codes", before)
            self.assertEqual((merged["glyphs"], merged["widths"], merged["evidence"]),
                             (before["glyphs"], before["widths"], before["evidence"]))
        self.assertEqual(prof["font_style"], raw["font_style"])
        self.assertEqual(prof["font_styles"], raw["font_styles"])
        self.assertEqual({key: prof["script"][key] for key in raw["script"]}, raw["script"])
        discovered = sources.header["scripts"]
        self.assertTrue(discovered["table_verified"])
        self.assertEqual(prof["script"]["command_table"], discovered["table"])
        self.assertEqual(prof["script"]["command_table_end"], discovered["end"])
        # Window declarations expand into per-string maps.
        declared = schema.read(prof.path).overlay
        # Derived windows retain instance annotations.
        declared["layout"] = schema.merge(sources.generated.get("layout", {}), declared["layout"])
        # Bound notes fill emptied prose fields.
        for section in ("layout", "save"):
            self.assertEqual(schema.value_digest(prof[section]), schema.value_digest(declared[section]))
        self.assertNotIn("family", prof.data)


GAME_NAME = re.compile(r"(?<![a-z])unbound(?![a-z])", re.I)


EV_BASE = re.compile(r"(?:raises|increases|boosts|’s|[Ii]ts) (?:the )?base "
                     r"(?:HP|Attack|Defense|Speed|Sp\. ?Atk|Sp\. ?Def|\{\w+\})")


@needs_rom
class SpriteOrientationTest(unittest.TestCase):
    def test_sprite_orientation_matches_the_engine_config(self):
        prof = Profile.by_name("unbound-2.1.1.1")
        sprites = prof["pokedex"]["sprites"]
        self.assertEqual(sprites["front"]["base"], 0x1A1D5B4)
        self.assertEqual(sprites["back"]["base"], 0x19DE42C)
        path = rom_path()
        rom = prof.load_rom(path)
        self.assertEqual(rom.u32(0x128) - 0x08000000, sprites["front"]["base"])
        self.assertEqual(rom.u32(0x12C) - 0x08000000, sprites["back"]["base"])
        self.assertEqual(rom.u32(0x9B35F0), 0x08000128)
        self.assertEqual(rom.u32(0x9B3640), 0x0800012C)


@needs_rom
class ProfileValuesTest(unittest.TestCase):
    def test_toolkit_contains_no_game_names_or_data_boundary(self):
        root = Path(gen3tl.__file__).parent
        for path in root.rglob("*.py"):
            with self.subTest(path=path.name):
                source = path.read_text().lower()
                self.assertIsNone(GAME_NAME.search(source))
                self.assertNotIn("0x740000", source)

    def test_game_name_guard_distinguishes_identifiers_from_words(self):
        for source in ("unbounded decoding", "Unbounded", "unboundness"):
            with self.subTest(source=source):
                self.assertIsNone(GAME_NAME.search(source))
        for source in ('"unbound"', "UNBOUND_DATA", "unbound-2.1.1.1", "rom/unbound.gba", "my_unbound_profile"):
            with self.subTest(source=source):
                self.assertIsNotNone(GAME_NAME.search(source))

    def test_profile_regions_preserve_existing_boundaries(self):
        prof = Profile.by_name("unbound-2.1.1.1")
        reach = prof["reach"]
        for offset, expected in ((0, "firered"), (0x170000, "firered-script"),
                                 (0x1CFFFF, "firered-script"), (0x1D0000, "firered"),
                                 (0x73FFFF, "firered"), (0x740000, "unbound"),
                                 (0x1FFFFFF, "unbound")):
            self.assertEqual(origin(offset, reach["origin_regions"], reach["default_origin"]), expected)
        self.assertEqual(origin(0x740000), "rom")

    def test_output_names_follow_profile_and_language(self):
        prof = Profile({"project": {"slug": "custom"}}, Path("game-1.2.3.toml"))
        self.assertEqual(prof.output_stem("fr"), "custom-fr")
        prof.data.clear()
        self.assertEqual(prof.output_stem("de"), "game-1.2.3-de")

    def test_trace_source_line_rejects_content_beside_full_name(self):
        prof = unbound()
        source = source_text("s03FC8C2")
        fills = qa.fill_slots("s03FC8C2", source, {"refs": []},
                              qa.code_fills(prof["layout"]), 6)
        limit = Limit("battle", 222, 2,
                      placeholders={key: value.translated for key, value in fills.items()})
        measure = Measure(lambda _: 6, prof["layout"]["placeholders"])
        cm = LangPack.load("ru", prof["font_style"]["style"]).charmap()
        unsafe = 'с покемона “{B_BUFF1}” талант'
        self.assertTrue(check(unsafe, limit, measure, cm))
        safe = ('{B_SCR_ACTIVE_NAME_WITH_PREFIX} копирует\\n'
                'с покемона “{B_BUFF1}”\\lталант {B_BUFF2}!')
        self.assertEqual(check(safe, limit, measure, cm), [])
        actual = entry_measure(measure, limit)
        self.assertGreater(actual.width('{B_BUFF2}', cm),
                           measure.width('{B_BUFF2}', cm))

    def test_stat_change_lines_take_the_widest_stat_name(self):
        # {B_BUFF1} from gStatNamesTable
        prof = unbound()
        catalog = load_catalog(UNBOUND / "translation/ru/po")
        fills = qa.code_fills(prof["layout"])
        measure = Measure(lambda _: 6, prof["layout"]["placeholders"])
        cm = LangPack.load("ru", prof["font_style"]["style"]).charmap()
        sources = qa.source_fills(prof, catalog, measure, cm, {})
        stats = [f"s{0x3FD590 + d:07X}" for d in (0, 3, 0xA, 0x12, 0x18, 0x20, 0x28, 0x31)]
        widest = 6 * max(len(catalog[sid][1].msgstr) for sid in stats)
        self.assertEqual(widest, 78)
        for sid in ("s03FB7D5", "s0966078", "s03FCB6A"):
            with self.subTest(sid=sid):
                slots = qa.fill_slots(sid, catalog[sid][1].msgid, {"refs": []}, fills, 6, sources)
                self.assertEqual(slots["B_BUFF1"].translated, widest)
        text = "{B_ATK_NAME_WITH_PREFIX}:\\n{B_BUFF1} " + "а" * 24   # 60 + 6 + 144 = 210
        self.assertEqual(check(text, Limit("battle", 222, 2, placeholders={"B_BUFF1": 60}), measure, cm), [])
        self.assertTrue(check(text, Limit("battle", 222, 2, placeholders={"B_BUFF1": widest}), measure, cm))

    def test_effort_value_base_stats_carry_translator_notes(self):
        # the English hides the EV sense
        prof = unbound()   # the project holds the notes
        root = UNBOUND / "translation/ru/po"
        catalog = load_catalog(root, prof)
        notes = guidance.entry_notes(prof, catalog)
        found = [sid for sid, (_, e) in catalog.items() if EV_BASE.search(e.msgid)]
        self.assertGreaterEqual(len(found), 21)
        for sid in found:
            with self.subTest(sid=sid):
                self.assertIn(sid, notes)
                self.assertIn("effort values", notes[sid][0]["text"])

    def test_quoted_settings_labels_match_the_menu(self):
        # tips quote the menu labels
        root = UNBOUND / "translation/ru/po"
        catalog = load_catalog(root)
        menus = {"region-1F40000.po", "table-1FB39FC.po", "table-1FB39C0.po"}
        labels = [(sid, e.msgid, e.msgstr) for sid, (path, e) in catalog.items()
                  if path.name in menus and e.msgstr and "\\" not in e.msgid and len(e.msgid) <= 20]
        labels += [(sid, catalog[sid][1].msgid, catalog[sid][1].msgstr)
                   for sid in ("s0A4ED04", "s0A4ED0C", "s0A4ED28", "s0A4ED2F")]
        # Mission Log feature name, not the menu entry
        features = {"s1F0BC67", "s1F0D3E1"}
        # a cut menu label: dialogue quotes the full name
        glossary = UNBOUND / "translation/ru/glossary.tsv"
        full = {}
        for line in glossary.read_text(encoding="utf-8").splitlines()[1:]:
            cols = line.split("\t")
            if len(cols) > 4 and cols[4]:
                full[cols[2], cols[4]] = cols[3]
        labels = [(sid, english, full.get((english, label), label))
                  for sid, english, label in labels]
        checked = 0
        for sid, (path, e) in catalog.items():
            if path.name in menus or sid in features or not e.msgstr or e.fuzzy:
                continue
            for lid, english, label in labels:
                if "{COLOR 06}" + english + "{COLOR" in e.msgid:
                    checked += 1
                    with self.subTest(sid=sid, label=lid):
                        quoted = "{color 06}" + label.lower() + "{color"
                        text = e.msgstr.lower().replace("“", "").replace("”", "")
                        self.assertIn(quoted, text)
        self.assertGreaterEqual(checked, 30)

    def test_aqua_compounds_are_written_solid(self):

        root = UNBOUND
        hyphen = re.compile(r"(?<![А-Яа-яЁё])[Аа]ква-[а-яё]")
        catalog = load_catalog(root / "translation/ru/po")
        lines = [sid for sid, (_, e) in catalog.items() if hyphen.search(e.msgstr or "")]
        rows = [line.split("\t")[0] for line in
                (root / "translation/ru/glossary.tsv").read_text(encoding="utf-8").splitlines()
                if hyphen.search("\t".join(line.split("\t")[3:5]))]
        self.assertEqual((lines, rows), ([], []))

    def test_dynamic_placeholders_are_measured_at_their_fills(self):
        # {F7 xx} at its widest fill
        prof = unbound()
        by_id, _ = qa.code_fills(prof["layout"])
        catalog = load_catalog(UNBOUND / "translation/ru/po")
        hosts = [(sid, e.msgid) for sid, (p, e) in catalog.items() if "{F7 " in e.msgid and (
            p.name == "region-0410000.po" and sid >= "s041A000" or sid in ("s041B3FB", "s041B4C6"))]
        self.assertGreaterEqual(len(hosts), 39)
        for sid, english in hosts:
            with self.subTest(sid=sid):
                tokens = set(re.findall(r"\{(F7 [0-9A-F]{2})\}", english))
                measured = {name for r in by_id.get(sid, []) for name, s in r["slots"].items()
                            if {"digits", "width", "strings"} & set(s)}
                self.assertEqual(tokens - measured, set())

    def test_memo_and_union_card_fills_are_measured(self):
        # every {F7 xx} slot has a fill
        prof = unbound()
        by_id, _ = qa.code_fills(prof["layout"])
        catalog = load_catalog(UNBOUND / "translation/ru/po")
        hosts = [sid for sid in catalog if "s0419782" <= sid <= "s04199F4" and "{F7 " in catalog[sid][1].msgid]
        hosts += ["s04594C4", "s0459504", "s0459544", "s0459564", "s0459588"]
        self.assertEqual(len(hosts), 19)
        for sid in hosts:
            with self.subTest(sid=sid):
                tokens = set(re.findall(r"\{(F7 [0-9A-F]{2})\}", catalog[sid][1].msgid))
                rules = by_id.get(sid, [])
                measured = {name for r in rules for name, s in r["slots"].items()
                            if {"digits", "width", "strings"} & set(s)}
                self.assertEqual(tokens - measured, set())

    def test_dungeon_window_measures_the_descriptions(self):
        # +8 of the record is the description
        import struct
        prof = Profile.by_name("unbound-2.1.1.1")
        rule = next(t for t in prof["layout"]["table_window"] if t["name"] == "firered-dungeon-descriptions")
        rom = prof.load_rom(rom_path()).data
        members = [f"s{struct.unpack_from('<I', rom, rule['base'] + k * rule['stride'] + f)[0] - 0x8000000:07X}"
                   for k in range(rule["count"]) for f in rule["fields"]]
        self.assertEqual((members[0], len(members)), ("s0418ECB", 19))
        catalog = load_catalog(UNBOUND / "translation/ru/po")
        self.assertTrue(all(len(catalog[sid][1].msgid) > 20 for sid in members))   # texts, not map names

    def test_z_move_names_fit_the_small_move_menu(self):
        # 128 px, small font
        import struct
        prof = unbound()
        rule = next(t for t in prof["layout"]["table_window"] if t["name"] == "z-move-names")
        rom = prof.load_rom(rom_path()).data
        names = {f"s{struct.unpack_from('<I', rom, rule['base'] + 4 * k)[0] - 0x8000000:07X}"
                 for k in range(rule["count"])}
        self.assertEqual((rule["width"], len(names)), (128, 35))
        styles = prof["layout"]["window_style"]
        self.assertEqual({styles.get(sid) for sid in names}, {"unbound-small"})
        m = Measure(lambda _: 6, {}, styles={"unbound-small": lambda _: 5})
        cm = LangPack.load("ru", prof["font_style"]["style"]).charmap()
        lim = Limit("multiline", 128, 1, style="unbound-small")
        self.assertEqual(check("а" * 25, lim, m, cm), [])        # 125 px small
        self.assertTrue(check("а" * 26, lim, m, cm))             # 130 px small

    def test_quiz_answers_can_be_typed(self):
        # never printed; template 6, 12 letters
        root = UNBOUND / "translation/ru/po"
        catalog = load_catalog(root)
        answers = ["s1F2BF32", "s1F2BF39", "s1F2BF43", "s1F2BF49", "s1F2BF51",
                   "s1F2BF57", "s1F2BF5D", "s1F2BF63", "s1F2BF68", "s1F2BF6E"]
        for sid in answers:
            with self.subTest(sid=sid):
                text = catalog[sid][1].msgstr
                self.assertTrue(0 < len(text) <= 12)
                self.assertEqual(text, text.upper())   # the keyboard opens on capitals
                self.assertNotIn("Ё", text)

    def test_ball_changer_question_takes_the_ball_names(self):
        # callasm 0x9EB8ECD fills STR_VAR_2
        import json

        from gen3tl.discover import maps
        prof = Profile.by_name("unbound-2.1.1.1")
        rule = maps.native_fill_rules(prof)[0x1EB8ECD]
        self.assertEqual((rule["slot"], rule["base"], rule["exclude"]), (1, 0x1FB2204, [27]))
        inv = PROJECT_ROOT / "build/inventory.json"
        if inv.exists():
            sources = maps.native_fill_sources(rule, json.loads(inv.read_text(encoding="utf-8")))
            self.assertEqual(len(sources), 27)

    def test_frontier_names_fill_the_sands_announcer(self):
        # widest Frontier names
        prof = unbound()
        fills = qa.code_fills(prof["layout"])
        english = source_text("s1F8EC20")
        slots = qa.fill_slots("s1F8EC20", english, {"refs": []}, fills, 6)
        self.assertEqual({k: (v.translated, v.source_width) for k, v in slots.items()},
                         {"STR_VAR_1": (54, 60), "STR_VAR_2": (48, 45)})

    def test_pointer_trainer_classes_have_windows(self):
        # no English-width fallback
        prof = unbound()
        widths = prof["layout"]["window_width"]
        root = UNBOUND / "translation/ru/po"
        pointers = [sid for sid, (p, _) in load_catalog(root).items()
                    if p.name == "trainer_classes.po" and sid.startswith("s")]
        self.assertEqual(len(pointers), 9)
        self.assertEqual([sid for sid in pointers if sid not in widths], [])

    def test_easy_chat_progressives_take_the_first_person(self):
        # form set by the project's style rules
        progressive = {"FEELING", "GOING", "HEARING", "JOKING", "KIDDING", "LOLLING", "MAKING",
                       "TALKING", "TWIRLING", "USING", "WALKING", "WANDERING", "WORKING"}
        root = UNBOUND / "translation/ru/po"
        words = {e.msgid: e.msgstr for _, (p, e) in load_catalog(root).items()
                 if p.name.startswith("table-03E") and e.msgid in progressive}
        self.assertEqual(set(words), progressive)
        for english, russian in words.items():
            with self.subTest(english=english):
                self.assertRegex(russian, r"(Ю|У|ЮСЬ|УСЬ)$")

    def test_hoopa_cries_share_one_form(self):

        root = UNBOUND / "translation/ru/po"
        pause = re.compile(r"\{PAUSE \d+\}")
        cries = [(sid, e) for sid, (_, e) in load_catalog(root).items()
                 if e.msgid.startswith(source_text("s1F382E5")) and e.msgstr]
        self.assertGreaterEqual(len(cries), 7)
        for sid, e in cries:
            with self.subTest(sid=sid):
                self.assertTrue(e.msgstr.startswith("{COLOR 06}Ху-у…"))
                self.assertEqual(pause.findall(e.msgstr), pause.findall(e.msgid))
