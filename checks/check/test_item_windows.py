import unittest

from gen3tl.check import qa
from gen3tl.profile.profile import Profile

from rom_support import needs_rom, rom_path

@needs_rom
class UnboundItemWindowTest(unittest.TestCase):
    def test_consumer_selection_matches_native_item_pockets(self):
        profile = Profile.by_name("unbound-2.1.1.1")
        rom = profile.load_rom(rom_path())
        table = next(t for t in profile["table"] if t["name"] == "items")
        entries, pointers = [], 0
        for i in range(table["count"]):
            at = table["base"] + i * table["stride"]
            target = rom.ptr_at(at)
            if target is None:
                entry = {"id": f"items:{i}", "kind": "fixed", "table": "items", "index": i}
            else:
                pointers += 1
                entry = {"id": f"item-pointer:{i}", "kind": "pointer",
                         "refs": [{"at": at, "kind": "table:items"}]}
            entries.append(entry)
        windows = qa.Windows(profile, {"entries": entries})
        self.assertEqual(pointers, 33)
        for i, entry in enumerate(entries):
            pocket = rom.u8(table["base"] + i * table["stride"] + 26)
            rules = windows.rules(entry["id"])
            expected_width = {2: 104, 4: 101, 5: 71}.get(pocket, 92)
            expected_chars = {2: 17, 4: None, 5: 12}.get(pocket, 15)
            with self.subTest(item=i, pocket=pocket):
                self.assertEqual(min(w["width"] for w in rules), expected_width)
                self.assertEqual(min((w["chars"] for w in rules if "chars" in w), default=None),
                                 expected_chars)
