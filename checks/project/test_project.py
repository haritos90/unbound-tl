import hashlib
import io
import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from gen3tl.build.release import game_title, release_names
from gen3tl.cli import main as cli
from gen3tl.catalog.po import PoEntry, write
from gen3tl.profile.profile import Profile
from gen3tl.project import Manifest, Registry, build_scope

from rom_support import source_text, needs_rom, rom_path
from project_fixture import UNBOUND, copy_policy

VROOM = {"id": "s1EDD100", "offset": 32362752, "length": 38, "kind": "pointer", "category": "script",
         "mode": "field", "text": "",
         "refs": [{"at": 31792455, "kind": "script:loadpointer"}, {"at": 31792478, "kind": "script:loadpointer"}],
         "table": None, "index": None, "flags": [],
         "mode_evidence": {"fallback_reasons": ["default-field"], "fallback_mode": "field",
                           "reference_kinds": ["script:loadpointer"], "rule": "script-text-only"}}


@needs_rom
class BuildScopeCommandTest(unittest.TestCase):
    """Each kind of command reads and writes the build documents of the scope, from another working directory."""

    def setUp(self):
        from gen3tl.lang import language, termbase
        self.entry = {**VROOM, "text": source_text("s1EDD100")}
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name).resolve()
        self.root, self.work, self.elsewhere = base / "project", base / "work", base / "elsewhere"
        for directory in (self.root, self.work, self.elsewhere):
            directory.mkdir()
        (self.root / "projects.toml").write_text(
            '[defaults]\nprofile = "unbound-2.1.1.1"\nlanguage = "ru"\n\n[[project]]\nprofile = "unbound-2.1.1.1"\n'
            'language = "ru"\nroot = "."\npolicy = "policy.toml"\n', encoding="utf-8")
        copy_policy(self.root)
        sha1 = Profile.by_name("unbound-2.1.1.1").sha1
        identity = {"profile": "unbound-2.1.1.1", "rom_sha1": sha1}
        documents = {"inventory": {**identity, "entries": [self.entry]},
                     "context": {**identity, "maps": {}, "strings": {self.entry["id"]: {"uses": [], "speakers": []}}},
                     "reach": {**identity, "strings": {self.entry["id"]: {"class": "unreachable", "group": "script"}}}}
        for name, doc in documents.items():
            (self.work / f"{name}.json").write_text(json.dumps(doc), encoding="utf-8")
        translation = self.root / "translation"
        write(translation / "po/script.po", [PoEntry(self.entry["id"], self.entry["text"], "  ВРУМ   ВРУМ\\pЧёрный Ферроторн!")],
              {"Project-Id-Version": "unbound-2.1.1.1", "Language": "ru"})
        (translation / "release.toml").write_text('version = "0.1.0"\n', encoding="utf-8")
        gym = {f"{case}.{number}": "гим" for case in termbase.CASES for number in ("sing", "plur")}
        stadium = {key: "стадион" for key in gym}
        self.replacement = base / "replacement.tsv"
        with language.use("ru"):
            termbase.save(translation / "glossary.tsv", [termbase.Term("term:gym", "term", "Gym", "гим",
                                                                       declension="manual", forms=gym)])
            termbase.save(self.replacement, [termbase.Term("term:gym", "term", "Gym", "стадион",
                                                           declension="manual", forms=stadium)])
        self.batch = translation / "batches/scope"
        self.export = base / "export.json"
        self.export.write_text(json.dumps({"profile": "unbound-2.1.1.1", "language": "ru", "entries": [
            {"id": self.entry["id"], "source_text": self.entry["text"], "translation": "  ВРУМ   ВРУМ\\pЧёрный Ферроторн!"}]},
            ensure_ascii=False), encoding="utf-8")
        profile = Profile.by_name("unbound-2.1.1.1")
        self.build_name = release_names(game_title(profile), "ru", "0.1.0").output
        self.converter = f"{profile.output_stem('ru')}-save-convert.py"

    def identified_base(self, name="base.gba"):
        path = self.work / name
        shutil.copyfile(rom_path(), path)
        profile = Profile.by_name("unbound-2.1.1.1")
        identity = {"profile": profile.name, "language": "ru", "rom_sha1": profile.sha1,
                    "built_sha1": hashlib.sha1(path.read_bytes()).hexdigest()}
        path.with_suffix(".project.json").write_text(json.dumps(identity), encoding="utf-8")
        return path

    def scoped(self, *argv, code=0):
        """Run from another directory without writing outside the scope."""
        out = io.StringIO()
        caller_files = sorted(self.elsewhere.rglob("*"))
        with build_scope(self.work), redirect_stdout(out), redirect_stderr(out):
            previous = Path.cwd()
            try:
                os.chdir(self.elsewhere)
                result = cli.main(["--project-root", str(self.root), "--profile", str(UNBOUND / "profile"),
                                   "--lang", "ru", "--rom", str(rom_path()), *argv])
            finally:
                os.chdir(previous)
        self.assertEqual(result or 0, code, out.getvalue())
        self.assertNotIn(f"missing      {self.work}", out.getvalue())
        self.assertFalse((self.root / "build").exists())
        self.assertEqual(sorted(self.elsewhere.rglob("*")), caller_files)
        return out.getvalue()

    def test_catalog_export_reads_the_inventory_context_and_reach(self):
        self.scoped("catalog", "export")

    def test_batch_plan_reads_the_context_and_defers_by_the_reach(self):
        self.scoped("catalog", "batch-plan")

    def test_batch_export_reads_the_inventory(self):
        self.scoped("catalog", "batch-export", "scope", "--ids", self.entry["id"])

    def test_check_qa_reads_the_inventory_and_writes_its_reports(self):
        self.scoped("check", "qa")
        for name in ("qa-report.md", "inserted-width-report.md"):
            self.assertTrue((self.work / name).is_file(), name)

    def test_check_batch_reads_the_inventory(self):
        self.scoped("catalog", "batch-export", "scope", "--ids", self.entry["id"])
        (self.batch / "translation.json").write_text(json.dumps({self.entry["id"]: "ВРУМ"}, ensure_ascii=False),
                                                     encoding="utf-8")
        self.scoped("check", "batch", "scope")
        with patch.object(Profile, "load_rom", side_effect=FileNotFoundError(2, "missing", "absent.gba")) as load_rom:
            self.assertIn("absent.gba", self.scoped("check", "batch", "scope", code=1))
            load_rom.assert_called_once()

    def test_check_coverage_defaults_to_the_scope(self):
        self.scoped("check", "coverage", "--built", str(self.identified_base()), code=1)   # the base ROM leaves entries open
        self.assertTrue((self.work / "coverage-report.md").is_file())

    def test_lang_rename_reads_the_inventory(self):
        self.scoped("lang", "rename", "term:gym", "стадион", "--replacement-glossary", str(self.replacement))

    def test_web_import_reads_the_inventory(self):
        self.scoped("web", "import", str(self.export), "--dry-run")

    def test_build_and_patch_default_to_the_scope(self):
        from gen3tl.build.graphics import GraphicsConfig
        with patch.object(GraphicsConfig, "from_profile", return_value=GraphicsConfig({}, self.root)):
            self.scoped("build", "rom", "--no-font", "--no-keyboard", "--no-graphics")
        self.scoped("build", "patch")
        for name in (f"{self.build_name}.gba", f"{self.build_name}.ups", self.converter,
                     "build-report.md", "release-notes.md"):
            self.assertTrue((self.work / name).is_file(), name)

    def test_coverage_reads_the_default_build_and_caller_relative_documents(self):
        self.identified_base(f"{self.build_name}.gba")
        for name in ("inventory", "context"):
            shutil.copyfile(self.work / f"{name}.json", self.elsewhere / f"{name}.json")
        self.scoped("check", "coverage", "--inventory", "inventory.json", "--context", "context.json", code=1)
        self.assertTrue((self.work / "coverage-report.md").is_file())

    def test_font_build_and_previews_default_to_the_scope(self):
        self.scoped("build", "font")
        self.scoped("build", "font-preview", "--scale", "1", "ABC")
        self.scoped("build", "font-compare", "--scale", "1", "--pairs", "A:A")
        self.assertTrue((self.work / "font-only.gba").is_file())
        self.assertEqual(len(list((self.work / "preview").glob("font-*.png"))), 2)

    def test_graphics_extraction_defaults_to_the_scope(self):
        from gen3tl.build.graphics import Graphic, GraphicsConfig, Sheet
        graphic = Graphic("G01", 0, False, 32, 32, 1, 4, "", [], True)
        sheet = Sheet(graphic, 1, [[0] * 8 for _ in range(8)], [(255, 255, 255)] * 16, "fixture", bytes(32))
        config = GraphicsConfig({}, self.root)
        with patch.object(GraphicsConfig, "from_profile", return_value=config), \
                patch.object(config, "graphic", return_value=graphic), patch.object(config, "sheet", return_value=sheet):
            self.scoped("build", "gfx-extract", "G01")
        for name in ("G01.png", "G01.json"):
            self.assertTrue((self.work / "graphics/edit" / name).is_file(), name)

    def test_catalog_reports_default_to_the_scope(self):
        self.scoped("catalog", "tm")
        self.scoped("catalog", "progress", "--markdown")
        for name in ("tm-report.md", "progress.md"):
            self.assertTrue((self.work / name).is_file(), name)

    def test_unmeasured_and_box_render_default_to_the_scope(self):
        self.scoped("check", "unmeasured")
        self.scoped("catalog", "batch-export", "scope", "--ids", self.entry["id"])
        (self.batch / "translation.json").write_text(json.dumps({self.entry["id"]: "ВРУМ"}, ensure_ascii=False),
                                                     encoding="utf-8")
        self.scoped("check", "render", "scope", "--scale", "1")
        for name in ("unmeasured-report.md", "screens/scope-boxes.png"):
            self.assertTrue((self.work / name).is_file(), name)

    def test_language_outputs_default_to_the_scope(self):
        self.scoped("lang", "fill-tables")
        self.scoped("lang", "sprite-sheet", "--scale", "1")
        self.assertTrue((self.work / "fill-missing.tsv").is_file())
        self.assertTrue(list((self.work / "preview").glob("sprite-*.png")))

    def test_discovery_defaults_to_the_scope_without_activating_the_project(self):
        from gen3tl.core.rom import Rom
        with patch.object(Profile, "load_rom", return_value=Rom(b"\xff" * 64)), \
                patch("gen3tl.project.Project.activate", side_effect=AssertionError("translation project")):
            self.scoped("discover", "candidates")
        self.assertTrue((self.work / "discovery/unbound-2.1.1.1/candidates.json").is_file())

    def test_screens_and_saves_default_to_the_scope(self):
        from types import SimpleNamespace

        from gen3tl.check.render import Canvas, write_png
        scenario = self.elsewhere / "sample.txt"
        scenario.write_text("wait 1\n", encoding="utf-8")

        def run_scenario(rom, script, out, tag, **kwargs):
            write_png(out / f"{tag}-sample.png", Canvas(2, 2).px)

        def subprocess_run(argv, **kwargs):
            exec(argv[2], {})
            return SimpleNamespace(returncode=0)

        def make_fixture(rom, layout, out, state):
            out.mkdir(parents=True, exist_ok=True)
            path = out / "fixture.sav"
            path.write_bytes(b"save fixture")
            return path

        def check_save(rom, save, out):
            out = Path(out)
            out.mkdir(parents=True, exist_ok=True)
            path = out / "field.png"
            write_png(path, Canvas(2, 2).px)
            return [path]

        def record_presses(rom, state, presses, out):
            out.mkdir(parents=True, exist_ok=True)
            write_png(out / "000.png", Canvas(2, 2).px)

        pairs = self.elsewhere / "dialogue.tsv"
        pairs.write_text("name\tsource\ttranslated\nopening\t0\t0\n", encoding="utf-8")
        built = self.identified_base()
        with patch("gen3tl.verify.headless.run_scenario", side_effect=run_scenario), \
                patch("gen3tl.verify.headless.record_presses", side_effect=record_presses), \
                patch("gen3tl.verify.savefixture.check_save", side_effect=check_save), \
                patch("gen3tl.verify.savefixture.battle_session"), \
                patch("gen3tl.verify.savefixture.pc_session"), \
                patch("subprocess.run", side_effect=subprocess_run):
            self.scoped("verify", "shots", "sample.txt", "--built", str(built))
            self.scoped("verify", "story", "dialogue.tsv", "--state", "fixture", "--presses", "1",
                        "--built", str(built))
            self.scoped("verify", "ui-shots", "--base-save", "original.sav", "--translated-save", "translated.sav",
                        "--built", str(built))
        with patch("gen3tl.verify.savefixture.make_fixture", side_effect=make_fixture):
            self.scoped("verify", "save-fixture")
        with patch("gen3tl.verify.savefixture.check_save", side_effect=check_save):
            self.scoped("verify", "save-check", str(self.work / "saves/fixture.sav"), "--game-rom", str(rom_path()))
        for name in ("screens/sample/base-sample.png", "screens/dialogue/base/000.png", "screens/ui/base/field.png",
                     "screens/sample/sheet.png", "screens/dialogue/sheet.png", "screens/ui/sheet.png",
                     "saves/fixture.sav", "saves/check/field.png"):
            self.assertTrue((self.work / name).is_file(), name)

    def test_pokedex_defaults_to_the_build_scope(self):
        from gen3tl.data import pokedexlabels
        profile = Profile.by_name("unbound-2.1.1.1")
        project = Registry.load(UNBOUND).resolve(profile, "ru")
        profile.data["pokedex"]["labels"] = pokedexlabels.load(profile["pokedex"]["labels"],
                                                             project.pokedex_labels)
        with patch.object(Profile, "by_name", return_value=profile):
            self.scoped("data", "pokedex")
        self.assertTrue((self.work / "pokedex/unbound-2.1.1.1/pokedex.json").is_file())

    def test_pokedex_defaults_to_the_game_dataset(self):
        from gen3tl import __version__
        translation = self.root / "translation"
        translation.rename(self.root / "language")
        translation.mkdir()
        (self.root / "language").rename(translation / "ru")
        manifest = self.root / "project.toml"
        manifest.write_text(Manifest(manifest, "unbound-2.1.1.1", Profile.by_name("unbound-2.1.1.1").sha1,
                                     __version__, ("ru",), "ru").text(), encoding="utf-8")
        source = Registry.load(UNBOUND).resolve("unbound-2.1.1.1", "ru").pokedex_labels
        target = Registry.load(self.root).resolve("unbound-2.1.1.1", "ru").pokedex_labels
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        self.scoped("data", "pokedex")
        self.assertTrue((self.root / "data/pokedex/pokedex.json").is_file())
        self.assertFalse((self.work / "pokedex").exists())

    def test_web_data_defaults_to_the_scope(self):
        self.scoped("web", "data")
        doc = json.loads((self.work / "editor/ru.json").read_text(encoding="utf-8"))
        self.assertEqual(len(doc["entries"]), 1)

    def test_partial_inventory_supports_snapshot_and_offline_data(self):
        snapshot = self.work / "scope.snapshot.json"
        self.scoped("web", "snapshot", "--out", str(snapshot))
        self.scoped("web", "data", "--no-rom", "--snapshot", str(snapshot))
        doc = json.loads((self.work / "editor/ru.json").read_text(encoding="utf-8"))
        self.assertEqual(len(doc["entries"]), 1)

    def test_commands_preserve_projects_without_declared_substitution_sources(self):
        from project_fixture import recorded_substitutions
        select = Profile.by_name
        with patch.object(Profile, "by_name", side_effect=lambda *args: recorded_substitutions(select(*args))):
            self.test_check_qa_reads_the_inventory_and_writes_its_reports()
            self.test_check_batch_reads_the_inventory()
            self.test_build_and_patch_default_to_the_scope()
            self.test_web_data_defaults_to_the_scope()
            self.test_partial_inventory_supports_snapshot_and_offline_data()
