import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from gen3tl.web import patcher
from gen3tl.core import ups
from gen3tl.profile.profile import Profile

from test_roots import TEST_ROOT, TOOLKIT_ROOT

ROOT = TOOLKIT_ROOT

NODE = shutil.which("node")

class ReleaseFixture:
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.base = bytes(range(256))
        self.target = self.base[:30] + b"translated" + self.base[40:]
        self.profile = Profile({"rom": {"name": "Example Game", "sha1": hashlib.sha1(self.base).hexdigest()}}, self.root / "example.toml")
        self.out = self.root / "site/releases"
        self.built = self.root / "translated.gba"
        self.patch = self.root / "translated.ups"
        self.write_release()

    def write_release(self, version="0.1.17", language="ru", target=None):
        target = self.target if target is None else target
        self.built.write_bytes(target)
        self.patch.write_bytes(ups.create(self.base, target))
        self.identity = {"profile": self.profile.name, "language": language,
                         "rom_sha1": self.profile.sha1, "built_sha1": hashlib.sha1(target).hexdigest(),
                         "version": version}
        self.built.with_suffix(".project.json").write_text(json.dumps(self.identity))

    def prepare(self, language="ru"):
        return patcher.prepare(self.profile, language, self.base, self.built, self.patch, self.out)

class CopyReleasesTest(ReleaseFixture, unittest.TestCase):
    """A game project's releases/ copied into the site data."""

    def setUp(self):
        super().setUp()
        self.data = self.root / "data/releases"
        other = Profile({"rom": {"name": "Other Game", "sha1": self.profile.sha1}}, self.root / "other.toml")
        identity = dict(self.identity, profile="other", language="de")
        self.built.with_suffix(".project.json").write_text(json.dumps(identity))
        patcher.prepare(other, "de", self.base, self.built, self.patch, self.data)   # another profile's row
        self.write_release()

    def rows(self):
        return patcher.validate(json.loads((self.data / "releases.json").read_text()))


    def test_the_editor_data_takes_the_releases_of_the_game_project(self):
        import os

        from gen3tl.project import Manifest, registry_scope
        from gen3tl.web.editordata import write_releases
        game = self.root / "game"
        game.mkdir()
        (game / "project.toml").write_text(Manifest(game / "project.toml", "example", self.profile.sha1,
                                                    "1.0.0", (), "").text(), encoding="utf-8")
        self.out = game / "releases"
        row = self.prepare()
        cwd = os.getcwd()
        os.chdir(game)   # the game project is the registry of the command
        try:
            with registry_scope(game):
                self.assertEqual(write_releases(self.data.parent), 1)
        finally:
            os.chdir(cwd)
        self.assertEqual([r["profile"] for r in self.rows()], ["example", "other"])
        self.assertEqual((self.data / row["patch"]).read_bytes(), self.patch.read_bytes())


@unittest.skipUnless(NODE, "Node is required for browser UPS tests")
class BrowserPatcherTest(ReleaseFixture, unittest.TestCase):
    def node(self, script, data):
        fixture = self.root / "input.json"
        fixture.write_text(json.dumps(data))
        result = subprocess.run([NODE, "--input-type=module", "-e", script, str(fixture)],
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def test_release_hashes_and_manifest_are_required(self):
        row = self.prepare()
        script = f'''import fs from "node:fs";
import assert from "node:assert/strict";
await import({json.dumps((TEST_ROOT / "web/patch-fixture.mjs").as_uri())});
import {{ patchRelease, validateManifest }} from {json.dumps((TOOLKIT_ROOT / "web/js/patcher-core.js").as_uri())};
const data = JSON.parse(fs.readFileSync(process.argv[1]));
const source = Uint8Array.from(data.source), patch = Uint8Array.from(data.patch), row = data.row;
assert.deepEqual([...await patchRelease(source, patch, row)], data.target);
for (const field of ["source_sha1", "result_sha1", "patch_sha256"])
  await assert.rejects(patchRelease(source, patch, {{...row, [field]: "0".repeat(row[field].length)}}));
for (const field of ["source_size", "result_size", "patch_size"])
  await assert.rejects(patchRelease(source, patch, {{...row, [field]: row[field] + 1}}));
assert.throws(() => validateManifest({{schema: 1, releases: [row, row]}}), /Duplicate/);
assert.throws(() => validateManifest({{schema: 1, releases: [{{...row, patch: "../escape.ups"}}]}}));
assert.throws(() => validateManifest({{schema: 1, releases: [{{...row, source_size: true}}]}}));
const other = {{...row, version: "0.1.18", patch: "example/ru/0.1.18.ups", output: "example-ru-0.1.18.gba", source_sha1: "0".repeat(40)}};
assert.throws(() => validateManifest({{schema: 1, releases: [row, other]}}), /Inconsistent/);
assert.deepEqual(validateManifest({{schema: 1, releases: []}}), []);'''
        self.node(script, {"row": patcher.browser_row(row), "source": list(self.base), "target": list(self.target),
                           "patch": list(self.patch.read_bytes())})
