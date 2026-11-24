import unittest

from gen3tl.lang.langpack import LangPack
from gen3tl.check.layout import Limit, Measure, check, fits
from gen3tl.check.provenance import code

from rom_support import needs_rom, rom_path
from project_fixture import UNBOUND, select_language, unbound

def setUpModule():
    select_language("ru")


PACK = LangPack.load("ru", "unbound")


CM = PACK.charmap()


M = Measure(lambda b: 6, {"PLAYER": 42})  # 6 px per character for predictable tests


@needs_rom
class RomShadowTest(unittest.TestCase):
    """The shadow rule with base ROM and pack glyphs."""

    @classmethod
    def setUpClass(cls):
        from gen3tl.cli.common import _shadow_end
        from gen3tl.build.font import FontTable
        prof = unbound()
        rom = prof.load_rom(rom_path())
        font = FontTable.from_profile(prof)[0]
        slots = PACK.glyph_slots(rom, font)
        cls.m = Measure(lambda b: slots[b].width if b in slots else font.width(rom, b), {},
                        shadow_end=_shadow_end(slots, font, rom))

    def test_labels(self):
        # labels clipping only the shadow fit
        for text, width, ok in (("Великая пустыня", 88, True), ("Деревня Тармиган", 94, True),
                                ("Деревня Магнолия", 94, True), ("Подземный проход", 94, False)):
            with self.subTest(text=text):
                self.assertEqual(check(text, Limit("single", width, 1), self.m, CM) == [], ok)
                self.assertFalse(check(text, Limit("single", self.m.width(text, CM) - 2, 1), self.m, CM) == [])

    def test_rom_glyphs(self):

        for text, ok in (("Вода", True), ("Тест Q", False), ("Тест ñ", False)):
            with self.subTest(text=text):
                w = self.m.width(text, CM)
                self.assertEqual(fits(text, w - 1, self.m, CM), ok)


@needs_rom
class InteriorHeadTest(unittest.TestCase):
    """A string code reads from inside the slot."""

    HEAD_PROBLEM = code("head_missing", head="{STR_VAR_1}", byte=2)

    def test_check_requires_the_head(self):
        lim = Limit("multiline", 200, 2, head="{STR_VAR_1}")
        self.assertIn(self.HEAD_PROBLEM, check("Выбрано:\\n{STR_VAR_1}.", lim, M, CM))
        self.assertEqual(check("{STR_VAR_1}:\\nвыбрано.", lim, M, CM), [])
        self.assertEqual(check("Выбрано:\\n{STR_VAR_1}.", Limit("multiline", 200, 2), M, CM), [])

    def test_head_checked_before_a_strip(self):
        lim = Limit("single", 200, 1, head="{STR_VAR_1}", strip=["{STR_VAR_1}"])
        self.assertEqual(check("{STR_VAR_1} да", lim, M, CM), [])

    def heads(self, word: int, evidence: str = "pool word"):
        from gen3tl.check.qa import interior_heads
        from gen3tl.core.rom import Rom, ptr_bytes
        d = bytearray(0x200)
        d[0x100:0x110] = CM.encode("{STR_VAR_1} aa\\nbbbbbbbb.")
        d[0x40:0x44] = ptr_bytes(word)
        prof = {"strings": {"interior": [{"pointer": 0x40, "id": "s0000100", "offset": 2, "evidence": evidence}]}}
        inv = {"entries": [{"id": "s0000100", "offset": 0x100, "length": 16, "text": "{STR_VAR_1} aa\\nbbbbbbbb."}]}
        return interior_heads(prof, inv, CM, Rom(d))

    def test_interior_heads(self):
        self.assertEqual(self.heads(0x102), {"s0000100": "{STR_VAR_1}"})
        with self.assertRaises(ValueError):   # the word does not point 2 bytes in
            self.heads(0x100)
        with self.assertRaises(ValueError):
            self.heads(0x102, evidence="")

    def test_tm_case_selection_message(self):
        import json

        from gen3tl.catalog.catalog import load_catalog
        from gen3tl.check.qa import compute_limits
        root = UNBOUND
        prof = unbound()
        rom = prof.load_rom(rom_path())
        # ldr r1, [pc, #0x78] at 0x1324E2 loads 0x13255C; bl StringAppend
        self.assertEqual((rom.u16(0x1324E2), rom.u32(0x13255C)), (0x491E, 0x08416301))
        self.assertEqual(rom.read(0x4162FF, 2), b"\xfd\x02")
        inv = json.loads((root / "build" / "inventory.json").read_text(encoding="utf-8"))
        cat = load_catalog(root / "translation" / "ru" / "po")
        lim = compute_limits(prof, inv, cat, M, CM, rom=rom)["s04162FF"]
        self.assertEqual((lim.head, lim.bytes), ("{STR_VAR_1}", 15))
        self.assertIn(self.HEAD_PROBLEM, check("Выбрано:\\n{STR_VAR_1}.", lim, M, CM))
        self.assertNotIn(self.HEAD_PROBLEM, check("{STR_VAR_1}:\\nвыбрано.", lim, M, CM))
