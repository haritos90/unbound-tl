import unittest

from gen3tl.data import pokedexdata as pd

from project_fixture import UNBOUND, needs_unbound

class FormResolutionTest(unittest.TestCase):

    @needs_unbound
    def test_gengar_forms_resolve_to_gengars_tables(self):
        path = UNBOUND / "data/pokedex/pokedex.json"
        doc = pd.read(path)
        records = {record["slot"]: record for record in doc["species"]}
        base = records[94]
        self.assertEqual(base["learnset_species"], 94)
        self.assertEqual(sum(row["method"] == 1 for row in base["learnset"]), 51)
        self.assertEqual(sum(row["method"] == 3 for row in base["learnset"]), 27)
        for slot in (877, 1267):
            form = records[slot]
            self.assertEqual(form["learnset_species"], 94)
            self.assertEqual(len(form["learnset"]), 20)
            self.assertTrue(all(row["method"] == 0 for row in form["learnset"]))
            self.assertEqual(records[form["learnset_species"]]["learnset"], base["learnset"])

    @needs_unbound
    def test_persistent_and_ambiguous_forms_keep_their_own_tables(self):
        path = UNBOUND / "data/pokedex/pokedex.json"
        records = {record["slot"]: record for record in pd.read(path)["species"]}
        self.assertEqual(records[1020]["learnset_species"], 1020)
        self.assertEqual(sum(row["method"] == 2 for row in records[1020]["learnset"]), 11)
        self.assertEqual(records[1081]["learnset_species"], 1081)
