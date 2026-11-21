import unittest
import base64
import struct

from gen3tl.web.editorgfx import graphics_data, Pictures
from gen3tl.build.graphics import inventory_rows, Cell, lz77_decompress

from rom_support import rom_path as base_rom_path, needs_rom
from project_fixture import UNBOUND, unbound

class RegisteredPreviewsTest(unittest.TestCase):
    def test_every_inventory_crop_has_rom_free_layout(self):
        profile = unbound()
        section = profile["graphics"]
        rows = inventory_rows(UNBOUND / section["inventory"])
        want = {r["id"] for r in rows if f"/crops/{r['id']}.png" in r["image"]}
        data = graphics_data(section, UNBOUND, profile.release_path)
        self.assertEqual(set(data["previews"]), want | {"G53", "G54", "G55", "G56", "G59", "G60"})
        allowed = {"label", "width", "height", "cells", "map", "rects", "palette", "background",
                   "palettes", "transparent"}
        for gid, views in data["previews"].items():
            for view in views:
                self.assertLessEqual(set(view), allowed, gid)
                self.assertTrue({"cells", "map", "rects"} & set(view), gid)
                self.assertNotIn("pixels", view)
                self.assertNotIn("png", view)
                if "map" in view:
                    self.assertTrue(view["map"]["full"], gid)
                    self.assertNotIn("origin", view["map"], gid)
                for cell in view.get("cells", []):
                    x, y = cell[:2]
                    self.assertGreaterEqual(min(x, y), 0, gid)
                    self.assertLessEqual(x + 8, view["width"], gid)
                    self.assertLessEqual(y + 8, view["height"], gid)
        self.assertTrue(all("image" not in r for r in data["inventory"]))


    @needs_rom
    def test_all_compositions_from_real_rom(self):
        rom_path = base_rom_path()
        profile = unbound()
        data = graphics_data(profile["graphics"], UNBOUND, profile.release_path)
        pictures = Pictures(data, profile.load_rom(rom_path).data)
        for gid, dimensions in {"G01": (256, 160), "G06": (256, 160),
                                "G07": (256, 160), "G15": (256, 160),
                                "G16": (256, 160), "G24": (256, 160),
                                "G30": (256, 256), "G31": (256, 160),
                                "G32": (256, 160), "G40": (256, 512),
                                "G52": (256, 256)}.items():
            view = pictures.preview(gid)[0]
            self.assertEqual((view["width"], view["height"]), dimensions, gid)
        for gid in data["previews"]:
            original = pictures.preview(gid)
            for view in original:
                self.assertEqual(len(base64.b64decode(view["pixels"])), view["width"] * view["height"], gid)
            if gid in data["edits"]:
                translated = pictures.preview(gid, edited=True)
                self.assertNotEqual([v["pixels"] for v in original], [v["pixels"] for v in translated], gid)


    @needs_rom
    def test_compositions_include_every_changed_source_pixel(self):
        rom_path = base_rom_path()
        profile = unbound()
        data = graphics_data(profile["graphics"], UNBOUND, profile.release_path)
        pictures = Pictures(data, profile.load_rom(rom_path).data)
        rows = {}   # shared edits show in every covered row
        for gid, edit in data["edits"].items():
            rows.setdefault(edit.get("shared", gid), []).append(gid)
        for gid in data["previews"].keys() & rows.keys():
            sheet = pictures.sheet(gid)
            covered, tiles = set(), set()
            for view in (view for row in rows[gid] for view in data["previews"].get(row, [])):
                tiles.update(c[2] for c in view.get("cells", []))
                if "map" in view:
                    m = view["map"]
                    raw = lz77_decompress(pictures.rom.data, m["offset"])[0]
                    entries = list(struct.unpack(f"<{len(raw) // 2}H", raw))
                    for edit in data["tilemap_edits"]:
                        if edit["offset"] == m["offset"]:
                            for c in edit["cells"]:
                                i = c["row"] * m["width"] + c["column"]
                                entries[i] = Cell(**c).apply(entries[i])
                    tiles.update(e & 1023 for e in entries)
                for x, y, w, h, _, _ in view.get("rects", []):
                    covered.update((x + dx, y + dy) for dx in range(w) for dy in range(h))
            for tile in tiles:
                x, y = tile % sheet.width_tiles * 8, tile // sheet.width_tiles * 8
                covered.update((x + dx, y + dy) for dx in range(8) for dy in range(8))
            edited = pictures.edited(gid)
            missing = []
            for i, value in enumerate(base64.b64decode(edited["pixels"])):
                x, y = i % sheet.width, i // sheet.width
                tile = y // 8 * sheet.width_tiles + x // 8
                if tile >= edited["tiles"]:
                    continue
                original = sheet.pixels[y][x] if tile < sheet.graphic.tiles else 0
                if value != original and (x, y) not in covered:
                    missing.append((x, y))
            self.assertEqual(missing, [], gid)
