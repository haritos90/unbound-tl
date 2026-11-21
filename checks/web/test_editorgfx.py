import contextlib
import io
import json
import shutil
import subprocess
import tempfile
import unittest
import base64
import sys
import zipfile
from pathlib import Path

from gen3tl.profile.profile import Profile
from gen3tl.__main__ import main
from gen3tl.web.editorgfx import graphics_data, Pictures
from gen3tl.build.graphics import GraphicsConfig, area_palette, hex_rgb, inject_graphics
from gen3tl.web import editorcheck
from gen3tl.build.inject import FreeSpace
from gen3tl.check.render import png_image

from rom_support import rom_path as base_rom_path, needs_rom
from test_roots import PROJECT_ROOT, TEST_ROOT, TOOLKIT_ROOT
from graphics_support import fixture
from project_fixture import UNBOUND, unbound, write_policy

ROOT = PROJECT_ROOT

NODE = shutil.which("node")

class Fixture(unittest.TestCase):
    """A synthetic ROM (graphics_support.fixture), its config and a profile file for the CLI."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.tmp = Path(self.tmpdir.name)
        self.base, self.lz_data, self.raw_data, self.slot = fixture(self.tmp)
        self.section = {"inventory": "inv.tsv", "sheet_width": {"T1": 4}}
        self.cfg = GraphicsConfig(self.section, self.tmp)
        self.sheet = self.cfg.sheet(self.base, self.cfg.graphic("T1"))
        self.rom_path = self.tmp / "base.gba"
        self.base.save(self.rom_path)

    def tearDown(self):
        self.tmpdir.cleanup()

    def profile(self, edits: str = "") -> Path:
        import tomllib

        from project_fixture import literal
        prof = self.tmp / "p.toml"
        translated = tomllib.loads(edits).get("graphics", {}).get("edit", [])
        facts = ""
        for entry in translated:
            entry["png"] = str(Path(entry["png"]).relative_to(self.tmp))
            metadata = {"evidence": entry.pop("evidence", "fixture")}
            if "tiles" in entry:
                metadata["max_tiles"] = entry["tiles"]
            facts += f'\n[graphics.edit_facts.{entry["id"]}]\n'
            facts += "\n".join(f"{k} = {literal(v)}" for k, v in metadata.items()) + "\n"
        prof.write_text(f'[rom]\nname = "t"\npath = "{self.rom_path}"\nsha1 = "{self.base.sha1()}"\n\n'
                        f'[graphics]\ninventory = "{self.tmp / "inv.tsv"}"\n\n[graphics.sheet_width]\nT1 = 4\n'
                        + facts, encoding="utf-8")
        write_policy(self.tmp, Profile.load(prof), graphics={"edit": translated})
        return prof

    def cli(self, prof: Path, *args) -> tuple[int, list[str]]:
        (self.tmp / "projects.toml").write_text('[defaults]\nprofile = "p"\nlanguage = "ru"\n[[project]]\nprofile = "p"\nlanguage = "ru"\nroot = "."\npolicy = "policy.toml"\n', encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()) as out:
            code = main(["--project-root", str(self.tmp), "--profile", str(prof), *args])
        return code, out.getvalue().splitlines()

    def data(self, **extra) -> dict:
        return graphics_data(dict(self.section, **extra), self.tmp)

class GraphicsDataTest(Fixture):


    def test_the_slot_machine_labels_share_one_edit_and_the_title_mark_keeps_none(self):
        prof = unbound()
        edits = graphics_data(prof["graphics"], UNBOUND, prof.release_path)["edits"]
        self.assertEqual(edits["G60"], {**edits["G59"], "shared": "G59"})
        self.assertIn("G04", edits)
        self.assertNotIn("G05", edits, "a keep row on the edited title background")
        self.assertEqual({gid for gid, e in edits.items() if "shared" in e}, SHARED_EDITS)

@unittest.skipUnless(NODE, "node is unavailable")
class PictureNotesTest(unittest.TestCase):
    def test_every_migrated_summary_and_search_match_in_each_project(self):
        from gen3tl.lang import language
        from gen3tl.project.registry import Registry
        from gen3tl.web.editordata import attach_notes

        documents = []
        for project in Registry.load(UNBOUND).projects:
            with language.use(project.language):
                prof = Profile.by_name(project.profile).for_project(project.language, project.root)
                doc = {"language": project.language, "entries": [],
                       "graphics": graphics_data(prof["graphics"], project.root, prof.release_path)}
                attach_notes(doc, prof, {}, folder=project.translation, wording=[])
                documents.append(doc)
        self.assertTrue(documents)
        script = r'''
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { filterGraphics, PicturesView, reasonOf, summaryOf } from "./web/js/pictures.js";
import { stubPage } from "./web/test/fixture.mjs";
const { $ } = stubPage({ after() {} }, "editor");
for (const index of JSON.parse(readFileSync(0, "utf8"))) {
  const rows = index.graphics.inventory, migrated = rows.filter((row) => row.note_ids?.length);
  assert.ok(migrated.length);
  const before = JSON.stringify(index);
  const view = new PicturesView({ index: () => index, uploads: () => ({ map: new Map() }) }, $);
  view.rows = rows;
  view.filtered = rows.map((_, i) => i);
  view.renderList();
  assert.deepEqual($("p-list").children.map((row) => row.children[2].textContent), rows.map((row) => summaryOf(row, index)));
  for (const row of migrated) {
    // exports carry the note records, not a flattened string
    assert.equal(row.reason, undefined, `${index.language}/${row.id}`);
    const summary = summaryOf(row, index), text = reasonOf(row, index);
    assert.ok(summary, `${index.language}/${row.id}`);
    for (const query of [row.id, row.screen, ...summary.split("\n"), ...text.split(/\s+/)]) {
      if (!query.trim()) continue;
      assert.ok(filterGraphics(rows, { search: query }, index.graphics, new Map(), null, index)
        .includes(rows.indexOf(row)), `${index.language}/${row.id}/${query}`);
    }
  }
  assert.deepEqual(filterGraphics(rows, { search: "no matching graphic note" }, index.graphics, new Map(), null, index), []);
  assert.equal(JSON.stringify(index), before);
}
'''.replace("./web/js/pictures.js", (TOOLKIT_ROOT / "web/js/pictures.js").as_uri()).replace("./web/test/fixture.mjs", (TEST_ROOT / "web/fixture.mjs").as_uri())
        result = subprocess.run([NODE, "--input-type=module", "-e", script], cwd=ROOT,
                                input=json.dumps(documents), text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

SHARED_EDITS = {"G60"}


WEB = TOOLKIT_ROOT / "web"


def have_pyodide() -> bool:
    """Node with the pyodide package (NODE_PATH may name its node_modules)."""
    return NODE is not None and subprocess.run([NODE, "-e", "require.resolve('pyodide')"],
                                               capture_output=True).returncode == 0


def flat(rows) -> bytes:
    return bytes(v for row in rows for v in row)


DRIVER = '''
import base64, json, sys


def run(bundle, inp_path, rom_path, out_path):
    sys.path.insert(0, bundle)
    from gen3tl.web import editorgfx
    with open(inp_path, encoding="utf-8") as fh:
        inp = json.load(fh)
    with open(rom_path, "rb") as fh:
        pics = editorgfx.Pictures(json.dumps(inp["graphics"]), fh.read())
    out = {"file": editorgfx.__file__, "png": {i: pics.png_b64(i) for i in inp["ids"]}}
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(out, fh)


if __name__ == "__main__":
    run(*sys.argv[1:])
'''


NODE_GFX = '''
import fs from "node:fs";
import { createRequire } from "node:module";
import { Gfx } from "%s";
const require = createRequire(import.meta.url);
const { loadPyodide } = require("pyodide");
const [input, out] = process.argv.slice(2);
const inp = JSON.parse(fs.readFileSync(input, "utf8"));
const b64 = (b) => Buffer.from(b).toString("base64");
const gfx = new Gfx(await loadPyodide(), new Uint8Array(fs.readFileSync(inp.bundle)));
gfx.load(inp.graphics, new Uint8Array(fs.readFileSync(inp.rom)));
const res = { png: {}, sheets: {}, edited: {} };
for (const id of inp.ids) {
  const s = gfx.sheet(id);
  res.png[id] = b64(gfx.png(id));
  res.sheets[id] = { width: s.width, height: s.height, palette: s.palette, pixels: b64(s.pixels) };
}
for (const id of Object.keys(inp.graphics.edits)) {
  const e = gfx.edited(id);
  res.edited[id] = { findings: e.findings, changed: e.changed, pixels: b64(e.pixels), png: b64(e.png) };
}
const c = inp.check;
const r = gfx.check(c.id, new Uint8Array(fs.readFileSync(c.png)), "upload.png", c.areas, c.tiles);
res.check = { code: r.code, lines: r.lines, area_png: b64(r.area_png) };
fs.writeFileSync(out, JSON.stringify(res));
'''


PROFILE_EDITS = {"G10", "G16", "G08", "G12", "G25", "G26", "G27", "G09", "G11", "G28"}


PROFILE_EDITS |= {"G04", "G07", "G14", "G15"}


PROFILE_EDITS |= {"G17", "G24", "G40", "G41", "G42"}


PROFILE_EDITS |= {"G19", "G21", "G22", "G23", "G30", "G32"}


PROFILE_EDITS |= {"G34", "G35", "G36", "G37", "G38", "G39", "G43", "G44"}


PROFILE_EDITS |= {"G33"}   # counter labels


PROFILE_EDITS.add("G55")   # summary status icons


PROFILE_EDITS.add("G01")   # generated boot version


PROFILE_EDITS.add("G03")   # boot PRESENTS


PROFILE_EDITS.add("G59")   # slot machine labels


@needs_rom
class BaseRomTest(unittest.TestCase):
    """Every catalogued base ROM graphic extracts and rebuilds as the CLI does."""

    @classmethod
    def setUpClass(cls):
        cls.prof = unbound()
        cls.rom_path = base_rom_path()
        cls.base = cls.prof.load_rom(cls.rom_path)
        cls.cfg = GraphicsConfig.from_profile(cls.prof)
        cls.graphics = graphics_data(cls.prof["graphics"], UNBOUND, cls.prof.release_path)
        cls.ids = [r["id"] for r in cls.graphics["inventory"] if r["rom_offset"]]
        cls.tmpdir = tempfile.TemporaryDirectory()
        cls.tmp = Path(cls.tmpdir.name)
        with contextlib.redirect_stdout(io.StringIO()):
            code = main(["--project-root", str(UNBOUND), "--rom", str(cls.rom_path), "build", "gfx-extract", *cls.ids, "--out", str(cls.tmp / "x")])
        assert code == 0
        cls.cli = {i: (cls.tmp / "x" / f"{i}.png").read_bytes() for i in cls.ids}
        cls.pics = Pictures(cls.graphics, bytes(cls.base.data))

    @classmethod
    def tearDownClass(cls):
        cls.tmpdir.cleanup()

    def test_catalogue(self):
        profile_ids = list(self.cfg.inventory)
        self.assertEqual([r["id"] for r in self.graphics["inventory"]], profile_ids)
        self.assertEqual(self.ids, [gid for gid in profile_ids if self.cfg.inventory[gid] is not None])
        self.assertEqual(set(self.graphics["edits"]), PROFILE_EDITS | SHARED_EDITS)
        for gid, e in self.graphics["edits"].items():
            if "label" in e:
                self.assertNotIn("png", e)
                self.assertIn("parts", e["label"]["glyphs"]["0"])
                continue
            grey = area_palette(self.cfg.graphic(gid).bpp)
            self.assertEqual(png_image(base64.b64decode(e["png"])).palette, grey, gid)

    def same_as_cli(self, gid: str, png: bytes, sheet: dict | None = None):
        self.assertEqual(png, self.cli[gid], gid)
        if sheet is not None:
            img = png_image(self.cli[gid])
            self.assertEqual((sheet["width"], sheet["height"]), (img.width, img.height), gid)
            self.assertEqual(base64.b64decode(sheet["pixels"]), flat(img.indices), gid)
            self.assertEqual(sheet["palette"], [hex_rgb(c) for c in img.palette], gid)

    def test_every_graphic_as_gfx_extract(self):
        for gid in self.ids:
            self.same_as_cli(gid, self.pics.png(gid), self.pics.sheet_data(gid))

    def test_bundle_alone(self):
        bundle = self.tmp / "bundle"
        editorcheck.write_bundle(self.tmp / "b.zip", {})
        with zipfile.ZipFile(self.tmp / "b.zip") as z:
            z.extractall(bundle)
        (self.tmp / "driver.py").write_text(DRIVER, encoding="utf-8")
        (self.tmp / "in.json").write_text(json.dumps({"graphics": self.graphics, "ids": self.ids}), encoding="utf-8")
        subprocess.run([sys.executable, "-I", str(self.tmp / "driver.py"), str(bundle), str(self.tmp / "in.json"),
                        str(self.rom_path), str(self.tmp / "out.json")], check=True, capture_output=True)
        out = json.loads((self.tmp / "out.json").read_text(encoding="utf-8"))
        self.assertTrue(out["file"].startswith(str(bundle)))
        for gid in self.ids:
            self.same_as_cli(gid, base64.b64decode(out["png"][gid]))

    def test_project_edits_as_built(self):
        rom = self.base.copy()
        res = inject_graphics(rom, self.base, self.cfg, FreeSpace.scan(bytes(self.base.data)))
        self.assertEqual(res.failures, [])
        built = {p.id: p for p in res.placements}
        self.assertEqual(set(built), PROFILE_EDITS)
        for gid, p in built.items():
            e = self.pics.edited(gid)
            self.assertEqual((e["findings"], e["changed"]), ([], p.changed_pixels))
            px = base64.b64decode(e["pixels"])
            rows = [list(px[y * e["width"]:(y + 1) * e["width"]]) for y in range(e["height"])]
            self.assertEqual(self.pics.sheet(gid).encode(rows, p.tiles), p.data, gid)

    def test_check_as_gfx_check(self):
        e = self.graphics["edits"]["G16"]
        up = self.tmp / "G16-edited.png"
        up.write_bytes(base64.b64decode(self.pics.edited("G16")["png"]))
        with contextlib.redirect_stdout(io.StringIO()) as out:
            code = main(["--project-root", str(UNBOUND), "--rom", str(self.rom_path), "build", "gfx-check", "G16", str(up),
                         "--area", *[",".join(map(str, a)) for a in e["areas"]], "--tiles", str(e["tiles"])])
        res = self.pics.check("G16", up.read_bytes(), up.name, e["areas"], e["tiles"])
        self.assertEqual(res["code"], code)
        self.assertIn("verified     passed", out.getvalue())
        self.assertIn("findings     0 findings", out.getvalue())
        self.assertEqual(code, 0)
        # the area form of the upload is the stored one
        stored = next(x.png for x in self.cfg.edits if x.id == "G16")
        self.assertEqual(base64.b64decode(res["area_png"]), stored.read_bytes())

    @unittest.skipUnless(have_pyodide(), "no node with the pyodide package (set NODE_PATH to its node_modules)")
    def test_pyodide(self):
        e = self.graphics["edits"]["G16"]
        up = self.tmp / "G16-up.png"
        up.write_bytes(base64.b64decode(self.pics.edited("G16")["png"]))
        editorcheck.write_bundle(self.tmp / "check.zip", {})
        (self.tmp / "gfx.mjs").write_text(NODE_GFX % (WEB / "js" / "gfx.js").as_uri(), encoding="utf-8")
        (self.tmp / "in.json").write_text(json.dumps({
            "graphics": self.graphics, "ids": self.ids, "bundle": str(self.tmp / "check.zip"),
            "rom": str(self.rom_path), "check": {"id": "G16", "png": str(up), "areas": e["areas"],
                                                 "tiles": e["tiles"]}}), encoding="utf-8")
        run = subprocess.run([NODE, str(self.tmp / "gfx.mjs"), str(self.tmp / "in.json"), str(self.tmp / "out.json")],
                             capture_output=True, text=True, timeout=600)
        self.assertEqual(run.returncode, 0, run.stderr[-2000:])
        out = json.loads((self.tmp / "out.json").read_text(encoding="utf-8"))
        for gid in self.ids:
            self.same_as_cli(gid, base64.b64decode(out["png"][gid]), out["sheets"][gid])
        for gid, got in out["edited"].items():
            want = self.pics.edited(gid)
            self.assertEqual((got["findings"], got["changed"], got["pixels"], got["png"]),
                             (want["findings"], want["changed"], want["pixels"], want["png"]), gid)
        res = self.pics.check("G16", up.read_bytes(), "upload.png", e["areas"], e["tiles"])
        self.assertEqual(out["check"], {"code": 0, "lines": res["lines"], "area_png": res["area_png"]})
