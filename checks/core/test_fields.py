import unittest

from gen3tl.core.fields import long_name_fields

from rom_support import needs_rom
from project_fixture import UNBOUND, project_wording_rows

@needs_rom
class ProjectLongNameTest(unittest.TestCase):
    def test_declared_long_names_use_full_glossary_forms(self):
        """A field given pointer capacity keeps no fitting compact label."""
        from gen3tl.catalog.catalog import load_catalog
        from gen3tl.profile.profile import Profile
        from gen3tl.lang.termbase import load
        profile = Profile.by_name("unbound-2.1.1.1")
        catalog = load_catalog(UNBOUND / "translation" / "ru" / "po")
        terms = {t.id: t for t in load(UNBOUND / "translation" / "ru" / "glossary.tsv")}
        checked = 0
        for table in profile.data["table"]:
            for index, rule in long_name_fields(table).items():
                sid = f"{table['name']}:{index}"
                with self.subTest(sid=sid):
                    entry = catalog[sid][1]
                    filled = [c for c in entry.translator if c.startswith("filled from glossary ")]
                    self.assertEqual(len(filled), 1)
                    term = terms[filled[0].removeprefix("filled from glossary ")]
                    if len(term.translation) < rule["length"]:
                        self.assertEqual(entry.msgstr, term.translation)
                        self.assertIn(term.label, ("", term.translation))
                    checked += 1
        self.assertGreaterEqual(checked, 9)

    def test_abbreviation_families_share_one_cut(self):
        """A recorded word family keeps one cut in every member."""
        from gen3tl.catalog.catalog import load_catalog
        from gen3tl.catalog.po import PoEntry
        catalog = load_catalog(UNBOUND / "translation" / "ru" / "po")
        rows = [dict(row, ids=" ".join(row["ids"])) for row in project_wording_rows()]
        self.assertTrue(rows)
        self.assertEqual(family_misses(rows, catalog), [])
        # the check finds a member without the family's cut
        sample = [{"ids": "s1 s2", "rule": "Cut «Песч.»: one cut for Песчаный."}]
        members = {"s1": (None, PoEntry("s1", "Sand", "Песч. змея")), "s2": (None, PoEntry("s2", "Sand", "Песчаная змея"))}
        self.assertEqual(family_misses(sample, members), [("s2", "песч.")])


def family_misses(rows, catalog):
    """(entry, cut) of each family member whose translation lacks the family's cut."""
    import re
    misses = []
    for row in rows:
        # a structured rule states its prose as note guidance
        texts = [row["rule"]] if "rule" in row else [g for note in row["notes"] for g in note.get("guidance", [])]
        match = next(filter(None, (re.match(r"Cut «([^»]+)»:", text) for text in texts)), None)
        if match is None:
            continue
        cut = match.group(1).lower()
        misses += [(sid, cut) for sid in row["ids"].split() if cut not in catalog[sid][1].msgstr.lower()]
    return misses
