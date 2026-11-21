from test_roots import PROJECT_ROOT, TEST_ROOT, TOOLKIT_ROOT
"""Savefile editing unbound checks and fixtures."""

import sys
from pathlib import Path
import contextlib
import io
import struct
import tempfile
import unittest

sys.path.insert(0, str(TOOLKIT_ROOT / "src"))

from gen3tl.verify.savefile import (
    EOS, Layout, SaveError, SaveFile, blank_save, convert, find_name, main, name_of,
)
from gen3tl.verify.savefixture import GAME_EGG_NICKNAME, TestMon, compressed_pokemon, party_pokemon

import savefile_support
from savefile_support import (
    BrowserConvertTest, CS, EditOnlyTest, FAKE_NAMES, LAYOUT, NameFieldTest, SAVE, SHARED, TABLE, 
    en, padded, ru, setUpModule,
)


ROOT = PROJECT_ROOT


class EditOnlyTest(savefile_support.EditOnlyTest, unittest.TestCase):
    def test_no_edit_returns_the_file_and_lists_every_name(self):
        save = NameFieldTest.make(self).to_bytes()
        report, out = self.edit(save, True)
        self.assertEqual(out, save)
        self.assertEqual(report["renamed"], 0)
        rows = {r["place"]: r for r in report["rows"]}
        self.assertEqual(len(rows), len(report["rows"]))                 # one row per name
        for place in ("player", "rival", "party 1", "party 2", "party 3", "party 3 OT", "box 1 slot 1", "box 1 slot 1 OT",
                      "box 3", "box 20 slot 1", "mail 1", "link record 1"):
            self.assertIn(place, rows)
        self.assertNotIn("party 1 OT", rows)                               # the player's name: one row, the player
        self.assertNotIn("hall of fame 1 slot 2", rows)                    # the same Pokemon as party 2
        self.assertEqual((rows["player"]["stored"], rows["player"]["after"], rows["player"]["kind"], rows["player"]["limit"]),
                         ("Женя", "Женя", "kept", 7))
        self.assertEqual((rows["party 2"]["stored"], rows["box 1 slot 1"]["stored"]), ("Щекочущий", "ЩУКА"))
        self.assertEqual(report["container"], "raw")

    def test_name_spanning_sector_boundary_round_trip(self):
        s = SaveFile(blank_save(LAYOUT, rotation=3), LAYOUT)
        slot = s.slots[0]
        storage = LAYOUT.blocks["storage"]
        nickname = storage["ram"] + LAYOUT.data_size - 8
        record = nickname - LAYOUT.mon_names["nickname"]
        s.write(slot, record, compressed_pokemon(TestMon("box", 0, 25, en("Boundary")), en("OT")))
        s.fix_checksums()
        save = s.to_bytes()

        report, out = self.edit(save, False)
        self.assertEqual((report["renamed"], out), (0, save))
        f = find_name(s.name_fields(), "box 3 slot 11", slot.index)
        self.assertEqual([n for _o, n in f.segments], [8, 2])
        self.assertEqual(s.field_name(f), en("Boundary"))

        _report, edited = self.edit(save, False, [("box 3 slot 11", "Span")])
        changed = {i for i in range(len(save)) if save[i] != edited[i]}
        self.assertLessEqual(changed, self.ranges(save, "box 3 slot 11"))
        edited_save = SaveFile(edited, LAYOUT)
        f = find_name(edited_save.name_fields(), "box 3 slot 11", slot.index)
        self.assertEqual(edited_save.field_name(f), en("Span"))
        _report, restored = self.edit(edited, False, [("box 3 slot 11", "Boundary")])
        self.assertEqual(restored, save)

    def test_an_edit_writes_only_its_fields(self):
        save = NameFieldTest.make(self).to_bytes()
        for place, text in (("party 2", "Искра"), ("player", "Саша"), ("box 3", "Дом"), ("rival", "Gary")):
            with self.subTest(place=place):
                report, out = self.edit(save, True, [(place, text)])
                changed = {i for i in range(len(save)) if save[i] != out[i]}
                self.assertTrue(changed)
                self.assertLessEqual(changed, self.ranges(save, place))
                s = SaveFile(out, LAYOUT)                                    # every checksum still valid
                self.assertEqual([x.index for x in s.slots], [1, 0])
                self.assertTrue(s.hof_valid)
                got = {(f.slots[0] if f.slots else None, f.label): s.field_name(f) for f in s.name_fields()}
                self.assertEqual(got[1, place], ru(text) if place != "rival" else en(text))
                self.assertEqual(got[0, place], got[1, place])
                self.assertEqual([r["place"] for r in report["rows"] if r["kind"] == "renamed"], [place])
        _report, out = self.edit(save, True, [("party 2", "Искра")])
        got = {f.label: SaveFile(out, LAYOUT).field_name(f) for f in SaveFile(out, LAYOUT).name_fields() if not f.slots}
        self.assertEqual(got["hall of fame 1 slot 2"], ru("Искра"))       # the same Pokemon in the Hall of Fame
        report, out = self.edit(save, True, [("player", "Саша")])
        got = {(f.slots[0] if f.slots else None, f.label): SaveFile(out, LAYOUT).field_name(f)
               for f in SaveFile(out, LAYOUT).name_fields()}
        self.assertEqual((got[1, "party 1 OT"], got[1, "box 1 slot 1 OT"]), (ru("Саша"), ru("Вася")))

    def test_blank_and_wrong_names_from_a_conversion_are_corrected(self):
        s = NameFieldTest.make(self, nickname2="Шарик")
        for slot in s.slots:   # blank or transliterated nickname from an earlier conversion
            s.write(slot, LAYOUT.party["base"] + 8, bytes([EOS]) * 10)
            s.write(slot, LAYOUT.party["base"] + 108, padded(en("Sharik"), 10))
        s.fix_checksums()
        save = s.to_bytes()
        report, _out = self.edit(save, True)
        rows = {r["place"]: r for r in report["rows"]}
        self.assertEqual((rows["party 1"]["stored"], rows["party 2"]["stored"]), ("", "Sharik"))
        report, out = self.edit(save, True, [("party 1", "Шустрик"), ("party 2", "Шарик")])
        got = {(f.slots[0], f.label): SaveFile(out, LAYOUT).field_name(f) for f in SaveFile(out, LAYOUT).name_fields() if f.slots}
        for slot in (0, 1):
            self.assertEqual((got[slot, "party 1"], got[slot, "party 2"]), (ru("Шустрик"), ru("Шарик")))
        self.assertEqual({r["place"]: r["kind"] for r in report["rows"] if r["kind"] != "kept"},
                         {"party 1": "renamed", "party 2": "renamed"})

    def test_the_limit_and_the_letters_of_the_rom(self):
        save = NameFieldTest.make(self).to_bytes()
        with self.assertRaisesRegex(SaveError, "11 letters, the field holds 10"):
            self.edit(save, True, [("party 2", "Щекочущийся")])
        with self.assertRaisesRegex(SaveError, "8 letters, the field holds 7"):
            self.edit(save, True, [("player", "Евгения1")])
        with self.assertRaisesRegex(SaveError, "the target ROM has no"):
            self.edit(save, False, [("party 2", "Искра")])                # the English ROM has no Cyrillic letters
        with self.assertRaisesRegex(SaveError, "rename the player"):
            self.edit(save, True, [("slot 0 party 2 OT", "Боб")])
        report, out = self.edit(save, False, [("party 3", "Rex")])        # Latin fits both ROMs
        self.assertEqual(SaveFile(out, LAYOUT).field_name(find_name(SaveFile(out, LAYOUT).name_fields(), "party 3", 1)),
                         en("Rex"))

    def test_an_english_save_and_its_detection(self):
        from gen3tl.verify.savefile import default_matches, names_of, name_table
        layout = Layout.from_dict(dict(SAVE, names=FAKE_NAMES))
        en_names, ru_names = (names_of(name_table(rom, layout)) for rom in (BrowserConvertTest.EN, BrowserConvertTest.RU))
        s = SaveFile(blank_save(LAYOUT, rotation=3), LAYOUT)
        slot = s.slots[0]
        s.write(slot, LAYOUT.party["count"], bytes([3]))
        s.write(slot, LAYOUT.party["base"], party_pokemon(TestMon("party", 0, 1, en("BULBASAUR")), en("ASH")))
        s.write(slot, LAYOUT.party["base"] + 100, party_pokemon(TestMon("party", 1, 3, en("Sparky")), en("ASH")))
        s.write(slot, LAYOUT.party["base"] + 200, party_pokemon(TestMon("party", 2, 2, en("EGG"), egg=True), en("ASH")))
        s.fix_checksums()
        save = s.to_bytes()
        self.assertEqual(default_matches(SaveFile(save, LAYOUT), [en_names, ru_names]), [1, 0])   # not the egg word
        report, out = self.edit(save, False, [("party 1", "Bulby")])
        self.assertEqual({r["place"]: (r["stored"], r["egg"]) for r in report["rows"]
                          if r["place"] in ("party 1", "party 2", "party 3")},
                         {"party 1": ("BULBASAUR", False), "party 2": ("Sparky", False), "party 3": ("", True)})
        self.assertLessEqual({i for i in range(len(save)) if save[i] != out[i]}, self.ranges(save, "party 1"))
        converted = SaveFile(save, LAYOUT)
        convert(converted, en_names, ru_names)
        self.assertEqual(default_matches(converted, [en_names, ru_names]), [0, 1])

    def test_the_report_lists_the_letters_a_name_may_hold(self):
        """The page checks typed names against them; the write accepts exactly these."""
        save = NameFieldTest.make(self).to_bytes()
        translated, english = self.edit(save, True)[0]["letters"], self.edit(save, False)[0]["letters"]
        self.assertIn("Ж", translated)
        self.assertNotIn("Ж", english)
        self.assertLess(set(english), set(translated))
        for letters, target in ((translated, True), (english, False)):
            self.assertEqual(CS.encode(letters, target), bytes(CS.translated[ch] if target else CS.latin[ch] for ch in letters))
        with self.assertRaisesRegex(SaveError, "the target ROM has no '©'"):
            self.edit(save, True, [("party 3", "Rex©")])
        self.assertNotIn("©", translated)
        to_english = BrowserConvertTest.browser(self, save, BrowserConvertTest.RU, BrowserConvertTest.EN,
                                                [("party 2", "Tickles")])[0]
        to_russian = BrowserConvertTest.browser(self, save, BrowserConvertTest.EN, BrowserConvertTest.RU)[0]
        self.assertEqual((to_english["letters"], to_russian["letters"]), (english, translated))

    def test_a_game_made_egg_keeps_its_bytes_in_every_pass(self):
        """No pass writes an egg name; its row holds no name."""
        s = SaveFile(blank_save(LAYOUT, rotation=3), LAYOUT)
        slot = s.slots[0]
        boxes = {rng["first"]: rng["ram"] for rng in LAYOUT.boxes}
        s.write(slot, LAYOUT.party["count"], bytes([2]))
        s.write(slot, LAYOUT.party["base"], party_pokemon(TestMon("party", 0, 3, ru("Искра"), personality=7), ru("Женя")))
        s.write(slot, LAYOUT.party["base"] + 100, party_pokemon(TestMon("party", 1, 2, GAME_EGG_NICKNAME, egg=True,
                                                                        personality=8), ru("Женя")))
        s.write(slot, boxes[1], compressed_pokemon(TestMon("box", 0, 2, GAME_EGG_NICKNAME, egg=True, personality=9),
                                                   ru("Женя")))
        s.fix_checksums()
        save = s.to_bytes()
        self.assertTrue(CS.has_target_letters(name_of(GAME_EGG_NICKNAME)))

        def eggs(data):
            sv = SaveFile(data, LAYOUT)
            return [sv.nickname(sv.slots[0], addr) for addr in (LAYOUT.party["base"] + 100, boxes[1])]

        report, out = self.edit(save, True)
        rows = {r["place"]: r for r in report["rows"]}
        self.assertEqual([(rows[p]["stored"], rows[p]["after"], rows[p]["kind"], rows[p]["egg"])
                          for p in ("party 1", "party 2", "box 1 slot 1")],
                         [("Искра", "Искра", "kept", False), ("", "", "kept", True), ("", "", "kept", True)])
        self.assertEqual(out, save)
        for place in ("party 2", "box 1 slot 1"):
            with self.assertRaisesRegex(SaveError, f"{place} is an egg: the game names it at hatching"):
                self.edit(save, True, [(place, "Малыш")])
        report, out = self.edit(save, True, [("party 1", "Шарик")])
        self.assertLessEqual({i for i in range(len(save)) if save[i] != out[i]}, self.ranges(save, "party 1"))
        to_english = BrowserConvertTest.browser(self, save, BrowserConvertTest.RU, BrowserConvertTest.EN)
        to_russian = BrowserConvertTest.browser(self, save, BrowserConvertTest.EN, BrowserConvertTest.RU)
        for (report, out), main_args in ((to_english, (BrowserConvertTest.RU, BrowserConvertTest.EN)),
                                         (to_russian, (BrowserConvertTest.EN, BrowserConvertTest.RU))):
            rows = {r["place"]: r for r in report["rows"]}
            self.assertEqual((rows["party 2"]["stored"], rows["party 2"]["after"], rows["party 2"]["kind"],
                              rows["party 2"]["egg"]), ("", "", "kept", True))
            self.assertEqual(eggs(out), [GAME_EGG_NICKNAME, GAME_EGG_NICKNAME])
            self.assertEqual(out, BrowserConvertTest.main_bytes(self, save, *main_args, []))
        self.assertEqual([(g["kind"], g["count"]) for g in to_english[0]["transliterated_groups"]],
                         [("Pokémon nickname", 1), ("original trainer of a Pokémon", 3)])   # Искра, not the eggs
        with self.assertRaisesRegex(SaveError, "party 2 is an egg: the game names it at hatching"):
            BrowserConvertTest.browser(self, save, BrowserConvertTest.RU, BrowserConvertTest.EN, [("party 2", "Baby")])
        self.assertIsNone(BrowserConvertTest.main_bytes(self, save, BrowserConvertTest.RU, BrowserConvertTest.EN,
                                                        ["--rename", "party 2=Baby"]))

    def test_a_container_is_kept(self):
        import gzip
        data = gzip.decompress((TEST_ROOT / "fixtures" / "saves" / "gameshark-sp.gsv.gz").read_bytes())
        report, out = self.edit(data, True)
        self.assertEqual((report["container"], out), ("gsv", data))
        report, out = self.edit(data, True, [("party 2", "Искра")])
        self.assertEqual((len(out), out[:0x20], out[0x22:0x430]),
                         (len(data), data[:0x20], data[0x22:0x430]))
        self.assertLessEqual({i - 0x430 for i in range(0x430, len(data)) if data[i] != out[i]},
                             self.ranges(data[0x430:], "party 2"))


class EditCommandTest(unittest.TestCase):
    """verify save-convert --edit: the page's edit pass on the command line."""

    def run_main(self, d: Path, name: str, data: bytes, args: list[str]) -> tuple[int, list[str], str]:
        (d / name).write_bytes(data)
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = main([str(d / name)] + args, layout=dict(SAVE, names=FAKE_NAMES), charmap=TABLE, charmap_target=SHARED,
                      interactive=False)
        return rc, out.getvalue().splitlines(), err.getvalue()

    def english_save(self) -> bytes:
        s = SaveFile(blank_save(LAYOUT, rotation=3), LAYOUT)
        slot = s.slots[0]
        s.write(slot, LAYOUT.player["name"], padded(en("ASH"), LAYOUT.player["size"]))
        s.write(slot, LAYOUT.player["trainer_id"], struct.pack("<I", 0x2468ACE))   # TestMon's OT id
        s.write(slot, LAYOUT.party["count"], bytes([3]))
        s.write(slot, LAYOUT.party["base"], party_pokemon(TestMon("party", 0, 1, en("BULBASAUR")), en("ASH")))
        s.write(slot, LAYOUT.party["base"] + 100, party_pokemon(TestMon("party", 1, 3, en("Sparky"), personality=9), en("ASH")))
        s.write(slot, LAYOUT.party["base"] + 200, party_pokemon(TestMon("party", 2, 2, GAME_EGG_NICKNAME, egg=True,
                                                                        personality=10), en("ASH")))
        s.fix_checksums()
        return s.to_bytes()

    def test_the_same_bytes_as_the_page_in_the_input_container(self):
        import gzip

        from gen3tl.verify.savefile import browser_edit
        data = gzip.decompress((TEST_ROOT / "fixtures" / "saves" / "gameshark-sp.gsv.gz").read_bytes())
        requested = [("party 2", "Искра"), ("player", "Саша"), ("box 3", "Дом")]
        _report, page = browser_edit(data, SAVE, EditOnlyTest.CHARMAP, SHARED, True, requested)
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            rc, lines, _err = self.run_main(d, "Unbound.gsv", data, ["--edit", "--game", "translated", "--rename",
                                                                     "party 2=Искра", "--player-name", "Саша",
                                                                     "--box-name", "3=Дом"])
            self.assertEqual(rc, 0)
            self.assertEqual((d / "Unbound-edited.gsv").read_bytes(), page)
            self.assertNotEqual(page, data)
            for want in ("container    GameShark SP file", "game         translated", "field        party 2",
                         "before       Шарик", "after        Искра", "status       renamed", f"wrote        {d / 'Unbound-edited.gsv'}"):
                self.assertIn(want, lines)
            rc, _lines, _err = self.run_main(d, "Unbound.gsv", data, [str(d / "out.gsv"), "--edit", "--game", "translated"])
            self.assertEqual((rc, (d / "out.gsv").read_bytes()), (0, data))     # no rename: the file as it was

    def test_the_game_is_detected_from_the_default_names(self):
        from gen3tl.verify.savefile import browser_edit
        save = self.english_save()
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "en.gba").write_bytes(BrowserConvertTest.EN)
            (d / "ru.gba").write_bytes(BrowserConvertTest.RU)
            roms = ["--from-rom", str(d / "ru.gba"), "--to-rom", str(d / "en.gba")]
            rc, lines, _err = self.run_main(d, "game", save, ["--edit", *roms, "--rename", "party 2=Bulby"])
            self.assertEqual(rc, 0)
            self.assertEqual(lines[lines.index("game         original") + 1:][:2], [f"rom          {d / 'en.gba'}",
                                                                                     "matches      1 names"])
            page = browser_edit(save, SAVE, EditOnlyTest.CHARMAP, SHARED, False, [("party 2", "Bulby")])[1]
            self.assertEqual((d / "game-edited.sav").read_bytes(), page)
            rc, _lines, err = self.run_main(d, "game", save, ["--edit", *roms, "--rename", "party 2=Искра"])
            self.assertEqual((rc, err.splitlines()),
                             (1, ["error        'Искра': the target ROM has no 'И', 'а', 'к', 'р', 'с'"]))
            rc, lines, _err = self.run_main(d, "game", save, ["--edit", "--from-rom", str(d / "ru.gba"), "--dry-run"])
            self.assertIn("game         translated", lines)                  # one ROM: the game is that ROM
            blank = SaveFile(blank_save(LAYOUT, rotation=3), LAYOUT).to_bytes()
            rc, _lines, err = self.run_main(d, "blank.sav", blank, ["--edit", *roms])
            self.assertEqual((rc, err), (1, "error        no default name in this save tells the games apart: "
                                            "choose it with --game\n"))

    def test_the_dry_run_lists_every_name_and_writes_nothing(self):
        from gen3tl.verify.savefile import browser_edit
        save = self.english_save()
        report = browser_edit(save, SAVE, EditOnlyTest.CHARMAP, SHARED, False)[0]
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            rc, lines, _err = self.run_main(d, "x.srm", save, ["--edit", "--game", "original", "--dry-run"])
            self.assertEqual(rc, 0)
            self.assertEqual(sorted(p.name for p in d.iterdir()), ["x.srm"])
            text = "\n".join(lines)
            self.assertIn("field        player\nname         ASH\nlimit        7 letters\nstatus       kept", text)
            self.assertIn("field        party 3\nstatus       egg\n", text)                # no name: the game's egg word
            self.assertIn("renamed      0 names", lines)
            self.assertEqual([x[13:] for x in lines if x.startswith("field ")], [r["place"] for r in report["rows"]])
            self.assertNotIn("field        party 1 OT", lines)                      # the player's name
            rc, _lines, err = self.run_main(d, "x.srm", save, ["--edit", "--game", "original", "--rename", "party 3=Baby"])
            self.assertEqual((rc, err), (1, "error        party 3 is an egg: the game names it at hatching\n"))
            rc, _lines, err = self.run_main(d, "x.srm", save, ["--edit", "--game", "original", "--rename",
                                                               "party 2=Sparky12345"])
            self.assertEqual((rc, err), (1, "error        party 2: 11 letters, the field holds 10\n"))
            self.assertEqual(sorted(p.name for p in d.iterdir()), ["x.srm"])

    def test_options_and_the_output_name(self):
        from gen3tl.verify.savefile import edited_name
        cases = [("Unbound.srm", "Unbound-edited.srm"), ("UNBOUND.SAV", "UNBOUND-edited.SAV"), ("game", "game-edited.sav"),
                 ("Pokemon Unbound 2.1.1.1", "Pokemon Unbound 2.1.1.1-edited.sav"), (".srm", "save-edited.srm"),
                 ("Unbound.SaveRAM", "Unbound-edited.SaveRAM")]
        self.assertEqual([edited_name(name) for name, _out in cases], [out for _name, out in cases])
        save = self.english_save()
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            for args in (["--edit"], [str(d / "out.sav")],
                         [str(d / "out.sav"), "--game", "original", "--from-rom", "x", "--to-rom", "y"]):
                with self.subTest(args=args):
                    with self.assertRaises(SystemExit) as caught:
                        self.run_main(d, "in.sav", save, args)
                    self.assertEqual(caught.exception.code, 2)
