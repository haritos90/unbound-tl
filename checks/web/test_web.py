import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from gen3tl.catalog.catalog import load_catalog
from gen3tl.core.charmap import CharmapError
from gen3tl.web.editordata import codec_data
from gen3tl.lang.langpack import LangPack
from gen3tl.check.layout import Measure, line_width, lines_of, paragraphs

from rom_support import needs_rom
from test_roots import TOOLKIT_ROOT
from project_fixture import UNBOUND


WEB = TOOLKIT_ROOT / "web"


NODE = shutil.which("node")


WIDTHS = '''
import fs from "node:fs";
import { Codec, Measure } from "%s";
const inp = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const m = new Measure((b) => inp.widths[b], new Codec(inp.codec, inp.pack), inp.ph, inp.fallback);
const out = inp.lines.map((l) => {
  try {
    return m.lineWidth(l);
  } catch {
    return null;
  }
});
fs.writeFileSync(process.argv[3], JSON.stringify(out));
'''


@needs_rom
@unittest.skipUnless(NODE, "no node")
class NodeTest(unittest.TestCase):

    def test_widths_match_layout(self):
        pack = LangPack.load("ru")
        cm = pack.charmap()
        widths = [(b * 7) % 9 + 2 for b in range(512)]   # the bytes, then the F9 glyphs
        ph = {"PLAYER": 42, "STR_VAR_1": 60, "F8 00": 8, "B_ATK_NAME_WITH_PREFIX": 143}
        m = Measure(lambda b: widths[b], ph, 60)
        texts = ["Hi, {PLAYER}!  {COLOR 06}", "{LV}5 {F8 00}{F8 01} {FD 3D} {B_BUFF1} {JPN}x", "{NOPE} a", "Ж{1F}"]
        catalog = load_catalog(UNBOUND / "translation" / "ru" / "po")
        for i, (_, e) in enumerate(catalog.values()):
            if i % 25 == 0:
                texts += [e.msgid, e.msgstr]
        lines = [l for t in texts for p in paragraphs(t) for l in lines_of(p)]
        want = []
        for l in lines:
            try:
                want.append(line_width(l, m, cm))
            except CharmapError:
                want.append(None)
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "widths.mjs").write_text(WIDTHS % (WEB / "js" / "font.js").as_uri(), encoding="utf-8")
            (tmp / "in.json").write_text(json.dumps({
                "codec": codec_data(), "pack": {c: f"{b:02X}" for c, b in pack.chars.items()},
                "widths": widths, "ph": ph, "fallback": 60, "lines": lines}, ensure_ascii=False), encoding="utf-8")
            run = subprocess.run([NODE, str(tmp / "widths.mjs"), str(tmp / "in.json"), str(tmp / "out.json")],
                                 capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            got = json.loads((tmp / "out.json").read_text(encoding="utf-8"))
        self.assertGreater(len(lines), 1000)
        diff = [(l, a, b) for l, a, b in zip(lines, want, got) if a != b]
        self.assertEqual(diff[:5], [])
