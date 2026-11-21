from pathlib import Path
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

from gen3tl.build.graphics import graphics_document, inventory_of
from gen3tl.cli import main as cli
from gen3tl.discover import graphics as gfx
from gen3tl.profile.profile import Profile

from rom_support import needs_rom, rom_path
import graphics_discovery_support
from project_fixture import UNBOUND
from graphics_discovery_support import candidate

class FlaggingTest(graphics_discovery_support.FlaggingTest, unittest.TestCase):
    def test_public_cli_rederives_and_rejects_wrong_rom(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "graphics.toml"
            before = self.document()
            path.write_text(before, encoding="utf-8")
            rom = self.proved_raw_rom()
            doc = gfx.write(gfx.scan(rom), rom, root / "discovery", render=False)
            index = root / "discovery/index.json"
            argv = ["discover", "flag", "--graphics", str(path), "--index", str(index),
                    "--id", "g0002000", "--category", "translate", "--reason", "text"]
            profile = Profile.by_name("unbound-2.1.1.1")
            with patch.object(Profile, "by_name", return_value=profile), \
                    patch.object(Profile, "load_rom", return_value=rom), redirect_stdout(io.StringIO()):
                self.assertEqual(cli.main(argv), 0)
            self.assertIn('id = "g0002000"', path.read_text(encoding="utf-8"))

            path.write_text(before, encoding="utf-8")
            doc["rom_sha1"] = "0" * 40
            index.write_text(json.dumps(doc), encoding="utf-8")
            with patch.object(Profile, "by_name", return_value=profile), \
                    patch.object(Profile, "load_rom", return_value=rom), \
                    redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(cli.main(argv), 1)
            self.assertEqual(path.read_text(encoding="utf-8"), before)
            with self.assertRaisesRegex(ValueError, "original ROM"):
                gfx.write_flags(path, [{"id": "g0002000", "category": "translate", "reason": "text"}], doc)
            self.assertEqual(path.read_text(encoding="utf-8"), before)

            existing = ["discover", "flag", "--graphics", str(path), "--id", "G01",
                        "--category", "optional", "--reason", "existing row"]
            with patch.object(Profile, "by_name", return_value=profile), redirect_stdout(io.StringIO()):
                self.assertEqual(cli.main(existing), 0)
            self.assertIn('category = "optional"', path.read_text(encoding="utf-8"))

class UnboundFlaggingTest(unittest.TestCase):
    def test_long_multiple_flags_are_transactional_and_preserve_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "graphics.toml"
            before = (UNBOUND / "source/graphics.toml").read_bytes()
            path.write_bytes(before)
            original = graphics_document(path)
            long_reason = "x" * 1000
            updated = gfx.write_flags(path, [
                {"id": "G01", "category": "optional", "reason": long_reason},
                {"id": "G02", "category": "translate", "reason": "second row"},
            ])
            self.assertEqual(updated, ["G01", "G02"])
            changed = graphics_document(path)
            before_rows = {row["id"]: row for row in original["graphic"]}
            after_rows = {row["id"]: row for row in changed["graphic"]}
            self.assertEqual(original["views"], changed["views"])
            self.assertEqual(set(before_rows), set(after_rows))
            for gid, row in before_rows.items():
                if gid not in ("G01", "G02"):
                    self.assertEqual(after_rows[gid], row)
                else:
                    self.assertEqual({k: v for k, v in after_rows[gid].items() if k not in ("category", "reason")},
                                     {k: v for k, v in row.items() if k not in ("category", "reason")})
            self.assertEqual(after_rows["G01"]["reason"], long_reason)
            self.assertEqual(after_rows["G02"]["category"], "translate")
            self.assertEqual(inventory_of(changed["graphic"])["G02"].category, "translate")

            path.write_bytes(before)
            with self.assertRaisesRegex(ValueError, "category"):
                gfx.write_flags(path, [
                    {"id": "G01", "category": "optional", "reason": long_reason},
                    {"id": "G02", "category": "drop", "reason": "invalid"},
                ])
            self.assertEqual(path.read_bytes(), before)


@needs_rom
class UnboundRecallTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        prof = Profile.by_name("unbound-2.1.1.1")
        cls.result = gfx.scan(prof.load_rom(rom_path()))

    def test_every_catalogued_graphic_is_recalled_with_rom_evidence(self):
        rows = graphics_document(UNBOUND / "source/graphics.toml")["graphic"]
        result = self.result
        rec = gfx.recall(result, rows)
        raw_rows = [r for r in rows if r.get("rom_offset") and not r.get("compressed", "").startswith("yes")]
        self.assertEqual(len(rec["matched"]), len(rows))
        self.assertEqual(len(rec["raw"]), len(raw_rows))
        self.assertEqual(rec["missing"], [])
        self.assertTrue(rec["complete"])
        self.assertTrue(all(m["size_matches"] and m["block_matches"] and m["compression_matches"]
                            for m in rec["matched"]))
        matched = {m["id"]: m for m in rec["matched"]}
        self.assertEqual(matched["G13"]["size_evidence"]["method"], "bounded-tile-duplicate")
        self.assertEqual(matched["G13"]["decoded_size"], 8192)
        self.assertEqual(matched["G13"]["references"], [])
        self.assertEqual(len(matched["G56"]["references"]), 2)
        g13 = next(c for c in result["candidates"] if c.id == matched["G13"]["candidate"])
        self.assertEqual(g13.palettes, [])
        g07_sheet = next(c for c in result["candidates"] if c.offset == 0x0B1BBE0)
        self.assertIsNone(g07_sheet.palette_for(4))
        self.assertFalse(any(p.get("tier") in gfx.ROM_EVIDENCE_TIERS for p in g07_sheet.palettes))
        self.assertTrue(any(p["spec"] == "lz:0x0B1BDC0" and p.get("tier") == "candidate"
                            and p["evidence"].get("palette", {}).get("method") == "staging-dma-candidate"
                            for p in g07_sheet.palettes))
        record = {**g07_sheet.to_dict(), "palette": "", "palette_bpp": None, "palette_source": "candidate"}
        with self.assertRaisesRegex(ValueError, "ROM-evidenced palette"):
            gfx._candidate_row(record, "keep", "candidate-only palette")
        g01_map = next(c for c in result["candidates"] if c.offset == 0x1FC145C)
        self.assertTrue(any(m["sheet_offset"] == 0x1FC08A0 and "raw:0x1FC16E0" in m["palettes"].values()
                            and m.get("tier") == "candidate" for m in g01_map.tilemaps))
        g07_map = next(c for c in result["candidates"] if c.offset == 0x0B1BCE8)
        self.assertTrue(any(m["sheet_offset"] == 0x0B1BBE0 and "lz:0x0B1BDC0" in m["palettes"].values()
                            and m.get("tier") == "candidate" for m in g07_map.tilemaps))
        self.assertFalse(any(m.get("tier") in gfx.ROM_EVIDENCE_TIERS for m in g07_map.tilemaps))
        g52 = next(c for c in result["candidates"] if c.offset == 0x1FDC378)
        self.assertFalse(any(m.get("tier") in gfx.ROM_EVIDENCE_TIERS for m in g52.tilemaps))

    def test_open_counterexamples_are_composed_with_trust_boundaries(self):
        result = self.result
        by_offset = {c.offset: c for c in result["candidates"]}
        expected = (("card front", 0x1FDA820), ("stat scanner", 0x1FD1E94),
                    ("summary move detail", 0xE9BA30), ("the end", 0x410B94))
        for name, map_offset in expected:
            candidate = by_offset[map_offset]
            self.assertFalse(any(m.get("tier") in gfx.ROM_EVIDENCE_TIERS for m in candidate.tilemaps), name)
        card_back = by_offset[0x1FDB2AC]
        self.assertFalse(any(m.get("tier") in gfx.ROM_EVIDENCE_TIERS for m in card_back.tilemaps))
        scanner = by_offset[0x1FD1E94]
        geometries = {(m["width"], m["height"]) for m in scanner.tilemaps}
        self.assertLessEqual(geometries, {(64, 32), (32, 64)})
        self.assertTrue(all(m["evidence"]["geometry_verified"] is False for m in scanner.tilemaps))
        self.assertTrue(all(m.get("tier") == "candidate" for m in scanner.tilemaps))
        g02 = by_offset[0x0EF3588]
        self.assertIsNone(g02.palette_for(4))
        self.assertFalse(any(p.get("tier") in gfx.ROM_EVIDENCE_TIERS for p in g02.palettes))
        self.assertFalse(any(p["target"] == 0x0EF3808 and p.get("tier") in gfx.ROM_EVIDENCE_TIERS
                             for p in result["palettes"]))
        staged = [p for p in result["palettes"]
                  if p["evidence"].get("destination_kind", "").startswith("staging-dma")]
        self.assertTrue(staged)
        self.assertTrue(all(p.get("tier") == "candidate"
                            and p["evidence"].get("method") == "staging-dma-candidate" for p in staged))
        self.assertTrue(any(p["target"] == 0x0EF3808 and p.get("tier") == "candidate" for p in staged))
        self.assertFalse(any(p.get("tier") in gfx.ROM_EVIDENCE_TIERS for p in staged))
        # Runtime table indices leave the exact entry unresolved.
        descriptor_map = by_offset[0x0EA52B8]
        self.assertIsNone(descriptor_map.palette_for(4))
        self.assertTrue(any(p["target"] == 0x0EA463C and p.get("tier") == "candidate"
                            and p["evidence"].get("verified") is None
                            for p in result["palettes"]))
