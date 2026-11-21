from pathlib import Path
from unittest import mock

from gen3tl.check import qa
from gen3tl.check.layout import Measure
from gen3tl.catalog.po import PoEntry

from rom_support import needs_rom, rom_path
from test_roots import PROJECT_ROOT as ROOT
import qa_support
from project_fixture import unbound
from qa_support import PACK, batch_messages, setUpModule, tearDownModule

@needs_rom
class FrontierWindowTest(qa_support.LabelWindowTest):
    """Battle Frontier, DexNav and record-screen windows; FD buffer words."""

    CASES = {
        "s0A378AE": (222, None, "Стоит густой туман…", True),
        "s0A43A55": (76, "unbound-small", "Сёрф по лаве", True),
        "s0A43A5F": (76, "unbound-small", "Старая удочка", True),
        "s0A442F8": (65, None, "выключены", True),
        "s0A45287": (60, None, "Джинджер", True),
        "s0A466D5": (222, None, "Сегодня опять поймал крупную рыбу!", True),
        "s0A46CD2": (208, None, "Кружись, кружись, кружись…", True),
        "s0A452A8": (208, None, "Ааааааааааааааааааааааааааааааааааа!", False),
        "s0A43A34": (42, None, "Цепочка звеньев: ", False),
    }
    MESSAGES = ["s0A43A34: line too wide: 93 > 42 px: 'Цепочка звеньев: '"]

    def test_record_speakers(self):
        from gen3tl.discover import inventory as inv_mod
        from gen3tl.catalog.batch import record_speakers
        from gen3tl.profile.profile import Profile
        prof = unbound()
        notes = record_speakers(prof["context"]["record_speakers"], prof.load_rom(rom_path()),
                                inv_mod.load(ROOT / "build" / "inventory.json"))
        self.assertTrue(notes["s0A452A8"][0].startswith("speaker: male, trainer class"))
        self.assertTrue(notes["s0A452A8"][0].endswith("(record 0 of battle-tower-trainers)"))
        females = {sid for sid, ls in notes.items() if any(l.startswith("speaker: female") for l in ls)}
        self.assertTrue(females)
        self.assertGreater(len(notes), 450)


@needs_rom
class FrontierSettingsWindowTest(qa_support.LabelWindowTest):
    """Battle Frontier settings and outfits."""

    CASES = {
        "s1F949C6": (80, None, "Чемпион Лиги покемонов", False),
        "s1F94426": (208, None, "Бой! Тренер Борриуса", True),
        "s1F94923": (208, None, "Тропа", True),
    }
    MESSAGES = ["s1F949C6: line too wide: 130 > 80 px: 'Чемпион Лиги покемонов'"]

    def test_window_kinds(self):
        from gen3tl.discover import inventory as inv_mod
        from gen3tl.profile.profile import Profile
        prof = unbound()
        lims = qa.compute_limits(prof, inv_mod.load(Path("build/inventory.json")), qa.load_catalog(Path("po")),
                                 Measure(lambda b: 6, {}), PACK.charmap(), rom=prof.load_rom(rom_path()))
        self.assertEqual((lims["s1F94426"].kind, lims["s1F94426"].width), ("single", 208))


@needs_rom
class BattleStringTableWindowTest(qa_support.LabelWindowTest):
    """FireRed battle strings and their windows."""

    CASES = {
        "s03FD124": (222, None, "{B_ATK_NAME_WITH_PREFIX}\\nустраивается вздремнуть!", True),
        "s03FCB0C": (222, None, "{B_ATK_NAME_WITH_PREFIX}\\nцепенеет от страха!", True),
        "s03FCA03": (222, None, "{B_SCR_ACTIVE_NAME_WITH_PREFIX}\\nменяет форму!", True),
        "s03FE714": (222, None, "{PAUSE 10}Ожидание связи…", True),
        "s03FDC58": (208, None, "Лог: В любом бою главное -\\nнаносить урон противнику.\\p", True),
        "s03FBBB4": (208, None, "{B_ATK_PREFIX2} окутывается\\nТуманом!", True),
        "s01A5CF1": (208, None, "Покемон {B_COPY_VAR_2} отправляется на чей-то ПК.\\pОн попадает в ячейку "
                                "“{B_COPY_VAR_1}”.", True),
        "s03FD56D": (103, None, "Команда игрока", True),
        "s03FD560": (103, None, "Противник", True),
        "s03FD60C": (126, None, "слишком сладко!", True),
        "s03FCB4A": (66, None, "повышается!", True),
        "s03FB283": (108, None, " повышенные", True),
        "s03FD8A2": (78, None, "Энигма-ягода", True),
        "s03FE846": (115, None, "заморозка", True),
        "s03FE868": (60, None, "Плохое яйцо", False),
        "s03FE874": (64, None, "{HIGHLIGHT 00}Победа", True),
        "s03FE883": (64, None, "{HIGHLIGHT 00}Ничья, никто не победил", False),
        "s03FE81C": (32, "unbound-small", "{HIGHLIGHT 02}Ост.: ", True),
        # the digits and the name measured
        "s03FE998": (120, None, "{B_COPY_VAR_1} мин. {B_COPY_VAR_2},{B_COPY_VAR_3} сек.", True),
        "s03FE6D5": (110, None, "Что сделает\\n{B_ACTIVE_NAME_WITH_PREFIX}?", True),
        "s03FE7A0": (64, None, "{PALETTE 05}{COLOR_HIGHLIGHT_SHADOW 0D 0E 0F}С каким\\nпоменять?", True),
    }
    MESSAGES = ["s03FE868: line too wide: 66 > 60 px: 'Плохое яйцо'",
                "s03FE868: field overflow: 11 > 10 characters",
                "s03FE883: line too wide: 135 > 64 px: '{HIGHLIGHT 00}Ничья, никто не победил'"]

    def test_window_kinds(self):
        from gen3tl.discover import inventory as inv_mod
        from gen3tl.profile.profile import Profile
        prof = unbound()
        lims = qa.compute_limits(prof, inv_mod.load(Path("build/inventory.json")), qa.load_catalog(Path("po")),
                                 Measure(lambda b: 6, {}), PACK.charmap(), rom=prof.load_rom(rom_path()))
        kinds = {"s03FD124": ("battle", 2, None), "s03FE714": ("battle", 2, None),
                 "s03FDC58": ("dialogue", 2, None), "s03FBBB4": ("dialogue", 2, None),
                 "s01A5CF1": ("dialogue", 2, None), "s03FCB4A": ("single", 1, None),
                 "s03FE868": ("single", 1, 10), "s03FE6D5": ("multiline", 2, None),
                 "s03FE7A0": ("multiline", 2, None)}
        self.assertEqual({sid: (lims[sid].kind, lims[sid].lines, lims[sid].chars) for sid in kinds}, kinds)

    def test_battle_box_lines(self):
        """A third line in a box of the battle message window must scroll."""
        import json

        from gen3tl.__main__ import main
        (self.batch / "translation.json").write_text(json.dumps(
            {"s03FD124": "{B_ATK_NAME_WITH_PREFIX}\\nустраивается\\nвздремнуть!"}, ensure_ascii=False),
            encoding="utf-8")
        with mock.patch("builtins.print") as out:
            main(["--rom", str(rom_path()), "check", "batch", "t", "--po-root", "po"])
        lines = batch_messages(out)
        self.assertIn("s03FD124: 3 lines in one box without scrolling", lines)

    def test_side_prefix_tokens(self):
        """Host lines measure the side prefix tokens at the widest fill, 'Ally'."""
        from gen3tl.profile.profile import Profile
        prof = unbound()
        m = Measure(lambda b: 6, prof["layout"]["placeholders"])
        tokens = [f"{{B_{side}_PREFIX{n}}}" for side in ("ATK", "DEF") for n in (1, 2, 3)]
        self.assertEqual({t: m.width(t, PACK.charmap()) for t in tokens}, {t: 82 for t in tokens})


@needs_rom
class RegionBattleBoxWindowTest(qa_support.LabelWindowTest):
    """Battle texts of two regions print in the battle message window."""

    CASES = {
        "s07649D7": (238, None, "{PLAYER} спешит к ближайшему\\nцелителю, оберегая измученных\\nи ослабевших "
                                "покемонов\\nот новых бед…\\p", True),
        "s0883590": (66, None, "очень резко ", True),
        "s08835A0": (66, None, "чрезвычайно сильно ", False),
        "s0893A04": (208, None, "У вас уже есть ТМ с этим приёмом.{PAUSE_UNTIL_PRESS}", True),
        "s082FFEC": (222, None, "{B_BUFF1} обретает\\nистинную силу через Ультравзрыв!", True),
        "s083008C": (222, None, "{B_BUFF1}: предмет {B_BUFF2}\\nреагирует на предмет {B_COPY_VAR_2}\\l"
                                "тренера {B_COPY_VAR_1}!", True),
        "s08A985E": (222, None, "Приём {B_CURRENT_MOVE} прикрывает\\nкоманду игрока!", True),
        "s08854B0": (222, None, "{B_TRAINER1_CLASS} {B_TRAINER1_NAME}\\nвызывает на бой!\\p", True),
        "s096C080": (222, None, "{B_ATK_NAME_WITH_PREFIX}\\nи {B_DEF_NAME_WITH_PREFIX}\\lменяются изменениями\\l"
                                "Атаки и Особой атаки!", True),
        "s096DB7C": (222, None, "Проливной дождь прекратился!", True),
    }
    MESSAGES = ["s08835A0: line too wide: 107 > 66 px: 'чрезвычайно сильно '"]

    def limits(self):
        from gen3tl.discover import inventory as inv_mod
        from gen3tl.profile.profile import Profile
        prof = unbound()
        return qa.compute_limits(prof, inv_mod.load(Path("build/inventory.json")), qa.load_catalog(Path("po")),
                                 Measure(lambda b: 6, {}), PACK.charmap(), rom=prof.load_rom(rom_path()))

    def test_window_kinds(self):
        lims = self.limits()
        kinds = {"s07649D7": ("multiline", 5), "s0883590": ("single", 1), "s0893A04": ("dialogue", 2),
                 "s082FFEC": ("battle", 2), "s083008C": ("battle", 2), "s08A985E": ("battle", 2),
                 "s08854B0": ("battle", 2), "s096C080": ("battle", 3), "s096DB7C": ("battle", 2)}
        self.assertEqual({sid: (lims[sid].kind, lims[sid].lines) for sid in kinds}, kinds)

    def test_battle_box_lines(self):
        """A battle text breaks into a second line and scrolls with \\l: no error."""
        import json

        from gen3tl.__main__ import main
        ids = ["s082FFEC", "s083008C", "s08A985E", "s096C080"]
        src = json.loads((self.batch / "source.json").read_text(encoding="utf-8"))
        (self.batch / "source.json").write_text(json.dumps([x for x in src if x["id"] in ids]), encoding="utf-8")
        (self.batch / "translation.json").write_text(json.dumps(
            {sid: self.CASES[sid][2] for sid in ids}, ensure_ascii=False), encoding="utf-8")
        with mock.patch("builtins.print") as out:
            main(["--rom", str(rom_path()), "check", "batch", "t", "--po-root", "po"])
        lines = batch_messages(out)
        self.assertEqual([l for l in lines if l.startswith("s") and "(warning)" not in l], [], lines)
        self.assertEqual(lines[-4:], ["checked      4 entries", "errors       0 errors",
                                      "warnings     3 warnings", "never        0 entries"])


@needs_rom
class FrontierAndMaxLabelWindowTest(qa_support.LabelWindowTest):
    """CFRU battle intros, G-Max labels and tier names in their windows."""

    CASES = {
        "s0A4C371": (222, None, "{FD 32} {FD 33}\\nвыпускает покемона {B_PLAYER_MON2_NAME}!\\l"
                                "Вперёд, {B_PLAYER_MON1_NAME}!", True),
        "s0A4C478": (222, None, "{B_TRAINER1_CLASS} {B_TRAINER1_NAME}\\nи {FD 2E} {FD 2F}\\lвыигрывают бой.\\p", True),
        "s0A4CD6A": (128, "unbound-small", "Разбрасывает Стальн. шипы", True),
        "s0A4CC5F": (128, "unbound-small", "Ком. + Шанс крит. попадания", False),
        "s0A4CBC6": (82, "unbound-small", "песчаную бурю", True),
        "s0A4CBA3": (61, "unbound-small", "Вызывает ", True),
        "s0A44134": (144, "unbound-small", "Без ограничений", True),
        "s0A4422A": (160, None, "Smogon Бенджамин Баттерфри", True),
        "s0A44261": (160, None, "Smogon Национальный Покедекс OU", False),
        "s0A442E3": (82, None, "“Кордильера”", True),
        "s0A442B9": (82, None, "Формат “Пещера”", False),
        "s0A44289": (203, None, "Smogon UU 7-го поколения", True),
        "s0A44092": (203, None, "Случайная одиночная битва", True),
        "s0A4432A": (208, None, "на наэлектризованном поле боя!\\pПокемоны на земле не могут уснуть,\\n"
                                "а их приёмы типа Электро сильнее!", True),
        "s0A44927": (208, None, "под защитной вуалью на обеих\\lсторонах поля боя!\\pПокемоны не смогут "
                                "вызывать\\nособые состояния друг у друга!", True),
    }
    MESSAGES = ["s0A4CC5F: line too wide: 139 > 128 px: 'Ком. + Шанс крит. попадания'",
                "s0A44261: line too wide: 182 > 160 px: 'Smogon Национальный Покедекс OU'",
                "s0A442B9: line too wide: 90 > 82 px: 'Формат “Пещера”'"]

    def test_window_kinds(self):
        from gen3tl.discover import inventory as inv_mod
        from gen3tl.profile.profile import Profile
        prof = unbound()
        lims = qa.compute_limits(prof, inv_mod.load(Path("build/inventory.json")), qa.load_catalog(Path("po")),
                                 Measure(lambda b: 6, {}), PACK.charmap(), rom=prof.load_rom(rom_path()))
        kinds = {"s0A4C371": ("battle", 3), "s0A4C478": ("battle", 3), "s0A4CD6A": ("single", 1),
                 "s0A44134": ("single", 1), "s0A44092": ("single", 1), "s0A4432A": ("dialogue", 2),
                 "s0A44927": ("dialogue", 2)}
        self.assertEqual({sid: (lims[sid].kind, lims[sid].lines) for sid in kinds}, kinds)

    def test_rom_tables(self):
        """The tables and windows the rules name, as the ROM holds them."""
        import json

        from gen3tl.profile.profile import Profile
        rom = unbound().load_rom(rom_path())
        inv = {e["id"]: e["offset"] for e in json.loads((ROOT / "build" / "inventory.json")
                                                         .read_text(encoding="utf-8"))["entries"]}
        tiers = [rom.ptr_at(0xA6B700 + 4 * k) for k in range(26)]
        self.assertEqual((tiers[0], tiers[1], tiers[17], tiers[18], tiers[22], tiers[25]),
                         tuple(inv[s] for s in ("s0A4412B", "s0A44134", "s0A44261", "s0A44278", "s0A442B9",
                                                "s0A442E3")))
        self.assertEqual(rom.ptr_at(0xA6B778), inv["s0A44092"])
        self.assertEqual((rom.ptr_at(0xA6B7A0), rom.ptr_at(0xA6B81C)), (inv["s0A4432A"], inv["s0A44C6B"]))
        viewer = {rom.u8(0xA6D220 + 2 * k) for k in range(24)}
        self.assertEqual(viewer, {0, *range(2, 18), *range(22, 26)})
        record = ({rom.u8(0xA6B6E8 + k) for k in range(rom.u8(0xA6B826))}
                  | {rom.u8(0xA6B6F0 + k) for k in range(rom.u8(0xA6B820))}
                  | {rom.u8(0xA6B822 + k) for k in range(rom.u8(0xA6B821))})
        self.assertEqual(record, {*range(0, 18), *range(22, 26)})
        mine = {rom.u8(0xA6B78C + k) for k in range(10)}
        self.assertEqual(mine, {2, 3, 4, 7, 8, 9, 11, 12, 13, 14})
        # window widths in tiles: viewer title, record tier, Max label
        self.assertEqual((rom.u8(0xA6D260 + 3), rom.u8(0xA6B8EC + 8 * 12 + 3), rom.u8(0x248330 + 8 * 5 + 3)),
                         (20, 18, 16))
        self.assertEqual(rom.u8(0x3FEB64 + 12 * 5 + 1), 0)   # window 5 prints in font 0


@needs_rom
class SendOutWindowTest(qa_support.SendOutWindowTest):
    pass


@needs_rom
class PartnerSendOutWindowTest(qa_support.SendOutWindowTest):
    """The partner's double send-out prints like the intro lines."""

    MONS = "{B_PLAYER_MON1_NAME} и {B_PLAYER_MON2_NAME}!"
    CASES = {"s0A4C3D8": (222, None, "{FD 32} {FD 33}\\nвыпускает на поле покемонов\\l" + MONS, False)}
    MESSAGES = ["s0A4C3D8: too many lines: 3 > 2"]
    # the form with a scroll, which stops the intro
    SCROLL = {"s0A4C3D8": "{FD 32} {FD 33}\\nвыпускает покемонов\\l" + MONS}
    # the two-line form that fits
    TWO_LINES = {"s0A4C3D8": "{FD 32} {FD 33} выпускает\\nпокемонов " + MONS}

    def test_box_kept(self):
        from gen3tl.discover import inventory as inv_mod
        from gen3tl.profile.profile import Profile
        prof = unbound()
        inv = inv_mod.load(ROOT / "build" / "inventory.json")
        by_id = {e["id"]: e for e in inv["entries"]}
        ids = ["s0A4C371", "s0A4C3F2"]
        self.assertIn("\\l", by_id["s0A4C371"]["text"])
        catalog = {sid: (Path("battle.po"), PoEntry(sid, by_id[sid]["text"], "")) for sid in ids}
        lims = qa.compute_limits(prof, inv, catalog, Measure(lambda b: 6, {}), PACK.charmap(), rom=prof.load_rom(rom_path()))
        self.assertEqual({sid: (lims[sid].kind, lims[sid].width) for sid in ids}, dict.fromkeys(ids, ("battle", 222)))
