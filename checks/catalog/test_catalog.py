import json
import unittest

from gen3tl.catalog.catalog import load_catalog, never_shown

from rom_support import needs_rom
from test_roots import PROJECT_ROOT

@needs_rom
class ProfileNeverShownTest(unittest.TestCase):
    """The profile's reviewed overrides name catalog entries with evidence."""

    def test_rules(self):
        from gen3tl.profile.profile import Profile
        rules = Profile.by_name("unbound-2.1.1.1").get("reach", {}).get("never_shown", [])
        self.assertTrue(rules)
        never = never_shown(None, rules)   # every rule has ids and evidence
        root = PROJECT_ROOT
        po = root / "translation" / "po"
        if po.exists():
            self.assertEqual(sorted(set(never) - set(load_catalog(po))), [])
        # texts reached only through code, not map scripts
        for sid in ("s041A155", "s041B8BF", "s041E5A4", "s041CB3C", "s041E5FD", "s041B285", "s03FD2D9",
                    "s0920045", "s1F4DEA1", "s1F4E086"):
            self.assertTrue(never[sid].startswith("review: "), sid)
        self.assertNotIn("s03FE747", never)   # safari menu: probable only
        inv = root / "build" / "inventory.json"
        if inv.exists():
            # no entry for the live move descriptions
            import json
            live = {e["id"] for e in json.loads(inv.read_text(encoding="utf-8"))["entries"]
                    for r in e["refs"] if 0x99F190 <= r["at"] < 0x99FE60}
            self.assertEqual(sorted(live & set(never)), [])
