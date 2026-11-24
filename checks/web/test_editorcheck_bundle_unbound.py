import sys
import dataclasses
import json
import os
import random
import re
import shutil
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path

from gen3tl.web import editordata
from gen3tl.check import qa
from gen3tl.check.entrycheck import BRACE
from gen3tl.check.layout import Measure, entry_measure, layout, line_width
from gen3tl.check.provenance import formatted
from gen3tl.catalog.po import read
from gen3tl.project import Manifest
from gen3tl.build.release import expand

from rom_support import needs_rom, rom_path
from test_roots import TEST_ROOT, TOOLKIT_ROOT, PROJECT_ROOT as ROOT
from project_fixture import UNBOUND, unbound
from editorcheck_support import entry

def have_pyodide() -> bool:
    """Node with the pyodide package (NODE_PATH may name its node_modules)."""
    if shutil.which("node") is None:
        return False
    return subprocess.run(["node", "-e", "require.resolve('pyodide')"], capture_output=True).returncode == 0


DRIVER = '''
import json
import sys


def run(bundle, work, rom_path, tag):
    sys.path.insert(0, bundle)
    from gen3tl.web import editorcheck
    with open(work + "/input.json", encoding="utf-8") as fh:
        inp = json.load(fh)
    with open(bundle + "/rules.json", encoding="utf-8") as fh:
        rules = fh.read()
    with open(rom_path, "rb") as fh:
        rom = fh.read()
    latin = editorcheck.latin_widths(inp["doc"]["fonts"], rom, inp["doc"]["rom"]["sha1"])
    cells = editorcheck.latin_cells(inp["doc"]["fonts"], rom)
    checker = editorcheck.Checker(json.dumps(inp["doc"]), latin, rules, inp["version"], cells)
    out = {"file": editorcheck.__file__,
           "results": [json.loads(checker.check_json(json.dumps(x["entry"]), x["text"])) for x in inp["items"]]}
    try:
        import gen3tl.check.qa  # noqa: F401
        out["qa"] = True
    except ImportError:
        out["qa"] = False
    with open(work + "/out-" + tag + ".json", "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False)


if __name__ == "__main__" and len(sys.argv) == 5:
    run(*sys.argv[1:])
'''


NODE = '''
const fs = require("fs");
const path = require("path");
const { loadPyodide } = require("pyodide");
const [work, zip, rom] = process.argv.slice(2);
(async () => {
  const py = await loadPyodide();
  py.unpackArchive(new Uint8Array(fs.readFileSync(zip)), "zip", { extractDir: "/bundle" });
  py.FS.mkdirTree("/work");
  py.FS.mount(py.FS.filesystems.NODEFS, { root: work }, "/work");
  py.FS.mkdirTree("/rom");
  // NODEFS cannot open a symlinked folder
  py.FS.mount(py.FS.filesystems.NODEFS, { root: fs.realpathSync(path.dirname(rom)) }, "/rom");
  py.runPython(fs.readFileSync(path.join(work, "driver.py"), "utf8"));
  py.globals.get("run")("/bundle", "/work", "/rom/" + path.basename(rom), "pyodide");
})().catch((e) => { console.error(e); process.exit(1); });
'''


KINDS = {
    "single": lambda e, w, main: w["kind"] == "single",
    "field": lambda e, w, main: w["kind"] == "field",
    "dialogue": lambda e, w, main: w["kind"] == "dialogue",
    "battle": lambda e, w, main: w["kind"] == "battle",
    "lines": lambda e, w, main: w["kind"] == "multiline",
    "small font": lambda e, w, main: w["font"] != main,
    "other styles": lambda e, w, main: bool(w.get("other")),
    "inserted": lambda e, w, main: bool(e["context"]["inserted"]),
    "slot widths": lambda e, w, main: bool(w.get("placeholders")),
    "keys": lambda e, w, main: w.get("keys") is not None,
    "bytes": lambda e, w, main: w.get("bytes") is not None,
    "host": lambda e, w, main: w.get("host") is not None,
}


PER_KIND = 6


SOURCE_ID = re.compile(r"\b(s[0-9A-F]{7}|[a-z_]+:\d+)\b")


def edits(text: str, i: int) -> str:
    """An edited translation that the checks catch."""
    k = i % 5
    if k == 0:
        return text + " " + text   # too wide, more lines
    if k == 1:
        return text + " @VERSION@"
    if k == 2:
        return text + "..."
    if k == 3 and BRACE.search(text):
        return BRACE.sub("", text, count=1)
    return ""


@needs_rom
class BundleAgainstBatchCheckTest(unittest.TestCase):
    """The bundle agrees with `gen3tl check batch` on sample entries."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        tmp = Path(cls.tmp.name)
        env = {**os.environ, "PYTHONPATH": str(TOOLKIT_ROOT / "src")}
        gen3tl = [sys.executable, "-m", "gen3tl", "--rom", str(rom_path())]
        subprocess.run(gen3tl + ["web", "data", "--out", str(tmp / "ru.json")], cwd=ROOT, env=env, check=True,
                       capture_output=True)
        cls.zip = tmp / "gen3tl-check.zip"
        subprocess.run(gen3tl + ["web", "bundle", "--out", str(cls.zip)], cwd=ROOT, env=env, check=True,
                       capture_output=True)
        doc = json.loads((tmp / "ru.json").read_text(encoding="utf-8"))
        english = {e.msgctxt: e.msgid for e in read(ROOT / "build" / "catalog.pot")[1]}
        for e in doc["entries"]:   # as the page reads it from the ROM
            e["source_text"] = english[e["id"]]
        main = doc["fonts"]["main"]
        # texts other limits depend on stay as in the catalog:
        # - words a slot width names (untranslated: other source)
        # - for edits: inserted words, table names, centred titles
        sources = {m for e in doc["entries"] if e["window"]
                   for s in (e["window"].get("slot_sources") or {}).values() for m in SOURCE_ID.findall(formatted(s))}
        from gen3tl.catalog.keys import for_profile
        key = for_profile(unbound()).key
        sources |= {key(sid) for entry in doc["entries"]
                    for detail in ((entry.get("window") or {}).get("slot_details") or {}).values()
                    for sid in detail.get("dependencies", [])}
        lay = unbound().get("layout", {})
        inv = json.loads((ROOT / "build" / "inventory.json").read_text(encoding="utf-8"))
        ctx = json.loads((ROOT / "build" / "context.json").read_text(encoding="utf-8"))["strings"]
        centres = qa.window_centres(lay)
        buffered = set(lay.get("buffer_tables", {}).values())
        held = sources | {ref for ref, _ in centres.values()}
        held |= {e["id"] for e in inv["entries"]
                 if e.get("table") in buffered or any(r["at"] in centres for r in e["refs"])}
        held |= {sid for sid, s in ctx.items() if s.get("fills")}
        held |= {v for s in ctx.values() for sl in s.get("slots", {}).values() for k, v in sl.get("fills", [])
                 if k == "string"}
        held = {key(sid) for sid in held}
        fixed = lambda e: e["id"] in held or e["context"]["hosts"]
        rng = random.Random(1672)
        cls.items = []
        seen = set()
        for kind, test in KINDS.items():
            pool = [e for e in doc["entries"] if e["window"] and e["id"] not in seen and test(e, e["window"], main)]
            for status in ("approved", "untranslated"):
                cand = [e for e in pool if e["status"] == status and (status == "approved" or e["id"] not in sources)]
                for e in rng.sample(cand, min(PER_KIND, len(cand))):
                    text = e["translation"] if status == "approved" else e["source_text"]
                    cls.items.append({"entry": e, "text": text, "kind": kind, "how": status})
                    seen.add(e["id"])
            cand = [e for e in pool if e["status"] == "approved" and e["id"] not in seen and not fixed(e)]
            for i, e in enumerate(rng.sample(cand, min(PER_KIND, len(cand)))):
                cls.items.append({"entry": e, "text": edits(e["translation"], i), "kind": kind,
                                  "how": "edited"})
                seen.add(e["id"])
        # Isolate the sample from project data.
        work = tmp / "repo"
        batch = work / "translation" / "ru" / "batches" / "editor-check"
        batch.mkdir(parents=True)
        (work / "projects.toml").write_text('[defaults]\nprofile = "unbound-2.1.1.1"\nlanguage = "ru"\n[[project]]\nprofile = "unbound-2.1.1.1"\nlanguage = "ru"\nroot = "."\npolicy = "translation/ru/policy.toml"\n', encoding="utf-8")
        manifest = Manifest.read(ROOT / "project.toml")
        (work / "project.toml").write_text(dataclasses.replace(manifest, languages=("ru",)).text(), encoding="utf-8")
        shutil.copytree(UNBOUND / "profile", work / "profile")
        for name in ("build", "data", "source"):
            (work / name).symlink_to(ROOT / name)
        for f in ("glossary.tsv", "release.toml", "notes", "research"):   # the glossary resolves its notes
            (work / "translation" / "ru" / f).symlink_to(ROOT / "translation" / "ru" / f)
        # copies: the policy and its graphics stay inside the project
        policy = work / "translation" / "ru" / "policy.toml"
        policy.write_bytes((TEST_ROOT / "fixtures" / "unbound-2.1.1.1-policy.toml").read_bytes())
        shutil.copytree(UNBOUND / "translation" / "ru" / "graphics", work / "translation" / "ru" / "graphics")
        (batch / "source.json").write_text(json.dumps([{"id": x["entry"]["id"], "source_text": x["entry"]["source_text"]}
                                                       for x in cls.items], ensure_ascii=False), encoding="utf-8")
        (batch / "translation.json").write_text(json.dumps({x["entry"]["id"]: x["text"] for x in cls.items},
                                                           ensure_ascii=False), encoding="utf-8")
        run = subprocess.run(gen3tl + ["check", "batch", "editor-check", "--po-root", str(ROOT / "translation" / "ru" / "po")],
                             cwd=work, env=env, capture_output=True, text=True)
        # findings exit 1 with only the final reason on stderr
        failed = [line for line in run.stderr.splitlines() if not line.startswith("result       failed: ")]
        if run.returncode not in (0, 1) or failed or bool(run.stderr) != (run.returncode == 1):
            raise AssertionError(f"check batch failed: {run.stderr[-2000:]}")
        cls.cli: dict[str, list[str]] = {}
        lines = run.stdout.splitlines()
        cls.summary = dict(line.split(None, 1) for line in lines[-4:])
        cls.never = {}
        sid = None
        for line in lines[:-4]:
            label, value = line.split(None, 1)
            if label == "entry":
                sid = value
            elif label in ("error", "warning", "never"):
                if value.startswith("reach: never shown ("):
                    cls.never[sid] = value
                else:
                    cls.cli.setdefault(sid, []).append(value)
        # the bundle alone, in CPython
        cls.work = tmp / "work"
        bundle = tmp / "bundle"
        with zipfile.ZipFile(cls.zip) as z:
            z.extractall(bundle)
        cls.work.mkdir()
        (cls.work / "driver.py").write_text(DRIVER, encoding="utf-8")
        from gen3tl.build.release import load as load_version
        cls.version = load_version(ROOT / "translation" / "ru" / "release.toml")
        header = {k: v for k, v in doc.items() if k != "entries"}
        (cls.work / "input.json").write_text(json.dumps({"doc": header, "version": cls.version, "items": [
            {"entry": x["entry"], "text": x["text"]} for x in cls.items]}, ensure_ascii=False), encoding="utf-8")
        cls.rom = unbound().load_rom(rom_path()).path
        subprocess.run([sys.executable, "-I", str(cls.work / "driver.py"), str(bundle), str(cls.work), str(cls.rom),
                        "cpython"], check=True, capture_output=True)
        cls.out = json.loads((cls.work / "out-cpython.json").read_text(encoding="utf-8"))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_sample(self):
        # every kind, approved, untranslated and edited texts
        got = {(x["kind"], x["how"]) for x in self.items}
        for kind in KINDS:
            self.assertIn((kind, "approved"), got)
        # unused field slots have nothing to translate
        self.assertGreaterEqual(len({k for k, h in got if h == "untranslated"}), 7)
        self.assertGreaterEqual(len({k for k, h in got if h == "edited"}), 4)
        self.assertEqual(self.summary["checked"], f"{len(self.items)} entries")
        for label in ("errors", "warnings"):
            self.assertRegex(self.summary[label], rf"^\d+ {label}$")
        self.assertRegex(self.summary["never"], r"^\d+ entries$")

    def test_bundle_alone(self):
        self.assertTrue(self.out["file"].startswith(str(self.tmp.name)))
        self.assertFalse(self.out["qa"])

    def test_same_problems_as_batch_check(self):
        res = self.out["results"]
        for x, r in zip(self.items, res):
            sid = x["entry"]["id"]
            with self.subTest(sid=sid, kind=x["kind"], how=x["how"]):
                self.assertEqual([formatted(p["message"]) for p in r["problems"]], self.cli.get(sid, []))
        errors = sum(r["errors"] for r in res)
        warnings = sum(r["warnings"] for r in res)
        self.assertEqual(self.summary, {"checked": f"{len(self.items)} entries", "errors": f"{errors} errors",
                                        "warnings": f"{warnings} warnings", "never": f"{len(self.never)} entries"})
        self.assertGreater(errors, 0)

    def test_same_layout_as_gen3tl(self):
        # Compare layout using the ROM metrics.
        from gen3tl.cli.common import _font_codes, _shadow_end, _style_shadow_ends, _style_widths
        from gen3tl.build.font import FontTable
        from gen3tl.lang.langpack import LangPack
        prof = unbound()
        rom = prof.load_rom(rom_path())
        font = FontTable.from_profile(prof)[0]
        pack = LangPack.load("ru", prof["font_style"]["style"])
        # copied letters read their glyphs from the ROM
        slots, cm = pack.glyph_slots(rom, font), pack.charmap()
        measure = Measure(lambda b: slots[b].width if b in slots else font.width(rom, b),
                          prof.get("layout", {}).get("placeholders", {}), styles=_style_widths(prof, rom, "ru"),
                          shadow_end=_shadow_end(slots, font, rom), shadow_styles=_style_shadow_ends(prof, rom, "ru"),
                          fonts=_font_codes(prof))
        n = 0
        for x, r in zip(self.items, self.out["results"]):
            t = expand(x["text"], self.version)
            if not cm.can_encode(t):
                continue
            lim = editordata.limit_of(x["entry"]["window"])
            laid = layout(t, lim, measure, cm)
            me = entry_measure(measure, lim)
            with self.subTest(sid=x["entry"]["id"]):
                self.assertEqual(r["laid"], laid)
                self.assertEqual([[l["width"] for l in box] for box in r["lines"]],
                                 [[line_width(l, me, cm) for l in re.split(r"\\[nl]", par)]
                                  for par in laid.split("\\p")])
            n += 1
        self.assertGreater(n, len(self.items) // 2)

    @unittest.skipUnless(have_pyodide(), "no node with the pyodide package (set NODE_PATH to its node_modules)")
    def test_pyodide(self):
        # the same driver in Pyodide under Node: the same results
        (self.work / "run.cjs").write_text(NODE, encoding="utf-8")
        run = subprocess.run(["node", str(self.work / "run.cjs"), str(self.work), str(self.zip), str(self.rom)],
                             capture_output=True, text=True, timeout=600)
        self.assertEqual(run.returncode, 0, run.stderr[-2000:])
        out = json.loads((self.work / "out-pyodide.json").read_text(encoding="utf-8"))
        self.assertEqual((out["file"], out["qa"]), ("/bundle/gen3tl/web/editorcheck.py", False))
        self.assertEqual(out["results"], self.out["results"])
