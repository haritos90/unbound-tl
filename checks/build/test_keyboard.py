import unittest

from gen3tl.build import keyboard as K
from gen3tl.core.charmap import Charmap

from rom_support import needs_rom, rom_path
from project_fixture import unbound, UNBOUND

class ProfileTest(unittest.TestCase):
    def test_profile_declares_the_five_keyboard_pages(self):
        kb = unbound()["keyboard"]
        K._check_config(kb)
        names = [p["name"] for p in kb["pages"]]
        order = [names[(kb["first_page"] + i) % len(names)] for i in range(len(names))]
        self.assertEqual(order, ["А–Я", "а–я", "A–Z", "a–z", "others"])
        self.assertEqual(kb["reserved"], [0x1FFF000, 0x2000000])
        self.assertEqual(kb["opening_keyboards"], [1, 0])
        self.assertEqual(kb["opening_keyboard_offsets"], [0x09DEB0, 0x09DEA2])
        for address in ("0x09DE88", "0x09DEA2", "0x09DEB0"):
            self.assertIn(address, kb["evidence"])


    @needs_rom
    def test_profile_opening_keyboards_match_the_base_rom(self):
        kb = unbound()["keyboard"]
        base = unbound().load_rom(rom_path())
        self.assertEqual(K.check_base(kb, base), [])
        changed = base.copy()
        changed.write(kb["opening_keyboard_offsets"][0], b"\x02\x21")
        self.assertIn("keyboard: opening keyboard 0x9deb0 is not movs rX,#1 (02 21)",
                      K.check_base(kb, changed))


CM = Charmap()


@needs_rom
class CyrillicKeysTest(unittest.TestCase):
    """Cyrillic pages type the pack's bytes, Latin pages the base ROM's."""

    @classmethod
    def setUpClass(cls):
        from gen3tl.lang.langpack import LangPack
        from gen3tl.catalog.catalog import load_catalog
        cls.pack = LangPack.load("ru")
        cm = cls.pack.charmap()
        catalog = load_catalog(UNBOUND / "translation" / "ru" / "po", unbound())
        entries = [e for sid, (_, e) in catalog.items() if sid.startswith("naming_keyboard:")]
        cls.keys = {int(sid.split(":")[1]): cm.encode(e.msgstr, terminate=False)
                    for sid, (_, e) in catalog.items() if sid.startswith("naming_keyboard:")}

    def test_cyrillic_pages_type_pack_bytes(self):
        own = set(self.pack.chars.values())
        for row in range(8):
            self.assertTrue(set(self.keys[row]) <= own, row)
        self.assertEqual(self.keys[0][0], self.pack.chars["а"])
        self.assertEqual(self.keys[4][0], self.pack.chars["А"])
        self.assertEqual(self.keys[8][5], self.pack.chars["ё"])
        self.assertEqual(self.keys[9][5], self.pack.chars["Ё"])
        self.assertFalse(set(b"".join(self.keys.values())) & set(range(0xBB, 0xEF)))   # no Latin letter

    def test_latin_pages_keep_the_base_keys(self):
        prof = unbound()
        kb, base = prof["keyboard"], prof.load_rom(rom_path())
        rom = base.copy()
        for row, b in self.keys.items():   # the catalog keys, as the build writes them
            rom.write(0x3E22D0 + 8 * row, b)
        patch = K.plan(kb, base, rom)
        keys = next(blob for _, blob, what in patch.writes if what == "keys")
        by_name = {k["name"]: keys[32 * i:32 * i + 32] for i, k in enumerate(kb["keyboards"])}
        self.assertEqual(by_name["а–я"], b"".join(self.keys[r] for r in range(4)))
        self.assertEqual(by_name["А–Я"], b"".join(self.keys[r] for r in range(4, 8)))
        self.assertEqual(by_name["a–z"], base.read(0x3E22D0, 32))
        self.assertEqual(by_name["A–Z"], base.read(0x3E22D0 + 32, 32))
        self.assertEqual(CM.decode(by_name["A–Z"] + b"\xff")[0], "ABCDEF .GHIJKL ,MNOPQRS TUVWXYZ ")
