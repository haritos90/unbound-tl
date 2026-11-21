"""Teachy TV's two-line lesson window."""

import json
import re
import unittest
from pathlib import Path

from gen3tl.check import qa
from gen3tl.cli.common import _style_measures
from gen3tl.catalog.catalog import load_catalog
from gen3tl.core.charmap import Charmap
from gen3tl.build.font import font_codes
from gen3tl.lang.langpack import LangPack
from gen3tl.check.layout import Measure, check, layout, paragraphs
from gen3tl.catalog.extract import english
from gen3tl.catalog.po import read

from rom_support import needs_rom, rom_path
from project_fixture import ENGLISH, UNBOUND, unbound

IDS = ("s041B8BF", "s041BB40", "s041BE76", "s041C23B", "s041C459", "s041C82A",
       "s041BA41", "s041BD10", "s041C0AF", "s041C384", "s041C7B4", "s041C994")


def profile():
    return unbound()


@needs_rom
class TeachyTvWindowTest(unittest.TestCase):
    def test_exact_table_and_two_visible_lines(self):
        prof = profile()
        rule = next(r for r in prof["layout"]["table_window"] if r["name"] == "teachy-tv-lessons")
        self.assertEqual((rule["base"], rule["stride"], rule["count"], rule["fields"]),
                         (0x479560, 4, 12, [0]))
        self.assertEqual((rule["width"], rule["box"]), (208, "dialogue"))
        self.assertEqual({prof["layout"]["window_lines"][sid] for sid in IDS}, {2})
        self.assertEqual(font_codes(prof)["04"], prof["font_style"]["style"])
        self.assertIn("0x815B1DC", rule["evidence"])
        inv, catalog = {"entries": []}, {}
        for index, sid in enumerate(IDS):
            from gen3tl.catalog.po import PoEntry
            catalog[sid] = (Path("lesson.po"), PoEntry(sid, "One\\nTwo\\lThree\\lFour", ""))
            inv["entries"].append({"id": sid, "offset": int(sid[1:], 16), "kind": "pointer",
                "category": "data-table", "mode": "field", "flags": [], "length": 30,
                "refs": [{"at": 0x479560 + index * 4, "kind": "table"}]})
        limited = {"layout": {"table_window": [rule], "window_lines": {sid: 2 for sid in IDS}}}
        cm, measure = Charmap(), Measure(lambda _: 6, {})
        limits = qa.compute_limits(limited, inv, catalog, measure, cm)
        for sid, lim in limits.items():
            with self.subTest(id=sid):
                self.assertEqual((lim.kind, lim.width, lim.lines), ("dialogue", 208, 2))
                self.assertIn("3 lines in one box without scrolling", check("One\\nTwo\\nThree", lim, measure, cm))
                laid = layout("word " * 24, lim, measure, cm)
                self.assertIn("\\l", laid)
                self.assertEqual(check(laid, lim, measure, cm), [])

    def test_actual_consumers_template_font_and_sources(self):
        prof = profile(); rom = prof.load_rom(rom_path()); cm = Charmap()
        self.assertEqual(rom.read(0x4792F0, 5), bytes([1, 2, 15, 26, 4]))
        self.assertEqual(rom.ptr_at(0x15AEE4), 0x4792F0)
        self.assertEqual(rom.ptr_at(0x15B5B8), 0x479560)
        self.assertEqual(rom.ptr_at(0x15B5F0), 0x479578)
        self.assertEqual(rom.read(0x15B208, 4), bytes.fromhex("00200421"))
        self.assertEqual(rom.read(0xF6CF8, 2), bytes.fromhex("8471"))
        entries = read(UNBOUND / "translation/ru/po/system/table-0479560.po")[1]
        english(entries, ENGLISH)
        rows = {f"s{int(e.references[0], 16):07X}": e for e in entries}   # the reference keeps the offset
        self.assertEqual(set(rows), set(IDS))
        for index, sid in enumerate(IDS):
            offset = rom.ptr_at(0x479560 + index * 4)
            self.assertEqual(f"s{offset:07X}", sid)
            self.assertEqual(cm.decode(rom.data, offset)[0], rows[sid].msgid)

    def test_current_catalog_uses_scrolling_without_wording_changes(self):
        prof = profile(); rom = prof.load_rom(rom_path())
        catalog = load_catalog(UNBOUND / "translation/ru/po", prof)
        inv = json.loads((UNBOUND / "build/inventory.json").read_text())
        pack = LangPack.load("ru", prof["font_style"]["style"])
        measure = _style_measures(prof, rom, "ru")[prof["font_style"]["style"]][0]
        limits = qa.compute_limits(prof, inv, catalog, measure, pack.charmap(), rom=rom)
        scrolls = 0
        for sid in IDS:
            with self.subTest(id=sid):
                text, lim = catalog[sid][1].msgstr, limits[sid]
                laid = layout(text, lim, measure, pack.charmap())
                self.assertEqual((lim.kind, lim.width, lim.lines), ("dialogue", 208, 2))
                self.assertEqual(check(laid, lim, measure, pack.charmap()), [])
                normalize = lambda value: re.sub(r"\\[nlp]|\s", "", value)
                self.assertEqual(normalize(text), normalize(laid))
                self.assertTrue(all(part.count("\\n") <= 1 for part in paragraphs(laid)))
                scrolls += laid.count("\\l")
        self.assertGreater(scrolls, 0)
