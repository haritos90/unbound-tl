import copy
import hashlib
import unittest

from gen3tl.data import pokedexdata as pd, pokedextrainerabilities, pokedextrainerivs as iv
from gen3tl.profile.profile import Profile

from rom_support import needs_rom, rom_path
from pokedextrainerivs_support import DATASET, member, trainer, uniform

@needs_rom
class RomVectorTest(unittest.TestCase):
    """Retained synthetic original-ROM party-builder vectors."""
    @classmethod
    def setUpClass(cls):
        cls.profile = Profile.by_name("unbound-2.1.1.1")
        cls.block = cls.profile["pokedex"]
        cls.data = cls.profile.load_rom(rom_path()).data
        cls.dataset = pd.read(DATASET / "pokedex.json")
        class_iv, spreads = iv.read_tables(cls.block["trainers"]["ivs"], cls.data)
        cls.learnsets = {record["slot"]: record["learnset"] for record in cls.dataset["species"]}
        cls.resolver = iv.Resolver(cls.block["trainers"]["ivs"], class_iv, spreads, cls.learnsets)
        cls.trainers = {row["id"]: row for row in cls.dataset["trainers"]}

    def resolve(self, trainer_id, slot, difficulty, side=1, **kwargs):
        trainer = self.trainers[trainer_id]
        member = next(row for row in trainer["party"] if row["index"] == slot)
        return self.resolver.resolve(trainer, member, difficulty=difficulty, side=side, **kwargs)

    def test_exact_rom_hashes_and_write_audit_pass(self):
        iv.validate_rom(self.block["trainers"]["ivs"], self.data)
        damaged = bytearray(self.data)
        damaged[self.block["trainers"]["ivs"]["tables"][1]["offset"]] ^= 1
        with self.assertRaisesRegex(iv.TrainerIvError, "unsupported ROM SHA-256"):
            iv.validate_rom(self.block["trainers"]["ivs"], bytes(damaged))
        damaged_block = copy.deepcopy(self.block["trainers"]["ivs"])
        damaged_block["rom_sha256"] = hashlib.sha256(damaged).hexdigest()
        with self.assertRaisesRegex(iv.TrainerIvError, "table hash mismatch"):
            iv.validate_rom(damaged_block, bytes(damaged))

    def test_changed_species_condition_proof_fails_generation(self):
        block = copy.deepcopy(self.block["trainers"]["ivs"])
        block["species_conditions"][0]["rom"][0]["sha256"] = "0" * 64
        with self.assertRaisesRegex(iv.TrainerIvError, "species condition hash mismatch"):
            iv.validate_rom(block, self.data)

    def species_inputs(self):
        return self.dataset["items"], {record["slot"]: record.get("abilities") for record in self.dataset["species"]}

    def test_changed_species_rule_proof_fails_generation(self):
        block = copy.deepcopy(self.block["trainers"]["ivs"])
        block["species_rules"][0]["rom"][0]["sha256"] = "0" * 64
        with self.assertRaisesRegex(iv.TrainerIvError, "species rule hash mismatch"):
            iv.validate_rom(block, self.data)

    def test_public_regeneration_reproduces_the_companion(self):
        generated = iv.build(self.block["trainers"]["ivs"], self.data, self.dataset["trainers"],
                             self.learnsets, self.dataset["profile"], self.dataset["rom"],
                             self.dataset["profile_block"], self.block["trainers"]["evs"],
                             iv.absent_members(self.block["trainers"]), *self.species_inputs(),
                             self.dataset["trainer_encounters"])
        pokedextrainerabilities.annotate_changes(self.block["trainers"], self.data, self.dataset["trainers"],
                                                 self.block["species"], generated)
        self.assertEqual(generated, self.dataset["trainer_ivs"])

    def test_species_rules_require_item_effects(self):
        with self.assertRaisesRegex(iv.TrainerIvError, "item hold effects unavailable"):
            iv.build(self.block["trainers"]["ivs"], self.data, self.dataset["trainers"], self.learnsets,
                     self.dataset["profile"], self.dataset["rom"], self.dataset["profile_block"])

    def test_unknown_species_variant_members_fail_generation(self):
        block = copy.deepcopy(self.block["trainers"]["ivs"])
        block["species_variants"].append({**block["species_variants"][0], "trainer": 999})
        with self.assertRaisesRegex(iv.TrainerIvError, "species variants without listed members"):
            iv.build(block, self.data, self.dataset["trainers"], self.learnsets,
                     self.dataset["profile"], self.dataset["rom"], self.dataset["profile_block"],
                     items=self.species_inputs()[0], abilities=self.species_inputs()[1],
                     encounters=self.dataset["trainer_encounters"])

    def test_fixed_minior_core_follows_the_native_personality(self):
        block = self.block["trainers"]["ivs"]
        class_iv, spreads = iv.read_tables(block, self.data)
        resolver = iv.Resolver(block, class_iv, spreads, self.learnsets)
        rules = iv.SpeciesRules(block, self.data, resolver, *self.species_inputs(), set(),
                                self.dataset["trainer_encounters"])
        fixed = next(rule for rule in block["species_rules"] if rule["id"] == "minior-core-fixed")
        party = [mon for mon in self.trainers[725]["party"] if mon["species"]]
        self.assertEqual(rules._personality(fixed, self.trainers[725], party, 2), 0x1BEE78)

    def scaled_rules(self, block=None, encounters=None):
        block = block or self.block["trainers"]["ivs"]
        class_iv, spreads = iv.read_tables(block, self.data)
        resolver = iv.Resolver(block, class_iv, spreads, self.learnsets)
        return iv.SpeciesRules(block, self.data, resolver, *self.species_inputs(), set(),
                               self.dataset["trainer_encounters"] if encounters is None else encounters)

    def test_scaled_evolution_follows_the_rom_routine(self):
        rules = self.scaled_rules()
        rule = next(row for row in rules.rules if row["kind"] == "scaled_evolution")
        # Bulbasaur evolves at 16 and 32.
        # Eevee follows the first passing entry.
        self.assertEqual([rules._evolve(rule, 1, level) for level in (15, 16, 31, 32)], [1, 2, 2, 3])
        self.assertEqual([rules._evolve(rule, 133, level) for level in (44, 45, 54, 55)], [133, 136, 136, 196])
        self.assertEqual(rules._chain(rule, 19, 10), [{"species": 20, "level": 20}])
        self.assertEqual(rules.badge_levels[rule["id"]], [0, 15, 20, 25, 30, 38, 47, 51, 58, 70])
        # Native Difficult runs: badge 8 minimum raises and evolves.
        # The average alone does not.
        trainer = self.trainers[1]
        rows = rules._scaled_evolution(rule, trainer, trainer["party"][0])[1]
        self.assertEqual(rows[0], {"species": 20, "rule": rule["id"], "level": 20, "difficulties": [0, 2], "badges": 1})

    def test_scaled_evolution_needs_declared_battle_conditions(self):
        block = copy.deepcopy(self.block["trainers"]["ivs"])
        rule = next(row for row in block["species_rules"] if row["kind"] == "scaled_evolution")
        rule["battles"] = [row for row in rule["battles"] if row["id"] != "rematch"]
        rules = self.scaled_rules(block)
        with self.assertRaisesRegex(iv.TrainerIvError, "trainer 126: scaled-evolution battle condition undeclared"):
            rules.changes(self.trainers[126], self.trainers[126]["party"][0])
        partner = [{"variants": [{"record": 1, "role": "partner", "settings": None}],
                    "commands": [{"script": "0x1", "mode": 13}]}]
        self.assertEqual(self.scaled_rules(encounters=partner).changes(self.trainers[1], self.trainers[1]["party"][0]), [])
        damaged = bytearray(self.data)
        damaged[rule["evolutions"]["pointer"]] ^= 2
        class_iv, spreads = iv.read_tables(block, self.data)
        with self.assertRaisesRegex(iv.TrainerIvError, "evolution table pointer mismatch"):
            iv.SpeciesRules(block, bytes(damaged), iv.Resolver(block, class_iv, spreads, self.learnsets),
                            *self.species_inputs(), set(), [])

    def test_joey_native_opponent_and_partner_vectors(self):
        difficult = self.resolve(1, 0, 0, listed=False, construction="trainer-party",
                                 species=19, level=31, moves=[158, 458, 242, 162])
        insane = self.resolve(1, 0, 3, listed=False, construction="trainer-party",
                              species=19, level=34, moves=[458, 242, 162, 38])
        partner = self.resolve(1, 0, 3, side=0, listed=False, construction="trainer-party",
                               species=19, level=10, moves=[39, 98, 116, 228])
        self.assertEqual(difficult["ivs"], uniform(5))
        self.assertEqual(insane["ivs"], uniform(31))
        self.assertEqual(partner["ivs"], uniform(5))

    def test_jax_and_final_mask_native_vectors(self):
        jax414 = self.resolve(414, 0, 0, listed=False, construction="trainer-party",
                              species=397, level=68, moves=[337, 304, 53, 211])
        suicune = self.resolve(718, 1, 3)
        magnezone = self.resolve(718, 2, 3)
        self.assertEqual(jax414["ivs"], uniform(31))
        self.assertEqual(suicune["ivs"], [31, 31, 31, 31, 30, 31])
        self.assertEqual(magnezone["ivs"], [31, 31, 31, 30, 30, 31])

    def test_trainer_masks_native_vectors_on_every_difficulty(self):
        expected = {(51, 2): [31, 30, 31, 30, 30, 31], (52, 0): [31, 30, 30, 30, 30, 30],
                    (61, 4): [31, 30, 31, 30, 30, 31], (62, 5): [31, 30, 30, 30, 30, 30],
                    (70, 5): [31, 30, 31, 31, 30, 31], (88, 3): [31, 30, 31, 30, 30, 31],
                    (469, 1): [31, 30, 31, 31, 30, 31], (693, 1): [31, 30, 31, 30, 30, 31],
                    (709, 5): [31, 30, 30, 30, 30, 30], (712, 0): [31, 30, 31, 30, 30, 31],
                    (712, 5): [31, 30, 31, 30, 30, 31]}
        for (trainer_id, slot), ivs in expected.items():
            for difficulty in range(4):
                with self.subTest(trainer=trainer_id, slot=slot, difficulty=difficulty):
                    self.assertEqual(self.resolve(trainer_id, slot, difficulty)["ivs"], ivs)

    def test_expert_rival_spread_bypasses_the_trainer_69_mask(self):
        for difficulty, ivs in enumerate(([31, 0, 30, 31, 31, 31], [31, 0, 30, 31, 31, 31],
                                          uniform(31), [31, 0, 30, 31, 31, 31])):
            with self.subTest(difficulty=difficulty):
                self.assertEqual(self.resolve(69, 1, difficulty)["ivs"], ivs)

    def test_native_default_move_boundary_vectors(self):
        level56 = self.resolve(635, 0, 0, level=56)
        level57 = self.resolve(635, 0, 0, level=57)
        self.assertEqual(level56["ivs"], uniform(31))
        self.assertEqual(level57["ivs"], uniform(31, 0))
        self.assertEqual(iv.default_moves(self.learnsets, 82, 56), [368, 319, 449, 113])
        self.assertEqual(iv.default_moves(self.learnsets, 82, 57), [319, 449, 113, 510])

    def ev_resolver(self):
        trainers = self.block["trainers"]
        iv.validate_ev_rom(trainers["evs"], self.data)
        return iv.EvResolver(trainers["evs"], self.resolver, *iv.read_ev_tables(trainers["evs"], self.data),
                             iv.absent_members(trainers))

    def native_evs(self, trainer_id, slot, difficulty, species, level, moves, flags=None, place="14.3", section=None):
        trainer = self.trainers[trainer_id]
        member = dict(next(row for row in trainer["party"] if row["index"] == slot), level=level)
        context = {0x821: 1, 0x16E2: 0, 0x82C: 0, 0x170B: 0, 0x9F3: 0, **(flags or {})}
        return self.ev_resolver().evs(trainer, member, species, difficulty, context, place, section, 1, moves)

    def test_retained_native_ev_vectors(self):
        self.assertEqual(self.native_evs(1, 0, 0, 19, 31, [158, 458, 242, 162]), [0] * 6)
        self.assertEqual(self.native_evs(1, 0, 3, 19, 34, [458, 242, 162, 38]), [0, 252, 0, 252, 0, 0])
        self.assertEqual(self.native_evs(1, 1, 3, 161, 34, [21, 522, 156, 458]), [0, 252, 0, 0, 0, 252])
        self.assertEqual(self.native_evs(1, 0, 3, 19, 34, [458, 242, 162, 38], {0x821: 0}), [0] * 6)
        self.assertEqual(self.native_evs(12, 0, 2, 286, 28, [207, 46, 44, 184]), [252, 252, 0, 0, 0, 0])
        self.assertEqual(self.native_evs(12, 2, 2, 604, 28, [259, 91, 207, 535]), [0, 252, 0, 252, 0, 0])
        self.assertEqual(self.native_evs(12, 0, 0, 286, 28, [207, 46, 44, 184]), [0] * 6)
        self.assertEqual(self.native_evs(329, 0, 2, 220, 31, [385, 54, 381, 203]), [6, 252, 0, 252, 0, 0])
        self.assertEqual(self.native_evs(329, 0, 2, 220, 31, [385, 54, 381, 203], {0x170B: 1}), [6, 252, 0, 252, 0, 0])
        self.assertEqual(self.native_evs(718, 0, 3, 406, 69, [369, 559, 554, 382]), [0, 128, 0, 252, 128, 0])
        self.assertEqual(self.native_evs(659, 0, 1, 18, 49, [356, 97, 730, 395]), [0] * 6)
        self.assertEqual(self.native_evs(700, 4, 0, 1076, 60, [510, 157, 544, 632]), [252, 252, 0, 0, 0, 6])

    def test_retained_variable_opponent_vectors(self):
        self.assertEqual(self.native_evs(59, 0, 3, 23, 34, [256, 255, 425, 385]), [0, 252, 0, 252, 0, 0])
        self.assertEqual(self.native_evs(61, 0, 3, 530, 78, [725, 571, 8, 9]), [252, 252, 0, 6, 0, 0])
        self.assertEqual(self.native_evs(63, 0, 3, 319, 77, [58, 92, 468, 609]), [252, 0, 4, 0, 0, 252])
        self.assertEqual(self.native_evs(205, 0, 0, 606, 49, [89, 242, 617, 433]), [0] * 6)
        self.assertEqual(self.native_evs(205, 0, 2, 606, 49, [89, 242, 617, 182]), [6, 252, 0, 0, 0, 252])

    def test_league_room_and_rebalanced_variant(self):
        moves = [369, 559, 554, 382]
        self.assertEqual(self.native_evs(718, 0, 3, 406, 69, moves, place="1.79", section=137), [252] * 6)
        self.assertEqual(self.native_evs(718, 2, 3, 515, 68, [85, 449, 237, 182], place="1.79", section=137),
                         [252, 0, 0, 6, 252, 0])
        self.assertEqual(self.native_evs(718, 2, 3, 515, 68, [85, 449, 237, 182], {0x82C: 1}, "1.79", 137), [252] * 6)
        resolver = self.ev_resolver()
        self.assertEqual(resolver.top_two(19, False), (3, 1))
        self.assertEqual(resolver.top_two(286, False), (1, 0))

    def test_vanilla_zero_spread_and_rival_native_vectors(self):
        vanilla = self.resolve(659, 1, 1)
        zero = self.resolve(12, 0, 0)
        rival = self.resolve(329, 0, 2)
        difficult_rival = self.resolve(329, 0, 0)
        self.assertEqual(vanilla["ivs"], uniform(10, 0))
        self.assertEqual(zero["ivs"], uniform(25))
        self.assertEqual(rival["ivs"], uniform(31))
        self.assertEqual(difficult_rival["ivs"], uniform(25))

    def test_corrected_slots_and_same_member_precedence_native_vectors(self):
        self.assertEqual(self.resolve(513, 3, 1)["ivs"], uniform(31, 0))
        self.assertEqual(self.resolve(513, 4, 2)["ivs"], [31, 30, 31, 31, 30, 31])
        self.assertEqual(self.resolve(700, 4, 0)["ivs"], [31, 31, 14, 0, 31, 31])
