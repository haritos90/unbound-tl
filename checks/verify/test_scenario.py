import unittest

from gen3tl.verify.savefile import Layout, SaveFile, blank_save
from gen3tl.verify.savefixture import GAME_EGG_NICKNAME, TestMon, hatch_check, party_pokemon

from savefile_support import LAYOUT, SAVE, TABLE, en, ru
from project_fixture import select_language

def setUpModule():
    select_language("ru")

class HatchCheckTest(unittest.TestCase):
    """The party slot of a saved game against the species catalog's name."""

    def save(self, *mons: TestMon) -> bytes:
        s = SaveFile(blank_save(LAYOUT, rotation=3), LAYOUT)
        slot = s.slots[0]
        s.write(slot, LAYOUT.party["count"], bytes([len(mons)]))
        for i, m in enumerate(mons):
            s.write(slot, LAYOUT.party["base"] + 100 * i, party_pokemon(m, en("A")))
        s.fix_checksums()
        return s.to_bytes()

    def check(self, data: bytes, slot: int, catalog: str) -> dict:
        return hatch_check(data, Layout.from_dict(SAVE), slot, 175, catalog, TABLE)

    def test_the_hatched_name_against_the_catalog(self):
        # the species name overwrites the egg's; later bytes stay
        hatched = (ru("Тогэпи") + b"\xff\x03\xe4\x30")
        data = self.save(TestMon("party", 0, 1, ru("Бульбазавр")), TestMon("party", 1, 175, hatched))
        self.assertEqual(self.check(data, 2, "Тогэпи"),
                         {"species": 175, "egg": False, "name": "Тогэпи", "catalog": "Тогэпи", "passed": True})
        self.assertFalse(self.check(data, 2, "Тогепи")["passed"])                  # another name
        self.assertEqual(self.check(data, 1, "Тогэпи")["species"], 1)               # another species
        self.assertFalse(self.check(data, 1, "Тогэпи")["passed"])
        self.assertEqual(self.check(data, 3, "Тогэпи"),
                         {"species": 0, "egg": False, "name": "", "catalog": "Тогэпи", "passed": False})
        english = self.save(TestMon("party", 0, 175, en("Togepi")))
        self.assertTrue(self.check(english, 1, "Togepi")["passed"])

    def test_an_egg_has_not_hatched(self):
        data = self.save(TestMon("party", 0, 175, GAME_EGG_NICKNAME, egg=True))
        result = self.check(data, 1, "Тогэпи")
        self.assertEqual((result["species"], result["egg"], result["passed"]), (175, True, False))
