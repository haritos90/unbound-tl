import json
import unittest

from gen3tl.discover.map_facts import Roots, discover

from rom_support import needs_rom, rom_path
from test_roots import TOOLKIT_ROOT
from project_fixture import unbound

@needs_rom
class ReferenceMapsTest(unittest.TestCase):
    def test_every_header_and_root_matches_the_existing_walk(self):
        profile = unbound()
        rom = profile.load_rom(rom_path())
        knowledge = json.loads((TOOLKIT_ROOT / "families/firered-cfru/maps.json").read_text())
        result = discover(rom, knowledge, "firered-cfru")
        walker = Roots(rom, profile)
        walker.walk_all()
        walker.walk_structural()
        self.assertEqual(result.data["maps"]["groups"], profile["maps"]["groups"])
        self.assertEqual(result.data["maps"]["engine"],
                         {key: profile["maps"]["engine"][key] for key in ("groups", "count", "bank_xor")})
        self.assertEqual({row["map"]: row["header"] for row in result.metadata["headers"]}, walker.ctx.headers)
        self.assertEqual(result.metadata["roots"], walker.roots)
