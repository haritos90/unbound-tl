import unittest

from gen3tl.discover import foundations, save
from gen3tl.profile import schema
from gen3tl.profile.profile import Profile

from rom_support import needs_rom, rom_path

@needs_rom
class ReferenceSaveTest(unittest.TestCase):
    def test_real_rom_reproduces_the_scoped_save_facts(self):
        profile = Profile.by_name("unbound-2.1.1.1")
        result = foundations.run(profile.load_rom(rom_path()))
        actual = result.data["save"]
        for name in ("size", "sector_size", "data_size", "signature", "slot_sectors", "section_sizes",
                     "box_record", "party", "daycare", "boxes", "names", "blocks", "parasite", "extra", "player",
                     "rival", "mon_names", "box_names", "mail", "daycare_mail", "link_records",
                     "hall_of_fame", "egg_hatch"):
            with self.subTest(fact=name):
                def technical(value):
                    if isinstance(value, dict):
                        return {key: technical(item) for key, item in value.items() if not schema.is_prose(key)}
                    if isinstance(value, list):
                        return [technical(item) for item in value]
                    return value
                self.assertEqual(actual[name], technical(profile["save"][name]))
        self.assertFalse([fact for fact in result.issues if fact.section.startswith("save")])
        proofs = [fact for fact in result.facts if fact.section.startswith("save")]
        self.assertTrue(proofs)
        self.assertTrue(all(fact.source == save.SOURCE and fact.evidence.method for fact in proofs))
