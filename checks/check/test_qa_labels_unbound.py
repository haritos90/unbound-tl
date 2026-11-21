import unittest
from pathlib import Path
from unittest import mock

from gen3tl.check import qa
from gen3tl.check.layout import Measure
from gen3tl.catalog.po import PoEntry, write

from rom_support import needs_rom, rom_path
from test_roots import PROJECT_ROOT as ROOT
import qa_support
from project_fixture import unbound
from qa_support import PACK, assert_never_shown_groups, batch_messages, battle, setUpModule, tearDownModule

@needs_rom
class BagDescriptionWindowTest(qa_support.LabelWindowTest):
    """The bag prints every item description in window 1."""

    CASES = {
        "s0EB3A2D": (200, None, "Предмет, который держит покемон. Это поношенный пояс, усиливающий "
                                "суперэффективные приёмы.", True),
        "s0EB3E1E": (200, None, "Предмет, который держит покемон. Покемон парит до первого удара. "
                                "От удара предмет лопается.", True),
        "s078133B": (200, None, "Необычный предмет, вызывающий эволюцию некоторых покемонов.", True),
        "s03DA8B4": (200, None, "Посылка с Покедексом\\nдля соперника.", True),
    }
    MESSAGES = []
    POCKETS = (1, 2, 3)   # pocket byte +0x1A: Items, Key Items, Poké Balls
    RULES = {f"bag-descriptions{s}" for s in ("", "-2", "-3", "-4", "-5", "-6")}

    def test_description_lines(self):
        """Three lines show; the approved Air Balloon text takes a fourth."""
        import json

        from gen3tl.discover import inventory as inv_mod
        from gen3tl.__main__ import main
        from gen3tl.profile.profile import Profile
        prof = unbound()
        lims = qa.compute_limits(prof, inv_mod.load(Path("build/inventory.json")), qa.load_catalog(Path("po")),
                                 Measure(lambda b: 6, {}), PACK.charmap(), rom=prof.load_rom(rom_path()))
        self.assertEqual({sid: (lims[sid].kind, lims[sid].lines) for sid in self.CASES},
                         {sid: ("multiline", 3) for sid in self.CASES})
        (self.batch / "translation.json").write_text(json.dumps(
            {"s0EB3E1E": "Предмет, который держит покемон. Покемон парит в воздухе до первого удара. "
                         "От удара предмет лопается.",
             "s0EB3A2D": self.CASES["s0EB3A2D"][2]}, ensure_ascii=False), encoding="utf-8")
        with mock.patch("builtins.print") as out:
            main(["--rom", str(rom_path()), "check", "batch", "t", "--po-root", "po"])
        lines = batch_messages(out)
        self.assertIn("s0EB3E1E: too many lines: 4 > 3", lines)
        self.assertEqual([l for l in lines if l.startswith("s0EB3A2D:")], [])

    def test_rom_bag(self):
        """The description printer, the three pockets and the rules covering exactly them."""
        from gen3tl.profile.profile import Profile
        prof = unbound()
        rom = prof.load_rom(rom_path())
        items = [i for i in range(1, 729) if rom.u8(0x876200 + 44 * i + 0x1A) in self.POCKETS]
        self.assertEqual((len(items), items[0], items[-1]), (532, 1, 728))
        rules = [r for r in prof["layout"]["table_window"] if r["name"] in self.RULES]
        self.assertEqual({(r["width"], r["lines"]) for r in rules}, {(200, 3)})
        self.assertEqual(sorted(at for at, _, _ in qa.window_texts({"table_window": rules})),
                         [0x876200 + 44 * i + 0x14 for i in items])
        # window 1 of 0x4530C4: bg, left, top, width, height
        self.assertEqual([rom.u8(0x4530CC + k) for k in range(5)], [0, 5, 14, 25, 6])
        # window 1, font 2; BagPrintTextOnWindow and ItemId_GetDescription
        self.assertEqual([rom.u16(a) for a in (0x9F48CC, 0x9F48CE, 0x9F48D0, 0x9F48DE)],
                         [0x2203, 0x2300, 0x2102, 0x2001])
        self.assertEqual((rom.u32(0x9F4988), rom.u32(0x9F4980)), (0x0810B8F1, 0x0809A96D))
        # pockets 0-2 counted (0x9F44A2), none above 2 (0x9F44D2)
        self.assertEqual((rom.u16(0x9F44A2), rom.u16(0x9F44D2)), (0x2903, 0x2802))


@needs_rom
class CodeFillAndColumnWindowTest(qa_support.LabelWindowTest):
    """Code-filled numbers and names take their real width."""

    CASES = {
        "s04162A9": (76, None, "{STR_VAR_1}/{STR_VAR_2}\\nПокеболы: {STR_VAR_3}", True),
        "s0418188": (204, None, "Итого: В:{STR_VAR_1} П:{STR_VAR_2} Н:{STR_VAR_3}", True),
        "s041D13C": (114, None, "Подключено игроков: {STR_VAR_1}", False),
        "s03FE725": (96, None, "{PALETTE 05}{COLOR_HIGHLIGHT_SHADOW 0D 0E 0F}Бой{CLEAR_TO 38}Сумка\\n"
                               "Покемоны{CLEAR_TO 38}Бежать", True),
        "s03FE747": (96, None, "{PALETTE 05}{COLOR_HIGHLIGHT_SHADOW 0D 0E 0F}Сафари-бол{CLEAR_TO 38}Корм\\n"
                               "Камень{CLEAR_TO 38}Бежать", False),
        "s041EE2B": (192, None, "Стереть всё{CLEAR_TO 57}Отмена{CLEAR_TO A4}ОК", True),
        "s1F9AB0F": (125, None, "Мистический огонь{CLEAR_TO 63} {FONT 00}8 БО", True),
        "s1F9AA9E": (125, None, "Удар головой дзен{CLEAR_TO 63} {FONT 00}8 БО", False),
    }
    # the shop row's width is unmeasured
    MESSAGES = ["s041D13C: line too wide: 122 > 114 px: 'Подключено игроков: {STR_VAR_1}' with {STR_VAR_1} = 6 px "
                "(number of 1 digit, Berry Crush records, players)",
                "s03FE747: line too wide: 60 > 56 px before the column {CLEAR_TO 38}: 'Сафари-бол'",
                "s1F9AA9E: line too wide: 127 > 125 px: 'Удар головой дзен{CLEAR_TO 63} {FONT 00}' "
                "[unmeasured limit: the English width]",
                "s1F9AA9E: line too wide: 101 > 99 px before the column {CLEAR_TO 63}: 'Удар головой дзен'"]

    def test_profile_windows(self):
        # {FONT 00} price of an English row, 5 px glyphs
        from gen3tl.discover import inventory as inv_mod
        from gen3tl.build.font import font_codes
        from gen3tl.profile.profile import Profile
        prof = unbound()
        self.assertEqual(font_codes(prof), {"00": "unbound-small", "01": "unbound", "02": "unbound", "03": "unbound",
                                            "04": "unbound", "05": "unbound"})
        m = Measure(lambda b: 6, {}, styles={"unbound": lambda b: 6, "unbound-small": lambda b: 5},
                    fonts=font_codes(prof))
        lims = qa.compute_limits(prof, inv_mod.load(Path("build/inventory.json")), qa.load_catalog(Path("po")), m,
                                 PACK.charmap(), rom=prof.load_rom(rom_path()))
        self.assertEqual({sid: (l.width, l.style) for sid, l in lims.items()},
                         {sid: (w, s) for sid, (w, s, _, _) in self.CASES.items()})
        self.assertEqual(lims["s04162A9"].placeholders, {"STR_VAR_1": 18, "STR_VAR_2": 18, "STR_VAR_3": 12})
        self.assertEqual(lims["s0418188"].placeholders, {"STR_VAR_1": 24, "STR_VAR_2": 24, "STR_VAR_3": 24})


@needs_rom
class MusicPrefixTest(unittest.TestCase):
    """The music-name prefixes of the audio options page."""

    @classmethod
    def setUpClass(cls):
        from gen3tl.profile.profile import Profile
        cls.prof = unbound()
        cls.rom = cls.prof.load_rom(rom_path())

    def test_code_reads_the_profile_fields(self):
        tabs = {t["name"]: t for t in self.prof["table"]}
        battle, team = tabs["music_prefix_battle"], tabs["music_prefix_team"]
        base = self.rom.u32(0x1EBC440) - 0x08000000   # pool word of the getter
        # Thumb: memcpy size, compare length, offset, skip
        code = {0x1EBC398: 0x2209, 0x1EBC39A: 0x3158, 0x1EBC3A2: 0x2208, 0x1EBC3B2: 0x3408,
                0x1EBC3B6: 0x2206, 0x1EBC3B8: 0x3161, 0x1EBC3C0: 0x2205, 0x1EBC3CE: 0x3405}
        self.assertEqual({at: self.rom.u16(at) for at in code}, code)
        self.assertEqual((battle["base"], battle["field_length"]), (base + 0x58, 9))
        self.assertEqual((team["base"], team["field_length"]), (base + 0x61, 6))
        from gen3tl.core.charmap import Charmap
        self.assertEqual(self.rom.read(battle["base"], 9), Charmap().encode("Battle! "))
        self.assertEqual(self.rom.read(team["base"], 6), Charmap().encode("Team "))
        for name in ("options-trainer-themes", "options-wild-themes"):
            tw = next(t for t in self.prof["layout"]["table_window"] if t["name"] == name)
            self.assertEqual(tw["strip"], [{"reference": "music_prefix_battle:0", "chars": 8},
                                           {"reference": "music_prefix_team:0", "chars": 5}])

    def test_catalog(self):
        import json

        from gen3tl.catalog.catalog import load_catalog
        inv = json.loads((ROOT / "build" / "inventory.json").read_text(encoding="utf-8"))
        es = {e["id"]: e for e in inv["entries"] if e["id"].startswith("music_prefix_")}
        self.assertEqual({k: (e["offset"], e["length"], e["kind"], e["text"]) for k, e in es.items()},
                         {"music_prefix_battle:0": (0x1FB3860, 9, "fixed", "Battle! "),
                          "music_prefix_team:0": (0x1FB3869, 6, "fixed", "Team ")})
        cat = load_catalog(ROOT / "translation" / "ru" / "po")
        self.assertEqual(cat["music_prefix_battle:0"][1].msgstr, "Battle! ")
        team = cat["music_prefix_team:0"][1].msgstr
        self.assertEqual((team, len(PACK.charmap().encode(team, terminate=False))), ("Бой! ", 5))


@needs_rom
class MusicNameStripWindowTest(qa_support.LabelWindowTest):
    """Music names measure without the prefixes the getter strips."""

    # values between the arrows
    CASES = {
        "s1F94526": (98, None, "Бой! Элитная четвёрка", True),
        "s1F945B3": (98, None, "Бой! Агент Света гибели", False),
        "s1F9485C": (98, None, "Бой! Божество-хранитель", False),
        "s1F94777": (98, None, "Бой! Озёрное трио региона Синно", False),
    }
    MESSAGES = ["s1F94777: line too wide: 155 > 98 px: 'Озёрное трио региона Синно' (prefix 'Бой! ' stripped)",
                "s1F945B3: line too wide: 106 > 98 px: 'Агент Света гибели' (prefix 'Бой! ' stripped)"]
    PREFIXES = {"music_prefix_battle:0": "Battle! ", "music_prefix_team:0": "Бой! "}

    def setUp(self):
        import json

        from gen3tl.discover import inventory as inv_mod
        super().setUp()
        es = [x for x in inv_mod.load(ROOT / "build" / "inventory.json")["entries"] if x["id"] in self.PREFIXES]
        inv = json.loads(Path("build/inventory.json").read_text(encoding="utf-8"))
        Path("build/inventory.json").write_text(json.dumps({**inv, "entries": inv["entries"] + es}),
                                                encoding="utf-8")
        write(Path("po/tables/prefixes.po"), [PoEntry(e["id"], e["text"], self.PREFIXES[e["id"]]) for e in es],
              {"Project-Id-Version": "unbound-2.1.1.1", "Language": "ru"})

    def test_profile_windows(self):
        from gen3tl.discover import inventory as inv_mod
        from gen3tl.profile.profile import Profile
        prof = unbound()
        lims = qa.compute_limits(prof, inv_mod.load(Path("build/inventory.json")), qa.load_catalog(Path("po")),
                                 Measure(lambda b: 6, {}), PACK.charmap(), rom=prof.load_rom(rom_path()))
        self.assertEqual({sid: (lims[sid].width, lims[sid].strip) for sid in self.CASES},
                         {sid: (98, ["Battle! ", "Бой! "]) for sid in self.CASES})


@needs_rom
class StatNameWindowTest(qa_support.LabelWindowTest):
    """Stat names take the 78 px their host lines leave."""

    CASES = {
        "s03FD590": (78, None, "ОЖ", True),
        "s03FD593": (78, None, "Атака", True),
        "s03FD5A8": (78, None, "Особая атака", True),
        "s03FD5B0": (78, None, "Особая защита", True),
        "s03FD5C1": (78, None, "Уклонение от атак", False),
    }
    MESSAGES = ["s03FD5C1: line too wide: 100 > 78 px: 'Уклонение от атак'",
                "s03FD5C1: field overflow: 17 > 15 characters"]
    LIST = ["s0417FD9", "s0417FE6", "s0417FF3", "s0418000", "s041800D", "s0418017", "s0418022", "s041802F",
            "s04180A7", "s04180BC", "s04180D0", "s04180E4", "s04180FA", "s041810D", "s041811D", "s041812F",
            "s0418142", "s0418152", "s0418163"]

    def test_chars(self):
        from gen3tl.discover import inventory as inv_mod
        from gen3tl.profile.profile import Profile
        prof = unbound()
        lims = qa.compute_limits(prof, inv_mod.load(Path("build/inventory.json")), qa.load_catalog(Path("po")),
                                 Measure(lambda b: 6, {}), PACK.charmap(), rom=prof.load_rom(rom_path()))
        self.assertEqual({sid: (lims[sid].kind, lims[sid].chars) for sid in self.CASES},
                         {sid: ("single", 15) for sid in self.CASES})

    def test_list_array_never_shown(self):
        """Only the hooked-over load reads the array; its rows 0 and 5 alone are tagged."""
        import json

        from gen3tl.catalog.catalog import never_shown
        from gen3tl.profile.profile import Profile
        prof = unbound()
        rom = prof.load_rom(rom_path())
        self.assertEqual(rom.ptr_at(0xCBA68), 0x3F5BCC)
        self.assertEqual(rom.u16(0xCB970), 0x4A3D)   # ldr r2, [pc, #0xf4]: 0x80CBA68
        self.assertEqual((rom.u16(0xCB94C), rom.u16(0xCB94E), rom.u32(0xCB950)), (0x4800, 0x4700, 0x09E76979))
        self.assertEqual([rom.u32(0x1E769BC + 4 * k) for k in range(3)], [0x080CB975, 0x080CB9AF, 0x080CBA7D])
        inv = json.loads((ROOT / "build" / "inventory.json").read_text(encoding="utf-8"))
        hit = [e for e in inv["entries"] if any(0x3F5BCC <= r["at"] < 0x3F5D1C for r in e["refs"])]
        only = {e["id"] for e in hit if all(0x3F5BCC <= r["at"] < 0x3F5D1C for r in e["refs"])}
        self.assertEqual(only, set(self.LIST))
        never = never_shown(None, prof.get("reach", {}).get("never_shown", []))
        assert_never_shown_groups(self, prof, never, [self.LIST])
        self.assertEqual(sorted({e["id"] for e in hit} - only & set(never)), [])


@needs_rom
class LevelUpStatLabelWindowTest(qa_support.LabelWindowTest):
    """Level-up window stat labels end before the gain sign."""

    CASES = {
        "s041B2A9": (56, None, "{FONT 00}Макс.{FONT 02} ОЖ", True),
        "s041B2B7": (56, None, "Атака", True),
        "s041B2BE": (56, None, "Защита", True),
        "s041B2CC": (56, None, "Ос. атака", True),
        "s041B2D4": (56, None, "Ос. защита", False),
        "s041B2C6": (56, None, "Скорость", True),
    }
    MESSAGES = ["s041B2D4: line too wide: 59 > 56 px: 'Ос. защита'"]

    def test_short_form(self):
        """The term label «Ос. защ.» fits."""
        import json

        from gen3tl.__main__ import main
        (self.batch / "translation.json").write_text(json.dumps({"s041B2D4": "Ос. защ."}, ensure_ascii=False),
                                                     encoding="utf-8")
        with mock.patch("builtins.print") as out:
            main(["--rom", str(rom_path()), "check", "batch", "t", "--po-root", "po"])
        lines = batch_messages(out)
        self.assertFalse([l for l in lines if l.startswith("s041B2D4:")], lines)

    def test_rom_printer(self):
        """Labels at x 0, the sign at x 56 in font 0; battle and party menu draw the page."""
        import json

        from gen3tl.profile.profile import Profile
        prof = unbound()
        rom = prof.load_rom(rom_path())
        inv = {e["id"]: e for e in json.loads((ROOT / "build" / "inventory.json").read_text(encoding="utf-8"))
               ["entries"]}

        def bl(a):
            hi, lo = rom.u16(a) & 0x7FF, rom.u16(a + 2) & 0x7FF
            return a + 4 + ((hi - 0x800 if hi & 0x400 else hi) << 12) + (lo << 1)

        self.assertEqual(rom.ptr_at(0x11E930), 0x459B48)   # DrawLevelUpWindowPg1 pool
        self.assertEqual([rom.ptr_at(0x459B48 + 4 * k) for k in range(6)], [inv[s]["offset"] for s in self.CASES])
        self.assertEqual((rom.u16(0x11E89E), rom.u16(0x11E8CE)), (0x2200, 0x2238))   # movs r2, #0 / #0x38
        self.assertEqual((rom.u32(0x11E934), rom.u32(0x11E938)), (0x0841B2E5, 0x0841B2DC))   # '-' / '+'
        self.assertEqual((bytes(rom.data[0x41B2DC:0x41B2DF]), bytes(rom.data[0x41B2E5:0x41B2E8])),
                         (b"\xfc\x06\x00", b"\xfc\x06\x00"))   # {FONT 00}
        self.assertEqual([bl(a) for a in (0x26430, 0x11D786, 0x12659C)], [0x11E7F0] * 3)
        self.assertEqual({sid: prof["layout"]["window_width"].get(sid) for sid in self.CASES},
                         {sid: 56 for sid in self.CASES})


@needs_rom
class BerryPouchWindowTest(qa_support.LabelWindowTest):
    """The selected berry prefix leaves 82 px for names."""

    CASES = {
        "items:147": (82, None, "Айапапа-ягода", True),
        "items:165": (82, None, "Ватмель-ягода", True),
        "items:171": (82, None, "Петайя-ягода", True),
        "items:118": (82, None, "Энигма-ягода", True),
        "items:561": (82, None, "Ки-ягода", True),
        # lines fit; three of them do not (test_description_lines)
        "s03D700C": (200, None, "Предмет, который держит покемон. Восполняет ОЖ, но может вызвать замешательство.",
                     True),
        "s0EB3083": (200, None, "Нет иного применения, кроме приёма Дар природы.", True),
    }
    MESSAGES = []
    POUCH = 5   # pocket byte +0x1A of the item record
    RULES = {"berry-pouch-descriptions", "berry-pouch-descriptions-2", "berry-pouch-descriptions-3"}

    def test_natural_forms(self):
        """As LabelWindowTest, for ids with a colon."""
        import json

        from gen3tl.__main__ import main
        (self.batch / "translation.json").write_text(
            json.dumps({sid: ru for sid, (_, _, ru, _) in self.CASES.items()}, ensure_ascii=False), encoding="utf-8")
        with mock.patch("builtins.print") as out:
            main(["--rom", str(rom_path()), "check", "batch", "t", "--po-root", "po"])
        lines = batch_messages(out)
        too_wide = {l.split(": line too wide")[0] for l in lines if ": line too wide" in l}
        self.assertEqual(too_wide, {sid for sid, (_, _, _, fits) in self.CASES.items() if not fits}, lines)
        for m in self.MESSAGES:
            self.assertIn(m, lines)

    def test_description_lines(self):
        """Two lines show; the third falls below the window."""
        import json

        from gen3tl.discover import inventory as inv_mod
        from gen3tl.__main__ import main
        from gen3tl.profile.profile import Profile
        prof = unbound()
        lims = qa.compute_limits(prof, inv_mod.load(Path("build/inventory.json")), qa.load_catalog(Path("po")),
                                 Measure(lambda b: 6, {}), PACK.charmap(), rom=prof.load_rom(rom_path()))
        self.assertEqual({sid: (lims[sid].kind, lims[sid].lines) for sid in ("s03D700C", "s0EB3083")},
                         {"s03D700C": ("multiline", 2), "s0EB3083": ("multiline", 2)})
        (self.batch / "translation.json").write_text(json.dumps(
            {"s03D700C": self.CASES["s03D700C"][2]}, ensure_ascii=False), encoding="utf-8")
        with mock.patch("builtins.print") as out:
            main(["--rom", str(rom_path()), "check", "batch", "t", "--po-root", "po"])
        lines = batch_messages(out)
        self.assertIn("s03D700C: too many lines: 3 > 2", lines)

    def test_rom_berry_pouch(self):
        """The list and description printers, and the profile covering exactly pocket 5."""
        from gen3tl.profile.profile import Profile
        prof = unbound()
        rom = prof.load_rom(rom_path())
        items = [i for i in range(729) if rom.u8(0x876200 + 44 * i + 0x1A) == self.POUCH]
        self.assertEqual((len(items), items[0], items[-1]), (67, 118, 562))
        # only the pouch items: other items keep their own windows
        names = {k: v for k, v in prof["layout"]["window_width"].items()
                 if k.startswith("items:") and int(k.split(":")[1]) in items}
        self.assertEqual(names, {f"items:{i}": 82 for i in items})
        rules = [r for r in prof["layout"]["table_window"] if r["name"] in self.RULES]
        self.assertEqual({(r["width"], r["lines"]) for r in rules}, {(200, 2)})
        self.assertEqual(sorted(at for at, _, _ in qa.window_texts({"table_window": rules})),
                         [0x876200 + 44 * i + 0x14 for i in items])
        # windows 0 (list) and 1 (description): bg, left, top, size
        self.assertEqual([rom.u8(0x4643B8 + k) for k in range(5)], [0, 11, 1, 18, 14])
        self.assertEqual([rom.u8(0x4643C0 + k) for k in range(5)], [0, 5, 16, 25, 4])
        self.assertEqual(rom.u16(0x13D2AC), 0x2009)   # item_X 9

        self.assertEqual([rom.u32(p) for p in (0x13D388, 0x13D38C, 0x13D394, 0x13D398)],
                         [0x084166FF, 0x08416226, 0x084643B4, 0x08416703])
        self.assertEqual(bytes(rom.data[0x416226:0x41622C]), b"\xf9\x08\xfc\x11\x01\xff")
        self.assertEqual(rom.u16(0x13D492), 0x236E)   # quantity at x 110
        self.assertEqual((rom.u16(0x13D56E), rom.u16(0x13D582)), (0x2002, 0x2300))   # description y 2, x 0


@needs_rom
class SaveFieldNameWindowTest(qa_support.LabelWindowTest):
    """Default names copied into save fields take the field width."""

    CASES = {
        "s04186CD": (36, None, "Ячейка", True),
        "s1F11D18": (48, None, "Готовые", True),
        "s1F0EF10": (42, None, "Фрэнсис", True),
        "s08258E0": (42, None, "Эйс", True),
        "s071A8B7": (42, None, "Джулиана", False),
        "s1F6CDE8": (42, None, "Аревакс", True),
        "s1F18D9D": (42, None, "Бенджи", True),
        "s1F81D76": (60, None, "Сквидвард", True),
        "s1F81DF9": (60, None, "Морла", True),
        "s1F81E0A": (60, None, "Бойся меня", True),
        "s1F81E12": (60, None, "Бульдозер", True),
        "s1F81E1C": (42, None, "Эдмундович", False),
        "s1F5A560": (208, None, "В ячейке “{COLOR 06}{STR_VAR_1}{COLOR 08}” нет ни одного яйца…", True),
    }
    MESSAGES = ["s071A8B7: line too wide: 48 > 42 px: 'Джулиана'",
                "s071A8B7: field overflow: 8 > 7 characters",
                "s1F81E1C: line too wide: 60 > 42 px: 'Эдмундович'",
                "s1F81E1C: field overflow: 10 > 7 characters"]
    # host id -> (callasm offset, text pointer offset)
    HOSTS = {
        "s1EF779A": (0x1E61AA9, 0x1E61ABB), "s1EF77F7": (0x1E61AA9, 0x1E61AE0),
        "s1EF8C46": (0x1E622BF, 0x1E622C5), "s1EF8C8E": (0x1E622DA, 0x1E622E0),
        "s1EF8D0E": (0x1E62305, 0x1E6230C), "s1F026FF": (0x1E68D7C, 0x1E68D83),
        "s1F02A80": (0x1E68E87, 0x1E68E8E), "s1F0EF76": (0x1E70283, 0x1E7028A),
        "s1F598D8": (0x1E82180, 0x1E8218F), "s1F5A3F5": (0x1E81F77, 0x1E81F7E),
        "s1F5A560": (0x1E81FCE, 0x1E81FD5), "s1F905EF": (0x1E9E749, 0x1E9E750),
        "s1F573B2": (0x1E80DA4, 0x1E80E7C),
    }

    def test_field_characters(self):
        from gen3tl.discover import inventory as inv_mod
        from gen3tl.profile.profile import Profile
        prof = unbound()
        lims = qa.compute_limits(prof, inv_mod.load(Path("build/inventory.json")), qa.load_catalog(Path("po")),
                                 Measure(lambda b: 6, {}), PACK.charmap(), rom=prof.load_rom(rom_path()))
        chars = {"s04186CD": 6, "s1F11D18": 8, "s1F0EF10": 7, "s08258E0": 7, "s071A8B7": 7, "s1F6CDE8": 7,
                 "s1F18D9D": 7, "s1F81D76": 10, "s1F81DF9": 10, "s1F81E0A": 10, "s1F81E12": 10, "s1F81E1C": 7}
        self.assertEqual({sid: lims[sid].chars for sid in chars}, chars)
        self.assertEqual(lims["s1F5A560"].placeholders, {"STR_VAR_1": 48})

    def test_box_name_hosts(self):
        """Each host shows its text after a callasm that copies a box name into gStringVar1."""
        import json

        from gen3tl.profile.profile import Profile
        prof = unbound()
        rom = prof.load_rom(rom_path())
        inv = {e["id"]: e for e in json.loads((ROOT / "build" / "inventory.json").read_text())["entries"]}
        fills = {sid: r["slots"] for r in prof["layout"]["code_fill"] for sid in r.get("ids", [])}
        for sid, (call, text) in self.HOSTS.items():
            self.assertEqual(fills.get(sid), {"STR_VAR_1": {"width": 48}}, sid)
            self.assertIn("{STR_VAR_1}", inv[sid]["text"], sid)
            self.assertEqual((rom.u8(call), rom.ptr_at(text)), (0x23, inv[sid]["offset"]), sid)
            self.assertIn(rom.u32(call + 1), (0x09ECB2C5, 0x09EB74C9), sid)
        self.assertEqual(fills.get("s1F682A6"), {"B_COPY_VAR_3": {"width": 48}})
        # both callasms: StringCopy(gStringVar1, GetBoxNamePtr(box))
        for pool in (0x1ECB2E4, 0x1EB74E0):
            self.assertEqual([rom.u32(pool + k) for k in (0, 4)], [0x0808BD6D, 0x02021CD0])
        self.assertEqual(rom.u16(0x1EB74CC), 0x2018)   # box 24, Preset

    def test_rom_fields(self):
        from gen3tl.profile.profile import Profile
        rom = unbound().load_rom(rom_path())

        def bl(a):
            hi, lo = rom.u16(a) & 0x7FF, rom.u16(a + 2) & 0x7FF
            return a + 4 + ((hi - 0x800 if hi & 0x400 else hi) << 12) + (lo << 1)

        pools = {0x8C850: 0x4186CD, 0x1EC5B38: 0x1F11D18, 0x1EC7A54: 0x1F0EF10, 0x1EC7A58: 0x1F0EF18,
                 0x1EC7A68: 0x1F0EF1F, 0x8258A4: 0x8258E0, 0x8258D8: 0x8258E0, 0x1EC963C: 0x1F6CDE8,
                 0x1EC8204: 0x1F078C7, 0x46308C: 0x1C575E}
        self.assertEqual({p: rom.ptr_at(p) for p in pools}, pools)
        # default box names: StringCopy, then 2 digits, left-aligned
        self.assertEqual((bl(0x8C818), bl(0x8C824), rom.u16(0x8C820), rom.u16(0x8C822)),
                         (0x8D84, 0x8E78, 0x2200, 0x2302))
        # box title: padded to 8, two 32 px sprites
        self.assertEqual((bl(0x91B80), rom.u16(0x91B7E), bl(0x91BA2), rom.u16(0x91B98), rom.u16(0x91F74)),
                         (0x9230, 0x2308, 0x8BEB4, 0x2002, 0x20B0))
        # SetBoxMonData copies 10 nickname and 7 OT bytes
        self.assertEqual((rom.u32(0x40568 + 8), rom.u16(0x406EC), rom.u32(0x40568 + 28), rom.u16(0x4073C)),
                         (0x080406DC, 0x2A09, 0x0804072C, 0x2A06))
        self.assertEqual(rom.u16(0x8CF8), 0x250A)   # StringCopy10
        self.assertEqual(rom.u16(0x1317C6), 0x2A06)   # GetDefaultName: 7 characters
        # trade records from 0x1FB7074, 40 bytes, 39 checked
        self.assertEqual({rom.u32(p) for p in (0x1ED80CC, 0x1ED81D4, 0x1ED8220, 0x1ED829C, 0x1ED83D0)},
                         {0x09FB7074})
        self.assertEqual((rom.u16(0x1ED807E), rom.u16(0x1ED815A)), (0x2427, 0x2728))
        self.assertEqual([rom.u16(a) for a in (0x1ED8336, 0x1ED8338, 0x1ED8342, 0x1ED8344)],
                         [0x5972, 0x2102, 0x685A, 0x2107])   # nickname +0, OT name +4
        self.assertEqual(rom.u32(0x50E28), 0x09ED80DD)   # FireRed scene strings jump
        self.assertEqual(rom.ptr_at(0x1FB7074 + 40 * 38), 0x1F81E12)
        self.assertEqual(rom.ptr_at(0x1FB7074 + 40 * 38 + 4), 0x1F18D9D)


@needs_rom
class TradeNameSaveLinkTest(unittest.TestCase):
    """Unbound's in-game trade names reach the save."""

    NAMES = ["s1F81D28", "s1F81D30", "s1F81D3A", "s1F81D42", "s1F81D4A", "s1F81D55", "s1F81D5A",
             "s1F81E1C", "s1F81E23", "s1F81E2A", "s1F81E30", "s1F81E34", "s1F81E3C", "s1F2AE2B", "s1F2AE33"]

    @classmethod
    def setUpClass(cls):
        import json

        from gen3tl.profile.profile import Profile
        cls.prof = unbound()
        cls.inv = {e["id"]: e for e in json.loads((ROOT / "build" / "inventory.json").read_text(encoding="utf-8"))["entries"]}
        cls.rom = cls.prof.load_rom(rom_path())

    def test_table_names_are_the_list(self):
        rom, ids = self.rom, set()
        by_offset = {e["offset"]: sid for sid, e in self.inv.items()}
        for k in range(14):
            rec = 0x1FB7074 + 0x28 * k
            ids |= {by_offset[rom.ptr_at(rec)], by_offset[rom.ptr_at(rec + 4)]}
        self.assertEqual(rom.u32(0x1FB7074 + 0x28 * 14), 0)          # table end
        self.assertEqual(sorted(ids), sorted(self.NAMES))

    def bl_target(self, at):
        h1, h2 = self.rom.u16(at), self.rom.u16(at + 2)
        self.assertEqual((h1 >> 11, h2 >> 11), (0x1E, 0x1F), hex(at))
        off = ((h1 & 0x7FF) << 12) | ((h2 & 0x7FF) << 1)
        return at + 4 + (off - 0x800000 if off & 0x400000 else off)

    def test_written_into_the_save(self):
        rom = self.rom
        self.assertEqual(rom.u32(0x160154), 0x08053D69)               # special 0xFD
        self.assertEqual(self.bl_target(0x53D72), 0x53B48)
        self.assertEqual(rom.u32(0x53B48 + 4), 0x09ED82AD)            # hooked to Unbound
        self.assertEqual((rom.u32(0x1ED83D0), rom.u32(0x1ED83D4), rom.u32(0x1ED83DC)),
                         (0x09FB7074, 0x0202402C, 0x0804037D))        # table, gEnemyParty, SetMonData
        # nickname load: ldr, movs 2, movs
        self.assertEqual([rom.u16(0x1ED8336 + 2 * i) for i in range(3)], [0x5972, 0x2102, 0x0020])
        # OT name load: ldr, movs 7, movs
        self.assertEqual([rom.u16(0x1ED8342 + 2 * i) for i in range(3)], [0x685A, 0x2107, 0x0020])
        for at in (0x1ED833C, 0x1ED8348):
            self.assertEqual(self.bl_target(at), 0x1ED84B2)
        self.assertEqual(rom.u16(0x1ED84B2), 0x4738)                  # bx r7
        # trade scene: TradeMons(gSpecialVar_0x8005, 0)
        self.assertEqual((rom.u16(0x53698), rom.u32(0x536DC), rom.u16(0x5369C)), (0x4810, 0x020370C2, 0x2100))
        self.assertEqual(self.bl_target(0x5369E), 0x5080C)
        self.assertEqual((rom.u32(0x508D8), rom.u32(0x508DC)), (0x02024284, 0x0202402C))

    def test_flagged_save_link(self):
        listed = set(self.prof["strings"]["save_link"])
        self.assertEqual([sid for sid in self.NAMES if sid not in listed], [])
        self.assertEqual([sid for sid in self.NAMES if "save-link" not in self.inv[sid]["flags"]], [])
