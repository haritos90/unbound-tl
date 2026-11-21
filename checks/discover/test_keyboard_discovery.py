import unittest

from gen3tl.discover import tables
from gen3tl.discover.foundations import families
from gen3tl.profile.profile import Profile

from rom_support import needs_rom, rom_path

@needs_rom
class ReferenceKeyboardTest(unittest.TestCase):
    def test_real_rom_matches_the_hand_proven_layout(self):
        profile = Profile.by_name("unbound-2.1.1.1")
        result = tables.run(profile.load_rom(rom_path()), families()[0])
        actual = result.data["keyboard"]
        for name in ("reserved", "opening_keyboard_offsets", "page_count"):
            with self.subTest(fact=name):
                self.assertEqual(actual[name], profile["keyboard"][name])
            proof = next(fact for fact in result.facts if fact.id == "keyboard")
            self.assertEqual(proof.status, "verified")
            self.assertTrue(proof.evidence.method)
