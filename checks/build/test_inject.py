import unittest

from gen3tl.core.charmap import Charmap
from gen3tl.build.inject import inject, verify

from rom_support import needs_rom, rom_path
from project_fixture import UNBOUND, unbound

CM = Charmap({"Б": 0x37})


ROOT = UNBOUND


@needs_rom
class AbilityPopupPossessiveTest(unittest.TestCase):
    """The ability pop-up possessive: codes stored after the nickname."""

    @classmethod
    def setUpClass(cls):
        cls.prof = unbound()
        cls.rom = cls.prof.load_rom(rom_path())
        cls.table = next(t for t in cls.prof["table"] if t["name"] == "ability_popup_possessive")

    def test_fields_are_the_stored_immediates(self):
        # Thumb: movs r2, #0xB4; strb r2, [r3]; movs r2, #0xE7;
        # strb r2, [r3, #1]; movs r3, #0xFF; strb r3, [r2]
        code = {0x9A8F44: 0x22B4, 0x9A8F46: 0x701A, 0x9A8F52: 0x22E7, 0x9A8F54: 0x705A,
                0x9A8F58: 0x23FF, 0x9A8F5E: 0x7013}
        self.assertEqual({at: self.rom.u16(at) for at in code}, code)
        t = self.table
        fields = [t["base"] + i * t["stride"] + t.get("field_offset", 0) for i in range(t["count"])]
        self.assertEqual((fields, t["field_length"], t["terminated"], t["pad"]),
                         ([0x9A8F44, 0x9A8F52], 1, False, 0xFF))

    def test_catalog_drops_the_possessive(self):
        import json

        from gen3tl.catalog.catalog import load_catalog
        from gen3tl.build.inject import field_bytes
        inv = json.loads((ROOT / "build" / "inventory.json").read_text(encoding="utf-8"))
        es = {e["id"]: e for e in inv["entries"] if e["id"].startswith("ability_popup_possessive:")}
        self.assertEqual({k: (e["offset"], e["text"], e["flags"]) for k, e in es.items()},
                         {"ability_popup_possessive:0": (0x9A8F44, "’", ["unterminated"]),
                          "ability_popup_possessive:1": (0x9A8F52, "s", ["unterminated"])})
        cat = load_catalog(ROOT / "translation" / "ru" / "po")
        self.assertEqual({k: (cat[k][1].msgstr, cat[k][1].flags) for k in es},
                         {k: ("", ["empty"]) for k in es})
        self.assertEqual(field_bytes(CM.encode(""), 1, self.table["pad"]), b"\xff")


@needs_rom
class BerryBlenderPossessiveTest(unittest.TestCase):
    """The berry blender possessive: literal and immediate after the nickname."""

    IDS = ("berry_blender_possessive:0", "berry_blender_apostrophe:0")

    @classmethod
    def setUpClass(cls):
        import json

        from gen3tl.catalog.catalog import load_catalog
        cls.prof = unbound()
        cls.rom = cls.prof.load_rom(rom_path())
        cls.tables = {t["name"]: t for t in cls.prof.get("table", [])}
        inv = json.loads((ROOT / "build" / "inventory.json").read_text(encoding="utf-8"))
        cls.entries = {e["id"]: e for e in inv["entries"] if e["id"].startswith("berry_blender_")}
        cls.catalog = load_catalog(ROOT / "translation" / "ru" / "po")

    def encoded(self, sid):
        # what the build writes for the entry
        from gen3tl.build.inject import field_bytes
        e = self.catalog[sid][1]
        blob = CM.encode("" if "empty" in e.flags else e.msgstr)
        inv = self.entries[sid]
        if "unterminated" in inv["flags"]:
            blob = field_bytes(blob, inv["length"], self.tables[inv["table"]].get("pad", 0x00))
        return blob

    def test_fields_are_the_appended_characters(self):
        # Thumb stores the text immediates and compares them
        code = {0x1EBB938: 0x23B4, 0x1EBB93A: 0xAA06, 0x1EBB93C: 0x8013, 0x1EBB93E: 0x334B,
                0x1EBB940: 0x7093, 0x1EBB944: 0x4B90, 0x1EBB948: 0x930B, 0x1EBB964: 0x2ACD,
                0x1EBB96A: 0x2AE7}
        self.assertEqual({at: self.rom.u16(at) for at in code}, code)
        self.assertEqual(self.rom.u32(0x1EBBB88), 0xFF00E7B4)
        fields = {n: (t["base"] + t.get("field_offset", 0), t["count"], t["field_length"],
                      t.get("terminated", True), t.get("pad", 0x00))
                  for n, t in self.tables.items() if n.startswith("berry_blender_")}
        self.assertEqual(fields, {"berry_blender_possessive": (0x1EBBB88, 1, 4, True, 0x00),
                                  "berry_blender_apostrophe": (0x1EBB938, 1, 1, False, 0xFF)})

    def test_catalog_gives_the_connector(self):
        self.assertEqual({k: (e["offset"], e["text"], e["flags"]) for k, e in self.entries.items()},
                         {"berry_blender_possessive:0": (0x1EBBB88, "’s ", []),
                          "berry_blender_apostrophe:0": (0x1EBB938, "’", ["unterminated"])})
        self.assertEqual(self.encoded("berry_blender_possessive:0"), CM.encode(": "))

    def test_apostrophe_keeps_a_terminator(self):
        # only 0xB4 ends the text there.
        # 0xFF ends it at once.
        b = self.encoded("berry_blender_apostrophe:0")
        self.assertEqual(len(b), 1)
        self.assertIn(b[0], (0xB4, 0xFF))

    def test_build_changes_only_the_literal(self):
        from gen3tl.build.inject import diff_positions
        texts = {sid: self.encoded(sid) for sid in self.IDS}
        rom = self.rom.copy()
        res = inject(rom, self.rom, {"entries": list(self.entries.values())}, texts, self.tables)
        self.assertEqual(verify(rom, self.rom, res, texts, set()), [])
        self.assertEqual(diff_positions(rom.data, self.rom.data), [0x1EBBB88, 0x1EBBB89, 0x1EBBB8A])
        self.assertEqual(CM.decode(rom.data, 0x1EBBB88)[0], ": ")


@needs_rom
class ItemPluralEndingTest(unittest.TestCase):
    """The plural ending of item names, stored after the name."""

    # record -> (copy 1, copy 2, English immediate)
    RECORDS = {"s": (0xA072D8, 0x1ECB57C, 0xE7), "i": (0xA072F2, 0x1ECB596, 0xDD),
               "e": (0xA072F6, 0x1ECB59A, 0xD9), "I": (0xA07306, 0x1ECB5AA, 0xC3),
               "E": (0xA0730A, 0x1ECB5AE, 0xBF)}
    IDS = {"s": ("item_plural_s:0", "item_plural_s_trade:0"),
           "i": ("item_plural_lower:0", "item_plural_lower_trade:0"),
           "e": ("item_plural_lower:1", "item_plural_lower_trade:1"),
           "I": ("item_plural_upper:0", "item_plural_upper_trade:0"),
           "E": ("item_plural_upper:1", "item_plural_upper_trade:1")}

    @classmethod
    def setUpClass(cls):
        import json

        from gen3tl.catalog.catalog import load_catalog
        from gen3tl.lang.langpack import LangPack
        cls.prof = unbound()
        cls.rom = cls.prof.load_rom(rom_path())
        cls.tables = {t["name"]: t for t in cls.prof.get("table", [])}
        cls.inv = json.loads((ROOT / "build" / "inventory.json").read_text(encoding="utf-8"))
        cls.entries = {e["id"]: e for e in cls.inv["entries"] if e["id"].startswith("item_plural_")}
        cls.catalog = load_catalog(ROOT / "translation" / "ru" / "po")
        cls.ru = LangPack.load("ru").charmap()

    def encoded(self, sid):
        # what the build writes for the entry
        from gen3tl.build.inject import field_bytes
        e = self.catalog[sid][1]
        inv = self.entries[sid]
        blob = CM.encode("" if "empty" in e.flags else e.msgstr)
        return field_bytes(blob, inv["length"], self.tables[inv["table"]]["pad"])

    @staticmethod
    def pluralize(name: bytes, imm: dict) -> bytes:
        # the routine 0x8A072C4 with immediates imm
        buf = bytearray(name + b"\xff" + b"\x00" * 8)
        n, last = len(name), name[-1]
        if last in (0xCD, 0xE7):         # S, s: as it is
            return bytes(buf)
        if last in (0xD3, 0xED):         # Y, y: last letter replaced
            buf[n - 1] = imm["I" if last == 0xD3 else "i"]
        if last in (0xD3, 0xD2):         # Y, X: E, +0xE, +0x32
            e = imm["E"]
            buf[n:n + 3] = bytes([e, (e + 0xE) & 0xFF, (e + 0xE + 0x32) & 0xFF])
        elif last in (0xED, 0xEC):       # y, x: e, +0xE, +0x18
            e = imm["e"]
            buf[n:n + 3] = bytes([e, (e + 0xE) & 0xFF, (e + 0xE + 0x18) & 0xFF])
        else:                            # s, +0x18
            buf[n:n + 2] = bytes([imm["s"], (imm["s"] + 0x18) & 0xFF])
        return bytes(buf)

    def test_fields_are_the_stored_immediates(self):
        # both copies: movs r3, #imm (0x23 imm); the comparisons
        for k, (a, b, imm) in self.RECORDS.items():
            self.assertEqual((self.rom.u16(a), self.rom.u16(b)), (0x2300 | imm, 0x2300 | imm), k)
        cmps = {0x0A072CA: 0x2BD3, 0x0A072D0: 0x2BCD, 0x0A072D4: 0x2BD2, 0x0A072E4: 0x2BEC,
                0x0A072E8: 0x2BED, 0x0A072EC: 0x2BE7}
        self.assertEqual({at: self.rom.u16(at) for at in cmps}, cmps)
        self.assertEqual({at + 0x14C42A4: self.rom.u16(at + 0x14C42A4) for at in cmps},
                         {at + 0x14C42A4: v for at, v in cmps.items()})
        for k, ids in self.IDS.items():
            for sid, at in zip(ids, self.RECORDS[k][:2]):
                e = self.entries[sid]
                self.assertEqual((e["offset"], e["text"], e["flags"], e["length"]), (at, k, ["unterminated"], 1))

    def test_catalog_keeps_the_name(self):
        # s, e, E end the name; i, I store y
        want = {"s": b"\xff", "e": b"\xff", "E": b"\xff", "i": CM.encode("y")[:1], "I": CM.encode("Y")[:1]}
        for k, ids in self.IDS.items():
            for sid in ids:
                self.assertEqual(self.encoded(sid), want[k], sid)

    def test_english_model(self):
        # the model gives the English plurals
        base = {k: v[2] for k, v in self.RECORDS.items()}
        for name, plural in (("Test Ball", "Test Balls"), ("Test Berry", "Test Berries"),
                             ("Example X", "Example XES"), ("Test Revive", "Test Revives")):
            self.assertEqual(CM.decode(self.pluralize(CM.encode(name)[:-1], base), 0)[0], plural)

    def test_every_russian_item_name_stays(self):
        # in-table and long names; stores within gStringVar2 (20 bytes)
        imm = {k: self.encoded(ids[0])[0] for k, ids in self.IDS.items()}
        ids = {e["id"] for e in self.inv["entries"]
               if e.get("table") == "items" or any(r["kind"] == "table:items" for r in e["refs"])}
        names = set()
        for sid in ids:
            e = self.catalog[sid][1]
            text = e.msgstr or e.msgid
            if text:
                names.add(self.ru.encode(text)[:-1])
        self.assertGreater(len(names), 600)
        endings = {n[-1] for n in names}
        self.assertTrue({0xD2, 0xD3} <= endings)
        for n in names:
            out = self.pluralize(n, imm)
            self.assertEqual(out[:len(n) + 1], n + b"\xff", n)
            self.assertLessEqual(len(n) + 2, 19)

    def test_build_changes_only_the_immediates(self):
        from gen3tl.build.inject import diff_positions
        texts = {sid: self.encoded(sid) for ids in self.IDS.values() for sid in ids}
        rom = self.rom.copy()
        res = inject(rom, self.rom, {"entries": list(self.entries.values())}, texts, self.tables)
        self.assertEqual(verify(rom, self.rom, res, texts, set()), [])
        self.assertEqual(diff_positions(rom.data, self.rom.data),
                         sorted(at for v in self.RECORDS.values() for at in v[:2]))


@needs_rom
class CountPluralEndingTest(unittest.TestCase):
    """The plural «s» after counts: two immediates and a shard text."""

    # id -> (position, the bytes there in the English ROM)
    RECORDS = {"count_plural_s:0": (0x9E9284, b"\xe7\x21\x5a\x70\x19\x70"),
               "egg_count_plural_s:0": (0x1EC63BE, b"\xe7\x21\x5a\x70\x19\x70"),
               "shard_plural_s:0": (0x1FB542C, b"\xe7\xff")}

    @classmethod
    def setUpClass(cls):
        import json

        from gen3tl.catalog.catalog import load_catalog
        cls.prof = unbound()
        cls.rom = cls.prof.load_rom(rom_path())
        cls.tables = {t["name"]: t for t in cls.prof.get("table", [])}
        inv = json.loads((ROOT / "build" / "inventory.json").read_text(encoding="utf-8"))
        cls.entries = {e["id"]: e for e in inv["entries"] if e["id"] in cls.RECORDS}
        cls.catalog = load_catalog(ROOT / "translation" / "ru" / "po")

    def encoded(self, sid):
        # what the build writes for the entry
        from gen3tl.build.inject import field_bytes
        e = self.catalog[sid][1]
        inv = self.entries[sid]
        blob = CM.encode("" if "empty" in e.flags else e.msgstr)
        return field_bytes(blob, inv["length"], self.tables[inv["table"]]["pad"])

    def test_fields_are_the_stored_text(self):
        # movs r1, #'s'; strb r2, [r3, #1]; strb r1, [r3]
        for sid, (at, data) in self.RECORDS.items():
            with self.subTest(sid=sid):
                self.assertEqual(self.rom.data[at:at + len(data)], data)
                self.assertEqual(self.entries[sid]["offset"], at)
        self.assertEqual(self.rom.u32(0x1EC6A88), 0x09FB53F4)   # shard list base
        self.assertEqual(self.rom.u16(0x1EC6A00), 0x3138)       # adds r1, #0x38

    def test_counts_take_no_ending(self):
        for sid in self.RECORDS:
            with self.subTest(sid=sid):
                self.assertIn("empty", self.catalog[sid][1].flags)
                self.assertEqual(self.encoded(sid)[0], 0xFF)   # the buffer ends at once

    def test_build_changes_only_the_records(self):
        from gen3tl.build.inject import diff_positions
        texts = {sid: self.encoded(sid) for sid in self.RECORDS}
        rom = self.rom.copy()
        res = inject(rom, self.rom, {"entries": list(self.entries.values())}, texts, self.tables)
        self.assertEqual(verify(rom, self.rom, res, texts, set()), [])
        self.assertEqual(diff_positions(rom.data, self.rom.data), [0x9E9284, 0x1EC63BE, 0x1FB542C])
