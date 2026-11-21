import unittest

from gen3tl.build.font import decode_glyph, encode_glyph
from gen3tl.lang.langpack import format_art, parse_art, style_problems, LangPack

from rom_support import needs_rom, rom_path
from project_fixture import UNBOUND

class SmallFontTest(unittest.TestCase):
    """The small font style: 12-row cells starting at glyph row 1, 8x16 glyphs."""

    def setUp(self):
        from gen3tl.lang.langpack import load_styles
        from gen3tl.profile.profile import Profile
        prof = Profile.by_name("unbound-2.1.1.1").data
        self.packs = load_styles("ru", prof)

    def test_both_styles_cover_the_same_slots(self):
        self.assertEqual(set(self.packs), {"unbound", "unbound-small"})
        self.assertEqual(set(self.packs["unbound"].glyph_slots()), set(self.packs["unbound-small"].glyph_slots()))

    def test_small_glyphs_fit_the_cell_and_round_trip(self):
        for ch, g in self.packs["unbound-small"].glyphs.items():
            self.assertEqual(style_problems(g, 12, 1, 8), [], ch)
            self.assertTrue(all(v == 0 for v in g.pixels[0] + g.pixels[13]), ch)   # rows outside the cell
            self.assertEqual(decode_glyph(encode_glyph(g.pixels, "8x16"), "8x16"), g.pixels, ch)
            self.assertEqual(parse_art(format_art(g, 12, 1), 12, 1)[ch].pixels, g.pixels, ch)

    def test_write_glyphs_needs_every_style(self):
        from gen3tl.build.font import FontTable, write_glyphs
        fonts = [FontTable("small", 0, 0x4000, 512, "unbound-small", "8x16")]
        with self.assertRaises(ValueError):
            write_glyphs(None, fonts, {"unbound": {}})


@needs_rom
class SlotValidationTest(unittest.TestCase):
    """The pack's bytes against the original text and the base ROM fonts."""

    @classmethod
    def setUpClass(cls):
        from gen3tl.discover import inventory
        from gen3tl.build.font import FontTable
        from gen3tl.profile.profile import Profile
        prof = Profile.by_name("unbound-2.1.1.1")
        cls.rom = prof.load_rom(rom_path())
        cls.fonts = FontTable.from_profile(prof)
        cls.inv = inventory.load(UNBOUND / "build" / "inventory.json")
        cls.pack = LangPack.load("ru")

    def test_no_untranslated_string_uses_a_pack_byte(self):
        from gen3tl.catalog.catalog import load_catalog
        from gen3tl.core.charmap import Charmap
        from gen3tl.discover.inventory import slot_usage, untranslated_slot_usage
        slots = set(self.pack.chars.values())
        # translated Japanese text uses these slots
        self.assertEqual(untranslated_slot_usage(self.inv, slots, Charmap(),
                                                load_catalog(UNBOUND / "translation/ru/po")), [])
        # the validator sees a used byte
        self.assertTrue(slot_usage(self.inv, {0xBB}, Charmap(), unverified=True))

    def test_slots_blank_and_sources_drawn_in_every_font(self):
        from gen3tl.build.font import BACKGROUND, OUTSIDE
        blank = lambda f, b: all(v in (BACKGROUND, OUTSIDE) for row in f.glyph(self.rom, b) for v in row)  # noqa: E731
        for f in self.fonts:
            for b in self.pack.chars.values():
                self.assertTrue(blank(f, b), (f.name, hex(b)))
            for s in self.pack.copies.values():
                self.assertFalse(blank(f, s), (f.name, hex(s)))
