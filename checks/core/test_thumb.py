import unittest

from gen3tl.core.rom import ROM_BASE
from gen3tl.core.thumb import walk
from gen3tl.discover.accessors import analyze, literal_loads, script_read_calls, script_reader

from rom_support import needs_rom, rom_path
from project_fixture import unbound

@needs_rom
class UnboundThumbTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profile = unbound()
        path = rom_path()
        cls.rom = cls.profile.load_rom(path)
        cls.data = cls.rom.data

    def test_species_and_evolution_accessors_match_profile(self):
        species, = analyze(self.data, 0x43904, 0x43910).accessors
        profile = self.profile["pokedex"]["species"]
        self.assertEqual((species.base, species.indices, species.field_offset, species.width),
                         (profile["base"], (("r5", profile["stride"]),), profile["ev_yield"]["offset"], 1))
        self.assertEqual(species.literals[0].pool, 0x43914)
        evolution, = analyze(self.data, 0x42F66, 0x4318E).accessors
        profile = self.profile["pokedex"]["evolution"]
        self.assertEqual((evolution.base, sorted(v for _, v in evolution.indices), evolution.width),
                         (profile["base"], [profile["record"], profile["stride"]], 2))
        self.assertEqual(evolution.literals[0].pool, 0x42F6C)
        for start, field in [(0xA13F1C, "ability1"), (0xA13F38, "ability2"), (0xA13F54, "hidden_ability")]:
            item, = analyze(self.data, start, start + 0x18).accessors
            species = self.profile["pokedex"]["species"]
            self.assertEqual((item.base, item.indices, item.field_offset),
                             (species["base"], (("r0", 28),), species["fields"][field]))
            self.assertEqual(item.literals[0].pool, 0x1BC)

    def test_font_function_bodies_and_all_four_glyph_width_pairs(self):
        spans = [(0x64F0, 0x6598), (0x65B8, 0x66F8), (0x67EC, 0x692C), (0x6958, 0x6A98)]
        pools = [(0x658C, 0x6594), (0x66EC, 0x66F4), (0x6920, 0x6928), (0x6A8C, 0x6A94)]
        for font, (start, end), (glyph, width) in zip(self.profile["font"][:4], spans, pools):
            with self.subTest(font=font["name"]):
                body = walk(self.data, start, end)
                self.assertGreater(len(body), 60)
                self.assertFalse(any(i.mnemonic == "undefined" for i in body))
                values = {item.pool: item.value - ROM_BASE for item in literal_loads(self.data, start, end)}
                self.assertEqual((values[glyph], values[width]), (font["glyphs"], font["widths"]))
                self.assertFalse(set(values) & {i.address for i in body})
        widths = analyze(self.data, 0x6598, 0x65B6).accessors
        self.assertEqual([(a.base, a.width, a.indices[0][1]) for a in widths], [(0x1FB100, 1, 1)])
        self.assertIn(0x227930, [a.base for a in analyze(self.data, 0x6A98, 0x6ABE).accessors])

    def test_name_table_pool_references_and_name_stride(self):
        sites = [(0x113E4, 0x11450), (0x4EF62, 0x4EF84), (0xD8614, 0xD8624),
                 (0x9A8CE, 0x9A8D8), (0xD850C, 0xD8510), (0x30992, 0x309C8),
                 (0xD8096, 0xD80A0), (0x88E2C, 0x88E34), (0xFBE0, 0xFC00)]
        for table, (site, pool) in zip(self.profile["table"][:9], sites):
            with self.subTest(table=table["name"]):
                literal, = literal_loads(self.data, site, site + 2)
                self.assertEqual((literal.pool, literal.value - ROM_BASE), (pool, table["base"]))
        accessor, = analyze(self.data, 0x113E0, 0x113EA).accessors
        self.assertEqual((accessor.base, accessor.indices[0][1]),
                         (self.profile["table"][0]["base"], self.profile["table"][0]["stride"]))
        call, = analyze(self.data, 0x4EF5C, 0x4EF6C).calls
        self.assertEqual((call.arguments[1].constant - ROM_BASE, call.arguments[1].terms[0][1]),
                         (self.profile["table"][1]["base"], self.profile["table"][1]["stride"]))
        for start, end, site, table in [(0x9A8C6, 0x9A8D6, 0x9A8D0, self.profile["table"][3]),
                                       (0x88E20, 0x88E32, 0x88E2E, self.profile["table"][7])]:
            addresses = [a for a in analyze(self.data, start, end).addresses if a.site == site]
            self.assertEqual([(a.base, a.indices[0][1]) for a in addresses], [(table["base"], table["stride"])])

    def test_naming_page_count_call_operands(self):
        for immediate, start, end, target in [(0x9E2A0, 0x9E294, 0x9E2A8, 0x1E4684),
                                              (0x9ED1E, 0x9ED16, 0x9ED28, 0x1E40F4)]:
            call, = analyze(self.data, start, end).calls
            self.assertIn(immediate, self.profile["keyboard"]["page_count"])
            self.assertEqual((call.site, call.target, call.arguments[1].constant, call.arguments[1].terms),
                             (immediate + 2, target, 3, ()))

    def test_script_readers_and_command_handler_calls(self):
        halfword = script_reader(analyze(self.data, 0x698F8, 0x6990E))
        word = script_reader(analyze(self.data, 0x69910, 0x69940))
        self.assertEqual((halfword.width, halfword.pointer_offset, word.width, word.pointer_offset), (2, 8, 4, 8))
        for start, end, expected in [(0x69EFC, 0x69F18, [0x69EFE]),
                                     (0x69F3C, 0x69F58, [0x69F40, 0x69F50])]:
            calls = script_read_calls(analyze(self.data, start, end), (halfword, word))
            self.assertEqual([(c.site, reader.width) for c, reader in calls], [(site, 2) for site in expected])
        handler = self.rom.ptr_at(self.profile["pokedex"]["sources"]["commands"]["table"] + 0x0F * 4) & ~1
        calls = script_read_calls(analyze(self.data, handler, handler + 0x22), (halfword, word))
        self.assertEqual([(c.site, reader.width) for c, reader in calls], [(0x6A2C2, 4)])
