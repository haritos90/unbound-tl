import unittest

from gen3tl.check import rules
from gen3tl.catalog.catalog import load_catalog

from rom_support import needs_rom
from project_fixture import UNBOUND, project_wording_rows

@needs_rom
class RepositoryListTest(unittest.TestCase):
    """The project rule list retains its existing guidance."""

    def test_seed(self):
        out = rules.wording_rules(project_wording_rows(),
                                  load_catalog(UNBOUND / "translation" / "ru" / "po"))
        # the pair trainer class rule on the shared battle lines
        for sid in ("s0A4C4BD", "s03FD3C7", "s03FD3B1", "s03FD1C7", "s0A4C6FD"):
            self.assertTrue(any(r["text"].startswith("A trainer class is a singular noun phrase") for r in out[sid]), sid)
        self.assertIn("singular", out["s0A4C4BD"][0]["text"])
        # the byte-gap exception on the computed send-out lines
        for sid in ("s03FD3C7", "s03FD4FA", "s03FD535"):
            self.assertIn("project style rules", [r["source"] for r in out[sid]], sid)
