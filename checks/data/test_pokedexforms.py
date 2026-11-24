import copy
import unittest

from gen3tl.data import pokedexforms as forms

from project_fixture import UNBOUND, needs_unbound, unbound

class FormNamesTest(unittest.TestCase):


    @needs_unbound
    def test_unbound_catalog_labels_cover_verified_names_without_guessing(self):
        from gen3tl.data.pokedexstore import load
        data = load(UNBOUND / "data/pokedex/pokedex.json")
        rows = copy.deepcopy(data["species"])
        profile = unbound()["pokedex"]["form_names"]
        forms.apply(profile, rows)
        by_slot = {r["slot"]: r for r in rows}
        for slot, name in [(413, "species:413"), (713, "s0238D20"), (859, "s1F27B02"),
                           (990, None), (1048, "types:1"), (1064, "types:23"),
                           (546, "types:0"), (834, "types:23"),
                           (638, "page:Spring Form"), (639, "page:Spring Form"),
                           (738, "page:Summer Form"), (739, "page:Autumn Form"), (740, "page:Winter Form"),
                           (741, "page:Summer Form"), (742, "page:Autumn Form"), (743, "page:Winter Form"),
                           (1161, "s0EB9272"), (1199, "items:718"),
                           (774, "s1F27257"), (921, "s1F27293"), (868, "s1F27829"),
                           (1040, "s041B2B7"), (1041, "s041B2BE"), (1042, "s041B2C6"),
                           (703, "page:Female form"), (786, "page:Male form"), (1255, "page:Female form"),
                           (747, "items:636"), (748, "items:634"), (749, "items:637"), (750, "items:635")]:
            self.assertEqual(by_slot[slot]["form_name"], name)
        self.assertTrue(by_slot[413]["form_name_full"])
        self.assertEqual(by_slot[932]["form_name"], "page:Poké Ball Pattern")

    @needs_unbound
    def test_standard_names_follow_record_traits_and_preserve_precursors(self):
        from gen3tl.data.pokedexstore import load
        data = load(UNBOUND / "data/pokedex/pokedex.json")
        rows = {r["slot"]: r for r in data["species"]}
        for slot, dex, label in [(919, 483, "Origin Forme"), (920, 484, "Origin Forme"),
                                 (1209, 893, "Dada"), (1210, 898, "Ice Rider"),
                                 (1211, 898, "Shadow Rider"), (1259, 905, "Therian Forme")]:
            self.assertEqual((rows[slot]["dex"], rows[slot]["form_name"]), (dex, "page:" + label))
        self.assertEqual(rows[919]["base_stats"]["attack"], 100)
        self.assertEqual(rows[1210]["types"], [14, 15])
        self.assertEqual(rows[1211]["types"], [14, 7])
        for slot, base, target in [(1036, 102, 1037), (1038, 104, 1039)]:
            self.assertEqual(rows[slot]["form_name"], f"species:{slot}")
            self.assertTrue(rows[slot]["form_name_full"])
            self.assertEqual(rows[slot]["base_stats"], rows[base]["base_stats"])
            self.assertEqual({e["target"] for e in rows[slot]["evolution"]}, {target})
