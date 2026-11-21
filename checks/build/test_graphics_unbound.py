import tempfile
import unittest
from pathlib import Path

from gen3tl.build.graphics import GraphicsConfig, lz77_decompress, inject_graphics, pointer_problem, verify_graphics, write_sheet
from gen3tl.build.inject import BuildResult, FreeSpace, verify
from gen3tl.check.render import write_indexed_png

from rom_support import rom_path as base_rom_path, needs_rom
from project_fixture import unbound
from graphics_support import appended_sheet, graphics_guard, tiles

@needs_rom
class InventoryGraphicsTest(unittest.TestCase):
    """The profile's graphics on the real ROM round-trip."""

    @classmethod
    def setUpClass(cls):
        cls.prof = unbound()
        cls.base = cls.prof.load_rom(base_rom_path())
        cls.cfg = GraphicsConfig.from_profile(cls.prof)

    def test_every_graphic_round_trips(self):
        for gid, g in self.cfg.inventory.items():
            if g is None:
                continue
            sheet = self.cfg.sheet(self.base, g)
            self.assertEqual(sheet.encode(sheet.pixels), sheet.data, gid)

    def test_unedited_build_is_byte_identical(self):
        with tempfile.TemporaryDirectory() as tmp:
            edits = []
            for gid in ("G09", "G21"):
                png, _ = write_sheet(self.cfg.sheet(self.base, self.cfg.graphic(gid)), tmp)
                edits.append({"id": gid, "png": str(png), "areas": [[0, 0, 8, 8]]})
            # profile tilemaps name tiles only its edited sheets have
            cfg = GraphicsConfig(dict(self.prof["graphics"], edit=edits, tilemap=[]), self.cfg.root)
            rom = self.base.copy()
            res = inject_graphics(rom, self.base, cfg, FreeSpace.scan(bytes(self.base.data)))
            self.assertEqual((res.failures, [p.mode for p in res.placements]), ([], ["same", "same"]))
            self.assertEqual(rom.data, self.base.data)

    def test_g16_appended_tile_on_the_card_back(self):
        # G16 grows to 210 tiles.
        # the card tilemap places tile 209 at row 0.
        g = self.cfg.graphic("G16")
        sheet = self.cfg.sheet(self.base, g)
        self.assertEqual((g.tiles, sheet.width_tiles, sheet.height), (209, 16, 112))
        px = appended_sheet(sheet, 1, tweak=False)
        for r in range(8):
            px[104 + r][8:16] = sheet.pixels[r][64:72]
        tmap_at, tmap_ptr = 0x1FDB2AC, 0x1ED8AB8
        self.assertEqual(pointer_problem(self.base, tmap_at, [tmap_ptr], "the profile's"), "")
        base_map = lz77_decompress(self.base.data, tmap_at)[0]
        self.assertEqual(len(base_map), 1280)
        with tempfile.TemporaryDirectory() as tmp:
            write_indexed_png(Path(tmp) / "G16.png", px, sheet.palette, 4)
            section = dict(self.prof["graphics"],
                           edit=[{"id": "G16", "png": str(Path(tmp) / "G16.png"), "areas": [], "tiles": 210,
                                  "evidence": "test"}],
                           tilemap=[{"name": "card back", "graphic": "G16", "offset": tmap_at, "size": 1280,
                                     "pointers": [tmap_ptr], "cells": [{"row": 0, "column": 8, "tile": 209}]}])
            cfg = GraphicsConfig(section, self.cfg.root)
            rom = self.base.copy()
            res = inject_graphics(rom, self.base, cfg, FreeSpace.scan(bytes(self.base.data)))
        self.assertEqual(res.failures, [])
        p, t = res.placements[0], res.tilemaps[0]
        self.assertEqual((p.base_tiles, p.tiles), (209, 210))
        tiles = lz77_decompress(rom.data, p.new)[0]
        self.assertEqual(tiles, sheet.data + sheet.data[8 * 32:9 * 32])
        tmap = lz77_decompress(rom.data, t.new)[0]
        self.assertEqual(len(tmap), 1280)
        self.assertEqual([i for i in range(0, 1280, 2) if tmap[i:i + 2] != base_map[i:i + 2]], [16])
        self.assertEqual(int.from_bytes(tmap[16:18], "little"), 209 | (int.from_bytes(base_map[16:18], "little") & ~0x3FF))
        self.assertEqual(t.changes, [(0, 8, 0x0008, 0x00D1)])
        self.assertEqual(verify_graphics(rom, res), [])
        self.assertEqual(verify(rom, self.base, BuildResult(), {}, set(), graphics_guard(res)), [])
