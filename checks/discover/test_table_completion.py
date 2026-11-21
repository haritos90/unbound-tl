import unittest

from gen3tl.discover import foundations, table_core, table_maps, table_readers, table_sources
from gen3tl.profile.profile import Profile

from rom_support import needs_rom, rom_path

@needs_rom
class SpecialAndMapCompletionTest(unittest.TestCase):
    def test_trade_command_and_map_geometry_derive_from_native_evidence(self):
        profile = Profile.by_name("unbound-2.1.1.1")
        rom = profile.load_rom(rom_path())
        family = foundations.families()[0]
        readers = table_readers.Readers(rom, family.readers)
        result = table_core.Result()

        table_maps._map_geometry(rom, result, family.readers, readers)
        maps = next(fact for fact in result.facts if fact.id == "pokedex.maps")
        self.assertEqual(maps.value, {"primary_tiles": 640, "primary_metatiles": 640,
                                      "primary_palettes": 7, "palettes": 13})
        self.assertIn("metatile-partition", maps.evidence.method)

        dispatch = table_sources._specials_table(rom, result, family.readers, readers)
        self.assertIsNotNone(dispatch)
        self.assertEqual((dispatch["end"] - dispatch["table"]) % 4, 0)
        command = table_sources._trade_command(rom, result, family.readers, readers)
        self.assertIsNotNone(command)
        self.assertEqual(command["command"], 254)

    def test_new_family_fingerprints_are_unique_on_the_pinned_rom(self):
        profile = Profile.by_name("unbound-2.1.1.1")
        family = foundations.families()[0]
        readers = table_readers.Readers(profile.load_rom(rom_path()), family.readers)
        for name in ("specials-dispatch", "trade-special", "trade-task",
                     "map-tilesets", "map-palettes", "map-metatile-partition"):
            self.assertIn(name, readers.matches)
            self.assertTrue(readers.matches[name], name)
        self.assertEqual(len(readers.matches["specials-dispatch"]), 1)
        self.assertEqual(len(readers.matches["trade-task"]), 1)
        self.assertEqual(len(readers.matches["map-tilesets"]), 1)
        self.assertEqual(len(readers.matches["map-palettes"]), 1)
        self.assertEqual(len(readers.matches["map-metatile-partition"]), 1)
