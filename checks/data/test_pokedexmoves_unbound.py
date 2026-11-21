import unittest
import copy

from gen3tl.data import pokedexmoves as pm
from gen3tl.profile.profile import Profile

from rom_support import needs_rom, rom_path
from project_fixture import FLINCH_MOVES, unbound

class MoveDataTest(unittest.TestCase):


    def test_unbound_reader_pairs(self):
        profile = Profile.by_name("unbound-2.1.1.1")
        readers = pm.build_readers(profile.get("pokedex")["moves"])
        self.assertEqual(len(readers), 24)
        self.assertEqual(readers["punching"]["readers"], {"abilities": [93], "items": []})
        self.assertEqual(readers["sound"]["readers"], {"abilities": [43, 218], "items": [709]})
        self.assertEqual(readers["powder"]["readers"], {"abilities": [114, 143], "items": [493]})
        self.assertEqual(readers["makes_contact"]["readers"], {"abilities": [100, 217], "items": [578]})
        self.assertEqual(readers["magic_coat_affected"]["readers"], {"abilities": [90], "items": []})
        self.assertEqual(readers["triage_affected"]["readers"], {"abilities": [176], "items": []})
        self.assertEqual(readers["parental_bond_banned"]["readers"], {"abilities": [151], "items": []})
        self.assertEqual(readers["kings_rock_affected"]["readers"], {"abilities": [], "items": []})


    @needs_rom
    def test_unbound_curse_mechanics_are_rom_bound_and_leave_other_moves_unchanged(self):
        profile = Profile.by_name("unbound-2.1.1.1")
        block = copy.deepcopy(profile["pokedex"]["moves"])
        rom = profile.load_rom(rom_path()).data
        records = pm.build(block, rom)
        self.assertEqual(pm.check(block), [])
        self.assertEqual([record["id"] for record in records if "mechanics" in record], [174, 267, 290, 293])
        self.assertEqual(len(records[174]["mechanics"]["rows"]), 2)
        self.assertEqual(len(records[174]["mechanics"]["rows"][0]["notes"]), 4)
        self.assertEqual(records[174]["mechanics"]["rows"][1]["notes"], [])
        self.assertNotIn("environments", records[174]["mechanics"])
        del block["mechanics"]
        for move in (174, 267, 290, 293):
            records[move].pop("mechanics")
        self.assertEqual(records, pm.build(block, rom))
        rom[0x969048] ^= 1
        with self.assertRaisesRegex(ValueError, "move 174 mechanics evidence differs"):
            pm.build(profile["pokedex"]["moves"], rom)


    @needs_rom
    def test_unbound_environment_table_drives_secret_power_nature_power_and_camouflage(self):
        profile = Profile.by_name("unbound-2.1.1.1")
        rom = profile.load_rom(rom_path()).data
        records = pm.build(profile["pokedex"]["moves"], rom)
        rows = {move: records[move]["mechanics"]["environments"] for move in (267, 290, 293)}
        self.assertEqual([table["column"] for table in rows.values()], ["move", "effect", "type"])
        self.assertTrue(all(table["script_persistence"] == "page:mechanics:environment:rule:note_script_persistence"
                            for table in rows.values()))
        self.assertTrue(all(len(table["rows"]) == 50 for table in rows.values()))
        first = {move: table["rows"][0]["value"] for move, table in rows.items()}
        self.assertEqual(first, {267: 85, 290: "page:mechanics:environment:effect:paralysis", 293: 13})
        penny = {move: table["rows"][19]["value"] for move, table in rows.items()}
        self.assertEqual(penny, {267: 370, 290: "page:mechanics:environment:effect:user_stats_up", 293: 16})
        self.assertEqual(records[290]["secondary_chance"], 30)
        from gen3tl.data import pokedexencounters
        block = profile["pokedex"]
        layouts = {"maps": profile.get("maps"), "script": profile.get("script", {})}
        places = pm.environment_maps(block["moves"]["environments"], rom, layouts,
                                     pokedexencounters._context_maps(rom, block["encounters"]["context"]))
        maps = {index: {kind: [item["map"] for item in items] for kind, items in kinds.items()}
                for index, kinds in places.items()}
        self.assertEqual(maps[15], {"scene_maps": ["10.17", "13.1"]})
        self.assertEqual([maps[index] for index in (19, 20, 21, 22)],
                         [{"scene_maps": [f"1.{n}"]} for n in (75, 76, 77, 78)])
        self.assertEqual(maps[23], {"map_code_maps": ["1.79"]})
        self.assertIn("3.31", maps[41]["script_maps"])
        self.assertIn("3.31", maps[24]["also_script_maps"])
        self.assertIn("14.3", maps[33]["script_maps"])
        self.assertEqual(maps[7], {"also_script_maps": ["24.0", "33.5"]})
        self.assertEqual(maps[26], maps[27])
        self.assertTrue(all(len(kinds) == 1 for kinds in maps.values()))
        rom[0xA7D5A1] ^= 1
        with self.assertRaisesRegex(ValueError, "(environment table|flinch) evidence differs"):
            pm.build(profile["pokedex"]["moves"], rom)


    @needs_rom
    def test_unbound_smog_and_list_members(self):
        profile = Profile.by_name("unbound-2.1.1.1")
        records = pm.build(profile.get("pokedex")["moves"], profile.load_rom(rom_path()).data)
        overrides = profile["pokedex"]["moves"]["effect_overrides"]
        self.assertEqual(len(overrides), 108)
        for number, rule in overrides.items():
            self.assertEqual(records[int(number)]["effect_key"], rule["key"])
            self.assertEqual(records[int(number)]["effect"], rule["effect"])
        self.assertEqual(records[439]["effect_key"], "defense_up_3")
        self.assertEqual(records[294]["effect_key"], "special_attack_up_3")
        self.assertEqual(records[334]["effect_key"], "defense_up_2")
        self.assertEqual(records[386]["effect_key"], "special_attack_up_2")
        self.assertEqual(len(records), 923)
        computed = {67, 175, 179, 216, 217, 218, 222, 251, 255, 284, 323, 377, 482, 484,
                    506, 510, 526, 532, 534, 542, 544, 602, 643, 668, 740}
        computed.update(range(767, 803))
        computed.update(set(range(821, 923)) - set(range(885, 891)))
        rules = profile.get("pokedex")["moves"]["power"]
        self.assertEqual(len(rules), 228)
        self.assertEqual({row["id"] for row in records if row.get("power_kind") == "computed"}, computed)
        self.assertEqual({row["id"] for row in records if row.get("power_kind") == "fixed"},
                         {int(number) for number in rules} - computed)
        self.assertEqual((records[89]["power"], records[89]["power_kind"]), (100, "fixed"))
        self.assertEqual({row["id"]: row["power_base"] for row in records if "power_base" in row},
                         dict.fromkeys(range(885, 891), 160))
        self.assertEqual(records[216]["power_formula"], "page:power:return")
        self.assertEqual(records[216]["power"], 1)
        self.assertEqual(records[377]["power_formula"], "page:power:grass_knot")
        self.assertEqual(records[67]["power_weight"],
                         [[0, 20], [100, 40], [250, 60], [500, 80], [1000, 100], [2000, 120]])
        self.assertNotIn("power_weight", records[534])
        self.assertNotIn("power_tiers", records[216])
        expected = {
            67: [20, 40, 60, 80, 100, 120], 377: [20, 40, 60, 80, 100, 120],
            175: [200, 150, 100, 80, 40, 20], 179: [200, 150, 100, 80, 40, 20],
            222: [10, 30, 50, 70, 90, 110, 150], 534: [60, 80, 120, 150],
            532: [40, 60, 80, 100, 120], 544: [40, 60, 80, 100, 120],
        }
        self.assertEqual({record["id"] for record in records if "power_tiers" in record}, set(expected))
        for move, powers in expected.items():
            self.assertEqual([power for _, power in records[move]["power_tiers"]], powers)
        self.assertEqual(records[67]["power_tiers"][0], ["page:power:cond:weight_under_10", 20])
        self.assertEqual(records[67]["power_tiers"], records[377]["power_tiers"])
        self.assertEqual(records[175]["power_tiers"], records[179]["power_tiers"])
        self.assertEqual(records[532]["power_tiers"], records[544]["power_tiers"])
        from gen3tl.data.pokedexitems import build as build_items
        items = build_items(profile.get("pokedex")["items"], profile.load_rom(rom_path()).data)
        berries = records[506]["power_items"]
        self.assertEqual(len(berries), 67)
        self.assertEqual({row["item"] for row in berries}, {row["id"] for row in items if row["pocket"] == 5})
        self.assertEqual(berries[0], {"item": 133, "type": 10, "power": 80})
        self.assertIn({"item": 118, "type": 6, "power": 100}, berries)
        self.assertEqual(berries[-1], {"item": 562, "type": 17, "power": 100})
        self.assertEqual({row["power"] for row in berries}, {80, 90, 100})
        smog = records[123]
        self.assertEqual((smog["target_key"], smog["effect_key"], smog["secondary_chance"]),
                         ("selected", "poison_hit", 40))
        self.assertEqual(smog["flag_keys"], ["protect_affected", "mirror_move_affected"])
        self.assertNotIn("sheer_force", smog["list_keys"])
        self.assertIn("sheer_force", records[356]["list_keys"])
        self.assertIn("punching", records[7]["list_keys"])
        self.assertIn("sound", records[45]["list_keys"])
        for record in records:
            self.assertTrue(record["target_key"])
            self.assertTrue(record["effect_key"])
            self.assertEqual(record["flags"] & ~0x7F, 0)


@needs_rom
class FlinchTest(unittest.TestCase):
    def test_profile_flinch_paths_match_rom_and_the_audited_move_set(self):
        profile = unbound()
        block, data = profile["pokedex"]["moves"], profile.load_rom(rom_path()).data
        self.assertEqual(pm.check(block), [])
        records = pm.build(block, data)
        self.assertEqual({row["id"]: row["flinch_chance"] for row in records if row["flinch_chance"]}, FLINCH_MOVES)
        for row in records:
            self.assertEqual(bool(row["flinch_conditions"]), bool(row["flinch_chance"]))
        for item in [block["flinch"], *block["flinch"]["rules"]]:
            proof = item["rom"][0]
            changed = bytearray(data)
            changed[proof["offset"]] ^= 1
            with self.assertRaisesRegex(ValueError, "flinch evidence differs"):
                pm.build(block, changed)
