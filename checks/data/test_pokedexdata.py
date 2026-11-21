import unittest

from gen3tl.cli import data as cli
from gen3tl.data import pokedexdata as pd

from rom_support import needs_rom, rom_path

class UnboundTrainingTablesTest(unittest.TestCase):
    """The engine's growth, breeding and gender meanings."""

    @classmethod
    def setUpClass(cls):
        cls.pokedex = cli.Profile.by_name("unbound-2.1.1.1")["pokedex"]

    def test_growth_rate_keys_follow_the_experience_tables(self):
        rates = self.pokedex["growth_rates"]
        self.assertEqual({key: value for key, value in rates.items() if key.isdigit()}, {
            "0": "medium_fast", "1": "erratic", "2": "fluctuating",
            "3": "medium_slow", "4": "fast", "5": "slow",
        })
        self.assertEqual((rates["base"], rates["entries"]), (0xA79560, 256))
        self.assertIn("0x30084-0x300AA", rates["evidence"])
        for species in ("Caterpie", "Nincada", "Shroomish", "Bulbasaur", "Clefairy", "Growlithe"):
            self.assertIn(species, rates["evidence"])

    def test_egg_group_keys_cover_every_breeding_group(self):
        groups = self.pokedex["egg_groups"]
        self.assertEqual({key: value for key, value in groups.items() if key.isdigit()}, {
            "1": "monster", "2": "water_1", "3": "bug", "4": "flying", "5": "field",
            "6": "fairy", "7": "grass", "8": "human_like", "9": "water_3", "10": "mineral",
            "11": "amorphous", "12": "water_2", "13": "ditto", "14": "dragon", "15": "undiscovered",
        })
        self.assertIn("0x9D453C-0x9D462C", groups["evidence"])
        for key, value in groups.items():
            if key.isdigit():
                self.assertRegex(value, r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")

    def test_gender_thresholds_include_every_value_and_special_case(self):
        ratios = self.pokedex["gender_ratios"]
        self.assertEqual(ratios["thresholds"], [0, 31, 63, 127, 191, 223, 254, 255])
        self.assertEqual((ratios["male_only"], ratios["female_only"], ratios["genderless"]), (0, 254, 255))
        self.assertIn("0x3F78C-0x3F7D0", ratios["evidence"])
        self.assertIn("personality & 0xFF", ratios["evidence"])

class CommandTest(unittest.TestCase):


    def test_the_unbound_profile_carries_the_block(self):
        from project_fixture import unbound
        prof = unbound()
        self.assertEqual(pd.check(prof.get("pokedex")), [])


BASE = 0x100          # species table, stride 28


STRIDE = 28


DEX_BASE = 0x400      # dex records, stride 36, indexed by national dex


NAT_BASE = 0x300      # slot -> national dex, u16


def block(evolution=None, **overrides) -> dict:
    b = {
        "schema": 1,
        "name_table": "species",
        "species": {
            "base": BASE, "stride": STRIDE, "count": 3, "first": 1,
            "evidence": "synthetic fixture: six stat bytes at each stride",
            "fields": {
                "hp": 0, "attack": 1, "defense": 2, "speed": 3, "sp_attack": 4, "sp_defense": 5,
                "type1": 6, "type2": 7, "catch_rate": 8, "base_exp": 9, "growth": 22,
                "ability1": 24, "ability2": 25,
            },
        },
        "dex": {
            "index": "dex",
            "category_table": "pokedex_categories",
            "map": {"base": NAT_BASE, "stride": 2, "width": 2},
            "records": {
                "base": DEX_BASE, "stride": 36, "evidence": "one 36-byte record per dex number",
                "fields": {"category": 0, "height": 12, "weight": 14,
                           "description": {"offset": 16, "width": 4}},
            },
        },
    }
    if evolution is not None:
        b["evolution"] = evolution
    b.update(overrides)
    return b


@needs_rom
class UnboundEvYieldTest(unittest.TestCase):
    """Stored species facts from the supported ROM."""

    def test_primal_and_ultra_profile_kinds_preserve_raw_requirements(self):
        prof = cli.Profile.by_name("unbound-2.1.1.1")
        block = prof["pokedex"]
        data = prof.load_rom(rom_path()).data
        expected = [(404, 910, 277, 1, "primal"), (405, 909, 276, 1, "primal"),
                    (1079, 1081, 445, 3, "ultra"), (1080, 1081, 445, 3, "ultra")]
        for source, target, parameter, extra, kind in expected:
            edges = pd._evolution(block, data, source, 0)
            edge = next(edge for edge in edges if edge["target"] == target)
            self.assertEqual(edge, {"method": 254, "target": target, "parameter": parameter,
                                    "extra": extra, "kind": kind})
        for source, target in [(909, 405), (910, 404), (1081, 1079), (1081, 1080)]:
            edge = next(edge for edge in pd._evolution(block, data, source, 0) if edge["target"] == target)
            self.assertEqual(edge["parameter"], 0)
            self.assertNotIn("kind", edge)
        labels = {row["species"]: row for row in block["form_names"]["labels"]}
        for slot, label in [(909, "Primal Groudon"), (910, "Primal Kyogre"), (1081, "Ultra Necrozma")]:
            self.assertEqual(labels[slot], {"species": slot, "text": "page:" + label, "full": True})

    def test_known_species_yield_their_effort_points(self):
        prof = cli.Profile.by_name("unbound-2.1.1.1")
        b = {"name_table": prof["pokedex"]["name_table"], "species": prof["pokedex"]["species"]}
        species = {row["slot"]: row["ev_yield"] for row in pd.build(b, prof.load_rom(rom_path()).data, {"id": prof.name})["species"]}
        given = lambda slot: {stat: n for stat, n in species[slot].items() if n}   # noqa: E731
        self.assertEqual(given(25), {"speed": 2})   # Pikachu
        self.assertEqual(given(6), {"sp_attack": 3})   # Charizard
        self.assertEqual(given(113), {"hp": 2})   # Chansey
        self.assertEqual(given(213), {"defense": 1, "sp_defense": 1})   # Shuckle
        self.assertEqual(len(species), 1293)
        self.assertTrue(all(set(row) == set(pd.STAT_FIELDS) and set(row.values()) <= {0, 1, 2, 3}
                            for row in species.values()))
