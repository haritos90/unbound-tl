import copy
import unittest

from gen3tl.data import pokedexdata as pd, pokedextrainers as pt
from gen3tl.profile.profile import Profile

from rom_support import needs_rom, rom_path

@needs_rom
class UnboundTrainerMapTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        profile = Profile.by_name("unbound-2.1.1.1")
        pokedex = profile["pokedex"]
        metadata = {"id": profile.name, "maps": profile.get("maps"), "script": profile.get("script", {})}
        cls.block = pokedex
        cls.doc = pd.build(pokedex, profile.load_rom(rom_path()).data, metadata)
        cls.trainers = cls.doc["trainers"]

    def test_known_trainers_have_their_maps(self):
        self.assertEqual((self.trainers[523]["map"], self.trainers[523]["ev_training"]),
                         (["1.48", "2.108", "3.48"], False))
        self.assertEqual(self.trainers[523]["map_section"], [127, 165, 165])
        self.assertEqual(self.trainers[289]["map"], ["2.41", "53.4"])
        self.assertEqual(self.trainers[289]["map_section"], [138, 138])
        self.assertEqual(sum(1 for trainer in self.trainers if trainer["map"]), 679)

    def test_guarded_variable_records_have_locations_and_encounters(self):
        rules = self.block["trainers"]["maps"]["resolutions"]
        self.assertEqual(len(rules), 7)
        for rule in rules:
            for record in rule["records"]:
                self.assertTrue(self.trainers[record]["map"])
                self.assertTrue(self.trainers[record]["encounters"])
        self.assertEqual(len(self.doc["trainer_maps"]["unknown"]), 64)
        self.assertEqual(self.trainers[205]["map"], self.trainers[204]["map"])
        self.assertEqual(self.trainers[205]["kind"], "world")
        self.assertEqual(self.trainers[204]["kind"], "world")
        battle = self.doc["trainer_encounters"][self.trainers[205]["encounters"][0]]
        self.assertEqual([(row["record"], row["role"]) for row in battle["variants"]],
                         [(204, "opponent"), (205, "second_opponent")])

    def test_native_runs_mark_every_confirmed_declaration(self):
        trainers = self.block["trainers"]
        expected = {0x1E726D4, 0x1E89C6B, 0x1E5F609, 0x1E8D799, 0x1E57D2B, 0x1E6005F, 0x1E5959D,
                    0x1E7EC4C, 0x1E7ECEE, 0x1E7ED94, 0x1E7EE33, 0x1E7EED9, 0x1E7EF7C}
        self.assertEqual({row["script"] for row in trainers["difficulty"]["selections"]
                          if row.get("native") == "confirmed"}, expected)
        self.assertEqual(len(trainers["participants"]), 7)
        self.assertTrue(all(row["native"] == "confirmed" for row in trainers["participants"]))
        self.assertEqual([row["script"] for row in trainers["encounters"] if row.get("native") == "confirmed"],
                         [0x1EA7226])
        self.assertEqual(len(trainers["maps"]["resolutions"]), 7)
        self.assertTrue(all(row["native"] == "confirmed" for row in trainers["maps"]["resolutions"]))
        self.assertEqual(len(trainers["ivs"]["species_conditions"]), 4)
        self.assertTrue(all(row["native"] == "confirmed" for row in trainers["ivs"]["species_conditions"]))

    def test_declared_story_order_and_unknown_inventory_are_verified(self):
        battles = self.doc["trainer_encounters"]
        self.assertEqual(pt.check_order(self.block["trainers"]["order"], len(self.trainers)), [])
        self.assertTrue(any(row["order"]["status"] == "constrained" for row in battles))
        self.assertEqual(self.doc["trainer_order"]["unknown"],
                         [row["id"] for row in battles if row["order"]["status"] == "unknown"])
        self.assertEqual(pt.verify_encounters(battles, self.trainers, self.block["trainers"]), [])
        broken = copy.deepcopy(self.doc)
        broken["trainer_order"]["unknown"].pop()
        self.assertIn("trainer order: regenerate the dataset with gen3tl data pokedex",
                      pd.verify_doc(broken, self.block, self.doc["profile"]["id"], self.doc["rom"]["sha1"]))

    def test_the_trigger_battle_precedes_the_two_opponent_battle(self):
        battles = self.doc["trainer_encounters"]
        first = battles[self.trainers[203]["encounters"][0]]
        second = battles[self.trainers[204]["encounters"][0]]
        self.assertEqual(self.trainers[205]["encounters"], self.trainers[204]["encounters"])
        for row in (first, second):
            self.assertEqual(row["order"], {"status": "constrained", "rules": ["antisis-trigger-then-pair"]})
        self.assertLess(battles.index(first), battles.index(second))

    def test_game_difficulty_values_select_the_alice_rosters(self):
        self.assertEqual([self.trainers[index]["difficulty"] for index in (20, 725, 726, 727)],
                         [["difficult"], ["vanilla"], ["expert"], ["insane"]])
        self.assertEqual(len({tuple(self.trainers[index]["encounters"]) for index in (20, 725, 726, 727)}), 1)

    def test_the_nine_corrected_cards_use_one_encounter_per_battle_start(self):
        encounters = self.doc["trainer_encounters"]

        def variants(record):
            ids = self.trainers[record]["encounters"]
            return [[(v["record"], v["settings"], v.get("starter"), v.get("level_above"))
                     for v in encounters[i]["variants"] if v["role"] == "opponent"]
                    for i in ids]
        self.assertEqual(variants(375), [[(375, ["difficult"], None, None), (686, ["vanilla"], None, None),
                                          (687, ["expert"], None, None), (688, ["insane"], None, None)]])
        self.assertEqual(variants(720), [[(6, ["difficult"], None, None), (719, ["vanilla"], None, None),
                                          (720, ["expert"], None, None), (721, ["insane"], None, None),
                                          (721, ["expert"], None, 39)]])
        for first in (326, 329, 332):
            self.assertEqual(variants(first), [[(first + index, None, index + 1, None) for index in range(3)]])
        for low, high in ((426, 435), (429, 438)):
            self.assertEqual(variants(low), [[row for starter in range(3) for row in (
                (low + starter, ["difficult", "vanilla"], starter + 1, None),
                (high + starter, ["expert", "insane"], starter + 1, None))]])
        self.assertEqual(variants(432), [[row for starter in range(3) for row in (
            (432 + starter, ["difficult", "vanilla", "expert"], starter + 1, None), (69 + starter, ["insane"], starter + 1, None))]])
        self.assertEqual(self.doc["trainer_difficulty"]["starters"], [496, 246, 398])

    def test_multi_and_tag_participants_match_the_rom_selectors(self):
        encounters = {row["script"]: row for row in self.doc["trainer_encounters"] if row["script"]}
        expected = {
            "0x1E57D2B": [(391, 39), (391, 39), (664, 39), (665, 39)],
            "0x1E89C6B": [(365, 44), (365, 44), (666, 44), (667, 44)],
            "0x1E5959D": [(374, 38), (374, 38), (None, 38), (None, 38)],
            "0x1E8D799": [(None, 50)] * 4,
        }
        settings = self.block["trainers"]["difficulty"]["settings"]
        for script, pairs in expected.items():
            for setting, pair in zip(settings, pairs):
                rows = {v["role"]: v["record"] for v in encounters[script]["variants"]
                        if v["settings"] is None or setting in v["settings"]}
                self.assertEqual((rows.get("second_opponent"), rows.get("partner")), pair, (script, setting))
        self.assertEqual(self.trainers[374]["difficulty"], None)
        self.assertEqual(len(self.trainers[374]["encounters"]), 2)
        self.assertIn(self.trainers[375]["encounters"][0], self.trainers[374]["encounters"])
        for script in ("0x1E5F609", "0x1E6005F"):
            self.assertEqual([(v["record"], v["starter"], v["settings"]) for v in encounters[script]["variants"]
                              if v["role"] == "partner"], [(46, 1, None), (47, 2, None), (48, 3, None)])
        for record in (46, 47, 48):
            self.assertEqual(len(self.trainers[record]["encounters"]), 2)
            self.assertTrue(self.trainers[record]["map"])
        self.assertEqual(len(self.trainers[365]["encounters"]), 2)
        self.assertEqual(self.trainers[365]["difficulty"], None)

    def test_records_without_a_battle_start_have_no_encounter(self):
        unused = [row["id"] for row in self.trainers if row["party_size"] and not row["encounters"]]
        self.assertEqual(len(unused), 63)
        self.assertTrue({45, 49, 656, 657, 356, 630, 631, 632, 633,
                         634, 637, 638, 639, 640, 641, 642, 645, 646, 660, 661, 662, 663, 454} <= set(unused))
        self.assertFalse({38, 39, 44, 50, 453, 459, 460, 461, 462, 463} & set(unused))

    def test_every_difficulty_record_has_maps_in_the_real_dataset(self):
        selected = {record for selection in self.block["trainers"]["difficulty"]["selections"]
                    for record in selection["records"]}
        self.assertEqual(len(selected), 162)
        for index in selected:
            with self.subTest(trainer=index):
                self.assertTrue(self.trainers[index]["map"])
                self.assertEqual(len(self.trainers[index]["map"]), len(self.trainers[index]["map_section"]))
        for index in (6, 719, 720, 721):
            self.assertEqual((self.trainers[index]["map"], self.trainers[index]["map_section"]), (["7.4"], [90]))
        for index in (20, 725, 726, 727):
            self.assertEqual((self.trainers[index]["map"], self.trainers[index]["map_section"]),
                             (["2.137", "6.1"], [92, 92]))
        for index in (56, 57, 58):
            self.assertEqual(self.trainers[index]["map"], ["1.45", "1.79", "24.0", "33.5"])
            self.assertEqual(self.trainers[index]["map_section"], [133, 137, 167, 167])
        self.assertEqual(pd.verify_doc(self.doc, self.block, "unbound-2.1.1.1", self.doc["rom"]["sha1"]), [])
        broken = {**self.doc, "trainers": [{**row, "map": [], "map_section": []} if row["id"] == 721 else row
                                          for row in self.trainers]}
        self.assertIn("trainer maps: regenerate the dataset with gen3tl data pokedex",
                      pd.verify_doc(broken, self.block, "unbound-2.1.1.1", self.doc["rom"]["sha1"]))

    def test_all_four_buildings_flag_their_trainers(self):
        flagged = {t["id"]: (t["map"], t["map_section"]) for t in self.trainers if t["ev_training"]}
        dresco, inverse = (["7.3"], [0x5A]), (["14.11"], [0x5E])
        camomons, double = (["25.2", "33.13"], [0x77, 0x77]), (["10.7"], [0x62])
        self.assertEqual(flagged, {8: dresco, 9: dresco, 10: dresco, 11: dresco, 12: dresco, 451: dresco,
                                   249: inverse, 265: inverse, 336: (["14.12"], [0x5E]), 402: (["14.12"], [0x5E]),
                                   551: camomons, 552: camomons, 553: camomons,
                                   554: (["33.14", "42.0"], [0x77, 0x77]), 555: (["33.14", "42.0"], [0x77, 0x77]), 556: (["33.14", "42.0"], [0x77, 0x77]),
                                   29: double, 30: double, 31: double, 32: (["10.8"], [0x62]), 33: (["10.8"], [0x62])})

    def test_every_trainer_has_exactly_one_kind_including_known_roles(self):
        self.assertEqual(len(self.trainers), 743)
        self.assertEqual({t["kind"] for t in self.trainers}, set(pt.KINDS))
        groups = {kind: {t["id"] for t in self.trainers if t["kind"] == kind} for kind in pt.KINDS}
        self.assertEqual(sum(len(group) for group in groups.values()), len(self.trainers))
        for kind, ids in {
            "league": [6, 20, 42, 72, 410, 414, 716, 727],
            "story": [25, 26, 27, 199, 256, 257, 326, 329, 365, 375, 391, 426, 537, 658, 662, 664, 665, 666, 667],
            "special": [8, 9, 10, 11, 12, 35, 36, 37, 249, 265, 336, 402, 451],
            "partners": [38, 39, 44, 46, 47, 48, 50],
            "paired": [19, 484, 485, 486, 580],
            "world": [0, 1, 7, 14, 195, 523],
        }.items():
            self.assertTrue(set(ids) <= groups[kind], (kind, set(ids) - groups[kind]))
        self.assertTrue(all(t["kind"] == "special" for t in self.trainers if t["ev_training"]))
