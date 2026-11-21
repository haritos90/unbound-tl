from test_roots import TOOLKIT_ROOT
"""Savefile browser unbound checks and fixtures."""

import sys
from pathlib import Path
import contextlib
import io
import struct
import tempfile
import unittest

sys.path.insert(0, str(TOOLKIT_ROOT / "src"))

from gen3tl.verify.savefile import Layout, SaveError, SaveFile, blank_save, convert, main, name_of
from gen3tl.verify.savefixture import TestMon, compressed_pokemon, party_pokemon

import savefile_support
from savefile_support import (
    EditOnlyTest, FAKE_NAMES, LAYOUT, NameFieldTest, SAVE, SHARED, TABLE, en, fake_rom, padded, ru, 
    setUpModule,
)


class BrowserConvertTest(savefile_support.BrowserConvertTest, unittest.TestCase):
    def test_name_tables_round_trip(self):
        from gen3tl.verify.savefile import conversion_names, name_table, names_of
        layout = Layout.from_dict(dict(SAVE, names=FAKE_NAMES))
        self.assertEqual(names_of(name_table(self.RU, layout)), conversion_names(self.RU, layout))

    def test_same_bytes_as_main_to_english(self):
        save = NameFieldTest.make(self).to_bytes()
        report, out = self.browser(save, self.RU, self.EN)
        self.assertIsNone(out)
        self.assertEqual(report["over"], ["party 2"])   # Щекочущий: too long in Latin letters
        self.assertIsNone(self.main_bytes(save, self.RU, self.EN, []))
        requested = [("party 2", "Tickles"), ("player", "Sasha"), ("box 3", "Team")]
        report, out = self.browser(save, self.RU, self.EN, requested)
        self.assertEqual(report["over"], [])
        self.assertEqual(out, self.main_bytes(save, self.RU, self.EN, ["--rename", "party 2=Tickles", "--player-name",
                                                                       "Sasha", "--box-name", "3=Team"]))
        rows = {r["place"]: r for r in report["rows"]}
        self.assertEqual((rows["player"]["stored"], rows["player"]["after"], rows["player"]["kind"]),
                         ("Женя", "Sasha", "renamed"))
        self.assertEqual((rows["rival"]["after"], rows["rival"]["kind"]), ("Yura", "transliterated"))
        self.assertEqual((rows["party 3"]["after"], rows["party 3"]["kind"]), ("Sparky", "kept"))
        self.assertEqual(rows["box 3"]["limit"], LAYOUT.box_names["limit"])

    def test_the_counts_are_explained_by_kind(self):
        """A renamed player is also the original trainer on every Pokémon it caught."""
        from gen3tl.verify.savefile import change_kind, groups_text
        save = NameFieldTest.make(self).to_bytes()
        requested = [("party 2", "Tickles"), ("player", "Sasha"), ("box 3", "Team")]
        report, _out = self.browser(save, self.RU, self.EN, requested)
        self.assertEqual(report["renamed_groups"], [
            {"kind": "trainer record", "count": 2, "older_slot": 1}, {"kind": "box name", "count": 2, "older_slot": 1},
            {"kind": "original trainer of a Pokémon", "count": 5, "older_slot": 2},
            {"kind": "Pokémon nickname", "count": 3, "older_slot": 1}])
        self.assertEqual(sum(g["count"] for g in report["renamed_groups"]), report["renamed"])
        self.assertEqual(sum(g["count"] for g in report["transliterated_groups"]), report["transliterated"])
        self.assertEqual([g["kind"] for g in report["transliterated_groups"]],
                         ["rival", "Pokémon nickname", "original trainer of a Pokémon", "mail author", "link record"])
        self.assertEqual(groups_text(report["renamed_groups"][:2]),
                         "2 × trainer record (1 in the older save slot), 2 × box name (1 in the older save slot)")
        self.assertEqual([change_kind(x) for x in ("player", "rival", "box 2", "party 1", "party 1 OT", "box 3 slot 5",
                                                     "daycare 1 mail", "daycare 1 mail OT", "daycare 1 mail nickname",
                                                     "mail 2", "link record 1", "hall of fame 1 slot 2")],
                         ["trainer record", "rival", "box name", "Pokémon nickname", "original trainer of a Pokémon",
                          "Pokémon nickname", "mail author", "mail original trainer", "Pokémon nickname", "mail author",
                          "link record", "Pokémon nickname"])
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "in.sav").write_bytes(save)
            (d / "src.gba").write_bytes(self.RU)
            (d / "dst.gba").write_bytes(self.EN)
            argv = [str(d / "in.sav"), str(d / "out.sav"), "--from-rom", str(d / "src.gba"), "--to-rom",
                    str(d / "dst.gba"), "--rename", "party 2=Tickles", "--player-name", "Sasha", "--box-name", "3=Team"]
            out = io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
                rc = main(argv, layout=dict(SAVE, names=FAKE_NAMES), charmap=TABLE, charmap_target=SHARED, interactive=False)
            self.assertEqual(rc, 0)
            lines = out.getvalue().splitlines()
            self.assertIn("transliterated 16 names", lines)
            self.assertIn("renamed      12 names", lines)
            self.assertIn("group        trainer record\ncount        2 names\nolder        1 names", out.getvalue())
            self.assertIn("group        original trainer of a Pokémon\ncount        5 names\nolder        2 names", out.getvalue())
            self.assertIn("group        rival\ncount        2 names", out.getvalue())

    def test_same_bytes_as_main_from_english_and_errors(self):
        s = SaveFile(blank_save(LAYOUT, rotation=3), LAYOUT)
        slot = s.slots[0]
        s.write(slot, LAYOUT.party["count"], bytes([2]))
        s.write(slot, LAYOUT.party["base"], party_pokemon(TestMon("party", 0, 1, en("BULBASAUR")), en("ASH")))
        s.write(slot, LAYOUT.party["base"] + 100, party_pokemon(TestMon("party", 1, 3, en("Sparky")), en("ASH")))
        s.fix_checksums()
        save = s.to_bytes()
        report, out = self.browser(save, self.EN, self.RU)
        self.assertEqual(out, self.main_bytes(save, self.EN, self.RU, []))
        self.assertEqual((report["made"], report["defaults"], report["party"]), ({"source": 1, "target": 0}, 1, 2))
        rows = {r["place"]: r for r in report["rows"]}
        self.assertEqual((rows["party 1"]["stored"], rows["party 1"]["after"], rows["party 1"]["kind"]),
                         ("BULBASAUR", "Бульбазавр", "default"))
        report, out = self.browser(save, self.EN, self.RU, [("party 2", "Искра")])
        self.assertEqual(out, self.main_bytes(save, self.EN, self.RU, ["--rename", "party 2=Искра"]))
        with self.assertRaisesRegex(SaveError, "no name at"):
            self.browser(save, self.EN, self.RU, [("party 9", "X")])
        with self.assertRaisesRegex(SaveError, "no valid save slot"):
            self.browser(bytes(len(save)), self.EN, self.RU)


class NicknameEligibilityTest(unittest.TestCase):
    def setUp(self):
        self.tables = (([b"", en("BULBASAUR"), en("IVYSAUR")], en("EGG")),
                       ([b"", ru("Бульбазавр"), ru("Ивизавр")], ru("Яйцо")))
        self.charmap = {str(k): v for k, v in TABLE.items()}
        save = SaveFile(blank_save(LAYOUT, rotation=3), LAYOUT)
        slot = save.slots[0]
        names = [en("BULBASAUR"), ru("Бульбазавр"), en("IVYSAUR"), en("Buddy"), en("Bulbasaur"), b""]
        save.write(slot, LAYOUT.party["count"], bytes([len(names)]))
        for i, name in enumerate(names):
            save.write(slot, LAYOUT.party["base"] + 100 * i,
                       party_pokemon(TestMon("party", i, 1, name, personality=100 + i), en("ASH")))
        for i, name in enumerate([en("BULBASAUR"), en("IVYSAUR"), en("Buddy")]):
            save.write(slot, LAYOUT.boxes[0]["ram"] + LAYOUT.box_record["size"] * i,
                       compressed_pokemon(TestMon("box", i, 1, name, personality=200 + i), en("OT")))
        save.fix_checksums()
        self.data = save.to_bytes()

    def test_metadata_only_classification_uses_species_and_exact_bytes(self):
        from gen3tl.verify.savefile import browser_edit
        report, out = browser_edit(self.data, SAVE, self.charmap, SHARED, True, known_tables=self.tables)
        self.assertEqual(out, self.data)
        rows = {r["place"]: r for r in report["rows"]}
        for place in ("party 1", "party 2", "box 1 slot 1"):
            self.assertFalse(rows[place]["renameable"], place)
        for place in ("party 3", "party 4", "party 5", "party 6", "box 1 slot 2", "box 1 slot 3"):
            self.assertTrue(rows[place]["renameable"], place)
        unknown, _ = browser_edit(self.data, SAVE, self.charmap, SHARED, True)
        self.assertTrue(next(r for r in unknown["rows"] if r["place"] == "party 1")["renameable"])

    def test_conversion_shows_pc_nicknames_and_maps_only_same_species_defaults(self):
        from gen3tl.verify.savefile import browser_convert
        report, out = browser_convert(self.data, SAVE, *self.tables, self.charmap, SHARED,
                                      known_tables=self.tables)
        rows = {r["place"]: r for r in report["rows"]}
        self.assertFalse(rows["party 1"]["renameable"])
        self.assertFalse(rows["party 2"]["renameable"])
        self.assertTrue(rows["box 1 slot 2"]["renameable"])
        converted = SaveFile(out, LAYOUT)
        fields = {f.label: f for f in converted.name_fields()}
        self.assertEqual(converted.field_name(fields["party 1"]), ru("Бульбазавр"))
        self.assertEqual(converted.field_name(fields["box 1 slot 2"]), en("IVYSAUR"))
        back, english = browser_convert(self.data, SAVE, self.tables[0], self.tables[0], self.charmap, SHARED,
                                        known_tables=self.tables)
        converted = SaveFile(english, LAYOUT)
        fields = {f.label: f for f in converted.name_fields()}
        self.assertEqual(converted.field_name(fields["party 2"]), en("BULBASAUR"))
        self.assertFalse(next(r for r in back["rows"] if r["place"] == "party 2")["renameable"])

    def test_manual_rename_to_default_keeps_original_eligibility_and_conserves_bytes(self):
        from gen3tl.verify.savefile import browser_edit
        report, out = browser_edit(self.data, SAVE, self.charmap, SHARED, False,
                                   [("box 1 slot 3", "BULBASAUR")], known_tables=self.tables)
        row = next(r for r in report["rows"] if r["place"] == "box 1 slot 3")
        self.assertTrue(row["renameable"])
        self.assertEqual((row["after"], row["kind"]), ("BULBASAUR", "renamed"))
        allowed = EditOnlyTest.ranges(self, self.data, "box 1 slot 3")
        self.assertLessEqual({i for i, (a, b) in enumerate(zip(self.data, out)) if a != b}, allowed)
        SaveFile(out, LAYOUT)


BOX_NAMES = dict(FAKE_NAMES, box_text_pointer=0x14, box_name_pointers={"25": 0x18})


def box_rom(text: bytes, whole: bytes, species: list[bytes], egg: bytes) -> bytes:
    """fake_rom with the box text and the whole name of box 25."""
    data = bytearray(fake_rom(species, egg))
    struct.pack_into("<II", data, 0x14, 0x080001A0, 0x080001B0)
    data[0x1A0:0x1A9] = padded(text, 9)
    data[0x1B0:0x1B9] = padded(whole, 9)
    return bytes(data)


class BoxNameTest(unittest.TestCase):
    """Default box names map both ways; typed box names stay."""

    EN = box_rom(en("Box"), en("Preset"), [b"", en("BULBASAUR"), en("IVYSAUR"), en("VENUSAUR")], en("EGG"))
    RU = box_rom(ru("Ячейка"), ru("Готовые"), [b"", ru("Бульбазавр"), ru("Ивизавр"), ru("Венузавр")], ru("Яйцо"))
    LAYOUT = Layout.from_dict(dict(SAVE, names=BOX_NAMES))
    # typed: box 3, other box default (4), box 25 (24)
    TYPED = {3: "Team", 4: "Box1", 24: "Preset"}

    def save(self) -> SaveFile:
        s = SaveFile(blank_save(self.LAYOUT, rotation=3), self.LAYOUT)
        b = self.LAYOUT.box_names
        for i, addr in enumerate(b["addresses"], 1):
            name = self.TYPED.get(i, "Preset" if i == 25 else f"Box{i}")
            s.write(s.slots[0], addr, padded(en(name), b["size"]))
        s.fix_checksums()
        return SaveFile(s.to_bytes(), self.LAYOUT)

    def boxes(self, s: SaveFile) -> dict[int, bytes]:
        b = self.LAYOUT.box_names
        return {i: name_of(s.read(s.slots[0], addr, b["size"])) for i, addr in enumerate(b["addresses"], 1)}

    def test_default_box_names_both_directions(self):
        from gen3tl.verify.savefile import conversion_names, rom_names
        s = self.save()
        before = s.to_bytes()
        en_names, ru_names = conversion_names(self.EN, self.LAYOUT), conversion_names(self.RU, self.LAYOUT)
        self.assertEqual(en_names[2][24], [en("Box25"), en("Preset")])
        changes = convert(s, en_names, ru_names)
        self.assertEqual(sorted(int(c.place.split()[1]) for c in changes if c.box),
                         [i for i in range(1, 26) if i not in self.TYPED])
        got = self.boxes(SaveFile(s.to_bytes(), self.LAYOUT))           # checksums valid
        self.assertEqual((got[1], got[10], got[25]), (ru("Ячейка1"), ru("Ячейка10"), ru("Готовые")))
        self.assertEqual({i: got[i] for i in self.TYPED}, {i: en(n) for i, n in self.TYPED.items()})
        convert(s, ru_names, en_names)                                  # and back
        self.assertEqual(s.to_bytes(), before)
        s = self.save()
        s.write(s.slots[0], self.LAYOUT.box_names["addresses"][24], padded(en("Box25"), 9))
        convert(s, en_names, ru_names)
        self.assertEqual(self.boxes(s)[25], ru("Ячейка25"))              # the numbered default too
        s = self.save()
        convert(s, rom_names(self.EN, self.LAYOUT), rom_names(self.RU, self.LAYOUT))   # boxes kept
        self.assertEqual(self.boxes(s)[1], en("Box1"))

    def test_browser_and_main_convert_box_names_alike(self):
        from gen3tl.verify.savefile import browser_convert, conversion_names, name_table, names_of
        layout = dict(SAVE, names=BOX_NAMES)
        tables = [name_table(rom, self.LAYOUT) for rom in (self.EN, self.RU)]
        self.assertEqual(names_of(tables[0]), conversion_names(self.EN, self.LAYOUT))
        save = self.save().to_bytes()
        report, out = browser_convert(save, layout, *map(names_of, tables), {str(k): v for k, v in TABLE.items()},
                                      SHARED)
        rows = {r["place"]: r for r in report["rows"]}
        self.assertEqual((rows["box 1"]["stored"], rows["box 1"]["after"], rows["box 1"]["kind"]),
                         ("Box1", "Ячейка1", "default"))
        self.assertEqual((rows["box 3"]["after"], rows["box 3"]["kind"]), ("Team", "kept"))
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "in.sav").write_bytes(save)
            (d / "en.gba").write_bytes(self.EN)
            (d / "ru.gba").write_bytes(self.RU)
            argv = [str(d / "in.sav"), str(d / "out.sav"), "--from-rom", str(d / "en.gba"), "--to-rom",
                    str(d / "ru.gba")]
            with contextlib.redirect_stdout(io.StringIO()) as printed:
                rc = main(argv, layout=layout, charmap=TABLE, charmap_target=SHARED, interactive=False)
            self.assertEqual(rc, 0)
            self.assertIn("field        slot 0 box 1\nkind         box\nbefore       Box1\nafter        Ячейка1", printed.getvalue())
            self.assertEqual(out, (d / "out.sav").read_bytes())
        old = [{k: v for k, v in t.items() if k != "boxes"} for t in tables]   # tables published before
        _report, out = browser_convert(save, layout, *map(names_of, old), {str(k): v for k, v in TABLE.items()},
                                       SHARED)
        self.assertEqual(self.boxes(SaveFile(out, self.LAYOUT))[1], en("Box1"))
