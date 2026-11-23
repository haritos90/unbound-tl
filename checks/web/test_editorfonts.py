import base64
import copy
import json
import re
import shutil
import subprocess
import tempfile
import unittest
import contextlib
import io
from pathlib import Path

from gen3tl.build import spritefont
from gen3tl.check import render
from gen3tl.core.charmap import BASE_CHARS, NAMED_BYTES
from gen3tl.lang.langpack import LangPack, parse_art
from gen3tl.profile.profile import Profile
from gen3tl.web import editorfonts

from rom_support import needs_rom, rom_path
from test_roots import TEST_ROOT, TOOLKIT_ROOT
from project_fixture import rom_evidence, UNBOUND

ROOT = TOOLKIT_ROOT

PROFILE = "unbound-2.1.1.1"

NODE = shutil.which("node")

def light_accent() -> str:
    """The shared accent token of the light theme."""
    css = (TOOLKIT_ROOT / "web" / "site.css").read_text(encoding="utf-8")
    root = re.search(r":root\s*\{([^}]*)\}", css, re.S).group(1)
    return re.search(r"--accent:\s*(#[0-9a-fA-F]{6})\s*;", root).group(1)

class TileBase:
    """A base image whose sprite sheet holds `tiles` at `at`."""

    def __init__(self, at: int, tiles: bytes):
        self.at, self.tiles = at, tiles

    def read(self, offset: int, n: int) -> bytes:
        return self.tiles[offset - self.at:offset - self.at + n] if offset == self.at else bytes(n)

class PackSheetsTest(unittest.TestCase):
    """The game's sheets with the pack of the running translation."""

    @classmethod
    def setUpClass(cls):
        cls.prof = Profile.by_name(PROFILE)
        cls.data = editorfonts.font_sheets(cls.prof, "ru")
        cls.sheets = {s["name"]: s for s in cls.data["sheets"]}

    def test_every_sheet_in_profile_order(self):
        fonts = [f["name"] for f in self.prof["font"]]
        sprites = [f["name"] for f in self.prof["sprite_font"]]
        self.assertEqual([s["name"] for s in self.data["sheets"]], fonts + sprites)
        for entry in self.prof["font"]:
            sheet = self.sheets[entry["name"]]
            self.assertEqual(sheet["kind"], "font")
            self.assertEqual(sheet["rom"], {"glyphs": entry["glyphs"], "widths": entry["widths"]})
            self.assertEqual(sheet["codes"], [f"{c:02X}" for c in entry["codes"]])
            self.assertEqual(sheet["count"], entry["count"])
        self.assertEqual(self.sheets["small"]["format"], "8x16")
        self.assertEqual(self.data["pack"], "assets/lang/ru")

    def test_styles_link_their_art(self):
        for style, entry in self.data["styles"].items():
            self.assertTrue((ROOT / entry["art"]["source"]).is_file(), style)
            self.assertEqual(entry["art"]["path"], f"fonts/{style}.txt")
        self.assertEqual({s: (e["top"], e["rows"]) for s, e in self.data["styles"].items()},
                         {"unbound": (0, 14), "unbound-small": (1, 12), "unbound-outlined": (0, 8)})

    def test_font_glyphs_mark_the_pack(self):
        for name in ("font0", "small"):
            sheet = self.sheets[name]
            top, rows = self.data["styles"][sheet["style"]]["top"], self.data["styles"][sheet["style"]]["rows"]
            pack = LangPack.load("ru", sheet["style"], rows=rows, top=top)
            by_code = {g["code"]: g for g in sheet["glyphs"]}
            self.assertEqual([g["tile"] for g in sheet["glyphs"]], sorted(int(g["code"], 16) for g in sheet["glyphs"]))
            for b, c in BASE_CHARS.items():
                self.assertEqual((by_code[f"{b:02X}"]["char"], by_code[f"{b:02X}"]["source"]), (c, "base"))
                self.assertNotIn("width", by_code[f"{b:02X}"])   # the ROM's width
            for c, b in pack.chars.items():
                g = by_code[f"{b:02X}"]
                self.assertEqual(g["char"], c)
                if pack.sources[c] == "glyph":
                    self.assertEqual((g["source"], g["width"]), ("added", pack.glyphs[c].width))
                else:
                    self.assertEqual((g["source"], g["from"]), ("copied", f"{pack.copies[c]:02X}"))
                    self.assertNotIn("width", g)
            changed = {g["code"]: g for g in sheet["glyphs"] if g["source"] == "changed"}
            self.assertEqual(set(changed), {f"{k:02X}" if k < 0x100 else f"{k:03X}"
                                            for k in pack.glyphs if isinstance(k, int)})
            self.assertEqual(changed["34"]["name"], NAMED_BYTES[0x34])
            self.assertEqual(changed["105"], {"code": "105", "tile": 0x105, "name": "F9 05", "source": "changed",
                                              "width": pack.glyphs[0x105].width})
        self.assertEqual(self.sheets["font0"]["glyphs"], self.sheets["font3"]["glyphs"])   # copies of one style

    def test_sprite_font_is_the_build_plan(self):
        font = spritefont.from_profile(self.prof)[0]
        sheet = self.sheets[font.name]
        pack = LangPack.load("ru", font.style, rows=font.cell_rows, top=0)
        plan = spritefont.plan(font, editorfonts.BlankBase(), pack)
        self.assertEqual(sheet["table"], list(plan.table))
        self.assertEqual((sheet["kind"], sheet["tiles"], sheet["count"], sheet["advance"], sheet["fallback"]),
                         ("sprite", font.tiles, font.tiles + len(plan.added), 4, font.fallback))
        self.assertEqual(sheet["palette"], {"ink": font.ink, "shadow": font.shadow, "background": font.background})
        self.assertEqual(sheet["rom"], {"sheet": font.sheet})
        by_char = {g["char"]: g for g in sheet["glyphs"]}
        for c, tile in plan.added.items():
            self.assertEqual((by_char[c]["source"], by_char[c]["tile"]), ("added", tile))
            back = parse_art(f"glyph {c} width {pack.glyphs[c].width}\n" + "\n".join(sheet["art"][str(tile)]) + "\n",
                             font.cell_rows)
            self.assertEqual(back[c].pixels, pack.glyphs[c].pixels)
        for c, tile in plan.copied.items():
            g = by_char[c]
            self.assertEqual((g["source"], g["tile"]), ("copied", tile))
            self.assertEqual(sheet["table"][int(g["from"], 16)], tile)   # its base letter's tile
        for i, c in enumerate(font.order):
            self.assertEqual((by_char[c]["source"], by_char[c]["tile"]), ("base", i))
        self.assertEqual((by_char[":"]["source"], by_char[":"]["from"], by_char[":"]["tile"]),
                         ("alias", "00", by_char[" "]["tile"]))
        self.assertEqual(sheet["advances"], list(plan.advances))
        self.assertEqual([g["width"] for g in sheet["glyphs"]],
                         [plan.advances[int(g["code"], 16)] for g in sheet["glyphs"]])
        steps = spritefont.base_advances(font)
        self.assertEqual({g["char"]: g["width"] for g in sheet["glyphs"] if g["source"] == "base" and g["width"] != 4},
                         {c: steps[spritefont.BYTE_OF[c]] for c in font.advances})
        self.assertEqual(len(by_char), len(sheet["glyphs"]))
        self.assertEqual(len(sheet["glyphs"]), len(font.order) + len(font.aliases) + len(plan.added) + len(plan.copied))

    def test_no_rom_bytes(self):
        """Offsets and pack art only: no glyph, width or tile of the ROM."""
        text = json.dumps(self.data, ensure_ascii=False)
        self.assertNotIn("pixels", text)
        for sheet in self.data["sheets"]:
            if sheet["kind"] == "sprite":
                self.assertEqual(sorted(int(t) for t in sheet["art"]), list(range(sheet["tiles"], sheet["count"])))

class NeutralPackTest(unittest.TestCase):
    """Any pack and profile: one drawn letter, one copied, a sprite font with an advance."""

    PROF = {
        "font_style": {"style": "main", "cell_height": 14},
        "font": [{"name": "f0", "glyphs": 0x100, "widths": 0x8100, "count": 256, "codes": [1]}],
        "sprite_font": [{"name": "hud", "style": "hud", "cell_rows": 8, "sheet": 0x400, "tiles": 3,
                         "pointers": [0x200], "order": "AB ", "aliases": {":": " "}, "fallback": 0,
                         "ink": 1, "shadow": 12, "background": 0, "advance": 5,
                         "lookup": {"guard": rom_evidence(0x100, bytes(range(12))),
                                    "code": "014b9b5c5b0105e0"},
                         "evidence": "A routine draws one tile per character."}],
    }

    def write_pack(self, root: Path) -> None:
        (root / "xx" / "fonts").mkdir(parents=True)
        (root / "xx" / "charmap.tsv").write_text("char\tbyte\tsource\nQ\t37\tglyph\nW\t87\tcopy:BB\n",
                                                 encoding="utf-8")
        (root / "xx" / "fonts" / "main.txt").write_text("glyph Q width 3\n" + "_#_\n" * 14, encoding="utf-8")
        (root / "xx" / "fonts" / "hud.txt").write_text("glyph Q width 5\n" + "s###s\n" * 8, encoding="utf-8")


SHEET_SCRIPT = """
import fs from "node:fs";
import { SpriteTiles, drawSheet } from "%s";
const [input, out] = process.argv.slice(2);
const { sheet, rom, mark } = JSON.parse(fs.readFileSync(input, "utf8"));
const canvas = { width: 0, height: 0, getContext() {
  const px = this.px = Array.from({ length: this.height }, () => Array(this.width).fill(""));
  return { fillStyle: "", fillRect(x, y, w, h) {
    for (let j = y; j < y + h; j++) for (let i = x; i < x + w; i++) px[j][i] = this.fillStyle;
  } };
} };
const unknown = drawSheet(canvas, new SpriteTiles(sheet, new Uint8Array(Buffer.from(rom, "base64"))), 1, mark);
fs.writeFileSync(out, JSON.stringify({ unknown, px: canvas.px }));
"""

class SheetTest(unittest.TestCase):
    """The tile sheet of a sprite font: the command's image and the Fonts view's."""


    @unittest.skipUnless(NODE, "no node")
    def test_the_view_draws_the_command_image(self):
        prof = Profile.by_name(PROFILE)
        font = spritefont.from_profile(prof)[0]
        tiles = bytes((i * 37 + i // 7) % 256 for i in range(font.tiles * spritefont.TILE))
        pack = LangPack.load("ru", font.style, rows=font.cell_rows, top=0)
        plan = spritefont.plan(font, TileBase(font.sheet, tiles), pack)
        cv = render.sprite_sheet(plan.sheet, font.tiles, font.ink, font.shadow, font.background)
        sheet = next(s for s in editorfonts.font_sheets(prof, "ru")["sheets"] if s["name"] == font.name)
        sheet["rom"]["sheet"] = 0
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "sheet.mjs").write_text(SHEET_SCRIPT % (TOOLKIT_ROOT / "web" / "js" / "fonts.js").as_uri(), encoding="utf-8")
            (tmp / "in.json").write_text(json.dumps({"sheet": sheet, "rom": base64.b64encode(tiles).decode(),
                                                     "mark": light_accent()}), encoding="utf-8")
            run = subprocess.run([NODE, str(tmp / "sheet.mjs"), str(tmp / "in.json"), str(tmp / "out.json")],
                                 capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr[-2000:])
            out = json.loads((tmp / "out.json").read_text(encoding="utf-8"))
        self.assertEqual(out["unknown"], 0)
        self.assertEqual(out["px"], [["#%02x%02x%02x" % c for c in row] for row in cv.px])


    @needs_rom
    def test_command_writes_each_sheet(self):
        from gen3tl.__main__ import main
        prof = Profile.by_name(PROFILE)
        font = spritefont.from_profile(prof)[0]
        rom = prof.load_rom(rom_path())
        plan = spritefont.plan(font, rom, LangPack.load("ru", font.style, rows=font.cell_rows, top=0))
        want = render.sprite_sheet(plan.sheet, font.tiles, font.ink, font.shadow, font.background).scaled(2)
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()) as out:
            code = main(["--project-root", str(UNBOUND), "lang", "sprite-sheet",
                         "--rom", str(rom_path()), "--out", tmp, "--scale", "2"])
            path = Path(tmp) / f"sprite-ru-{font.name}.png"
            self.assertEqual(code, 0)
            self.assertEqual(render.read_png(path), want)
        lines = [line.split(None, 1) for line in out.getvalue().splitlines()]
        self.assertEqual(lines[:5], [["font", font.name], ["style", font.style],
                                     ["tiles", f"{font.tiles + len(plan.added)} tiles"],
                                     ["appended", f"{len(plan.added)} tiles"], ["copies", f"{len(plan.copied)} copies"]])
        self.assertEqual(lines[5][0], "wrote")
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(main(["--project-root", str(UNBOUND), "lang", "sprite-sheet", "--font", "nope"]), 1)
        self.assertIn("nope: no sprite font of the profile", out.getvalue())


EDIT_SCRIPT = """
import fs from "node:fs";
import { Codec } from "%(font)s";
import { EDIT_ZOOM, FontsView, artColors, draftFonts } from "%(fonts)s";
import { GlyphEdits, exportDoc } from "%(store)s";
import { fakeDocument } from "%(fixture)s";
const [input, out] = process.argv.slice(2);
const { index, ops, rom } = JSON.parse(fs.readFileSync(input, "utf8"));
const image = rom ? new Uint8Array(fs.readFileSync(rom)) : null;
const doc = fakeDocument();
doc.addEventListener ??= () => {};
globalThis.getComputedStyle ??= () => ({ getPropertyValue: () => "" });
const create = doc.createElement;
doc.createElement = (tag) => {
  const node = create(tag);
  node.setAttribute = (key, value) => { node[key] = value; };
  node.addEventListener = (type, fn) => { node[`on${type}`] = fn; };
  node.getContext = () => {
    const px = node.px = Array.from({ length: node.height }, () => Array(node.width).fill(""));
    return { fillStyle: "", fillRect(x, y, w, h) {
      for (let j = y; j < Math.min(y + h, node.height); j++) for (let i = x; i < Math.min(x + w, node.width); i++) px[j][i] = this.fillStyle;
    } };
  };
  return node;
};
globalThis.document = doc;
const nodes = new Map();
const $ = (id) => {
  if (!nodes.has(id)) nodes.set(id, Object.assign(doc.createElement("div"), { value: "" }));
  return nodes.get(id);
};
const edits = new GlyphEdits(null, index.language, index.profile);
const view = new FontsView({ index: () => index, rom: () => image, codec: () => new Codec(index.codec, index.charmap),
  dataUrl: (p) => p, setHash() {}, edits: () => edits, changed() {} }, $);
view.wire();
view.reset();
const shown = {};
for (const op of ops) {
  view.open(op.sheet);
  view.select(op.code);
  if (op.width) view.setWidth(op.width);
  view.setInk(op.ink);
  for (const [x, y] of op.paint) if (!view.paintAt(x, y)) throw new Error(`${op.sheet} ${op.code}: (${x}, ${y}) unchanged`);
  // the grid as drawn: one colour per square, back to art characters
  const target = view.target();
  const sprite = view.sheet(op.sheet).kind === "sprite";
  const zoom = EDIT_ZOOM[sprite ? "sprite" : "font"];
  const chars = Object.fromEntries(Object.entries(artColors(sprite)).map(([ch, color]) => [color, ch]));
  const at = (x, y) => chars[$("fo-art").px[y * zoom + zoom / 2][x * zoom + zoom / 2]];
  const rows = [];
  for (let r = 0; r < target.art.cell; r++) {
    let row = "";
    for (let x = 0; x < target.art.widest && at(x, target.art.top + r) !== undefined; x++) row += at(x, target.art.top + r);
    rows.push(row);
  }
  shown[`${target.base.style}:${op.code}`] = rows;
}
fs.writeFileSync(out, JSON.stringify({ doc: exportDoc(index.language, index.profile, [], [], [], edits.changes()), shown,
  sheets: view.sheets.map((s) => view.shown(s.name)), fonts: draftFonts(index, edits.all()).fonts }));
"""

def edit_script() -> str:
    """The edit script with the toolkit modules and the project's page fixture."""
    modules = {name: (TOOLKIT_ROOT / "web" / path).as_uri() for name, path in (
        ("font", "js/font.js"), ("fonts", "js/fonts.js"), ("store", "js/store.js"))}
    return EDIT_SCRIPT % {**modules, "fixture": (TEST_ROOT / "web/fixture.mjs").as_uri()}

def copied_rom(sheets: list[dict], path: Path) -> list[str]:
    """A ROM image with font sheets drawing byte BB as an ink column."""
    from gen3tl.build.font import BACKGROUND, INK, SHADOW, encode_glyph, glyph_size
    px = [[BACKGROUND] * 16 for _ in range(16)]
    for y in range(3, 11):
        px[y][:2] = [INK, SHADOW]
    fonts = [s for s in sheets if s["kind"] == "font"]
    image = bytearray(max(max(s["rom"]["glyphs"] + s["count"] * glyph_size(s["format"]), s["rom"]["widths"] + 256)
                          for s in fonts))
    for s in fonts:
        size = glyph_size(s["format"])
        image[s["rom"]["glyphs"] + 0xBB * size:s["rom"]["glyphs"] + 0xBC * size] = encode_glyph(px, s["format"])
        image[s["rom"]["widths"] + 0xBB] = 6
    path.write_bytes(bytes(image))
    return ["#s____" if 3 <= y < 11 else "______" for y in range(14)]

class GlyphRoundTripTest(unittest.TestCase):
    """A glyph redrawn in the Fonts view, exported and imported."""

    @unittest.skipUnless(NODE, "no node")
    def test_sprite_copy_and_new_slots_round_trip(self):
        from gen3tl.lang.langpack import load_styles
        from gen3tl.web.editordata import codec_data, fonts_data, glyph_art
        prof = copy.deepcopy(NeutralPackTest.PROF)
        prof["font"][0]["count"] = 512
        prof["sprite_font"][0].update(shared=1, advances={},
            routine={"code": "c046c046", "words": ["table", "advance", "tiles", "step"]},
            calls=[{"guard": rom_evidence(0x180, bytes(range(8))), "code": "004b1847", "entry": 2}])
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            root = tmp / "lang"
            NeutralPackTest().write_pack(root)
            charmap_path = root / "xx" / "charmap.tsv"
            charmap_path.write_text(charmap_path.read_text() + "A\tBB\tbase\n")
            packs = load_styles("xx", prof, root)
            fonts = fonts_data({**prof, "sprite_font": []}, packs)
            fonts["sprites"] = {name: m.data() for name, m in editorfonts.sprite_measures(prof, "xx", root).items()}
            index = {"language": "xx", "profile": "fixture", "fonts": fonts,
                     "glyphs": glyph_art(prof, packs), "font_sheets": editorfonts.font_sheets(prof, "xx", root),
                     "codec": codec_data(), "charmap": {"Q": "37", "W": "87"}}
            by_code = {g["code"]: g for g in index["font_sheets"]["sheets"][0]["glyphs"]}
            self.assertEqual([by_code[c]["source"] for c in ("34", "106", "1FF")], ["base"] * 3)
            self.assertTrue(by_code["BB"]["redraw"])
            self.assertNotIn("redraw", by_code["BC"])
            image_path = tmp / "rom.gba"
            copied_rom(index["font_sheets"]["sheets"], image_path)
            image = bytearray(image_path.read_bytes())
            image[0x400] = 0x1C
            image_path.write_bytes(image)
            ops = [{"sheet": "hud", "code": "87", "width": 4, "ink": "#", "paint": [[2, 0]]},
                   {"sheet": "f0", "code": "34", "width": 3, "ink": "#", "paint": [[1, 2]]},
                   {"sheet": "f0", "code": "106", "width": 3, "ink": "#", "paint": [[1, 3]]},
                   {"sheet": "f0", "code": "BB", "ink": "#", "paint": [[2, 4]]}]
            (tmp / "edit.mjs").write_text(edit_script(), encoding="utf-8")
            (tmp / "in.json").write_text(json.dumps({"index": index, "ops": ops, "rom": str(image_path)}), encoding="utf-8")
            run = subprocess.run([NODE, str(tmp / "edit.mjs"), str(tmp / "in.json"), str(tmp / "out.json")],
                                 capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr[-2000:])
            out = json.loads((tmp / "out.json").read_text(encoding="utf-8"))
            records = out["doc"]["glyphs"]
            self.assertEqual([(r.get("char", r.get("slot")), r["base"]) for r in records],
                             [("W", {"source": "copy:BB"}), ("106", {"source": "rom"}),
                              ("034", {"source": "rom"}), ("0BB", {"source": "rom"})])
            charmap = (root / "xx" / "charmap.tsv").read_bytes()
            edits = editorfonts.glyph_edits(records, prof, "xx", root)
            self.assertEqual(sorted(p.name for p in editorfonts.apply_glyph_edits(edits)), ["hud.txt", "main.txt"])
            self.assertEqual((root / "xx" / "charmap.tsv").read_bytes(), charmap)
            main = LangPack.load("xx", "main", root)
            hud = LangPack.load("xx", "hud", root, rows=8)
            for pack, key, code, rows in [(main, 0x34, "34", 14), (main, 0x106, "106", 14),
                                         (main, 0xBB, "BB", 14), (hud, "W", "87", 8)]:
                self.assertEqual(editorfonts.art_rows(pack.glyphs[key], 0, rows), out["shown"][f"{pack.style}:{code}"])
            self.assertEqual(main.sources["A"], "base")
            self.assertNotIn(0xBB, hud.glyphs)
            rebuilt_main = editorfonts.font_sheets(prof, "xx", root)["sheets"][0]
            letter = next(g for g in rebuilt_main["glyphs"] if g["code"] == "BB")
            self.assertEqual((letter["source"], letter["char"], letter["width"]), ("changed", "A", 6))
            self.assertEqual(main.copy_slots()[0x87], 0xBB)
            rebuilt = editorfonts.font_sheets(prof, "xx", root)["sheets"][1]
            self.assertEqual(rebuilt, out["sheets"][1])
            self.assertEqual((rebuilt["table"][0x87], rebuilt["advances"][0x87]), (4, 3))
            self.assertEqual(out["fonts"]["sprites"]["hud"]["table"], rebuilt["table"])
            self.assertEqual(out["fonts"]["sprites"]["hud"]["steps"], rebuilt["advances"])

    @unittest.skipUnless(NODE, "no node")
    def test_export_import_round_trip(self):
        from gen3tl.lang.langpack import load_styles
        from gen3tl.web.editordata import codec_data, fonts_data, glyph_art
        prof = Profile.by_name(PROFILE)
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            root = tmp / "lang"
            shutil.copytree(TOOLKIT_ROOT / "assets" / "lang" / "ru", root / "ru")
            packs = load_styles("ru", prof, root)
            art = glyph_art(prof, packs)
            index = {"language": "ru", "profile": prof.name, "fonts": fonts_data(prof, packs), "glyphs": art,
                     "font_sheets": editorfonts.font_sheets(prof, "ru", root), "codec": codec_data(),
                     "charmap": {c: f"{b:02X}" for c, b in packs["unbound"].chars.items()
                                 if packs["unbound"].sources[c] != "base"}}

            def blank(rows, top, last):
                """The first background pixel above the last cell row: (x, y) in the cell."""
                return next((x, top + r) for r, row in enumerate(rows[:last]) for x, c in enumerate(row) if c == "_")

            be, slot = art["unbound"]["art"]["37"], art["unbound-small"]["art"]["105"]
            hud = next(s for s in index["font_sheets"]["sheets"] if s["kind"] == "sprite")
            zhe = next(g for g in hud["glyphs"] if g["char"] == "Ж")
            wide = len(hud["art"][str(zhe["tile"])][0]) + 1   # a new column, background
            self.assertLessEqual(wide, 8)
            a = f"{packs['unbound'].chars['А']:02X}"   # copy:BB, art in the outlined style only
            self.assertEqual((packs["unbound"].sources["А"], packs["unbound"].copies["А"]), ("copy", 0xBB))
            copied = copied_rom(index["font_sheets"]["sheets"], tmp / "rom.gba")
            ops = [{"sheet": "font0", "code": "37", "width": len(be[0]) + 1, "ink": "#", "paint": [blank(be, 0, 12)]},
                   {"sheet": "small", "code": "105", "ink": "#", "paint": [blank(slot, 1, 11)]},
                   {"sheet": hud["name"], "code": zhe["code"], "width": wide, "ink": "s",
                    "paint": [[wide - 1, 0], [wide - 1, 7]]},
                   {"sheet": "font0", "code": a, "ink": "#", "paint": [[2, 4]]},
                   {"sheet": "small", "code": a, "ink": "#", "paint": [[2, 5]]}]
            (tmp / "edit.mjs").write_text(edit_script(), encoding="utf-8")
            (tmp / "in.json").write_text(json.dumps({"index": index, "ops": ops, "rom": str(tmp / "rom.gba")}),
                                         encoding="utf-8")
            run = subprocess.run([NODE, str(tmp / "edit.mjs"), str(tmp / "in.json"), str(tmp / "out.json")],
                                 capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr[-2000:])
            out = json.loads((tmp / "out.json").read_text(encoding="utf-8"))
            self.assertEqual(len(out["doc"]["glyphs"]), 5)
            self.assertEqual([g["base"] for g in out["doc"]["glyphs"] if g.get("char") == "А"], [{"source": "copy:BB"}] * 2)
            export = tmp / "edits.json"
            export.write_text(json.dumps(out["doc"], ensure_ascii=False), encoding="utf-8")
            found = editorfonts.glyph_edits(json.loads(export.read_text(encoding="utf-8"))["glyphs"], prof, "ru", root)
            self.assertEqual(sorted(p.name for p in editorfonts.apply_glyph_edits(found)),
                             ["charmap.tsv", "unbound-outlined.txt", "unbound-small.txt", "unbound.txt"])
            shown = out["shown"]
            again = load_styles("ru", prof, root)
            self.assertEqual(editorfonts.art_rows(again["unbound"].glyphs["Б"], 0, 14), shown["unbound:37"])
            self.assertEqual(len(shown["unbound:37"][0]), len(be[0]) + 1)
            self.assertEqual(editorfonts.art_rows(again["unbound-small"].glyphs[0x105], 1, 12), shown["unbound-small:105"])
            outlined = LangPack.load("ru", "unbound-outlined", root, rows=8)
            self.assertEqual(editorfonts.art_rows(outlined.glyphs["Ж"], 0, 8), shown[f"unbound-outlined:{zhe['code']}"])
            self.assertEqual([r[-1] for r in shown[f"unbound-outlined:{zhe['code']}"]], ["s"] + ["_"] * 6 + ["s"])
            self.assertNotEqual(shown["unbound:37"], be)
            self.assertEqual(glyph_art(prof, again)["unbound"]["art"]["37"], shown["unbound:37"])
            # copied letter with one more pixel, drawn in both fonts
            self.assertEqual(shown[f"unbound:{a}"], [r[:2] + "#" + r[3:] if y == 4 else r for y, r in enumerate(copied)])
            self.assertEqual(shown[f"unbound-small:{a}"], [r[:2] + "#" + r[3:] if y == 4 else r
                                                          for y, r in enumerate(copied[1:13])])
            self.assertEqual(again["unbound"].sources["А"], "glyph")
            self.assertEqual(editorfonts.art_rows(again["unbound"].glyphs["А"], 0, 14), shown[f"unbound:{a}"])
            self.assertEqual(editorfonts.art_rows(again["unbound-small"].glyphs["А"], 1, 12),
                             shown[f"unbound-small:{a}"])
            text = (root / "ru/fonts/unbound.txt").read_text(encoding="utf-8")
            self.assertLess(text.index("glyph А width 6"), text.index("glyph Б width"))   # in charmap order


@needs_rom
class ImportCommandTest(unittest.TestCase):
    def test_web_import_plans_a_glyph_redraw(self):
        from gen3tl.__main__ import main
        from gen3tl.lang.langpack import load_styles
        prof = Profile.by_name(PROFILE)
        art = load_styles("ru", prof)["unbound"].glyphs["Б"]
        rows = editorfonts.art_rows(art, 0, 14)
        drawn = [r.replace("s", "_") if y == 0 else r for y, r in enumerate(rows)]
        path = TOOLKIT_ROOT / "assets" / "lang" / "ru" / "fonts" / "unbound.txt"
        before = path.read_bytes()
        doc = {"profile": prof.name, "language": "ru", "entries": [], "pictures": [], "terms": [],
               "glyphs": [{"style": "unbound", "char": "Б", "width": art.width, "rows": [r[:-1] + "#" if y == 4 else r
                                                                                          for y, r in enumerate(drawn)],
                           "base": {"width": art.width, "rows": rows}}]}
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()) as out:
            export = Path(tmp) / "edits.json"
            export.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
            code = main(["--project-root", str(UNBOUND), "web", "import", str(export), "--dry-run"])
        self.assertEqual(code, 0, out.getvalue())
        lines = [line.split(None, 1) for line in out.getvalue().splitlines()]
        self.assertEqual(lines, [["glyph", "Б"], ["style", "unbound"], ["status", "planned"], ["catalog", "unchanged"],
                                 ["review", "required"]])
        self.assertEqual(path.read_bytes(), before)


    def test_web_import_plans_a_copied_letter_drawn_anew(self):
        from gen3tl.__main__ import main
        prof = Profile.by_name(PROFILE)
        main_rows = ["______"] * 3 + ["#s____"] * 8 + ["______"] * 3
        glyphs = [{"style": "unbound", "char": "А", "width": 6, "rows": main_rows, "base": {"source": "copy:BB"}},
                  {"style": "unbound-small", "char": "А", "width": 6, "rows": main_rows[1:13],
                   "base": {"source": "copy:BB"}}]
        charmap = TOOLKIT_ROOT / "assets" / "lang" / "ru" / "charmap.tsv"
        before = charmap.read_bytes()
        outputs = []
        for records in (glyphs[:1], glyphs):
            doc = {"profile": prof.name, "language": "ru", "entries": [], "glyphs": records}
            with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()) as out:
                export = Path(tmp) / "edits.json"
                export.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
                outputs.append((main(["web", "import", str(export), "--dry-run"]), out.getvalue()))
        self.assertEqual(outputs[0], (1, "error        glyph А: a drawn letter needs art in every style; "
                                         "draw it in unbound-small too\n"))
        code, text = outputs[1]
        self.assertEqual(code, 0, text)
        self.assertEqual([line.split(None, 1) for line in text.splitlines()][:4],
                         [["glyph", "А"], ["style", "unbound"], ["status", "planned"], ["source", "copy:BB -> glyph"]])
        self.assertEqual(charmap.read_bytes(), before)
