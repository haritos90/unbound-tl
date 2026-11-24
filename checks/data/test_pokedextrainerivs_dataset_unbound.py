from test_roots import TOOLKIT_ROOT
"""Pokedextrainerivs dataset unbound checks and fixtures."""

import sys
from pathlib import Path
import copy
import unittest

sys.path.insert(0, str(TOOLKIT_ROOT / "src"))

from gen3tl.data import pokedexdata as pd
from gen3tl.data import pokedextrainerivs as iv
from gen3tl.data.pokedexstore import load
from gen3tl.profile.profile import Profile

from project_fixture import needs_unbound
from pokedextrainerivs_support import DATASET, member, trainer, uniform


@needs_unbound
class TrackedDatasetTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profile = Profile.by_name("unbound-2.1.1.1")
        cls.block = cls.profile["pokedex"]
        cls.index = load(DATASET / "pokedex.json")
        cls.doc = iv.read(DATASET / "trainer-ivs.json")
        cls.members = {(row["trainer"], row["slot"]): row for row in cls.doc["members"]}

    def test_condition_labels_require_meanings_and_unknowns_keep_no_card_text(self):
        block = copy.deepcopy(self.block["trainers"]["evs"])
        self.assertEqual(iv.check_evs(block), [])
        for row in block["conditions"]:
            self.assertTrue(row["evidence"].strip())
            for key in ("set", "clear"):
                self.assertNotIn("{flag}", row[key])
        block["conditions"][0] = {"flag": 123, "status": "unknown", "evidence": "Reader found; setter meaning unresolved."}
        self.assertEqual(iv.check_evs(block), [])
        self.assertEqual(iv.condition_labels(block)[0], {"flag": "0x7B"})
        for label in ("Flag {flag} set", "Flag 0x7B set", ""):
            block["conditions"][0] = {"flag": 123, "set": label, "clear": "Before event", "evidence": "Reader"}
            self.assertIn("conditions", iv.check_evs(block))
        stale = dict(self.doc, ev_conditions=[])
        self.assertIn("EV conditions: regenerate trainer IV data", iv.verify_doc(
            stale, self.block["trainers"]["ivs"], self.profile.name, self.profile.sha1,
            self.index["profile_block"], self.block["trainers"]["evs"]))

    def test_companion_and_index_verify_without_private_inputs(self):
        self.assertEqual(iv.check(self.block["trainers"]["ivs"]), [])
        self.assertEqual(iv.verify_doc(self.doc, self.block["trainers"]["ivs"], self.profile.name,
                                       self.profile.sha1, self.index["profile_block"], self.block["trainers"]["evs"]), [])
        self.assertEqual(pd.verify_doc(self.index, self.block, self.profile.name, self.profile.sha1), [])
        inlined = pd.read(DATASET / "pokedex.json")
        self.assertEqual(inlined["trainer_ivs"], self.doc)
        self.assertEqual(pd.verify_doc(inlined, self.block, self.profile.name, self.profile.sha1), [])

    def test_all_listed_members_and_contexts_are_present(self):
        self.assertEqual(len(self.doc["members"]), 2200)
        self.assertEqual(self.doc["audit"]["species_variant_members"], 57)
        self.assertEqual(self.doc["audit"]["evaluated_contexts"], 65104)
        self.assertEqual(self.doc["audit"]["different_iv_outcomes"], 0)
        for row in self.doc["members"]:
            self.assertEqual(len(row["contexts"]), 4 if row["slot"] >= 3 else 8)
            self.assertFalse(any(key.endswith("/0") for key in row["contexts"] if row["slot"] >= 3))
            self.assertTrue(all(len(vector) == 6 for vector in row["contexts"].values()))

    def test_default_move_bands_cover_every_noncustom_member(self):
        for trainer in self.index["trainers"]:
            for mon in trainer["party"]:
                if not mon["species"]:
                    continue
                generated = self.members[trainer["id"], mon["index"]]
                self.assertEqual("move_bands" in generated, mon["moves"] is None)
                if mon["moves"] is None:
                    self.assertTrue(iv._move_bands(generated["move_bands"], generated["listed"],
                                                   generated["level_ranges"]))

    def test_native_level_extremes_bound_default_moves(self):
        cases = [(10, 0, 0, 15, 93), (10, 0, 1, 15, 15), (10, 0, 2, 15, 93), (10, 0, 3, 15, 98),
                 (547, 0, 1, 41, 96), (547, 1, 1, 40, 95), (1, 0, 0, 10, 95)]
        for trainer_id, slot, day, minimum, maximum in cases:
            row = self.members[trainer_id, slot]
            self.assertEqual(row["level_ranges"][str(day)], {"min": minimum, "max": maximum})

    def test_missing_or_damaged_level_ranges_fail_verification(self):
        for damage in (None, {}, {"0": {"min": 1, "max": 101}}):
            doc = pd.read(DATASET / "pokedex.json")
            member = next(row for row in doc["trainer_ivs"]["members"] if "move_bands" in row)
            member["level_ranges"] = damage
            self.assertIn("invalid default move level ranges", " ".join(pd.verify_doc(
                doc, self.block, self.profile.name, self.profile.sha1)))

    def test_missing_or_damaged_default_bands_fail_verification(self):
        doc = pd.read(DATASET / "pokedex.json")
        member = next(row for row in doc["trainer_ivs"]["members"] if "move_bands" in row)
        member["move_bands"][0]["level"] = 2
        self.assertIn("invalid default move bands", " ".join(pd.verify_doc(
            doc, self.block, self.profile.name, self.profile.sha1)))
        member.pop("move_bands")
        self.assertIn("trainer default moves", " ".join(pd.verify_doc(
            doc, self.block, self.profile.name, self.profile.sha1)))

    def test_conditional_writes_match_saved_builder_samples(self):
        cases = [
            (39, 0, None, 20, 2, [332, 119, 283, 297], 570),
            (39, 1, None, 22, 3, [351, 115, 113, 86], 90),
            (39, 2, None, 20, 2, [325, 8, 182, 174], 44),
            (42, 0, None, 28, 0, [185, 381, 332, 228], 0),
            (42, 1, None, 33, 0, [432, 404, 317, 258], 243),
            (332, 0, None, 25, 3, [361, 211, 350, 331], 187),
            (332, 1, 526, 58, 2, [432, 89, 381, 468], 0),
            (332, 2, 248, 59, 2, [429, 242, 89, 8], 0),
            (333, 2, 400, 71, 2, [309, 401, 379, 97], 0),
            (334, 2, 498, 71, 2, [486, 89, 242, 126], 0),
            (404, 1, None, 30, 3, [434, 9, 183, 109], 599),
            (404, 2, None, 31, 3, [58, 57, 182, 281], 142),
            (720, 2, 15, 37, 2, [450, 40, 228, 31], 188),
            (721, 2, 15, 37, 2, [400, 424, 403, 730], 450),
        ]
        for trainer, slot, species, level, day, moves, item in cases:
            with self.subTest(trainer=trainer, slot=slot, level=level, difficulty=day):
                source = self.members[trainer, slot]
                if species is not None:
                    source = next(row for row in source["species_changes"] if row["species"] == species
                                  and day in row["difficulties"] and row.get("level", 1) <= level <= row.get("last", 100))
                rows = [row for row in source["write_changes"] if day in row["difficulties"]
                        and row["level"] <= level <= row.get("last", 100)
                        and all(0 in values for values in row["when"].values())]
                self.assertEqual(len(rows), 1)
                self.assertEqual((rows[0]["moves"], rows[0]["item"]), (moves, item))

    def test_rival_items_follow_the_starter_variant_and_story_flags(self):
        # Native Insane builds at level 100 with the record's starter.
        cases = [
            (333, 2, 400, {}, [309, 401, 89, 8], 483),
            (333, 2, 400, {"0x16E2": 1}, [309, 401, 89, 8], 55),
            (334, 2, 498, {"0x16E2": 1}, [715, 89, 126, 14], 226),
            (435, 3, 665, {}, [200, 89, 242, 349], 493),
            (436, 3, 665, {}, [200, 89, 242, 349], 570),
            (437, 3, 384, {}, [429, 382, 692, 521], 557),
            (437, 3, 384, {"0x16E2": 1}, [429, 382, 692, 521], 473),
            (439, 3, None, {"0x16E2": 1}, [200, 89, 242, 349], 570),
            (440, 3, None, {"0x16E2": 1}, [429, 382, 692, 521], 473),
            (436, 4, 400, {"0x16E2": 1}, [309, 401, 89, 8], 55),
            (435, 1, None, {"0x170B": 1}, [65, 31, 350, 395], 210),
            (435, 0, 526, {"0x170B": 1}, [432, 404, 381, 468], 539),
            (435, 2, None, {"0x9F3": 1}, [352, 62, 98, 639], 541),
        ]
        for trainer, slot, species, flags, moves, item in cases:
            with self.subTest(trainer=trainer, slot=slot, flags=flags):
                source = self.members[trainer, slot]
                if species is not None:
                    source = next(row for row in source["species_changes"] if row["species"] == species
                                  and 3 in row["difficulties"] and row.get("level", 1) <= 100 <= row.get("last", 100))
                rows = [row for row in source["write_changes"] if 3 in row["difficulties"]
                        and row["level"] <= 100 <= row.get("last", 100)
                        and all(flags.get(key, 0) in values for key, values in row["when"].items())]
                self.assertEqual(len(rows), 1)
                self.assertEqual((rows[0]["moves"], rows[0]["item"]), (moves, item))
        rules = {row["id"]: row for row in self.doc["write_rules"]}
        self.assertFalse([name for name, row in rules.items() if row["status"] == "unknown"])
        self.assertEqual({rules[name]["native"] for name in ("rival-item-bird-late", "rival-item-mammoth-late",
                                                             "rival-item-water-late")}, {"confirmed"})

    def test_records_204_and_205_take_their_expert_and_insane_writes(self):
        # Native builds at the trigger's maps, every difficulty.
        cases = [(204, 0, [531, 257, 85, 706], 548), (204, 1, [531, 53, 202, 464], 55),
                 (205, 0, [89, 242, 592, 182], 142), (205, 1, [382, 390, 430, 216], 539)]
        expert = {(204, 0): [531, 257, 85, 706], (204, 1): [531, 53, 202, 464],
                  (205, 0): [89, 242, 617, 182], (205, 1): [382, 390, 430, 216]}
        for trainer, slot, moves, item in cases:
            with self.subTest(trainer=trainer, slot=slot):
                rows = self.members[trainer, slot]["write_changes"]
                self.assertEqual({day for row in rows for day in row["difficulties"]}, {2, 3})
                self.assertTrue(all(row["when"] == {} and row["level"] == 1 and "last" not in row for row in rows))
                insane = next(row for row in rows if 3 in row["difficulties"])
                self.assertEqual((insane["moves"], insane["item"]), (moves, item))
                expert_row = next(row for row in rows if 2 in row["difficulties"])
                self.assertEqual((expert_row["moves"], expert_row["item"]), (expert[trainer, slot], 0))
        self.assertFalse(any(self.members[203, slot].get("write_changes") for slot in range(4)))

    def test_listed_adjustments_match_saved_builder_samples(self):
        cases = [
            (396, 0, 0, 59, [396, 440, 157, 567], 0),
            (396, 0, 1, 59, [396, 440, 157, 567], 0),
            (396, 1, 0, 61, [473, 304, 563, 533], 0),
            (396, 1, 1, 61, [473, 304, 563, 533], 0),
            (397, 0, 0, 59, [360, 242, 334, 105], 0),
            (397, 0, 1, 59, [360, 242, 334, 105], 0),
            (397, 1, 0, 60, [69, 59, 86, 135], 0),
            (397, 1, 1, 60, [69, 59, 86, 135], 0),
            (397, 2, 0, 61, [413, 276, 621, 357], 0),
            (397, 2, 1, 61, [413, 276, 621, 357], 0),
            (408, 0, 0, 59, [423, 53, 202, 337], 0),
            (408, 0, 1, 59, [423, 53, 202, 337], 0),
            (408, 1, 0, 61, [596, 355, 242, 638], 0),
            (408, 1, 1, 61, [596, 355, 242, 638], 0),
            (409, 0, 0, 60, [89, 92, 303, 182], 0),
            (409, 0, 1, 60, [89, 92, 303, 182], 0),
            (409, 1, 0, 59, [577, 242, 280, 463], 0),
            (409, 1, 1, 59, [577, 242, 280, 463], 0),
            (409, 2, 0, 61, [498, 242, 463, 228], 0),
            (409, 2, 1, 61, [498, 242, 463, 228], 0),
            (497, 0, 2, 60, [76, 372, 202, 267], 183),
            (497, 0, 3, 60, [76, 372, 202, 267], 183),
            (497, 1, 2, 61, [76, 372, 267, 311], 446),
            (497, 1, 3, 61, [76, 372, 267, 311], 446),
            (497, 2, 2, 59, [76, 367, 257, 280], 55),
            (497, 2, 3, 59, [76, 367, 257, 280], 55),
            (511, 0, 1, 60, [53, 9, 89, 267], 550),
            (511, 0, 2, 60, [257, 76, 731, 267], 570),
            (511, 0, 3, 60, [257, 76, 284, 267], 178),
            (511, 1, 2, 61, [257, 356, 731, 76], 448),
            (511, 1, 3, 61, [257, 356, 731, 76], 448),
            (511, 2, 2, 59, [257, 692, 284, 182], 142),
            (511, 2, 3, 59, [257, 692, 284, 182], 142),
        ]
        for trainer, slot, day, level, moves, item in cases:
            with self.subTest(trainer=trainer, slot=slot, difficulty=day):
                member = self.members[trainer, slot]
                self.assertNotIn("species_changes", member)
                rows = [row for row in member["write_changes"] if day in row["difficulties"]
                        and row["level"] <= level <= row.get("last", 100)]
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]["when"], {})
                self.assertEqual((rows[0]["moves"], rows[0]["item"]), (moves, item))
        for trainer in (396, 397, 408, 409):
            for (record, _), member in self.members.items():
                if record == trainer:
                    self.assertEqual(member["write_changes"][0]["difficulties"], [0, 1])
                    self.assertEqual(member["write_changes"][0]["moves"], member["listed"]["moves"])
        for trainer in (497, 511):
            for (record, _), member in self.members.items():
                if record == trainer:
                    self.assertFalse(any(0 in row["difficulties"] for row in member["write_changes"]))

    def test_malformed_species_changes_report_without_crashing(self):
        for changes in (1, [None]):
            broken = copy.deepcopy(self.doc)
            broken["members"][0]["species_changes"] = changes
            self.assertIn("species changes without declared rules", " ".join(iv.verify_doc(
                broken, self.block["trainers"]["ivs"], self.profile.name, self.profile.sha1,
                self.index["profile_block"], self.block["trainers"]["evs"])))

    def test_species_variants_retain_each_condition_and_its_evidence(self):
        block = self.block["trainers"]["ivs"]
        self.assertEqual(self.doc["species_conditions"], block["species_conditions"])
        conditions = {row["id"]: row for row in self.doc["species_conditions"]}
        for variant in block["species_variants"]:
            member = self.members[variant["trainer"], variant["slot"]]
            self.assertEqual(member["species_variants"], variant["outcomes"])
            for outcome in member["species_variants"]:
                self.assertTrue(conditions[outcome["condition"]]["rom"])
        doc = copy.deepcopy(self.doc)
        next(row for row in doc["members"] if "species_variants" in row).pop("species_variants")
        problems = iv.verify_doc(doc, block, self.profile.name, self.profile.sha1,
                                 self.index["profile_block"], self.block["trainers"]["evs"])
        self.assertTrue(any("species conditions differ" in problem for problem in problems))

    def test_species_rules_reach_the_traced_members(self):
        block = self.block["trainers"]["ivs"]
        self.assertEqual(self.doc["species_rules"], block["species_rules"])
        self.assertEqual(self.doc["audit"]["species_rules"], {
            "trainer-651-level": {"members": 2, "changed": 2}, "partner-39-level": {"members": 3, "changed": 3},
            "held-item-form": {"members": 9, "changed": 1}, "minior-core-random": {"members": 1, "changed": 1},
            "minior-core-fixed": {"members": 1, "changed": 0}, "scaled-evolution": {"members": 965, "changed": 435}})
        changed = {key: [change for change in row["species_changes"] if change["rule"] != "scaled-evolution"]
                   for key, row in self.members.items() if "species_changes" in row}
        changed = {key: rows for key, rows in changed.items() if rows}
        self.assertEqual(sorted(changed), [(39, 0), (39, 1), (39, 2), (57, 0), (651, 1), (651, 3), (726, 0)])
        self.assertEqual([{key: row[key] for key in ("species", "rule", "level", "difficulties")}
                          for row in changed[651, 3]], [{"species": 553, "rule": "trainer-651-level", "level": 36,
                                                         "difficulties": [0, 1, 2, 3]}])
        self.assertEqual([(row["species"], row["level"], row["difficulties"]) for row in
                          changed[39, 0] + changed[39, 1] + changed[39, 2]], [(451, 34, [2, 3]), (82, 31, [2, 3]),
                                                                              (676, 43, [2, 3])])
        self.assertEqual([(row["species"], row["rule"], row["difficulties"]) for row in changed[57, 0]],
                         [(1055, "held-item-form", [0, 1, 2, 3])])
        self.assertEqual([row["species"] for row in changed[726, 0]], list(range(1065, 1072)))
        doc = copy.deepcopy(self.doc)
        doc["members"][next(index for index, row in enumerate(doc["members"]) if "species_changes" in row)][
            "species_changes"][0]["rule"] = "absent"
        problems = iv.verify_doc(doc, block, self.profile.name, self.profile.sha1,
                                 self.index["profile_block"], self.block["trainers"]["evs"])
        self.assertTrue(any("species changes without declared rules" in problem for problem in problems))

    def test_scaled_evolution_states_badges_levels_battles_and_sources(self):
        def scaled(trainer_id, slot):
            return [{key: value for key, value in row.items() if key in ("species", "level", "last", "badges",
                                                                       "battle", "from", "difficulties")}
                    for row in self.members[trainer_id, slot].get("species_changes", [])
                    if row["rule"] == "scaled-evolution"]
        self.assertEqual(scaled(1, 0), [{"species": 20, "level": 20, "difficulties": [0, 2], "badges": 1},
                                        {"species": 20, "level": 20, "difficulties": [3]}])
        self.assertEqual(scaled(126, 0), [
            {"species": 192, "level": 45, "difficulties": [0, 2], "badges": 3, "battle": "rematch"},
            {"species": 192, "level": 45, "difficulties": [3], "battle": "rematch"}])
        self.assertEqual(scaled(6, 0), [{"species": 849, "level": 45, "difficulties": [0], "battle": "party-level"}])
        self.assertEqual([(row["species"], row["level"], row.get("last"), row["from"]) for row in scaled(10, 0)
                          if row["difficulties"] == [3]], [(371, 20, 39, 370), (372, 40, None, 370)])
        self.assertEqual([(row["species"], row["level"], row.get("last")) for row in scaled(273, 0)
                          if row["difficulties"] == [3]], [(136, 45, 54), (196, 55, None)])
        self.assertEqual(scaled(651, 3), [])
        self.assertEqual(scaled(651, 5), [{"species": 110, "level": 35, "difficulties": [3]}])
        self.assertEqual(scaled(39, 0), [])
        self.assertFalse(any(1 in row["difficulties"] for key in self.members for row in scaled(*key)))
        block = self.block["trainers"]["ivs"]
        doc = copy.deepcopy(self.doc)
        member = next(row for row in doc["members"] if (row["trainer"], row["slot"]) == (10, 0))
        member["species_changes"][0].pop("from")
        problems = iv.verify_doc(doc, block, self.profile.name, self.profile.sha1,
                                 self.index["profile_block"], self.block["trainers"]["evs"])
        self.assertIn("member (10, 0): species changes without declared rules", problems)

    def test_built_species_carry_the_native_ability_moves_ivs_and_evs(self):
        def change(trainer_id, slot, species, day):
            return next(row for row in self.members[trainer_id, slot]["species_changes"]
                        if row["species"] == species and day in row["difficulties"])
        pignite = change(651, 3, 553, 2)
        self.assertEqual((pignite["abilities"]["2"], pignite["ivs"]["2"], pignite["evs"]["2"]),
                         ([91], uniform(31), [252, 252, 0, 252, 0, 0]))
        self.assertEqual((pignite["item"], pignite["moves"]), (176, [434, 276, 423, 89]))
        muk = change(651, 1, 1035, 3)
        self.assertEqual((muk["item"], muk["moves"], muk["evs"]["3"]), (494, [424, 430, 157, 7], [6, 252, 252, 0, 0, 0]))
        magneton = change(39, 1, 82, 2)
        self.assertEqual((magneton["abilities"]["2"], magneton["item"]), ([5], 90))
        self.assertEqual(magneton["bands"], [{"level": 31, "last": 39, "moves": [720, 115, 113, 86]},
                                             {"level": 40, "moves": [85, 115, 113, 86]}])
        self.assertEqual([(row["item"], row["moves"]) for row in (change(39, 0, 451, 3), change(39, 2, 676, 3))],
                         [(570, [332, 365, 283, 297]), (44, [325, 8, 182, 174])])
        venusaur = change(10, 0, 372, 3)
        band = next(row for row in venusaur["bands"] if row["level"] <= 98 <= row.get("last", 100))
        self.assertEqual(band["moves"], [103, 533, 473, 63])
        self.assertEqual(venusaur["ivs"]["3"], uniform(31))
        self.assertIn({"evs": [252, 252, 0, 0, 0, 0], "when": {"0x16E2": [0], "0x821": [1]}},
                      venusaur["evs"]["3"]["alternatives"])
        block = self.block["trainers"]["ivs"]
        doc = copy.deepcopy(self.doc)
        member = next(row for row in doc["members"] if (row["trainer"], row["slot"]) == (10, 0))
        member["species_changes"][0]["ivs"] = member["species_changes"][0]["bands"][0].get("ivs", {})
        problems = iv.verify_doc(doc, block, self.profile.name, self.profile.sha1,
                                 self.index["profile_block"], self.block["trainers"]["evs"])
        self.assertIn("member (10, 0): built species details incomplete", problems)

    def test_encounters_carry_their_battle_commands(self):
        encounters = self.index["trainer_encounters"]
        self.assertTrue(all(row["commands"] for row in encounters))
        mirskle = next(row for row in encounters if row["script"] == "0x1E726D4")
        self.assertEqual(mirskle["commands"], [{"script": "0x1E726D9", "mode": 3}, {"script": "0x1E726F2", "mode": 15}])
        enabled = {row["script"] for encounter in encounters for row in encounter["commands"]
                   if row["mode"] in (5, 7, 13, 14, 15, 16)}
        self.assertEqual(len(enabled), 559)

    def test_replacement_evs_exclude_completed_progress(self):
        for slot in (0, 1, 3):
            row = self.members[10, slot]
            replacement = row["species_variants"][1]["species"]
            alternatives = row["evs"]["3"]["alternatives"]
            selected = [option for option in alternatives if replacement in option["when"].get("species", [])]
            self.assertTrue(selected)
            for option in selected:
                self.assertEqual(option["when"]["0x82C"], [0])

    def test_trainer_109_uses_rom_ordered_default_moves(self):
        self.assertEqual(self.members[109, 2]["listed"]["moves"], [182, 106])

    def test_corrected_native_examples_are_in_the_companion(self):
        self.assertEqual(self.members[513, 3]["contexts"]["1/1"], uniform(31, 0))
        self.assertEqual(self.members[513, 4]["contexts"]["2/1"], [31, 30, 31, 31, 30, 31])
        self.assertEqual(self.members[700, 4]["contexts"]["0/1"], [31, 31, 14, 0, 31, 31])
        self.assertEqual(self.members[329, 0]["contexts"]["0/1"], uniform(25))
        self.assertEqual(self.members[329, 0]["contexts"]["2/1"], uniform(31))

    def test_listed_rival_moves_need_no_nominal_replacement(self):
        speed_moves = []
        for row in self.doc["members"]:
            if row["class_id"] in (81, 89) and {510, 632}.intersection(row["listed"]["moves"]):
                speed_moves.append((row["trainer"], row["slot"]))
        self.assertEqual(speed_moves, [])

    def test_stale_identity_and_invalid_vectors_are_rejected(self):
        broken = copy.deepcopy(self.doc)
        broken["profile_block"] = "stale"
        evs = self.block["trainers"]["evs"]
        self.assertIn("profile_block", " ".join(iv.verify_doc(
            broken, self.block["trainers"]["ivs"], self.profile.name, self.profile.sha1, self.index["profile_block"], evs)))
        broken = copy.deepcopy(self.doc)
        broken["members"][0]["contexts"]["0/1"] = [32] * 6
        self.assertIn("invalid IV vector", " ".join(iv.verify_doc(
            broken, self.block["trainers"]["ivs"], self.profile.name, self.profile.sha1, self.index["profile_block"], evs)))
        broken = copy.deepcopy(self.doc)
        broken["members"][0]["evs"]["2"] = [256] * 6
        self.assertIn("invalid EV vector", " ".join(iv.verify_doc(
            broken, self.block["trainers"]["ivs"], self.profile.name, self.profile.sha1, self.index["profile_block"], evs)))
        self.assertIn("EVs without declarations", " ".join(iv.verify_doc(
            self.doc, self.block["trainers"]["ivs"], self.profile.name, self.profile.sha1, self.index["profile_block"])))

    def test_named_ev_examples_are_in_the_companion(self):
        joey = self.members[1, 0]["evs"]
        self.assertEqual(joey["0"], [0] * 6)
        self.assertEqual(joey["3"], {"alternatives": [
            {"evs": [0] * 6, "when": {"0x821": [0]}},
            {"evs": [0, 252, 0, 252, 0, 0], "when": {"0x821": [1]}}]})
        rival = self.members[329, 0]["evs"]
        self.assertEqual(rival["2"], [6, 252, 0, 252, 0, 0])
        self.assertEqual(rival["3"], [6, 252, 0, 252, 0, 0])
        self.assertEqual(rival["0"], [0] * 6)
        self.assertEqual(self.members[12, 0]["evs"]["2"], [252, 252, 0, 0, 0, 0])
        self.assertEqual(self.members[718, 0]["evs"]["3"], [252] * 6)
        self.assertEqual(self.members[718, 2]["evs"]["3"], {"alternatives": [
            {"evs": [252, 0, 0, 6, 252, 0], "when": {"0x82C": [0]}},
            {"evs": [252] * 6, "when": {"0x82C": [1]}}]})
        self.assertEqual(self.members[497, 0]["evs"]["2"], [252, 0, 0, 0, 4, 252])
        self.assertEqual(self.members[712, 3]["evs"]["3"], [252, 252, 0, 6, 0, 0])
        self.assertTrue(all(value == [0] * 6 or value is None for row in self.doc["members"]
                            for key, value in row["evs"].items() if key == "1"))

    def test_ev_audit_counts_members_per_difficulty(self):
        self.assertEqual(self.doc["audit"]["evs"], {"members_with_evs": [760, 0, 998, 756],
                                                    "conditional_members": [0, 0, 120, 1444]})
        for member in self.doc["members"]:
            if member["trainer"] in (46, 47, 48):
                value = member["evs"]["3"]
                if member["slot"] == 0:
                    self.assertEqual(value, [6, 252, 0, 252, 0, 0])
                else:
                    self.assertTrue(all("place" not in row["when"] for row in value["alternatives"]))

    def test_resolved_maps_remove_only_unproven_place_alternatives(self):
        resolved = set(range(59, 69)) | {205}
        for member in self.doc["members"]:
            if member["trainer"] in resolved:
                for value in member["evs"].values():
                    if isinstance(value, dict):
                        self.assertTrue(all("place" not in row["when"] for row in value["alternatives"]))
        self.assertEqual(self.members[61, 0]["evs"]["3"], [252] * 6)
        self.assertEqual(self.members[205, 0]["evs"]["2"], [6, 252, 0, 0, 0, 252])
        self.assertTrue(any("place" in row["when"]
                            for row in self.members[56, 0]["evs"]["3"]["alternatives"]))
        self.assertTrue(any("place" in row["when"]
                            for row in self.members[19, 0]["evs"]["2"]["alternatives"]))
