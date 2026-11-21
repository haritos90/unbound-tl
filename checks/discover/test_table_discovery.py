import unittest

from gen3tl.discover import table_scope, foundations, tables
from gen3tl.profile import schema
from gen3tl.profile.profile import Profile

from rom_support import needs_rom, rom_path

class StructuralScopeTest(unittest.TestCase):


    def test_actual_scope_keeps_all_hard_structural_facts_and_named_configuration(self):
        facts = schema.overlay_facts(schema.read(Profile.by_name("unbound-2.1.1.1").path))
        report = table_scope.compare(facts, [])
        self.assertEqual(report["structural_facts"], 150)
        rows = {row["id"]: row for row in report["facts"]}
        self.assertEqual(set(rows), {fact.id for fact in facts if table_scope.selected(fact)})
        self.assertEqual(report["raw_named_facts"], sum(
            count for counts in report["sections"].values()
            for category, count in counts.items() if category != "structural"))
        for name in ("strings.pointer_table[name=credits-firered]", "pokedex.abilities", "pokedex.maps",
                     "pokedex.moves.fields.priority.signed", "pokedex.evolution.fields.extra.offset"):
            self.assertTrue(rows[name]["included"], name)
        for name in ("pokedex.name_table", "pokedex.form_names.type_families[#0]"):
            self.assertFalse(rows[name]["included"], name)
            self.assertTrue(rows[name]["reason"])


@needs_rom
class TableEvidenceTest(unittest.TestCase):


    def test_actual_header_name_bindings_are_independent_of_reference_addresses(self):
        profile = Profile.by_name("unbound-2.1.1.1")
        result = tables.run(profile.load_rom(rom_path()), foundations.families()[0])
        short_names = next(issue for issue in result.issues if issue.id == "table[name=types_short]")
        self.assertEqual(short_names.status, "candidate")
        self.assertIn("no confirmed linked indexed reader", short_names.evidence.sentence)
        self.assertEqual(dict(short_names.evidence.counts)["stride"], 7)
        self.assertNotIn("trades", result.data["pokedex"]["sources"])
        trade_issue = next(issue for issue in result.issues if issue.id == "pokedex.sources.trades")
        self.assertEqual(trade_issue.status, "omitted")
        self.assertEqual(trade_issue.evidence.method, "semantic-reader+entry-reachability")
        self.assertFalse([issue for issue in result.issues if issue.id in {
            "table[name=species]", "table[name=moves]", "table[name=abilities]", "table[name=items]",
            "pokedex.species", "pokedex.moves", "pokedex.abilities.descriptions",
            "pokedex.sprites.front", "pokedex.sprites.back", "pokedex.sprites.palettes", "pokedex.sprites.shiny_palettes"}])
        reference = {row["name"]: row for row in profile["table"]}
        for fact in result.facts:
            if not fact.id.startswith("table["):
                continue
            expected = reference[fact.value["name"]]
            for key in ("base", "stride", "count", "field_offset", "field_length"):
                self.assertEqual(fact.value[key], expected[key], (fact.id, key))
        for name in ("front", "palettes"):
            fact = next(fact for fact in result.facts if fact.id == f"pokedex.trainers.pictures.{name}")
            expected = profile["pokedex"]["trainers"]["pictures"][name]
            self.assertEqual(fact.value, {key: expected[key] for key in ("base", "stride", "count")})
