from test_roots import PROJECT_ROOT, TOOLKIT_ROOT
"""Publication permits only the declared branding bytes and path."""

import contextlib
import io
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from gen3tl.cli.web import site_assemble
from gen3tl.web.siteassets import write_build, write_manifest

ROOT = PROJECT_ROOT
SCRIPT = ROOT / ".github/scripts/site-check.py"


def guard():
    spec = importlib.util.spec_from_file_location("site_check", SCRIPT)
    site = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(site)
    return site


def checked(site, tree):
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        return site.main([str(SCRIPT), str(tree)]), output.getvalue()


class SiteBrandingTest(unittest.TestCase):
    def test_game_workflow_publishes_data_and_forwards_previews_to_the_application(self):
        workflow = (ROOT / ".github/workflows/site.yml").read_text()
        self.assertIn("PUBLIC_BASE: https://haritos90.github.io/unbound-tl", workflow)
        self.assertIn('--public-base "$PUBLIC_BASE" --application https://haritos90.github.io/gen3tl/', workflow)
        self.assertIn("PREVIOUS: https://${{ github.repository_owner }}.github.io/${{ github.event.repository.name }}/",
                      workflow)
        self.assertIn('web assemble --out site --public-base "$PUBLIC_BASE" --application '
                      'https://haritos90.github.io/gen3tl/ --previous "$PREVIOUS"\n', workflow)
        self.assertIn('web registry --game "$profile" --repository "$REPOSITORY"', workflow)
        self.assertIn("python .github/scripts/site-check.py site", workflow)

    def test_a_pushed_tag_writes_its_release_with_the_toolkit_command(self):
        from gen3tl.cli import build   # registers the build commands
        from gen3tl.cli.common import COMMANDS
        workflow = (ROOT / ".github/workflows/release.yml").read_text()
        self.assertIn("tags: ['*-v*']", workflow)
        self.assertIn("contents: write", workflow)
        self.assertIn('gen3tl --lang "${TAG%-v*}" build release-notes --tag "$TAG" --repository "$REPOSITORY"', workflow)
        self.assertIn("build release-notes", COMMANDS)
        # a written body stays; an empty one is filled; a missing release is created
        self.assertEqual(workflow.count("if: steps.found.outputs.state != 'written'"), 5)
        self.assertIn('gh release edit "$TAG"', workflow)
        self.assertIn('gh release create "$TAG" --repo "$REPOSITORY" --verify-tag', workflow)

    def test_artwork_identity_and_location(self):
        if not SCRIPT.is_file():
            self.skipTest("project publication guard is absent from this checkout")
        spec = importlib.util.spec_from_file_location("site_check", SCRIPT)
        site = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(site)
        artwork = (TOOLKIT_ROOT / "web/brand.png").read_bytes()
        with tempfile.TemporaryDirectory() as tmp:
            tree = Path(tmp)
            path = tree / "brand.png"
            path.write_bytes(artwork)
            self.assertTrue(site.is_site_image(tree, path))
            path.write_bytes(artwork + b"extra")
            self.assertFalse(site.is_site_image(tree, path))
            renamed = tree / "other.png"
            renamed.write_bytes(artwork)
            self.assertFalse(site.is_site_image(tree, renamed))
            nested = tree / "images" / "brand.png"
            nested.parent.mkdir()
            nested.write_bytes(artwork)
            self.assertFalse(site.is_site_image(tree, nested))


class SiteWasmTest(unittest.TestCase):
    def test_publication_accepts_only_the_vendored_module_at_its_versioned_path(self):
        site = guard()
        module = (TOOLKIT_ROOT / "web/js/patcher/rom-patcher.wasm").read_bytes()
        current, kept = "assets/2.4.0/js/patcher/rom-patcher.wasm", "assets/2.3.0/js/patcher/rom-patcher.wasm"
        cases = [({current: module}, 0), ({current: module + b"extra"}, 1), ({current: module, kept: module}, 0),
                 ({current: module, kept: module + b"extra"}, 1), ({current: module, "other.wasm": module}, 1),
                 ({current: module, "hidden.txt": module}, 1),
                 ({current: module, "js/patcher/rom-patcher.wasm": module}, 1)]
        for files, expected in cases:
            with self.subTest(files=sorted(files), expected=expected), tempfile.TemporaryDirectory() as tmp:
                tree = Path(tmp)
                for name, content in files.items():
                    (tree / name).parent.mkdir(parents=True, exist_ok=True)
                    (tree / name).write_bytes(content)
                # A matching manifest must not admit another module.
                versions = sorted((entry.name for entry in (tree / "assets").iterdir()), reverse=True)
                for version in versions:
                    write_manifest(tree, version)
                write_build(tree, versions[0], versions[1:])
                result, output = checked(site, tree)
                self.assertEqual(result, expected, output)
                self.assertIn(f"wasm         {expected} files\n", output)
                self.assertIn("version      0 files\n", output)


class SiteVersionsTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.tree = Path(temporary.name) / "site"
        self.site = guard()

    def publish(self, *versions, recorded=None):
        for version in versions:
            script = self.tree / "assets" / version / "js/app.js"
            script.parent.mkdir(parents=True, exist_ok=True)
            script.write_text(f"// {version}\n")
            write_manifest(self.tree, version)
        recorded = versions if recorded is None else recorded
        write_build(self.tree, recorded[0], recorded[1:])

    def refused(self, *paths):
        result, output = checked(self.site, self.tree)
        self.assertEqual(result, 1 if paths else 0, output)
        listed = [line.split(None, 1)[1] for line in output.splitlines() if line.startswith("file ")]
        self.assertEqual(listed, list(paths), output)
        self.assertIn(f"version      {len(paths)} files\n", output)

    def test_one_to_three_versions_that_match_their_manifests_pass(self):
        for versions in (["2.6.0"], ["2.6.0", "2.5.0"], ["2.6.0", "2.5.0", "2.4.0"]):
            with self.subTest(versions=versions):
                self.publish(*versions)
                self.refused()

    def test_no_version_and_four_versions_are_refused(self):
        self.tree.mkdir()
        self.refused("site-build.json")
        self.publish("2.6.0", "2.5.0", "2.4.0", "2.3.0")
        self.refused("site-build.json")

    def test_build_record_of_the_earlier_form_or_with_a_repeated_version_is_refused(self):
        self.publish("2.6.0")
        record = self.tree / "site-build.json"
        for doc in ({"id": "0" * 64}, {"id": "0" * 64, "version": "2.6.0"}, {"version": "2.6.0", "kept": "2.5.0"},
                    {"version": "2.6.0", "kept": ["2.6.0"]}, {"version": "../2.6.0", "kept": []}, []):
            with self.subTest(doc=doc):
                record.write_text(json.dumps(doc))
                self.refused("site-build.json")

    def test_folders_and_recorded_versions_must_agree(self):
        self.publish("2.6.0", "2.5.0", recorded=["2.6.0"])
        self.refused("assets/2.5.0")
        self.publish("2.6.0", "2.5.0", recorded=["2.6.0", "2.5.0", "2.4.0"])
        self.refused("assets/2.4.0")

    def test_each_version_is_checked_against_its_manifest(self):
        folder = "assets/2.5.0"
        cases = [
            ("changed", lambda: (self.tree / folder / "js/app.js").write_text("changed"), f"{folder}/js/app.js"),
            ("added", lambda: (self.tree / folder / "js/more.js").write_text("more"), f"{folder}/js/more.js"),
            ("removed", lambda: (self.tree / folder / "js/app.js").unlink(), f"{folder}/js/app.js"),
            ("unlisted", lambda: (self.tree / folder / "files.json").unlink(), f"{folder}/files.json"),
            ("invalid", lambda: (self.tree / folder / "files.json").write_text("[]"), f"{folder}/files.json"),
            ("renamed", lambda: (self.tree / folder / "files.json").write_text(
                (self.tree / "assets/2.6.0/files.json").read_text()), f"{folder}/files.json"),
        ]
        for name, damage, path in cases:
            with self.subTest(name=name):
                self.publish("2.6.0", "2.5.0")
                self.refused()
                damage()
                self.refused(path)
                for extra in (self.tree / folder / "js").glob("more.js"):
                    extra.unlink()

    def test_assembled_site_with_kept_versions_passes_until_a_kept_file_changes(self):
        root = self.tree.parent
        (root / "data").mkdir()
        (root / "data/languages.json").write_text(json.dumps({"bundle": "check.zip", "profiles": [], "languages": []}))
        previous = None
        for version in ("2.4.0", "2.5.0", "2.6.0", "2.7.0"):
            out = root / version
            args = SimpleNamespace(data=root / "data", out=out, public_base="https://site.test", previous=previous)
            with mock.patch("gen3tl.__version__", version), contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(site_assemble(args), 0, output.getvalue())
            previous = out
        self.assertEqual(sorted(path.name for path in (out / "assets").iterdir()), ["2.5.0", "2.6.0", "2.7.0"])
        self.tree = out
        self.refused()
        (out / "assets/2.5.0/site.css").write_text("changed")
        self.refused("assets/2.5.0/site.css")


if __name__ == "__main__":
    unittest.main()
