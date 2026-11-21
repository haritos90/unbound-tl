from pathlib import Path
from unittest import mock

from gen3tl.check import qa
from gen3tl.check.layout import Measure

from rom_support import needs_rom, rom_path
import qa_support
from project_fixture import unbound
from qa_support import PACK, batch_messages, setUpModule, tearDownModule

@needs_rom
class FireRedInterfaceWindowTest(qa_support.LabelWindowTest):
    """FireRed interface texts of region 0410000 in their windows."""

    CASES = {
        "s0415A97": (190, None, "Таинственный подарок", True),
        "s041EDBD": (120, None, "Таинственный подарок", True),
        "s041B6E3": (58, None, "Покедекс", True),
        # Unbound's save info: the value from x 47
        "s0416188": (43, "unbound-small", "Покедекс", True),
        "s0415D60": (232, "unbound-small", "{F8 0A}Выбор {F8 00}Далее {F8 01}Отмена", True),
        "s0415D93": (64, None, "Мальчик", True),
        "s04176FE": (96, None, "Почтовый ящик", True),
        "s04162DE": (56, None, "Важные вещи", False),
        "s0419C92": (84, "unbound-small", "{F8 0A}Выбор {F8 00}Смена", True),
        "s0418EBC": (40, "unbound-small", "{F8 0A}Выбор", True),
        "s0418E69": (127, None, "Имя соперника?", True),
        "s04186D1": (176, None, "Составить из четырёх слов", True),
        "s0417002": (224, None, "ОС приёма {STR_VAR_1} выросли.{PAUSE_UNTIL_PRESS}", True),
        "s0418C1B": (60, None, "Центр покемонов", False),
    }
    MESSAGES = ["s04162DE: line too wide: 66 > 56 px: 'Важные вещи'",
                "s0418C1B: line too wide: 89 > 60 px: 'Центр покемонов'"]

    def test_message_boxes(self):
        from gen3tl.discover import inventory as inv_mod
        from gen3tl.profile.profile import Profile
        prof = unbound()
        lims = qa.compute_limits(prof, inv_mod.load(Path("build/inventory.json")), qa.load_catalog(Path("po")),
                                 Measure(lambda b: 6, {}), PACK.charmap(), rom=prof.load_rom(rom_path()))
        self.assertEqual((lims["s0417002"].kind, lims["s0417002"].lines), ("dialogue", 2))


@needs_rom
class RemainingFireRedWindowTest(qa_support.LabelWindowTest):
    """FireRed interface texts of region 0410000: labels, bars, minigames."""

    CASES = {
        "s0419D57": (170, None, "Обмены покемонами", True),
        "s0419D66": (176, None, "Обмены и бои в Комнате союза", True),
        "s0419E57": (228, "unbound-small", "{F8 0A}Выбор {F8 0B}Смена {F8 00}{F8 01}Отмена", True),
        "s041A5FA": (238, None, "В ячейке {F7 00} перемещён\\nпокемон {F7 01}.", True),
        "s041B2A9": (56, None, "{FONT 00}Макс.{FONT 02} ОЖ", True),
        "s041B306": (224, None, "Покемон {F7 00} забыл\\nприём {F7 01}.\\p", True),
        "s041B554": (238, None, "{PLAYER} спешит в Центр покемонов,\\nоберегая измученных и ослабевших\\n"
                                "покемонов от новых бед…\\p", True),
        "s041B68F": (149, None, "Национальный", True),
        "s041B6F4": (72, None, "Предложить", True),
        "s041B779": (236, "unbound-small", "{F8 0B}Комбинации {F8 07}Ставка {F8 00}Стоп {F8 01}Выход", True),
        "s041D098": (73, None, "нажатий в секунду", False),
        "s041D13C": (114, None, "Игроков: {STR_VAR_1}", True),
        "s041DF82": (88, None, "На связи: {STR_VAR_1}", True),
        "s041DFAC": (124, "unbound-small", "{F8 0A}Выбор {F8 00}ОК {F8 01}Выход", True),
        "s041E20D": (208, None, "{STR_VAR_1} присылает: {STR_VAR_3}.", True),
        "s041E6A1": (208, None, "Чудо-карты нет, поэтому\\nбудет загружена новая карта.", True),
        "s041EB8E": (224, None, "Подарок отправлен тренеру {STR_VAR_1}.", True),
    }
    MESSAGES = ["s041D098: line too wide: 101 > 73 px: 'нажатий в секунду'"]

    def test_window_kinds(self):
        from gen3tl.discover import inventory as inv_mod
        from gen3tl.profile.profile import Profile
        prof = unbound()
        lims = qa.compute_limits(prof, inv_mod.load(Path("build/inventory.json")), qa.load_catalog(Path("po")),
                                 Measure(lambda b: 6, {}), PACK.charmap(), rom=prof.load_rom(rom_path()))
        self.assertEqual({sid: (lims[sid].kind, lims[sid].lines) for sid in
                          ("s041A5FA", "s041B306", "s041B554", "s041E20D", "s041E6A1")},
                         {"s041A5FA": ("multiline", 3), "s041B306": ("dialogue", 2), "s041B554": ("dialogue", 5),
                          "s041E20D": ("dialogue", 2), "s041E6A1": ("multiline", 2)})


@needs_rom
class FireRedTableWindowTest(qa_support.LabelWindowTest):
    """FireRed interface tables: lists, actions, messages and menus."""

    CASES = {
        "s0415F24": (148, None, "По номерам: Национальный", True),
        "s0415EFB": (160, None, "{COLOR 0F}{SHADOW 0E}Список покемонов", True),
        "s04161A0": (48, None, "Использовать", False),
        "s04161E9": (48, None, "Смотреть", True),
        "s041698D": (72, None, "Переставить", True),
        "s04161DE": (48, None, "Забрать", True),
        "s04169B7": (72, None, "Прочитать", True),
        "s0417242": (128, None, "Что делать с покемоном?", False),
        "s04172AE": (120, None, "ОС какого приёма?", True),
        "s04172D5": (152, None, "Что делать с предметом?", True),
        "s0417396": (168, None, "Выберите или отмените.", True),
        "s0A4E2E4": (168, None, "С каким покемоном слить?{PAUSE_UNTIL_PRESS}", True),
        "s0417445": (64, None, "Не может!", True),
        "s04175FB": (141, None, "Вернуться к месту лечения.", False),
        "s0417596": (141, None, "Колоть треснувшие камни.", True),
        "s04593C4": (123, None, "Обмен покемонами", True),
        "s041B375": (152, None, "Куда записать шаблон?", True),
        "s041B4D9": (224, None, "Если лидер уйдёт, чат будет\\nзавершён. Хорошо?", True),
        "s041EE21": (48, None, "Передать", True),
        "s041E245": (192, None, "Состояние беспроводной связи", True),
        "s041E284": (176, None, "В Комнате союза:", True),
        "s0457402": (56, None, "Игроков:\\n3", True),
        "s0419A3D": (220, None, "Странное яйцо покемона,\\nнайденное в Дневном уходе.", True),
        "s041CE3C": (208, None, "Готовы давить ягоды?\\nВыберите ягоду для игры.\\p", True),
        "s0459000": (208, None, "Выберите тренера\\nдля одиночной битвы.", True),
        "s045812C": (208, None, "Спасибо за ожидание!\\nДавай начнём бой!{PAUSE 3C}", True),
        "s0458668": (208, None, "Ого! Выпустить этого покемона\\nв такой ситуации?\\p", True),
        "s0417130": (224, None, "Этого покемона другой тренер\\nсейчас принять не может.", True),
    }
    MESSAGES = ["s04161A0: line too wide: 70 > 48 px: 'Использовать'",
                "s0417242: line too wide: 136 > 128 px: 'Что делать с покемоном?'",
                "s04175FB: line too wide: 153 > 141 px: 'Вернуться к месту лечения.'"]

    def test_window_kinds(self):
        from gen3tl.discover import inventory as inv_mod
        from gen3tl.profile.profile import Profile
        prof = unbound()
        lims = qa.compute_limits(prof, inv_mod.load(Path("build/inventory.json")), qa.load_catalog(Path("po")),
                                 Measure(lambda b: 6, {}), PACK.charmap(), rom=prof.load_rom(rom_path()))
        kinds = {"s0457402": ("multiline", 2), "s0419A3D": ("multiline", 3), "s041CE3C": ("dialogue", 2),
                 "s0459000": ("dialogue", 2), "s045812C": ("dialogue", 2), "s0458668": ("dialogue", 2),
                 "s0417130": ("dialogue", 2), "s04161A0": ("single", 1)}
        self.assertEqual({sid: (lims[sid].kind, lims[sid].lines) for sid in kinds}, kinds)


@needs_rom
class FireRedDataTableWindowTest(qa_support.LabelWindowTest):
    """FireRed options labels, PC menus, trade and multichoice windows."""

    CASES = {
        "s0419DD3": (122, None, "Скорость текста", True),
        "s0418484": (224, None, "Переместить", True),
        "s1F52A5F": (224, None, "Ностальгия", True),
        "s041825C": (144, None, "Выбор: {F7 00}.", True),
        "s0418433": (144, None, "Держит: {F7 00}.", True),
        "s0418392": (144, None, "{F7 00} возвращается!", True),
        "s041E1C5": (176, None, "Друг хочет обменяться\\nпокемонами.", True),
        "s04170FC": (176, None, "Покемона другого тренера\\nсейчас нельзя обменять.", True),
        "s0417E16": (80, None, "Четвёртый остров", False),
        "s0417DF3": (80, None, "Первый остров", True),
        "s0417F77": (214, None, "Вступить в группу", True),
        "s041808E": (214, None, "Уголок прямой связи", True),
        "s0417ECC": (214, None, "Остров Рождения", True),
        "s03DA8B4": (200, None, "Посылка с Покедексом\\nдля соперника.", True),
    }
    MESSAGES = ["s0417E16: line too wide: 96 > 80 px: 'Четвёртый остров'"]

    def limits(self):
        from gen3tl.discover import inventory as inv_mod
        from gen3tl.profile.profile import Profile
        prof = unbound()
        return qa.compute_limits(prof, inv_mod.load(Path("build/inventory.json")), qa.load_catalog(Path("po")),
                                 Measure(lambda b: 6, {}), PACK.charmap(), rom=prof.load_rom(rom_path()))

    def test_window_kinds(self):
        lims = self.limits()
        kinds = {"s041E1C5": ("multiline", 2, None), "s04170FC": ("multiline", 2, None),
                 "s0418484": ("single", 1, 27), "s0418392": ("single", 1, None), "s03DA8B4": ("multiline", 3, None)}
        self.assertEqual({sid: (lims[sid].kind, lims[sid].lines, lims[sid].chars) for sid in kinds}, kinds)

    def test_code_fills(self):
        """{F7 00} takes the item name where a record fills it so, else the nickname."""
        lims = self.limits()
        fills = {"s041825C": {"F7 00": 89}, "s0418433": {"F7 00": 89}, "s0418392": {"F7 00": 60}}
        self.assertEqual({sid: lims[sid].placeholders for sid in fills}, fills)

    def test_overflows(self):
        """A long item sentence, a 28-character menu item and a third trade line are refused."""
        import json

        from gen3tl.__main__ import main
        (self.batch / "translation.json").write_text(json.dumps(
            {"s0418433": "Покемон держит {F7 00}.", "s0418484": "Переместить на другое место.",
             "s041E1C5": "Ваш друг хочет обменяться с вами покемонами прямо сейчас, пока открыт зал."},
            ensure_ascii=False), encoding="utf-8")
        with mock.patch("builtins.print") as out:
            main(["--rom", str(rom_path()), "check", "batch", "t", "--po-root", "po"])
        lines = batch_messages(out)
        self.assertIn("s0418433: line too wide: 183 > 144 px: 'Покемон держит {F7 00}.' with {F7 00} = 89 px "
                      "(89 px, PC storage message window, item name)", lines)
        self.assertIn("s0418484: field overflow: 28 > 27 characters", lines)
        self.assertIn("s041E1C5: too many lines: 3 > 2", lines)


@needs_rom
class UnboundSystemRegionWindowTest(qa_support.LabelWindowTest):
    """Windows of the Unbound system region strings."""

    CASES = {
        "s1F10657": (86, None, "Назад", True),
        "s1F11D25": (238, None, "{PLAYER} спешит к ближайшему\\nцелителю, оберегая измученных\\nи ослабевших "
                                "покемонов\\nот новых бед…\\p", True),
        "s1F11DA3": (43, "unbound-small", "Прошлое", True),
        "s041617A": (43, "unbound-small", "Игрок", True),
        "s0416188": (43, "unbound-small", "Покедекс", True),
        "s0416190": (43, "unbound-small", "Время игры", False),
        "s1F11DAC": (92, "unbound-small", "{COLOR 02}{SHADOW 03}Никогда", True),
        "s1F11DD6": (104, None, "В Кубе:{FONT 00} {STR_VAR_1}", True),
        "s1F21C78": (48, None, "Кошелёк", True),
        "s1F21C01": (112, None, "Убрать в Куб", True),
        "s1F219FB": (184, None, "Предмет {STR_VAR_1} нельзя\\nзабрать из ПК!", True),
        "s1F21A82": (208, None, "Слишком темно, чтобы\\nиспользовать Локатор!\\p", True),
        "s1FB0052": (223, "unbound-small", "{COLOR 04}Цель миссии обновлена:{COLOR 02}", True),
        "s0416F9A": (224, None, "{STR_VAR_1} излечивается от ожога.{PAUSE_UNTIL_PRESS}", True),
        "s1F6822D": (237, "unbound-small", "Осталось: {B_COPY_VAR_2}    {F8 0C}Ход {F8 00}Бросок {F8 04}Ягода "
                                           "{F8 01}Бег", True),
        "s1F6834C": (237, "unbound-small", "{F8 0C}Ход {F8 01}Назад {F8 04}Другая {F8 00}Бросить: {B_COPY_VAR_1}",
                     False),
        "s1F68219": (224, None, "Появился дикий покемон {B_COPY_VAR_2}!", True),
        "s1F683E9": (224, None, "Отдать Сафариболы ({B_COPY_VAR_1} из {B_COPY_VAR_2} шт.),\\nчтобы перейти "
                                "к следующему покемону?", True),
        "s1F2BBBF": (208, None, "{COLOR 08}Как называется битва\\nпокемонов два на два?", True),
        "s1F061A0": (208, None, "Повысит уровень до {LV} {B_COPY_VAR_2}!", True),
        "s1F06757": (208, None, "Потеряет {B_COPY_VAR_2} ОЖ в месте:\\n{B_COPY_VAR_3}!", True),
        "s1F97D75": (222, None, "Озорной:{CLEAR_TO 4C}{COLOR 07}+Атака{CLEAR_TO 95}{COLOR 08}-Ос. защита", True),
        "s1F81ECD": (29, None, "сент. ", True),
        "s1F81E66": (134, None, "Начало пути", True),
        "s02375BD": (222, None, "Окаменелый панцирь", True),
    }
    MESSAGES = ["s0416190: line too wide: 52 > 43 px: 'Время игры'",
                "s1F6834C: line too wide: 239 > 237 px: '{F8 0C}Ход {F8 01}Назад {F8 04}Другая {F' with "
                "{B_COPY_VAR_1} = 60 px (60 px, Safari Game bar, Berry to throw)"]

    def limits(self):
        from gen3tl.discover import inventory as inv_mod
        from gen3tl.profile.profile import Profile
        prof = unbound()
        return qa.compute_limits(prof, inv_mod.load(Path("build/inventory.json")), qa.load_catalog(Path("po")),
                                 Measure(lambda b: 6, {}), PACK.charmap(), rom=prof.load_rom(rom_path()))

    def test_window_kinds(self):
        lims = self.limits()
        kinds = {"s1F11D25": ("dialogue", 5), "s1F219FB": ("multiline", 2), "s1F21A82": ("dialogue", 2),
                 "s0416F9A": ("dialogue", 2), "s1F68219": ("dialogue", 2), "s1F2BBBF": ("dialogue", 2),
                 "s1F061A0": ("dialogue", 2), "s1F6822D": ("single", 1), "s1F97D75": ("single", 1)}
        self.assertEqual({sid: (lims[sid].kind, lims[sid].lines) for sid in kinds}, kinds)

    def test_code_fills(self):
        lims = self.limits()
        fills = {"s1F11DD6": {"STR_VAR_1": 15}, "s1F6822D": {"B_COPY_VAR_2": 10}, "s1F6834C": {"B_COPY_VAR_1": 60},
                 "s1F683E9": {"B_COPY_VAR_1": 6, "B_COPY_VAR_2": 12}, "s1F061A0": {"B_COPY_VAR_2": 18},
                 "s1F06757": {"B_COPY_VAR_2": 24}}
        self.assertEqual({sid: lims[sid].placeholders for sid in fills}, fills)

    def test_item_pc_two_lines(self):
        """The item PC subwindow shows two lines: a third is refused."""
        import json

        from gen3tl.__main__ import main
        (self.batch / "translation.json").write_text(json.dumps(
            {"s1F219FB": "Предмет {STR_VAR_1} нельзя забрать из ПК: в сумке не осталось места для него!"},
            ensure_ascii=False), encoding="utf-8")
        with mock.patch("builtins.print") as out:
            main(["--rom", str(rom_path()), "check", "batch", "t", "--po-root", "po"])
        lines = batch_messages(out)
        self.assertIn("s1F219FB: too many lines: 3 > 2", lines)


@needs_rom
class UnionRoomWindowTest(qa_support.LabelWindowTest):
    """The Union Room and wireless windows."""

    CASES = {
        "s0459460": (208, None, "Бронзовая карточка!", True),
        "s0459488": (208, None, "Серебряная карточка!", True),
        "s045747C": (232, "unbound-small", "{F8 01}Отмена", True),
        "s0458FC8": (232, "unbound-small", "{F8 0A}Выбор  {F8 00}Вход  {F8 01}Отмена", True),
        "s0457A40": (208, None, "Привет! Хочешь чем-нибудь\\nзаняться?", True),
        "s045771C": (208, None, "Покинуть группу?", True),
        "s04594C4": (208, None, "Карточка тренера:\\n{F7 00} {F7 01}…\\l{F7 02}\\pПокедекс: {F7 03}\\n"
                                "Время:    {F7 04}:{F7 05}\\p", True),
        "s04571E0": (208, None, "Система беспроводной связи:\\nпоиск отменён.", True),
        "s0457234": (208, None, "{STR_VAR_1}! Ожидание связи\\nс другим игроком.", True),
        "s0459238": (208, None, "Ожидание ответа тренера {STR_VAR_1}…", False),
        "s0458FE4": (224, None, "Выберите тренера.", True),
        "s04574C4": (160, None, "{STR_VAR_2}: запрос.\\nПоделиться: {STR_VAR_1}?", True),
        "s0458FBC": (156, None, "Обмен яйцами", True),
    }
    # Activity hosts require every bounded source candidate.
    CASES.update({sid: (123, None, "", True) for sid in (
        "s0459394", "s04593A4", "s04593B4", "s04593C4", "s04593D4", "s04593DC",
        "s04593E4", "s04593F4", "s0459400", "s0459410", "s045941C", "s045942C")})
    CASES.update({"s0459434": (123, None, "Круговой обмен", True),
                  "s0459440": (123, None, "Обмен предметами", True)})
    MESSAGES = ["s0459238: line too wide: 210 > 208 px: 'Ожидание ответа тренера {STR_VAR_1}…'"]

    def limits(self):
        from gen3tl.discover import inventory as inv_mod
        from gen3tl.profile.profile import Profile
        prof = unbound()
        return qa.compute_limits(prof, inv_mod.load(Path("build/inventory.json")), qa.load_catalog(Path("po")),
                                 Measure(lambda b: 6, {}), PACK.charmap(), rom=prof.load_rom(rom_path()))

    def test_window_kinds(self):
        lims = self.limits()
        kinds = {"s0459460": ("single", 1), "s045747C": ("single", 1), "s0457A40": ("dialogue", 2),
                 "s045771C": ("dialogue", 2), "s04594C4": ("dialogue", 3), "s04571E0": ("multiline", 2),
                 "s0457234": ("multiline", 2), "s04574C4": ("multiline", 2)}
        self.assertEqual({sid: (lims[sid].kind, lims[sid].lines) for sid in kinds}, kinds)

    def test_prompt_window(self):
        """The Mystery Gift prompt window holds 160 px: the request wraps to a third line."""
        import json

        from gen3tl.__main__ import main
        (self.batch / "translation.json").write_text(json.dumps(
            {"s04574C4": "Запрос от тренера {STR_VAR_2}.\\nПоделиться: {STR_VAR_1}?"},
            ensure_ascii=False), encoding="utf-8")
        with mock.patch("builtins.print") as out:
            main(["--rom", str(rom_path()), "check", "batch", "t", "--po-root", "po"])
        lines = batch_messages(out)
        self.assertIn("s04574C4: too many lines: 3 > 2", lines)


@needs_rom
class FireRedListArrayWindowTest(qa_support.LabelWindowTest):
    """Rows 0 and 5 of the never-shown array size to their list."""

    CASES = {
        "s0417FD9": (222, None, "Значок валуна", True),
        "s0418000": (222, None, "Радужный значок", True),
        "s041802F": (222, None, "Значок земли, неба, гор, морей и всех рек мира", False),
        "s04180A7": (222, None, "Энергопорошок{CLEAR_TO 74}{FONT 00}50", True),
        "s0418163": (222, None, "Усилитель ОС{CLEAR_TO 65}{FONT 00}3000", True),
    }
    MESSAGES = ["s041802F: line too wide: 270 > 222 px: 'Значок земли, неба, гор, морей и всех ре'"]


@needs_rom
class SaveAndVsSeekerBoxWindowTest(qa_support.LabelWindowTest):
    """Start-menu save prompts and VS Seeker messages use window 0."""

    CASES = {
        "s01C566A": (208, None, "ВНИМАНИЕ!\\pУже есть сохранённый файл\\nдругой игры.\\pЕсли сохранить сейчас, "
                                "приключение\\nиз другого файла, включая предметы\\lи покемонов, пропадёт полностью."
                                "\\pВы точно хотите сохранить игру\\nи перезаписать другой файл?", True),
        "s01C55EA": (208, None, "Сохранение уже есть.\\nПерезаписать его?", True),
        "s01C137C": (208, None, "Батарея заряжена недостаточно.\\pШагов до полной зарядки\\nбатареи: {STR_VAR_1}"
                                "{PAUSE_UNTIL_PRESS}", True),
        "s01C13D6": (208, None, "В зоне действия нет тренеров,\\nс которыми можно сразиться…\\p"
                                "Боеискатель выключен.{PAUSE_UNTIL_PRESS}", True),
        "s01C1429": (208, None, "Другие тренеры, похоже,\\nещё не готовы к бою.\\pЛучше подождать."
                                "{PAUSE_UNTIL_PRESS}", True),
    }
    MESSAGES = []

    def test_window_kinds(self):
        from gen3tl.discover import inventory as inv_mod
        from gen3tl.profile.profile import Profile
        prof = unbound()
        lims = qa.compute_limits(prof, inv_mod.load(Path("build/inventory.json")), qa.load_catalog(Path("po")),
                                 Measure(lambda b: 6, {}), PACK.charmap(), rom=prof.load_rom(rom_path()))
        kinds = {"s01C566A": ("dialogue", 3), "s01C55EA": ("dialogue", 2), "s01C137C": ("dialogue", 2),
                 "s01C13D6": ("dialogue", 2), "s01C1429": ("dialogue", 2)}
        self.assertEqual({sid: (lims[sid].kind, lims[sid].lines) for sid in kinds}, kinds)

    def test_rom_printers(self):
        """Both printers draw in window 0 of the field templates, 26 tiles wide."""
        from gen3tl.profile.profile import Profile
        prof = unbound()
        box = prof["layout"]["window_box"]
        self.assertEqual({sid: box.get(sid) for sid in self.CASES}, {sid: "dialogue" for sid in self.CASES})
        rom = prof.load_rom(rom_path())

        def bl(a):
            hi, lo = rom.u16(a) & 0x7FF, rom.u16(a + 2) & 0x7FF
            return a + 4 + ((hi - 0x800 if hi & 0x400 else hi) << 12) + (lo << 1)

        self.assertEqual([rom.u8(0x41F42C + k) for k in range(5)], [0, 2, 15, 26, 4])   # bg, x, y, w, h
        self.assertEqual(rom.ptr_at(0xF6C84), 0x41F42C)   # InitStandardTextBoxWindows
        self.assertEqual([rom.ptr_at(p) for p in (0x6F884, 0x6F89C, 0x10C6CC, 0x10C6E8, 0x10C934)],
                         [0x1C566A, 0x1C55EA, 0x1C137C, 0x1C13D6, 0x1C1429])
        # save prompts: PrintSaveTextWithFollowupFunc, then AddTextPrinterForMessage_2
        self.assertEqual([bl(0x6F87A), bl(0x6F890), bl(0x6F6B4)], [0x6F69C, 0x6F69C, 0xF6E08])
        self.assertEqual((rom.u16(0xF6E3C), rom.u16(0xF6E3E), bl(0xF6E40)), (0x2000, 0x2102, 0xF6CD0))
        # VS Seeker: DisplayItemMessageOnField, window 0
        self.assertEqual([bl(0x10C6E2), bl(0x10C922)], [0xF7808, 0xF7808])
        self.assertEqual((rom.u16(0xF783C), bl(0xF7840)), (0x2100, 0xBF474))
