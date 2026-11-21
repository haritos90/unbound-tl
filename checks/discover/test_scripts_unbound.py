import unittest
from types import SimpleNamespace
from unittest.mock import patch

from gen3tl.core.rom import ROM_BASE, Rom
from gen3tl.discover import foundations, scripts
from gen3tl.discover.maps import CMD_LEN, TEXT_PTR_AT, Walker
from gen3tl.families.fingerprints import find
from gen3tl.families.knowledge import load_script
from gen3tl.profile.profile import Profile

from rom_support import needs_rom, rom_path
from scripts_support import words

@needs_rom
class UnboundScriptTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profile = Profile.by_name("unbound-2.1.1.1")
        path = rom_path()
        cls.rom = cls.profile.load_rom(path)
        cls.family = foundations.families()[0]
        cls.matches = find(cls.rom.data, cls.family.fingerprints)
        cls.result = scripts.discover(cls.rom, cls.family, cls.matches)

    def summary(self, result):
        return [(handler.opcode, handler.status, handler.lengths,
                 [(read.offset, read.width, read.target) for read in handler.reads], handler.reasons)
                for handler in result.handlers]

    def test_real_dispatch_fixed_comparison_and_text_positions(self):
        result = self.result
        self.assertEqual((result.table, result.end), (0x15F9B4, 0x15FD08))
        self.assertEqual((result.initializer, result.dispatcher), (0x69A80, 0x69804))
        self.assertTrue(result.table_verified)
        self.assertTrue(result.readers_verified)
        self.assertEqual(len(result.handlers), 213)
        proved = {
            0x00: 1, 0x01: 1, 0x0F: 6, 0x10: 3, 0x12: 6, 0x14: 3,
            0x1B: 3, 0x1C: 3, 0x1D: 6, 0x1E: 6, 0x1F: 6, 0x20: 9,
            0x24: 5, 0x2C: 1, 0x2D: 1, 0x30: 1, 0x32: 1, 0x66: 1,
            0x72: 1, 0x73: 5, 0x74: 1, 0x8C: 1, 0x8D: 1, 0x8E: 1,
            0x96: 1, 0xAE: 1, 0xC5: 1, 0xCC: 6,
        }
        variable = {0x5C, 0xB6}
        self.assertEqual({handler.opcode: handler.lengths[0] for handler in result.handlers
                          if handler.status == "fixed"}, {op: n for op, n in proved.items() if op not in (29, 32, 204)})
        self.assertEqual({handler.opcode for handler in result.handlers
                          if handler.status == "variable"}, variable)
        unresolved = [handler for handler in result.handlers if handler.status == "unresolved"]
        self.assertLess(len(unresolved), 183)
        self.assertTrue(all(handler.reasons for handler in unresolved))
        known_differences = {44: (5, 1), 116: (5, 1), 129: (4, 1), 138: (4, 1), 148: (3, 1),
                             150: (3, 1), 177: (8, 1), 179: (3, 5), 211: (5, 1)}
        derived = [handler for handler in result.handlers if handler.status in ("fixed", "shape")]
        self.assertGreaterEqual(len(derived), 150)
        differences = {}
        for handler in derived:
            self.assertEqual(len(handler.lengths), 1)
            self.assertFalse(handler.reasons)
            if handler.status == "shape":
                self.assertTrue(handler.assumptions)
                self.assertTrue(handler.assumption_sites)
            expected = CMD_LEN.get(handler.opcode)
            actual = handler.lengths[0]
            if actual != expected:
                differences[handler.opcode] = (expected, actual)
            if handler.opcode in TEXT_PTR_AT:
                candidates = {read.offset + 1 for read in handler.reads if read.width == 4}
                self.assertIn(TEXT_PTR_AT[handler.opcode], candidates)
        self.assertEqual(differences, known_differences)

    def test_variable_handlers_and_compatibility_provenance(self):
        variables = [issue for issue in self.result.issues if issue["status"] == "candidate"]
        unresolved = [issue for issue in self.result.issues if issue["status"] == "unresolved"]
        self.assertEqual([issue["opcode"] for issue in variables], [0x5C, 0xB6])
        self.assertEqual(len(unresolved), sum(h.status == "unresolved" for h in self.result.handlers))
        self.assertTrue(all(issue["reasons"] for issue in unresolved))
        trainer, repeated = variables
        self.assertTrue(any("cfru-trainerbattle" in reason for reason in trainer["reasons"]))
        self.assertTrue(all(self.result.handlers[row["opcode"]].conditions for row in variables))
        self.assertTrue(all(self.result.handlers[row["opcode"]].reads for row in variables))
        self.assertTrue(any("repeated-stream-advance" in reason for reason in repeated["reasons"]))
        knowledge = load_script("firered-cfru")
        self.assertNotIn("trainerbattle_text_offsets", knowledge.discovery["fixed_lengths"])
        self.assertIn("compatibility", knowledge.discovery["defaults"]["provenance"].lower())

    def test_walker_consumes_family_file_not_legacy_arrays(self):
        expected = {int(key): value for key, value in self.family.scripts["fixed_lengths"].items()}
        expected.update({int(key): value for key, value in self.family.scripts["defaults"]["command_lengths"].items()})
        expected_text = dict(TEXT_PTR_AT)
        with patch.dict(CMD_LEN, {}, clear=True), patch.dict(TEXT_PTR_AT, {}, clear=True):
            walker = Walker(self.rom, self.profile)
            self.assertEqual(walker.cmd_len, expected)
            self.assertEqual(walker.text_ptr_at, expected_text)
            self.assertEqual(walker.tb[16], (10, 14, 18, 22, 26, 30))
        replacement = SimpleNamespace(data={"script": {
            "command_lengths": {"0": 1}, "text_ptr_at": {}, "code_ptr_at": {},
            "end_ops": [], "trainerbattle_text_offsets": {}, "trainerbattle_continue_types": []}})
        with patch("gen3tl.discover.maps.load_script", return_value=replacement):
            walker = Walker(Rom(bytes(0x100)), {})
            self.assertEqual(walker.cmd_len, {0: 1})
            self.assertEqual(walker.tb, {})

    def test_relocation_determinism_ambiguity_and_failure(self):
        moved = self.rom.copy()
        old_table, old_end = self.result.table, self.result.end
        new_table, new_init = 0x1F00000, 0x1F01000
        size = old_end - old_table
        moved.write(new_table, self.rom.read(old_table, size))
        moved.write(new_init, self.rom.read(self.result.initializer, 24))
        for literal in foundations.literal_loads(self.rom.data, self.result.initializer,
                                                 self.result.initializer + 24):
            if literal.value == ROM_BASE + old_table:
                moved.put_u32(new_init + literal.pool - self.result.initializer, ROM_BASE + new_table)
            elif literal.value == ROM_BASE + old_end:
                moved.put_u32(new_init + literal.pool - self.result.initializer, ROM_BASE + new_table + size)
        moved.write(old_table, bytes(size))
        moved.write(self.result.initializer, bytes(24))
        relocated = scripts.discover(moved, self.family, self.matches)
        self.assertEqual((relocated.table, relocated.end, relocated.initializer),
                         (new_table, new_table + size, new_init))
        self.assertEqual(self.summary(relocated), self.summary(self.result))
        repeated = scripts.discover(self.rom, self.family, self.matches)
        self.assertEqual(self.summary(repeated), self.summary(self.result))

        ambiguous = self.rom.copy()
        ambiguous.write(new_init, self.rom.read(self.result.initializer, 24))
        result = scripts.discover(ambiguous, self.family, self.matches)
        self.assertIsNone(result.table)
        self.assertFalse(result.table_verified)
        self.assertTrue(any("found 2" in issue["reason"] for issue in result.issues))
        malformed = self.rom.copy()
        malformed.put_u32(old_table, 0)
        result = scripts.discover(malformed, self.family, self.matches)
        self.assertIsNone(result.table)
        self.assertFalse(result.table_verified)
        missing = dict(self.matches, **{"script-halfword": ()})
        result = scripts.discover(self.rom, self.family, missing)
        self.assertEqual(result.handlers, [])
        self.assertTrue(result.table_verified)
        self.assertFalse(result.readers_verified)
        self.assertTrue(any("script-halfword" in issue["id"] for issue in result.issues))
        wrong_value = self.rom.copy()
        reader = self.matches["script-halfword"][0]
        wrong_value.write(reader + 14, words(0x4301))
        result = scripts.discover(wrong_value, self.family, self.matches)
        self.assertTrue(result.table_verified)
        self.assertFalse(result.readers_verified)
        self.assertEqual(result.handlers, [])
        self.assertTrue(any("return proof" in issue["reason"] for issue in result.issues))
