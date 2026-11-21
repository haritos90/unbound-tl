from pathlib import Path
from unittest import mock

from gen3tl.check import qa
from gen3tl.check.layout import Measure

from rom_support import needs_rom, rom_path
import qa_support
from project_fixture import unbound
from qa_support import PACK, batch_messages, setUpModule, tearDownModule

@needs_rom
class CopiedWordWindowTest(qa_support.LabelWindowTest):
    """Words copied into a sentence or list; Town Map windows."""

    CASES = {
        "s1F63D68": (90, None, "{COLOR 06}Снайви", True),
        "s1F75798": (134, None, "красные", True),
        "s1F940FE": (89, None, "Серебро", True),
        "s1F94419": (112, None, "выключены", True),
        "s1F941B4": (150, None, "Команда ", True),
        "s1F966E8": (78, None, "Вирджиния", True),
        "s1F949D9": (78, None, "Карта Рубежа", True),
        "s1F77BAD": (212, "unbound-small", "{F8 0B}Выбор {F8 00}Изменить {F8 01}Выход {F8 02}{F8 03}Стр.", True),
        "s1F7804A": (220, None, "Этим приёмам сейчас научить нельзя.{PAUSE_UNTIL_PRESS}", True),
        # a message box text: re-wrapped into its 2 lines
        "s1F77D32": (220, None, "Сейчас этим приёмам научить нельзя, увы и ах.{PAUSE_UNTIL_PRESS}", True),
        "s1F67ECA": (198, None, "Древние руины, где, по преданию,\\nдавным-давно запечатали мощь\\nтёмной силы.", True),
    }
    MESSAGES = []

    def test_town_map_lines(self):
        from gen3tl.discover import inventory as inv_mod
        from gen3tl.profile.profile import Profile
        prof = unbound()
        lims = qa.compute_limits(prof, inv_mod.load(Path("build/inventory.json")), qa.load_catalog(Path("po")),
                                 Measure(lambda b: 6, {}), PACK.charmap(), rom=prof.load_rom(rom_path()))
        self.assertEqual((lims["s1F67ECA"].kind, lims["s1F67ECA"].lines), ("multiline", 5))


@needs_rom
class MissionListWindowTest(qa_support.LabelWindowTest):
    """Mission Log list items in the 171 px list window."""

    CASES = {
        "s1EE7188": (171, None, "Если бы людям было дано летать", False),   # 179 px
        "s1F08287": (171, None, "Капиталистическая революция", True),
        "s1F2CBA2": (171, None, "Путь героини", True),
        "s1F87B58": (157, None, "Энергостанция клетки", True),
        "s1FAFC94": (157, None, "Слишком много телевизора", True),
        "s1F85A4E": (154, None, "Ликитанг <-> Хитмонтоп", True),
        "s1F85B06": (154, None, "Шиинотик <-> Амунгусс", True),
        "s1EF6D1D": (148, None, "Окаменелость в подарок от Моулмена", False),
        "s1F692BF": (142, None, "Склад Сипорт", True),
    }
    MESSAGES = ["s1EE7188: too many lines: 2 > 1"]

    def test_profile_windows(self):
        from gen3tl.discover import inventory as inv_mod
        from gen3tl.profile.profile import Profile
        prof = unbound()
        lims = qa.compute_limits(prof, inv_mod.load(Path("build/inventory.json")), qa.load_catalog(Path("po")),
                                 Measure(lambda b: 6, {}), PACK.charmap(), rom=prof.load_rom(rom_path()))
        self.assertEqual({sid: (l.kind, l.width, l.lines) for sid, l in lims.items()},
                         {sid: ("multiline", w, 1) for sid, (w, _, _, _) in self.CASES.items()})

    def test_natural_forms(self):
        import json

        from gen3tl.__main__ import main
        (self.batch / "translation.json").write_text(
            json.dumps({sid: ru for sid, (_, _, ru, _) in self.CASES.items()}, ensure_ascii=False), encoding="utf-8")
        with mock.patch("builtins.print") as out:
            main(["--rom", str(rom_path()), "check", "batch", "t", "--po-root", "po"])
        lines = batch_messages(out)
        errors = {l.split(":")[0] for l in lines if l.startswith("s") and "(warning)" not in l}
        self.assertEqual(errors, {sid for sid, (_, _, _, fits) in self.CASES.items() if not fits}, lines)
        for m in self.MESSAGES:
            self.assertIn(m, lines)


@needs_rom
class StatScannerBoxTest(qa_support.LabelWindowTest):
    """Stat Scanner messages: 220 px box, 2 lines per box."""

    CASES = {
        "s1F77D72": (220, None, "Ещё рано учить этому приёму.{PAUSE_UNTIL_PRESS}", True),
        "s1F77F52": (220, None, "Этому приёму учит\\nфанат чешуек в\\nКратер-тауне.{PAUSE_UNTIL_PRESS}", False),
        "s1F781C2": (220, None, "Добро пожаловать!\\pЭта версия\\nпозволяет менять\\nпараметры…\\p", False),
        "s1F782CF": (220, None, "…учить их новым приёмам!\\p{F8 00} - начать изменения,\\n{F8 01} - сохранить их, "
                                "а {F8 02} и {F8 03} -\\lперейти на другую страницу!\\pДальнейшие подсказки по "
                                "ходу\\nизменений появляются внизу\\lинтерфейса.{PAUSE_UNTIL_PRESS}", True),
    }
    MESSAGES = ["s1F77F52: 3 lines in one box without scrolling",
                "s1F781C2: 3 lines in one box without scrolling"]

    def test_profile_windows(self):
        from gen3tl.discover import inventory as inv_mod
        from gen3tl.profile.profile import Profile
        prof = unbound()
        lims = qa.compute_limits(prof, inv_mod.load(Path("build/inventory.json")), qa.load_catalog(Path("po")),
                                 Measure(lambda b: 6, {}), PACK.charmap(), rom=prof.load_rom(rom_path()))
        self.assertEqual({sid: (l.kind, l.width, l.lines) for sid, l in lims.items()},
                         {sid: ("dialogue", 220, 2) for sid in self.CASES})

    def test_natural_forms(self):
        import json

        from gen3tl.__main__ import main
        (self.batch / "translation.json").write_text(
            json.dumps({sid: ru for sid, (_, _, ru, _) in self.CASES.items()}, ensure_ascii=False), encoding="utf-8")
        with mock.patch("builtins.print") as out:
            main(["--rom", str(rom_path()), "check", "batch", "t", "--po-root", "po"])
        lines = batch_messages(out)
        errors = {l.split(":")[0] for l in lines if l.startswith("s") and "(warning)" not in l}
        self.assertEqual(errors, {sid for sid, (_, _, _, fits) in self.CASES.items() if not fits}, lines)
        for m in self.MESSAGES:
            self.assertIn(m, lines)


@needs_rom
class KeypadIconWidthTest(qa_support.LabelWindowTest):
    """Keypad icons {F8 xx} measure at their drawn width."""

    CASES = {
        "s1F80B91": (120, "unbound-small", "{F8 0C}Ход {F8 00}Положить {F8 01}Отмена", True),
        "s1F80BA8": (120, "unbound-small", "{F8 0C}Ход {F8 00}Положить {F8 01}Отменить", False),
    }
    MESSAGES = ["s1F80BA8: line too wide: 128 > 120 px: '{F8 0C}Ход {F8 00}Положить {F8 01}Отмени'"]

    def test_measure_takes_the_token_width(self):
        m = Measure(lambda b: 6, {"F8 00": 8, "F8 04": 24}, styles={"small": lambda b: 5})
        cm = PACK.charmap()
        self.assertEqual(m.width("{F8 00}ОК", cm), 20)
        self.assertEqual(m.width("{F8 04}Голос", cm), 54)
        self.assertEqual(m.width("{F8 01}ОК", cm), 24)   # no width given: the two bytes

    def test_profile_widths_are_the_icon_table(self):
        from gen3tl.profile.profile import Profile
        prof = unbound()
        rom = prof.load_rom(rom_path())
        icons = {k: v for k, v in prof["layout"]["placeholders"].items() if k.startswith("F8 ")}
        # 4-byte records {tile, width, height}; record 13 is empty
        self.assertEqual(icons, {f"F8 {i:02X}": rom.u8(0x1EA6CC + 4 * i + 2) for i in range(13)})
        self.assertEqual(rom.u8(0x1EA6CC + 4 * 13 + 2), 0)


@needs_rom
class PcSelectionWindowTest(qa_support.LabelWindowTest):
    """Reject clipped PC labels with the longest names."""

    CASES = {
        "s0417B9F": (96, None, "Чей-то ПК", True),
        "s0417BAC": (96, None, "ПК Айлы", True),
        "s0417BB6": (96, None, "ПК тренера {PLAYER}", False),
        "s0417BBE": (104, None, "Зал славы", True),
        "s0417BCB": (96, None, "Выйти", True),
        "s0417BD3": (104, None, "ПК профессора Лога", False),
    }
    MESSAGES = ["s0417BB6: line too wide: 108 > 96 px: 'ПК тренера {PLAYER}'",
                "s0417BD3: line too wide: 107 > 104 px: 'ПК профессора Лога'"]


@needs_rom
class EasyChatWordWindowTest(qa_support.LabelWindowTest):
    """Easy chat words: 72 px and 12 characters per table."""

    CASES = {
        "s03E8A39": (72, None, "ДАЙ ПОБЕДИТЬ", True),
        "s03E9C96": (72, None, "ДОЛЖНО БЫТЬ", True),
        "s03E9235": (72, None, "Я", True),
        "s03E9C9E": (72, None, "ВСЕГДА ВМЕСТЕ", False),
    }
    MESSAGES = ["s03E9C9E: line too wide: 78 > 72 px: 'ВСЕГДА ВМЕСТЕ'",
                "s03E9C9E: field overflow: 13 > 12 characters"]

    def test_character_limit(self):
        from gen3tl.discover import inventory as inv_mod
        from gen3tl.profile.profile import Profile
        prof = unbound()
        lims = qa.compute_limits(prof, inv_mod.load(Path("build/inventory.json")), qa.load_catalog(Path("po")),
                                 Measure(lambda b: 6, {}), PACK.charmap(), rom=prof.load_rom(rom_path()))
        self.assertEqual({sid: lims[sid].chars for sid in self.CASES}, {sid: 12 for sid in self.CASES})


@needs_rom
class SortSuffixWindowTest(qa_support.LabelWindowTest):
    """The Mission Log header suffix ' A-Z' in the small font."""

    CASES = {"s1F5604A": (75, "unbound-small", " А-Я", True)}
    MESSAGES = []


@needs_rom
class MapSectionNameWindowTest(qa_support.LabelWindowTest):
    """Easy chat group names and map section names."""

    CASES = {
        "s041E07C": (80, None, "МОДНЫЕ СЛОВА", True),
        "s041E05C": (80, None, "ПРИЛАГАТЕЛЬНЫЕ", False),
        "s0B503A0": (94, None, "Мир деформации", True),
        "s03EEE9F": (94, None, "Подземный проход", False),
        "s0B52274": (94, None, "Детский сад покемонов", False),
        "s0B50214": (88, None, "Стоки Антисиса", True),
        "s07218F0": (88, None, "Великая пустыня", True),   # 89 px clips the shadow only
        "s03EF144": (80, None, "Боевая башня", True),
        "s1EDEFF4": (98, None, "Канализ. Антисис", True),   # a value between the arrows
    }
    MESSAGES = ["s041E05C: line too wide: 84 > 80 px: 'ПРИЛАГАТЕЛЬНЫЕ'",
                "s03EEE9F: line too wide: 96 > 94 px: 'Подземный проход'",
                "s0B52274: field overflow: 21 > 18 characters"]

    def test_track_name_column(self):
        """The full name, 114 px, wraps in the one-line 98 px column."""
        import json

        from gen3tl.__main__ import main
        (self.batch / "translation.json").write_text(
            json.dumps({"s1EDEFF4": "Канализация Антисис"}, ensure_ascii=False), encoding="utf-8")
        with mock.patch("builtins.print") as out:
            main(["--rom", str(rom_path()), "check", "batch", "t", "--po-root", "po"])
        lines = batch_messages(out)
        self.assertIn("s1EDEFF4: too many lines: 2 > 1", lines)

    def test_character_limit(self):
        from gen3tl.discover import inventory as inv_mod
        from gen3tl.profile.profile import Profile
        prof = unbound()
        lims = qa.compute_limits(prof, inv_mod.load(Path("build/inventory.json")), qa.load_catalog(Path("po")),
                                 Measure(lambda b: 6, {}), PACK.charmap(), rom=prof.load_rom(rom_path()))
        no_limit = {"s041E07C", "s041E05C", "s1EDEFF4"}   # not map section names
        self.assertEqual({sid: lims[sid].chars for sid in self.CASES},
                         {sid: None if sid in no_limit else 18 for sid in self.CASES})


@needs_rom
class PartyItemSubmenuWindowTest(qa_support.LabelWindowTest):
    """The party item submenu in its 7-tile window."""

    CASES = {
        "s0A4E1F1": (48, None, "Передать", True),
        "s04161C1": (48, None, "Отменить выбор", False),
    }
    MESSAGES = ["s04161C1: line too wide: 83 > 48 px: 'Отменить выбор'"]


@needs_rom
class OptionsScreenWindowTest(qa_support.LabelWindowTest):
    """Windows of Unbound's options screen."""

    CASES = {
        "s1F4DB6A": (96, None, "Общие настройки", True),
        "s1F4DABC": (94, None, "Звуковые эффекты", True),
        "s1F4DB3F": (94, None, "Ограничение предметов", False),
        "s0419E0A": (86, None, "Рамка", True),   # a value between the arrows
        "s1F4DB9D": (94, None, "Готово", True),
        "s1F4DD6D": (223, None, "Пропуск некоторых сюжетных сцен.", True),
        "s1F4DEDF": (223, None, "Динамики звучат одинаково.", True),
        # values between the arrows
        "s1F4DCBF": (98, None, "Только на Рубеже", True),
        "s1F4DD5F": (98, None, "Высокое (медленнее)", False),
        "s1F4DC62": (98, None, "Общая доля с лимитом", False),
        "s1EF2F17": (98, None, "Куб Корп. (снаружи)", False),
        "s1F94582": (98, None, "Бой! Агент Теней", True),
        "s1F94526": (98, None, "Бой! Элитная четвёрка", False),
        "s1F4DA6C": (98, None, "Нет", True),
        "s1F10619": (80, None, "По умолчанию", True),
        "s1F9425B": (98, None, "Без ограничений", True),   # a value between the arrows
        "s1F94397": (208, None, "Smogon Национальный Покедекс OU", True),
        "s1F4E230": (56, None, "Сохранить\\nСбросить\\nОтмена", True),
        "s1F4E4E2": (220, None, "{COLOR 06}Сохранить{COLOR 02} или {COLOR 04}сбросить{COLOR 02} изменения?", True),
        "s1F4E328": (220, None, "{COLOR 04}ВНИМАНИЕ!{COLOR 02}\\pЕсли понизить сложность боёв, её\\nнельзя будет "
                                "снова поднять, пока игра\\lне пройдена!\\pВы ТОЧНО хотите понизить\\nсложность боёв?", True),
    }
    MESSAGES = ["s1F4DB3F: line too wide: 125 > 94 px: 'Ограничение предметов'",
                "s1F4DB3F: field overflow: 21 > 19 characters",
                "s1F4DC62: line too wide: 120 > 98 px: 'Общая доля с лимитом'",
                "s1F94526: line too wide: 125 > 98 px: 'Бой! Элитная четвёрка'",
                "s1F4DD5F: line too wide: 111 > 98 px: 'Высокое (медленнее)'",
                "s1EF2F17: line too wide: 111 > 98 px: 'Куб Корп. (снаружи)'"]

    def test_window_kinds(self):
        from gen3tl.discover import inventory as inv_mod
        from gen3tl.profile.profile import Profile
        prof = unbound()
        lims = qa.compute_limits(prof, inv_mod.load(Path("build/inventory.json")), qa.load_catalog(Path("po")),
                                 Measure(lambda b: 6, {}), PACK.charmap(), rom=prof.load_rom(rom_path()))
        kinds = {"s1F4DABC": ("single", 1, 19), "s1F4DB3F": ("single", 1, 19), "s0419E0A": ("single", 1, 19),
                 "s1F4DB9D": ("single", 1, None), "s1F4DD6D": ("single", 1, None), "s1F4DCBF": ("single", 1, None),
                 "s1F94397": ("single", 1, None), "s1F4E230": ("multiline", 3, None),
                 "s1F4E4E2": ("dialogue", 2, None), "s1F4E328": ("dialogue", 2, None)}
        self.assertEqual({sid: (lims[sid].kind, lims[sid].lines, lims[sid].chars) for sid in kinds}, kinds)

    def test_message_box_lines(self):
        """A third line in a box of the 4-tile message window must scroll."""
        import json

        from gen3tl.__main__ import main
        (self.batch / "translation.json").write_text(json.dumps(
            {"s1F4E328": "Если понизить сложность боёв,\\nеё нельзя будет снова поднять,\\nпока игра не пройдена!"},
            ensure_ascii=False), encoding="utf-8")
        with mock.patch("builtins.print") as out:
            main(["--rom", str(rom_path()), "check", "batch", "t", "--po-root", "po"])
        lines = batch_messages(out)
        self.assertIn("s1F4E328: 3 lines in one box without scrolling", lines)


@needs_rom
class OptionsValueArrowWindowTest(qa_support.LabelWindowTest):
    """A selected options value is drawn between two arrows."""

    CASES = {
        "s1F4DD41": (98, None, "Низкое (быстрее)", True),
        "s1F4DD4E": (98, None, "Среднее (обычное)", False),
        "s1F4DD5F": (98, None, "Высокое (медленнее)", False),
        "s1F4DC62": (98, None, "Общая доля (лимит)", False),
        "s1F4DC8A": (98, None, "Только противник", True),
        "s1F4DA6C": (98, None, "Нет", True),
        "s0419E0A": (86, None, "Рамка", True),
    }
    MESSAGES = ["s1F4DD4E: line too wide: 100 > 98 px: 'Среднее (обычное)'",
                "s1F4DD5F: line too wide: 111 > 98 px: 'Высокое (медленнее)'",
                "s1F4DC62: line too wide: 106 > 98 px: 'Общая доля (лимит)'"]
    RULES = {"options-values": "options-values-arrows", "options-values-r-button": "options-values-r-button-arrows",
             "options-trainer-themes": "options-trainer-themes-arrows",
             "options-wild-themes": "options-wild-themes-arrows",
             "options-overworld-themes": "options-overworld-themes-arrows"}

    def test_widest_value(self):
        """A 99 px value ending in a shadow column passes, a 100 px one does not."""
        import json

        from gen3tl.__main__ import main
        (self.batch / "translation.json").write_text(json.dumps(
            {"s1F4DC62": "Общая доля (лим.)", "s1F4DD4E": "Среднее (базовое)"}, ensure_ascii=False),
            encoding="utf-8")
        with mock.patch("builtins.print") as out:
            main(["--rom", str(rom_path()), "check", "batch", "t", "--po-root", "po"])
        lines = batch_messages(out)
        self.assertEqual([l for l in lines if "line too wide" in l],
                         ["s1F4DD4E: line too wide: 100 > 98 px: 'Среднее (базовое)'"])

    def test_rom_arrow(self):
        """The right arrow sprite x is the value's width + 0x85; every value list has the rule."""
        from gen3tl.profile.profile import Profile
        prof = unbound()
        rom = prof.load_rom(rom_path())

        def bl(a):
            hi, lo = rom.u16(a) & 0x7FF, rom.u16(a + 2) & 0x7FF
            return a + 4 + ((hi - 0x800 if hi & 0x400 else hi) << 12) + (lo << 1)

        self.assertEqual([bl(0x1EBC4A4), bl(0x1EBC4A8)], [0x1EBC2D4, 0x1EBC450])   # getter, then arrow
        self.assertEqual((rom.u16(0x1EBC476), rom.u32(0x1EBC494)), (0x2001, 0x08005ED5))   # GetStringWidth font 1
        self.assertEqual((rom.u16(0x1EBC484), rom.u16(0x1EBC488)), (0x3085, 0x8418))   # x = width + 0x85
        self.assertEqual(rom.u32(0x1EBC498), 0x0202063C)   # gSprites
        rules = {r["name"]: r for r in prof["layout"]["table_window"]}
        keys = ("base", "stride", "count", "fields", "strip")
        for old, new in self.RULES.items():
            self.assertEqual({k: rules[old].get(k) for k in keys}, {k: rules[new].get(k) for k in keys}, new)
            self.assertEqual((rules[old]["width"], rules[new]["width"]), (112, 98))
        self.assertEqual(prof["layout"]["window_width"]["s1F4DA6C"], 98)


@needs_rom
class DexNavHelpAndBallListWindowTest(qa_support.LabelWindowTest):
    """The DexNav help pages and the ball changer list."""

    CASES = {
        "s1EE9B98": (208, None, "Иногда попадаются покемоны,\\nдержащие предмет.\\pЭто видно на панели поиска, "
                                "если\\nуровень поиска достаточно высок.", True),
        "s1EE983C": (208, None, "Чем выше уровень поиска, тем выше\\nшанс на идеальные характеристики.\\pКогда вы "
                                "подходите к покемону,\\nсеребряная звезда на панели поиска\\lпоказывает, что у него "
                                "может быть\\lидеальная характеристика.\\pУ покемона может быть не больше\\nтрёх "
                                "идеальных характеристик,\\lи каждую отмечает золотая звезда.", True),
        "s1F9842E": (208, None, "Приманка-бол", True),
        "s1F983A9": (208, None, "Гнездо-бол", True),
        "s1F9835E": (208, None, "Мастербол", True),
    }
    MESSAGES = []

    def test_window_kinds(self):
        from gen3tl.discover import inventory as inv_mod
        from gen3tl.profile.profile import Profile
        prof = unbound()
        lims = qa.compute_limits(prof, inv_mod.load(Path("build/inventory.json")), qa.load_catalog(Path("po")),
                                 Measure(lambda b: 6, {}), PACK.charmap(), rom=prof.load_rom(rom_path()))
        kinds = {"s1EE9B98": ("dialogue", 2, None), "s1EE983C": ("dialogue", 4, None),
                 "s1F9842E": ("single", 1, None)}
        self.assertEqual({sid: (lims[sid].kind, lims[sid].lines, lims[sid].chars) for sid in kinds}, kinds)

    def test_help_page_lines(self):
        """A third line in a box of a help page must scroll."""
        import json

        from gen3tl.__main__ import main
        out_of = {}
        for brk in ("\\n", "\\l"):
            (self.batch / "translation.json").write_text(json.dumps(
                {"s1EE9B98": f"Иногда попадаются\\nпокемоны,{brk}держащие предмет.\\pЭто видно на панели поиска, "
                             "если\\nуровень поиска достаточно высок."}, ensure_ascii=False), encoding="utf-8")
            with mock.patch("builtins.print") as out:
                main(["--rom", str(rom_path()), "check", "batch", "t", "--po-root", "po"])
            out_of[brk] = batch_messages(out)
        self.assertIn("s1EE9B98: 3 lines in one box without scrolling", out_of["\\n"])
        self.assertNotIn("s1EE9B98: 3 lines in one box without scrolling", out_of["\\l"])


@needs_rom
class SelfSizingListWindowTest(qa_support.LabelWindowTest):
    """Special 0x158 list items take the self-sizing window."""

    CASES = {
        "s1F71818": (222, None, "1 эт.: Стойка обслуживания", True),
        "s1F7182C": (222, None, "2 эт.: Лавка тренера, всё для путешествий и для тренировок", False),
        "s1F71841": (208, None, "3 эт.: Зона эволюции", True),
        "s1F0DE6A": (222, None, "Полис уязв.{CLEAR_TO 46} {FONT 00}10000 монет", True),
        "s1F0DDFA": (222, None, "Воздушный шар{CLEAR_TO 4B} {FONT 00}3000 монет", False),
        "s1F0DEFE": (222, None, "Поригон{CLEAR_TO 4B} {FONT 00}9999 монет", True),
        "s1F0DFF9": (222, None, "Танец мечей{CLEAR_TO 4B} {FONT 00}4000 монет", True),
        "s1EE9FFF": (222, None, "Скрытые таланты", True),
        "s1F27AFA": (222, None, "Естественная", True),
        "s1F941AE": (222, None, "Своя команда", True),
        "s1F6DEB2": (222, None, "Плита дракона", True),
        "s1F14A8B": (222, None, "Волшебноцвет", True),
    }
    MESSAGES = []

    def test_window_kinds(self):
        from gen3tl.discover import inventory as inv_mod
        from gen3tl.profile.profile import Profile
        prof = unbound()
        lims = qa.compute_limits(prof, inv_mod.load(Path("build/inventory.json")), qa.load_catalog(Path("po")),
                                 Measure(lambda b: 6, {}), PACK.charmap(), rom=prof.load_rom(rom_path()))
        kinds = {"s1F71818": ("single", 1), "s1F71841": ("multiline", 1), "s1F0DE6A": ("single", 1)}
        self.assertEqual({sid: (lims[sid].kind, lims[sid].lines) for sid in kinds}, kinds)

    def test_floor_sign_one_line(self):
        """A floor that is also a sign may not wrap: the list prints one line."""
        import json

        from gen3tl.__main__ import main
        (self.batch / "translation.json").write_text(json.dumps(
            {"s1F71841": "3 эт.: Зона эволюции, камни и предметы для обмена покемонами"}, ensure_ascii=False),
            encoding="utf-8")
        with mock.patch("builtins.print") as out:
            main(["--rom", str(rom_path()), "check", "batch", "t", "--po-root", "po"])
        lines = batch_messages(out)
        self.assertIn("s1F71841: too many lines: 2 > 1", lines)
