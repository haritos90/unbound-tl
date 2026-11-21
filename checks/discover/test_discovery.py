import unittest
from pathlib import Path

from gen3tl.profile.profile import Profile

class DiscoveryTest(unittest.TestCase):
    def profile(self):
        return Profile({"support": {"stage": "discovery"}, "engine": {"family": "emerald"}},
                       Path("test-game.toml"))


    def test_support_metadata_is_explicit_and_legacy_compatible(self):
        self.assertIsNone(Profile({}, Path("legacy.toml")).command_problem("build rom"))
        prof = self.profile()
        prof.data["support"]["stage"] = "typo"
        self.assertIn("unknown support", prof.command_problem("rom identify"))
        self.assertIsNone(Profile.by_name("unbound-2.1.1.1").command_problem("build rom"))
