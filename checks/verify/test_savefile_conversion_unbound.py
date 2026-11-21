from pathlib import Path
import contextlib
import io
import struct
import tempfile
import unittest

from gen3tl.verify.savefile import EOS, SaveError, SaveFile, apply_names, blank_save, convert, find_name, main, name_of, plan_names
from gen3tl.verify.savefixture import GAME_EGG_NICKNAME, TestMon, compressed_pokemon, party_pokemon

import savefile_support
from savefile_support import CS, LAYOUT, PLAYER_ID, SAVE, SHARED, TABLE, en, padded, put_hof, ru, setUpModule

class SaveTest(unittest.TestCase):
    def names(self):
        species = [b"", b"BULBA", b"ONIX", b"PIKACHU"]
        return (species, b"EGG"), ([b"", b"BULBAZAVR", b"ONIKS", b"PIKACHU"], b"YAJCO")

    def make(self, rotation=3):
        s = SaveFile(blank_save(LAYOUT, rotation=rotation), LAYOUT)
        slot = s.slots[0]
        s.write(slot, LAYOUT.party["count"], bytes([2]))
        s.write(slot, LAYOUT.party["base"], party_pokemon(TestMon("party", 0, 1, b"BULBA"), b"A"))
        s.write(slot, LAYOUT.party["base"] + 100, party_pokemon(TestMon("party", 1, 3, b"SPARKY"), b"A"))
        boxes = {rng["first"]: rng["ram"] for rng in LAYOUT.boxes}
        s.write(slot, boxes[20], compressed_pokemon(TestMon("box", 0, 2, b"ONIX"), b"A"))   # sector 30
        s.write(slot, boxes[25] + 29 * 58, compressed_pokemon(TestMon("box", 0, 2, b"EGG", egg=True), b"A"))
        s.write(slot, boxes[25] + 28 * 58, compressed_pokemon(TestMon("box", 0, 2, GAME_EGG_NICKNAME, egg=True), b"A"))
        s.write(slot, boxes[23], compressed_pokemon(TestMon("box", 0, 3, b"PIKACHU"), b"A"))
        s.fix_checksums()
        return s

    def test_regions_cover_every_box_area(self):
        s = self.make()
        slot = s.slots[0]
        for rng in LAYOUT.boxes:
            last = rng["ram"] + rng["count"] * 30 * 58
            s.locate(slot, rng["ram"], 58)
            s.locate(slot, last - 58, 58)
        self.assertGreaterEqual(s.locate(slot, LAYOUT.boxes[1]["ram"], 58), 30 * LAYOUT.sector_size)  # boxes 20-22
        with self.assertRaises(SaveError):
            s.locate(slot, 0x2000000, 4)

    def test_convert_round_trip_and_checksums(self):
        s = self.make()
        before = s.to_bytes()
        src, dst = self.names()
        changes = convert(s, src, dst)
        got = {(c.place, c.old, c.new) for c in changes}
        self.assertEqual(got, {("party 1", b"BULBA", b"BULBAZAVR"), ("box 20 slot 1", b"ONIX", b"ONIKS")})
        # PIKACHU equal, SPARKY typed; eggs keep their names
        s2 = SaveFile(s.to_bytes(), LAYOUT)   # checksums valid after conversion
        slot = s2.slots[0]
        self.assertEqual(name_of(s2.nickname(slot, LAYOUT.party["base"] + 100)), b"SPARKY")
        box25 = {rng["first"]: rng["ram"] for rng in LAYOUT.boxes}[25]
        self.assertEqual((s2.nickname(slot, box25 + 29 * 58)[:3], s2.nickname(slot, box25 + 28 * 58)),
                         (b"EGG", GAME_EGG_NICKNAME))
        convert(s2, dst, src)
        self.assertEqual(s2.to_bytes(), before)

    def test_box_name_round_trip_preserves_zero_fill(self):
        s = self.make()
        slot = s.slots[0]
        address = LAYOUT.box_names["addresses"][0]
        size = LAYOUT.box_names["size"]
        s.write(slot, address, b"BOX 1" + bytes([EOS]) + bytes(size - 6))
        s.fix_checksums()
        before = s.to_bytes()
        src, dst = self.names()
        src = (*src, [[b"BOX 1"]])
        dst = (*dst, [[b"YASHIK1"]])
        convert(s, src, dst)
        convert(s, dst, src)
        self.assertEqual(s.to_bytes(), before)

    def test_slots_newest_first_and_bad_checksum_rejected(self):
        raw = bytearray(blank_save(LAYOUT, counter=5, slot=0))
        b = blank_save(LAYOUT, counter=6, slot=1)
        raw[14 * 0x1000:28 * 0x1000] = b[14 * 0x1000:28 * 0x1000]
        s = SaveFile(bytes(raw), LAYOUT)
        self.assertEqual([x.counter for x in s.slots], [6, 5])
        raw[14 * 0x1000] ^= 1  # damage one section of slot 1
        self.assertEqual([x.counter for x in SaveFile(bytes(raw), LAYOUT).slots], [5])
        with self.assertRaises(SaveError):
            SaveFile(bytes(0x20000), LAYOUT)


class CyrillicNameTest(unittest.TestCase):
    def test_cyrillic_names(self):
        self.assertTrue(CS.has_target_letters(ru("Саша")))
        self.assertEqual(CS.transliterate(ru("Саша")), en("Sasha"))
        self.assertEqual(CS.transliterate(ru("Хрюша")), en("Khryusha"))
        self.assertEqual(CS.transliterate(ru("ЩУКА")), en("SCHUKA"))

    def test_look_alike_letters_have_their_own_codes(self):
        # «Сара» reads blank on the English ROM, not «Capa»
        self.assertNotEqual(ru("Сара"), en("Capa"))
        self.assertTrue(CS.has_target_letters(ru("Сара")))
        self.assertEqual(CS.transliterate(ru("Сара")), en("Sara"))
        self.assertEqual(CS.transliterate(ru("ОКО Ёх")), en("OKO Yokh"))
        self.assertEqual(CS.transliterate(ru("Сa")), en("Sa"))   # a Latin letter stays
        self.assertIsNone(CS.transliterate(en("Capa")))
        self.assertIsNone(CS.transliterate(en("Sparky")))

    def test_every_russian_code_transliterates(self):
        letters = "АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯабвгдеёжзийклмнопрстуфхцчшщъыьэюя"
        codes = {ch: b for b, ch in TABLE.items() if ch in letters}
        self.assertEqual(set(codes), set(letters))
        self.assertEqual(SHARED, {})
        latin = {b for b, ch in TABLE.items() if not "\u0400" <= ch <= "\u04ff"}
        self.assertFalse(set(codes.values()) & latin)
        for ch in letters.replace("ъ", "").replace("ь", "").replace("Ъ", "").replace("Ь", ""):
            out = CS.transliterate(bytes([codes[ch]]))
            self.assertTrue(out and all(b in latin for b in out), ch)

    def test_digits_and_symbols_kept(self):
        self.assertEqual(CS.transliterate(ru("Ёж-2!")), en("Yozh-2!"))

    def test_replacement_names_use_the_target_set(self):
        with self.assertRaises(SaveError):
            CS.encode("Женя", False)
        self.assertEqual(CS.encode("Женя", True), ru("Женя"))


class NameFieldTest(savefile_support.NameFieldTest, unittest.TestCase):
    def test_fields_and_limits(self):
        s = self.make()
        fields = s.name_fields()
        self.assertEqual([x.index for x in s.slots], [1, 0])
        labels = {f.label for f in fields}
        for label in ("player", "rival", "box 3", "party 1", "party 1 OT", "box 1 slot 1 OT", "box 20 slot 1",
                      "mail 1", "link record 1", "hall of fame 1 slot 2"):
            self.assertIn(label, labels)
        shared = [f for f in fields if f.label == "box 20 slot 1"]
        self.assertEqual([f.slots for f in shared], [[1, 0]])          # listed once, with both slots
        limit = {f.label: f.limit for f in fields}
        self.assertEqual((limit["player"], limit["party 1 OT"], limit["party 1"], limit["box 3"],
                          limit["rival"], limit["hall of fame 1 slot 1"]), (7, 7, 10, 8, 7, 10))

    def test_transliteration_and_overflow(self):
        s = self.make()
        before = s.to_bytes()
        changes, over = plan_names(s, s.name_fields(), CS, {}, True)
        self.assertEqual(len(over), 1)                                   # «Щекочущий» -> 14 letters, 10 fit
        self.assertEqual(over[0].latin, en("Schekochuschiy"))
        self.assertEqual({f.label for f in over[0].fields}, {"party 2", "hall of fame 1 slot 2"})
        self.assertEqual(s.to_bytes(), before)                           # planning writes nothing
        new = {(c.field.slots[0] if c.field.slots else None, c.field.label): c.new for c in changes}
        for slot in (0, 1):
            self.assertEqual(new[slot, "player"], en("Zhenya"))
            self.assertEqual(new[slot, "party 1 OT"], en("Zhenya"))     # consistent with the player
            self.assertEqual(new[slot, "party 3 OT"], en("Zhenya"))
            self.assertEqual(new[slot, "box 1 slot 1"], en("SCHUKA"))
            self.assertEqual(new[slot, "box 1 slot 1 OT"], en("Vasya"))
            self.assertEqual(new[slot, "box 3"], en("Khizhina"))
            self.assertEqual(new[slot, "rival"], en("Yura"))
            self.assertEqual(new[slot, "mail 1"], en("Yura"))
            self.assertEqual(new[slot, "link record 1"], en("Schukar"))
            self.assertNotIn((slot, "party 3"), new)                    # Latin «Sparky» stays
        self.assertEqual(new[1, "box 20 slot 1"], en("Yozhik"))
        self.assertEqual(new[None, "hall of fame 1 slot 1"], en("Shustrik"))

    def test_replacement_then_write(self):
        s = self.make()
        fields = s.name_fields()
        key = find_name(fields, "party 2", s.slots[0].index).key
        changes, over = plan_names(s, fields, CS, {key: en("Tickles")}, True)
        self.assertEqual(over, [])
        apply_names(s, changes)
        s2 = SaveFile(s.to_bytes(), LAYOUT)                               # slot and Hall of Fame checksums valid
        self.assertEqual([x.index for x in s2.slots], [1, 0])
        self.assertTrue(s2.hof_valid)
        got = self.names(s2)
        for slot in (0, 1):
            self.assertEqual(got[slot, "party 2"], en("Tickles"))
            self.assertEqual(got[slot, "party 1"], en("Shustrik"))
            self.assertEqual(got[slot, "mail 1"], en("Yura"))
            mail_field = s2.read(s2.slots[0], LAYOUT.mail["base"] + LAYOUT.mail["author"], 8)
            self.assertEqual(mail_field[:7], en("Yura") + b"\x00\x00" + bytes([EOS]))   # padded with spaces to 6
        self.assertEqual(got[None, "hall of fame 1 slot 2"], en("Tickles"))
        self.assertEqual(got[1, "box 20 slot 1"], en("Yozhik"))
        with self.assertRaises(SaveError):                                # never cut: a long name is refused
            plan_names(s, fields, CS, {key: en("Schekochuschiy")}, True)

    def test_player_rename_rewrites_matching_ot_names(self):
        s = self.make(nickname2="Шарик")
        fields = s.name_fields()
        newest = s.slots[0].index
        renames = {find_name(fields, "player", newest).key: en("Sasha"),
                   find_name(fields, "box 3", newest).key: en("Team"),
                   find_name(fields, "party 1", newest).key: en("Sparky"),
                   find_name(fields, "rival", newest).key: en("Gary")}
        changes, over = plan_names(s, fields, CS, renames, True)
        self.assertEqual(over, [])
        apply_names(s, changes)
        got = self.names(SaveFile(s.to_bytes(), LAYOUT))
        for slot in (0, 1):
            self.assertEqual(got[slot, "player"], en("Sasha"))
            self.assertEqual(got[slot, "party 1 OT"], en("Sasha"))       # trainer id and name are the player's
            self.assertEqual(got[slot, "party 2 OT"], en("Sasha"))
            self.assertEqual(got[slot, "party 3 OT"], en("Zhenya"))      # same name, other trainer id
            self.assertEqual(got[slot, "box 1 slot 1 OT"], en("Vasya"))  # player's id, other name
            self.assertEqual(got[slot, "party 1"], en("Sparky"))
            self.assertEqual(got[slot, "party 2"], en("Sharik"))
            self.assertEqual(got[slot, "box 3"], en("Team"))
            self.assertEqual(got[slot, "rival"], en("Gary"))
        self.assertEqual(got[1, "box 20 slot 1 OT"], en("Sasha"))
        self.assertEqual(got[None, "hall of fame 1 slot 1"], en("Sparky"))   # the same Pokemon, the same name

    def test_rename_without_transliteration(self):
        s = self.make()
        fields = s.name_fields()
        renames = {find_name(fields, "slot 0 party 3", s.slots[0].index).key: en("Rex")}
        changes, over = plan_names(s, fields, CS, renames, False)
        self.assertEqual(over, [])
        self.assertEqual({(c.field.slots[0], c.field.label) for c in changes}, {(0, "party 3"), (1, "party 3")})
        with self.assertRaises(SaveError):
            find_name(fields, "party 9", s.slots[0].index)

    def test_hall_of_fame_default_names_both_directions(self):
        """Hall of Fame default names map like those in the slots."""
        egg = LAYOUT.hall_of_fame["egg_species"]
        ru_names = ([b"", ru("Бульбазавр"), ru("Ивизавр"), ru("Венузавр")], ru("Яйцо"))
        en_names = ([b"", en("Bulbasaur"), en("Ivysaur"), en("Venusaur")], en("Egg"))
        raw = bytearray(blank_save(LAYOUT))
        put_hof(raw, [(1, 1, PLAYER_ID, ru("Бульбазавр")), (egg, 2, PLAYER_ID, ru("Яйцо")),
                      (3, 3, PLAYER_ID, ru("Шустрик")), (2, 4, PLAYER_ID, ru("Венузавр"))])  # not its species
        s = SaveFile(bytes(raw), LAYOUT)
        before = s.to_bytes()
        changes = convert(s, ru_names, en_names)
        self.assertEqual({(c.slot, c.place, c.egg, c.new) for c in changes},
                         {(None, "hall of fame 1 slot 1", False, en("Bulbasaur")),
                          (None, "hall of fame 1 slot 2", True, en("Egg"))})
        names, over = plan_names(s, s.name_fields(), CS, {}, True)
        self.assertEqual(over, [])
        self.assertEqual({c.field.label: c.new for c in names},
                         {"hall of fame 1 slot 3": en("Shustrik"), "hall of fame 1 slot 4": en("Venuzavr")})
        s2 = SaveFile(s.to_bytes(), LAYOUT)
        self.assertTrue(s2.hof_valid)                                   # checksum rewritten
        convert(s2, en_names, ru_names)                                 # and back: English defaults to Russian
        self.assertEqual(s2.to_bytes(), before)

    def test_main_refuses_until_every_name_fits(self):
        names = {"species_table": 0x40, "species_stride": 11, "species_count": 4, "egg_pointer": 0x10}

        def rom(species: list[bytes], egg: bytes) -> bytes:
            data = bytearray(0x200)
            struct.pack_into("<I", data, 0x10, 0x08000180)
            data[0x180:0x180 + 11] = padded(egg, 11)
            for i, n in enumerate(species):
                data[0x40 + 11 * i:0x40 + 11 * i + 11] = padded(n, 11)
            return bytes(data)

        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "ru.gba").write_bytes(rom([b"", ru("Бульбазавр"), ru("Ивизавр"), ru("Венузавр")], ru("Яйцо")))
            (d / "en.gba").write_bytes(rom([b"", en("BULBASAUR"), en("IVYSAUR"), en("VENUSAUR")], en("EGG")))
            (d / "in.sav").write_bytes(self.make().to_bytes())
            argv = [str(d / "in.sav"), str(d / "out.sav"), "--from-rom", str(d / "ru.gba"), "--to-rom",
                    str(d / "en.gba")]
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                rc = main(argv, layout=dict(SAVE, names=names), charmap=TABLE, charmap_target=SHARED, interactive=False)
            self.assertEqual(rc, 1)
            self.assertFalse((d / "out.sav").exists())
            self.assertIn('--rename "party 2=NEW"', err.getvalue())
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                rc = main(argv + ["--rename", "party 2=Tickles", "--player-name", "Sasha", "--box-name", "3=Team"],
                          layout=dict(SAVE, names=names), charmap=TABLE, charmap_target=SHARED, interactive=False)
            self.assertEqual(rc, 0)
            got = self.names(SaveFile((d / "out.sav").read_bytes(), LAYOUT))
            self.assertEqual((got[1, "player"], got[1, "party 1 OT"], got[1, "party 2"], got[1, "box 3"]),
                             (en("Sasha"), en("Sasha"), en("Tickles"), en("Team")))
            err = io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                rc = main(argv[:1] + [str(d / "out2.sav")] + argv[2:] + ["--rename", "party 2=Tickles", "--rename",
                                                                         "party 1 OT=Bob"],
                          layout=dict(SAVE, names=names), charmap=TABLE, charmap_target=SHARED, interactive=False)
            self.assertEqual(rc, 1)                          # the player's own OT name: only --player-name
            self.assertIn("--player-name renames it", err.getvalue())
            self.assertFalse((d / "out2.sav").exists())
