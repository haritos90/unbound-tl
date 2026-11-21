from test_roots import TOOLKIT_ROOT
"""Profile schema unbound checks and fixtures."""

import sys
from pathlib import Path
import json
import shutil
import tempfile
import unittest
from copy import deepcopy

sys.path.insert(0, str(TOOLKIT_ROOT / "src"))

from gen3tl.core import notes
from gen3tl.discover import emission
from gen3tl.profile import check, schema, tsv
from gen3tl.profile.profile import Profile

from project_fixture import UNBOUND, needs_unbound, unbound
import profile_schema_support


class ProfileNotesTest(profile_schema_support.ProfileNotesTest, unittest.TestCase):
    @needs_unbound
    def test_all_dataset_evidence_fields_accept_bound_notes(self):
        from gen3tl.data import pokedexdata, pokedexsprites

        block = unbound().get("pokedex")
        self.assertEqual(pokedexdata.check(block), [])
        self.assertEqual(pokedexsprites.check(block), [])
        for status in ("unreviewed", "accepted"):
            with self.subTest(status=status):
                migrated = self.migrated(block, status)
                self.assertEqual(pokedexdata.check(migrated), [])
                self.assertEqual(pokedexsprites.check(migrated), [])
        self.assertEqual(pokedexdata.check(json.loads(json.dumps(migrated))), [])

    @needs_unbound
    def test_profile_consumers_accept_visible_note_evidence(self):
        from gen3tl.build import codereplace, easychat, spritefont, textprefix
        from gen3tl.check import coverage, entrycheck, qa
        from gen3tl.core.fields import long_name_fields
        from gen3tl.discover import inventory, maps, reach
        from gen3tl.profile import languagerules

        from project_fixture import unbound

        data = self.migrated(Profile.by_name(None).data, "unreviewed")
        inventory.text_modes(data.get("strings", {}).get("text_mode", []))
        reach.declared_tables(data)
        reach.unused_entries(data)
        maps.native_fill_rules(data)
        coverage.unread_rules(data)
        qa.code_fills(self.migrated(unbound().get("layout", {}), "unreviewed"))
        for table in data.get("table", []):
            long_name_fields(table)
        for rule in data.get("code_replacement", []):
            codereplace.parse(rule)
        easychat.from_profile(data)
        spritefont.from_profile(data)
        textprefix.configure(data, [rule["name"] for rule in data.get("text_prefixes", [])])
        languagerules.load(data)
        for field in ("droppable", "addable"):
            rules = list(data.get("text_controls", {}).get(field, {}).values())
            getattr(entrycheck, f"{field}_tokens")({field: rules})

    @needs_unbound
    def test_dataset_consumers_refuse_empty_unbound_evidence(self):
        from gen3tl.data import pokedexdata, pokedexsprites

        block = unbound()["pokedex"]
        self.assertEqual(pokedexdata.check(block), [])
        paths = [
            "species", "species.ev_yield", "dex.records", "evolution", "tile_behaviors", "sprites",
            "species_browsing.253", "species_browsing.forms", "form_names", "abilities",
            "moves", "moves.environments", "moves.flinch.rules.0", "items", "items.sources",
            "items.sources.pickups", "items.held_effects.amounts.1", "items.mining", "items.uses",
            "items.uses.recipes.0",
            "learnsets.level_up", "encounters", "encounters.trigger_tiles", "encounters.method_labels.0",
            "locations", "locations.names", "locations.encounter_rates", "maps", "type_icons", "icons.split",
            "sources", "trainers.pictures", "trainers.abilities", "trainers.ivs", "trainers.evs",
            "trainers.maps", "trainers.maps.resolutions.0", "trainers.encounters.0",
            "trainers.difficulty.presentation", "trainers.participants.0", "trainers.order",
            "trainers.ivs.species_conditions.0", "trainers.ivs.species_rules.0", "trainers.ivs.write_rules.0",
            "trainers.ivs.species_rules.5.battles.0",
        ]
        for path in paths:
            with self.subTest(path=path):
                changed = deepcopy(block)
                row = changed
                for key in path.split("."):
                    row = row[int(key)] if isinstance(row, list) else row[key]
                self.assertTrue(notes.has_prose(row["evidence"]))
                row["evidence"] = ""
                self.assertTrue(pokedexdata.check(changed), path)
                if path in ("sprites", "trainers.pictures"):
                    self.assertTrue(pokedexsprites.check(changed), path)


class UnboundProfileTest(unittest.TestCase):
    """The real profile directory and its overlay read the same per language."""

    @needs_unbound
    def test_observations_and_physical_bindings_have_evidenced_tiers(self):
        directory = Profile.by_name("unbound-2.1.1.1")
        result = check.run(directory.path)
        facts = {c.fact.id: c.fact for c in result.comparisons}
        for fact in facts.values():
            if fact.id.startswith("reach.observed["):
                self.assertEqual(fact.tier, "ingame")
            elif fact.id.startswith(("table[", "font[", "keyboard.table[", "pokedex.moves.lists[")):
                self.assertEqual(fact.tier, "crossref", fact.id)
            if fact.tier:
                self.assertTrue(fact.evidence.sentence, fact.id)
        for parent, children in (
                ("pokedex.sprites", ("front", "back", "palettes", "shiny_palettes")),
                ("pokedex.trainers.pictures", ("front", "palettes")),
                ("pokedex.encounters.headers", ("day", "morning", "evening", "night"))):
            value = directory.data
            for key in parent.split("."):
                value = value[key]
            for child in children:
                fact = facts[f"{parent}.{child}"]
                self.assertEqual(fact.tier, "crossref")
                self.assertEqual(fact.value, value[child])
                self.assertTrue(fact.evidence.code_sites)
        self.assertIsNone(facts["strings.pointer_table[name=credits-firered]"].tier)
        self.assertIsNone(facts["pokedex.form_names.type_families[#0]"].tier)
        self.assertTrue(all(f.tier is None for f in facts.values() if f.id.startswith("layout.")))

    @needs_unbound
    def test_record_layout_tiers_keep_partial_proofs_and_configuration_explicit(self):
        directory = Profile.by_name("unbound-2.1.1.1")
        facts = {c.fact.id: c.fact for c in check.run(directory.path).comparisons}
        for name in ("save.names.species_table", "save.mon_names", "save.daycare_mail",
                     "pokedex.trainers.party", "pokedex.trainers.fields", "pokedex.items.fields",
                     "pokedex.items.fields.price", "pokedex.items.fields.description",
                     "pokedex.dex.records.fields", "pokedex.dex.records.fields.weight",
                     "pokedex.dex.records.fields.description", "pokedex.items.mining.item",
                     "pokedex.species.ev_yield", "pokedex.encounters.headers.stride",
                     "pokedex.encounters.methods.land", "pokedex.encounters.methods.fishing",
                     "pokedex.encounters.fishing.super", "pokedex.evolution.fields.target"):
            with self.subTest(fact=name):
                self.assertEqual(facts[name].tier, "crossref")
                self.assertTrue(facts[name].evidence.sentence)
        self.assertEqual(facts["save.names.species_table"].value,
                         facts["table[name=species]"].value["base"])
        self.assertEqual(facts["pokedex.trainers.party"].value,
                         directory["pokedex"]["trainers"]["party"])
        self.assertEqual(facts["pokedex.items.fields.price"].value, {"offset": 16, "width": 2})
        for name in ("pokedex.moves.fields.priority.signed", "pokedex.moves.fields.accuracy",
                     "pokedex.species.fields.catch_rate", "pokedex.evolution.fields.extra.offset",
                     "pokedex.maps", "save.party.stride"):
            self.assertIsNone(facts[name].tier, name)
        small = facts["font[name=small]"]
        self.assertEqual(small.value["style"], "unbound-small")
        self.assertIn("presentation configuration, not recovered ROM data", small.evidence.sentence)

    @needs_unbound
    def test_string_table_bindings_are_tiered_as_a_complete_family(self):
        directory = Profile.by_name("unbound-2.1.1.1")
        result = check.run(directory.path)
        bindings = directory["strings"]["table_base"]
        expected = {f"strings.table_base[id={row['id']}]": row for row in bindings}
        facts = {c.fact.id: c.fact for c in result.comparisons
                 if c.fact.section == "strings.table_base"}
        self.assertTrue(expected)
        self.assertEqual(set(facts), set(expected))
        for name, value in expected.items():
            self.assertEqual(facts[name].tier, "crossref", name)
            self.assertEqual(facts[name].value, value)
            self.assertEqual(facts[name].evidence.sentence, value["evidence"])
        tiers = check.tier_counts(result, ["strings.table_base"])
        self.assertEqual(tiers["overlay"], {"shape": 0, "crossref": len(bindings),
                                             "ingame": 0, "unstated": 0})
        self.assertFalse(any(tiers["family"].values()))
        self.assertFalse(any(tiers["generated"].values()))

    @needs_unbound
    def test_eggs_waiting_is_an_evidenced_profile_fact(self):
        directory = Profile.by_name("unbound-2.1.1.1")
        comparison = next(c for c in check.run(directory.path).comparisons if c.fact.id == "save.egg_hatch")
        self.assertEqual(comparison.fact.value["eggs_waiting"], 0x203B468)
        self.assertIn("special 0xBB", comparison.fact.evidence.sentence)
        self.assertIn("script 0x1E619AF", comparison.fact.evidence.sentence)
        self.assertIn("special 0xB8", comparison.fact.evidence.sentence)

    @needs_unbound
    def test_every_language_project_reads_the_same_effective_profile(self):
        from gen3tl.project import Registry
        registry = Registry.load(UNBOUND)
        directory = Profile.by_name("unbound-2.1.1.1")
        # Both forms project validated notes.
        with tempfile.TemporaryDirectory() as temporary:
            flat_path = Path(temporary) / schema.OVERLAY
            shutil.copyfile(directory.path / schema.GENERATED, flat_path.parent / schema.GENERATED)
            fragments = []
            for file in schema.overlay_files(directory.path):
                if file.suffix == ".toml":
                    fragments.append(file.read_text(encoding="utf-8"))
                elif file.suffix == ".tsv":
                    name = file.relative_to(directory.path / schema.OVERLAY_DIR).as_posix()
                    path, columns = schema.OVERLAY_TABLES[name]
                    for row in tsv.read(file, columns):
                        fragments.append(f"[[{schema.path_id(path)}]]\n" + "\n".join(
                            f"{schema.key_text(key)} = {emission.literal(value)}" for key, value in row.items()))
            flat_path.write_text("\n".join(fragments), encoding="utf-8")
            flat_data = Profile.load(flat_path.parent).data
        overlay = Profile(flat_data, directory.path.parent / f"{directory.name}.toml")
        projects = [p for p in registry.projects if p.profile == directory.name]
        self.assertGreater(len(projects), 1)
        for project in projects:
            with self.subTest(language=project.language):
                flat, merged = project.effective(overlay), project.effective(directory)
                self.assertTrue(check.same(merged.data, flat.data))
