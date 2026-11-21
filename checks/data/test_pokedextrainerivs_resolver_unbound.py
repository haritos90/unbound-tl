from test_roots import TOOLKIT_ROOT
"""Pokedextrainerivs resolver unbound checks and fixtures."""

import sys
from pathlib import Path
import copy
import unittest

sys.path.insert(0, str(TOOLKIT_ROOT / "src"))

from gen3tl.data import pokedextrainerivs as iv
from gen3tl.profile.profile import Profile

from pokedextrainerivs_support import member, trainer, uniform


class ResolverTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.block = Profile.by_name("unbound-2.1.1.1")["pokedex"]["trainers"]["ivs"]
        class_iv = [5] * 107
        class_iv[81] = class_iv[89] = 25
        spreads = [[0] * 10 for _ in range(142)]
        for index in (7, 11, 60, 80, 91, 100, 116, 129):
            spreads[index][1] = 31
        learnsets = {82: [
            {"method": 0, "move": 49, "level": 1, "index": 0},
            {"method": 0, "move": 368, "level": 2, "index": 1},
            {"method": 0, "move": 319, "level": 3, "index": 2},
            {"method": 0, "move": 449, "level": 4, "index": 3},
            {"method": 0, "move": 113, "level": 56, "index": 4},
            {"method": 0, "move": 510, "level": 57, "index": 5},
        ]}
        cls.resolver = iv.Resolver(cls.block, class_iv, spreads, learnsets)

    def resolve(self, trainer_row, member_row, difficulty, side=1, **kwargs):
        return self.resolver.resolve(trainer_row, member_row, difficulty=difficulty, side=side, **kwargs)

    def test_all_36_final_masks_replace_earlier_vectors(self):
        rules = self.block["stages"][4]["rules"]
        self.assertEqual(len(rules), 36)
        for rule in rules:
            species = 999 if rule["species"] == "any" else rule["species"][0]
            for difficulty in rule["difficulties"]:
                with self.subTest(mask=rule["id"], difficulty=difficulty):
                    result = self.resolve(trainer(rule["trainer"]), member(species, spread=60, moves=[510, 632]), difficulty)
                    self.assertEqual(result, {"status": "resolved", "ivs": iv.unpack(rule["packed"])})

    def test_class_81_selection_excludes_difficult_zero(self):
        row = member(220, spread=121, moves=[])
        self.assertEqual(self.resolve(trainer(329, 81), row, 0)["ivs"], uniform(25))
        self.assertEqual(self.resolve(trainer(329, 81), row, 1)["ivs"], uniform(25))
        self.assertEqual(self.resolve(trainer(329, 81), row, 2)["ivs"], uniform(31))
        self.assertEqual(self.resolve(trainer(329, 81), row, 3)["ivs"], uniform(31))

    def test_class_89_selection_is_expert_only(self):
        row = member(246, spread=121, moves=[])
        for difficulty, expected in enumerate((25, 25, 31, 31)):
            with self.subTest(difficulty=difficulty):
                self.assertEqual(self.resolve(trainer(500, 89), row, difficulty)["ivs"], uniform(expected))

    def test_unlisted_rival_species_defaults_to_spread_zero(self):
        result = self.resolve(trainer(329, 81), member(999, spread=60, moves=[510]), 2)
        self.assertEqual(result["ivs"], uniform(25))

    def test_zero_iv_spreads_preserve_the_base_vector(self):
        for difficulty in (0, 2):
            with self.subTest(difficulty=difficulty):
                self.assertEqual(self.resolve(trainer(), member(spread=121, moves=[]), difficulty)["ivs"], uniform(5))

    def test_vanilla_skips_spread_iv_but_not_speed_override(self):
        row = member(spread=80, moves=[510])
        self.assertEqual(self.resolve(trainer(), row, 1)["ivs"], uniform(5, 0))
        self.assertEqual(self.resolve(trainer(), row, 0)["ivs"], uniform(31, 0))
        self.assertEqual(self.resolve(trainer(), member(spread=0, moves=[510]), 1)["ivs"], uniform(5))

    def test_insane_base_depends_on_construction_side(self):
        self.assertEqual(self.resolve(trainer(), member(moves=[]), 3, side=1)["ivs"], uniform(31))
        self.assertEqual(self.resolve(trainer(), member(moves=[]), 3, side=0)["ivs"], uniform(5))

    def test_class_zero_and_cap_use_declared_base_rules(self):
        values = [0] * 107
        values[81] = 40
        resolver = iv.Resolver(self.block, values, [[0] * 10] * 142, {})
        self.assertEqual(resolver.resolve(trainer(), member(moves=[]), difficulty=0, side=1)["ivs"], uniform(10))
        self.assertEqual(resolver.resolve(trainer(329, 81), member(999, moves=[]), difficulty=0, side=1)["ivs"], uniform(31))

    def test_default_moves_cross_the_56_57_boundary(self):
        level56 = self.resolve(trainer(635), member(82, 56, 60), 0)
        level57 = self.resolve(trainer(635), member(82, 57, 60), 0)
        self.assertEqual(level56["ivs"], uniform(31))
        self.assertEqual(level57["ivs"], uniform(31, 0))
        self.assertEqual(iv.default_moves(self.resolver.learnsets, 82, 56), [368, 319, 449, 113])
        self.assertEqual(iv.default_moves(self.resolver.learnsets, 82, 57), [319, 449, 113, 510])

    def test_default_moves_deduplicate_after_selecting_rom_entries(self):
        rows = [
            {"method": 0, "move": 182, "level": 0},
            {"method": 0, "move": 106, "level": 1},
            {"method": 0, "move": 182, "level": 8},
        ]
        self.assertEqual(iv.default_moves({773: rows}, 773, 42), [182, 106])
        repeated = [{"method": 0, "move": move, "level": index} for index, move in enumerate([1, 2, 3, 4, 4])]
        self.assertEqual(iv.default_moves({1: repeated}, 1, 42), [2, 3, 4])

    def test_move_632_and_corrected_trainer_513_slots(self):
        speed = self.resolve(trainer(513), member(632, spread=100, moves=[632]), 1)
        mask = self.resolve(trainer(513), member(181, spread=99, moves=[]), 2)
        self.assertEqual(speed["ivs"], uniform(5, 0))
        self.assertEqual(mask["ivs"], [31, 30, 31, 31, 30, 31])

    def test_trainer_700_mask_has_final_precedence(self):
        result = self.resolve(trainer(700), member(1076, spread=129, moves=[510, 632]), 0)
        self.assertEqual(result["ivs"], [31, 31, 14, 0, 31, 31])

    def test_invalid_spreads_bypass_final_masks(self):
        self.assertEqual(self.resolve(trainer(700), member(1076, spread=129, moves=[]), 0)["ivs"],
                         [31, 31, 14, 0, 31, 31])
        for spread in (0, 142):
            with self.subTest(spread=spread):
                self.assertEqual(self.resolve(trainer(700), member(1076, spread=spread, moves=[]), 0)["ivs"], uniform(5))

    def test_missing_trainer_identity_is_unresolved(self):
        anonymous = trainer(718)
        del anonymous["id"]
        result = self.resolve(anonymous, member(245, spread=60, moves=[]), 3)
        self.assertEqual(result, {"status": "unresolved", "reasons": ["trainer"]})
        identified = self.resolve(trainer(718), member(245, spread=60, moves=[]), 3)
        self.assertEqual(identified["ivs"], [31, 31, 31, 31, 30, 31])

    def test_runtime_inputs_are_mandatory(self):
        result = self.resolve(trainer(), member(), 0, listed=False)
        self.assertEqual(result["status"], "unresolved")
        self.assertEqual(result["reasons"], ["construction", "level", "moves", "species"])
        resolved = self.resolve(trainer(), member(), 0, listed=False, construction="trainer-party",
                                species=19, level=31, moves=[158, 458, 242, 162])
        self.assertEqual(resolved["ivs"], uniform(5))

    def test_invalid_context_never_falls_back_to_zero(self):
        self.assertEqual(self.resolve(trainer(), member(moves=[]), 99)["reasons"], ["difficulty"])
        self.assertEqual(self.resolve(trainer(class_id=999), member(moves=[]), 0)["reasons"], ["class"])
        self.assertEqual(self.resolve(trainer(), member(spread=-1, moves=[]), 0)["reasons"], ["spread"])
        self.assertEqual(self.resolve(trainer(), member(spread=142, moves=[510]), 0)["ivs"], uniform(5))

    def test_uncollapsed_progress_stays_conditional(self):
        block = copy.deepcopy(self.block)
        spreads = [[0] * 10 for _ in range(142)]
        spreads[91][1] = 31
        resolver = iv.Resolver(block, [25] * 107, spreads, {})
        result = resolver.resolve(trainer(329, 81), member(526, moves=[]), difficulty=2, side=1)
        self.assertEqual(result["status"], "conditional")
        self.assertEqual(len(result["alternatives"]), 2)
        selected = resolver.resolve(trainer(329, 81), member(526, moves=[]), difficulty=2, side=1,
                                    progress={0x170B: 0})
        self.assertEqual(selected["ivs"], uniform(31))

    def test_rival_flag_gates_preserve_independent_item_writes(self):
        rival = dict(trainer(435, 81), ai_flags=7)
        writes = iv.PartyWrites(self.block, self.resolver)
        for species, item in ((221, 570), (526, 539)):
            mon = member(species, moves=[1, 2, 3, 4])
            changes = writes.changes(rival, mon, species, lambda level: (mon["moves"], 0), range(76, 77), [3])
            rows = [row for row in changes if all(
                {"0x170B": 1, "0x9F3": 0}[flag] in values for flag, values in row["when"].items())]
            self.assertEqual(len(rows), 1)
            self.assertEqual((rows[0]["item"], rows[0]["moves"]), (item, mon["moves"]))

    def test_rival_selector_follows_the_rom_species_cases(self):
        rival = trainer(329, 81)
        self.assertEqual(self.resolver.spread_options(rival, member(220), 220, 2, None), [(91, {})])
        self.assertEqual(self.resolver.spread_options(rival, member(247), 247, 3, None), [(7, {})])
        for species in (496, 497):
            self.assertEqual(self.resolver.spread_options(rival, member(species), species, 2, None), [(92, {})])
        self.assertEqual(self.resolver.spread_options(rival, member(134), 134, 3, None), [(11, {})])
        strong = dict(rival, ai_flags=7)
        self.assertEqual(self.resolver.spread_options(strong, member(134), 134, 2, None), [(11, {})])
        self.assertEqual(self.resolver.spread_options(strong, member(134), 134, 3, None),
                         [(11, {0x170B: 0}), (13, {0x170B: 1})])

    def test_unknown_operations_and_overlapping_masks_are_rejected(self):
        block = copy.deepcopy(self.block)
        block["stages"][0]["operation"] = "unknown"
        with self.assertRaisesRegex(iv.TrainerIvError, "ordered supported operations"):
            iv.Resolver(block, [5] * 107, [[0] * 10] * 142, {})
        with self.assertRaisesRegex(iv.TrainerIvError, "ordered supported operations"):
            iv.validate_rom(block, b"")
        block = copy.deepcopy(self.block)
        duplicate = copy.deepcopy(block["stages"][4]["rules"][7])
        duplicate["id"] = "duplicate-for-overlap-test"
        block["stages"][4]["rules"].append(duplicate)
        resolver = iv.Resolver(block, [5] * 107, [[0] * 10] * 142, {})
        with self.assertRaisesRegex(iv.TrainerIvError, "overlapping packed masks"):
            resolver.resolve(trainer(700), member(1076, spread=60, moves=[]), difficulty=0, side=1)
