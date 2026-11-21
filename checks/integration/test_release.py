import unittest
import json
import hashlib
import os
import tempfile
import tomllib
import zipfile
from pathlib import Path
from unittest import mock

from gen3tl.build import release
from gen3tl.cli.build import build_report_path
from gen3tl import __version__
from gen3tl.__main__ import main
from gen3tl.lang.langpack import LangPack
from gen3tl.catalog.po import PoEntry, write
from gen3tl.profile.profile import Profile
from gen3tl.core.rom import Rom

from rom_support import source_text, needs_rom, rom_path
from project_fixture import UNBOUND, copy_policy, literal

class ReleaseFileTest(unittest.TestCase):


    def test_repository_version(self):
        # releases follow semantic versioning
        repo = UNBOUND
        self.assertTrue(release.SEMVER.fullmatch(release.load(repo / "translation/ru/release.toml")))

class BuildReportPathTest(unittest.TestCase):
    def test_report_beside_a_test_build(self):
        # only the default build writes build/build-report.md
        current = "build/Pokemon Unbound 2.1.1.1 [RU by gen3tl].gba"
        self.assertEqual(build_report_path(current), Path("build/build-report.md"))
        self.assertEqual(build_report_path("build/test/t62.gba"), Path("build/test/t62.report.md"))
        self.assertEqual(build_report_path(Path("/tmp/x/label.gba")), Path("/tmp/x/label.report.md"))


PACK = LangPack.load("ru", "unbound")


CM = PACK.charmap()


def release_file(root: Path, version: str) -> Path:
    path = root / "translation" / "release.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'version = "{version}"\n', encoding="utf-8")
    return path


PROFILE = Profile.by_name("unbound-2.1.1.1")


WELCOME = {"id": "s1F0F5A6", "offset": 0x1F0F5A6, "length": 167, "kind": "pointer", "category": "script",
           "mode": "field", "table": None, "index": None, "flags": [],
           "refs": [{"at": 0x1E6F945, "kind": "script:loadpointer"}]}


WELCOME_RU = ("Добро пожаловать\\nв Pokémon Unbound!\\n\\nПрежде чем начать, учтите: это\\nнекоммерческая "
              "фанатская игра.\\n\\nЕсли вы заплатили за неё, сразу\\nтребуйте деньги назад!\\n"
              "Русская версия @VERSION@")


   # as inventory.build writes it


@needs_rom
class PatchNameTest(unittest.TestCase):
    """Default patches replace fixed filenames and archive every version."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.cwd = os.getcwd()
        os.chdir(self.root)
        (self.root / "projects.toml").write_text('[defaults]\nprofile = "unbound-2.1.1.1"\nlanguage = "ru"\n[[project]]\nprofile = "unbound-2.1.1.1"\nlanguage = "ru"\nroot = "."\npolicy = "policy.toml"\n', encoding="utf-8")
        copy_policy(self.root)
        (self.root / "build").mkdir()
        base = bytearray(0x10000)
        built = self.root / "build" / "t.gba"
        built.write_bytes(bytes(base[:0x100]) + b"\x01" + bytes(base[0x101:]))
        identity = {"profile": "unbound-2.1.1.1", "language": "ru",
                    "rom_sha1": PROFILE.sha1,
                    "built_sha1": hashlib.sha1(built.read_bytes()).hexdigest()}
        built.with_suffix(".project.json").write_text(json.dumps(identity), encoding="utf-8")
        self.rom = mock.patch.object(Profile, "load_rom", return_value=Rom(base))
        self.rom.start()

    def tearDown(self):
        self.rom.stop()
        os.chdir(self.cwd)
        self.tmp.cleanup()

    def patch(self, *extra: str) -> int:
        with mock.patch("builtins.print"):
            return main(["--profile", str(PROFILE.path), "build", "patch", "--built", "build/t.gba", "--notes", "build/notes.md",
                         "--converter", "build/convert.py", *extra])

    def test_a_version_below_one_names_the_default_patch(self):
        release_file(self.root, "0.1.0")
        self.assertEqual(self.patch(), 0)
        self.assertEqual(sorted(p.name for p in (self.root / "build").glob("*.ups")),
                         ["Pokemon Unbound 2.1.1.1 [RU v0.1.0 by gen3tl].ups"])
        notes = (self.root / "build" / "notes.md").read_text(encoding="utf-8")
        self.assertIn("## [RU by gen3tl] 0.1.0", notes)
        self.assertIn("UPS SHA-256:", notes)
        self.assertNotIn("Apply to", notes)

    def test_derived_name_and_cumulative_notes(self):
        name = "Pokemon Unbound 2.1.1.1 [RU by gen3tl]"
        archive_name = "Pokemon Unbound 2.1.1.1 (Previous versions) [RU by gen3tl].zip"
        for version in ("1.0.9", "1.0.10", "1.0.10"):
            release_file(self.root, version)
            self.assertEqual(self.patch("--notes", "build/release-notes.md"), 0)
        notes = (self.root / "build/release-notes.md").read_text()
        self.assertEqual(release.NOTE_HEADING.findall(notes), [("RU by gen3tl", "1.0.10"), ("RU by gen3tl", "1.0.9")])
        self.assertIn("UPS SHA-256:", notes)
        self.assertEqual([p.name for p in (self.root / "build").glob("*.ups")], [f"{name}.ups"])
        self.assertEqual([p.name for p in (self.root / "build").glob("*.zip")], [archive_name])
        with zipfile.ZipFile(self.root / "build" / archive_name) as zf:
            self.assertEqual(sorted(zf.namelist()), [f"{name}-{v}.ups" for v in ("1.0.10", "1.0.9")])

    def test_a_release_file_with_a_name_stops_the_patch(self):
        for key in ("output_name", "archive_name", "release_label"):
            with self.subTest(key=key):
                path = release_file(self.root, "1.0.0")
                path.write_text(path.read_text() + f'{key} = "Pokemon Unbound 2.1.1.1 [Translated]"\n')
                with mock.patch("builtins.print") as output:
                    status = main(["--profile", str(PROFILE.path), "build", "patch", "--built", "build/t.gba",
                                   "--notes", "build/notes.md", "--converter", "build/convert.py"])
                printed = [str(call.args[0]) for call in output.call_args_list if call.args]
                self.assertEqual(status, 1)
                self.assertTrue(printed[-1].endswith(
                    f"release.toml: remove {key}; the release names follow from the game, the language "
                    "and the version"), printed[-1])
        self.assertEqual(list((self.root / "build").glob("*.ups")), [])

    def test_older_patches_share_one_archive(self):
        """All versioned patches are archived, including earlier filenames."""
        build = self.root / "build"
        name = "Pokemon Unbound 2.1.1.1 [RU by gen3tl]"
        (build / "unbound-2.1.1.1-ru-0.0.9.ups").write_bytes(b"legacy patch")
        (build / "stress-test.ups").write_bytes(b"not a version")
        for version in ("1.0.0", "1.0.1", "1.0.2"):
            release_file(self.root, version)
            self.assertEqual(self.patch(), 0)
        self.assertEqual(sorted(p.name for p in build.glob("*.ups")), [f"{name}.ups", "stress-test.ups"])
        with zipfile.ZipFile(build / "Pokemon Unbound 2.1.1.1 (Previous versions) [RU by gen3tl].zip") as zf:
            self.assertEqual(sorted(zf.namelist()), [f"{name}-{v}.ups" for v in ("0.0.9", "1.0.0", "1.0.1", "1.0.2")])
            self.assertEqual(zf.read(f"{name}-0.0.9.ups"), b"legacy patch")

    def test_explicit_path_takes_the_token(self):
        release_file(self.root, "1.0.0")
        self.assertEqual(self.patch("--out", "build/ru-@VERSION@.ups"), 0)
        self.assertTrue((self.root / "build" / "ru-1.0.0.ups").exists())

    def test_missing_or_invalid_version_stops_the_patch(self):
        for version in (None, "0.1"):
            if version:
                release_file(self.root, version)
            with mock.patch("builtins.print") as output:
                status = main(["--profile", str(PROFILE.path), "build", "patch", "--built", "build/t.gba", "--notes", "build/notes.md",
                               "--converter", "build/convert.py"])
            printed = [str(call.args[0]) for call in output.call_args_list if call.args]
            reason = "missing path: " if version is None else "version '0.1' is not MAJOR.MINOR.PATCH"
            self.assertEqual(status, 1)
            self.assertIn(reason, printed[-1])
            self.assertTrue(printed[-1].startswith("result       failed: "))
        self.assertEqual(list((self.root / "build").glob("*.ups")), [])

    def test_history_command_records_only_explicit_gameplay(self):
        data = b"verified build"
        identity = {"profile": "unbound-2.1.1.1", "language": "ru", "rom_sha1": "base",
                    "built_sha1": hashlib.sha1(data).hexdigest()}
        release.preserve_build(data, self.root / "build/unbound-ru.gba", "0.1.0", identity)
        with mock.patch("builtins.print") as output:
            main(["--profile", str(PROFILE.path), "build", "history"])
            self.assertTrue(any("not-recorded" in str(c) for c in output.call_args_list))
            main(["--profile", str(PROFILE.path), "build", "history", "--mark", "0.1.0", "--status", "launched",
                  "--note", "Opened the title screen"])
        records = release.history(self.root / "build/translation-history.json")["versions"]
        self.assertEqual(records[0]["gameplay"], "launched")
        self.assertEqual(len(records[0]["playtests"]), 1)
        with mock.patch("builtins.print") as output:
            status = main(["--profile", str(PROFILE.path), "build", "history", "--mark", "0.1.0"])
        self.assertEqual(status, 1)
        self.assertEqual(str(output.call_args_list[-1].args[0]),
                         "result       failed: --mark requires --status and --note")


@needs_rom
class EveryPlaceTest(unittest.TestCase):
    """One edit of the release file changes the label, QA and patch."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.cwd = os.getcwd()
        os.chdir(self.root)
        (self.root / "projects.toml").write_text('[defaults]\nprofile = "unbound-2.1.1.1"\nlanguage = "ru"\n[[project]]\nprofile = "unbound-2.1.1.1"\nlanguage = "ru"\nroot = "."\npolicy = "translation/ru/policy.toml"\n', encoding="utf-8")
        from gen3tl.profile.profile import Profile
        from gen3tl.project import Manifest
        sha1 = PROFILE.sha1
        (self.root / "project.toml").write_text(Manifest(self.root / "project.toml", "unbound-2.1.1.1", sha1, __version__,
                                                         ("ru",), "ru").text(), encoding="utf-8")
        (self.root / "translation/ru").mkdir(parents=True)
        copy_policy(self.root / "translation/ru", self.root)
        policy_path = self.root / "translation/ru/policy.toml"
        policy = tomllib.loads(policy_path.read_text())
        policy["graphics"] = {
            "edit": [{"id": "G01", "label": "translation/ru/graphics/version-glyphs.json",
                      "form": "areas", "areas": [], "tiles": 259}],
            "tilemap": [{"name": "boot version", "cells": [
                {"row": 18 + y, "column": 1 + x, "tile": 237 + y * 11 + x}
                for y in range(2) for x in range(11)]}]}
        policy_path.write_text("\n".join(f"{k} = {literal(v)}" for k, v in policy.items()))
        assets = self.root / "translation/ru/graphics"
        assets.mkdir(parents=True)
        repository = UNBOUND
        (assets / "version-glyphs.json").write_bytes((repository / "translation/ru/graphics/version-glyphs.json").read_bytes())
        (self.root / "source").mkdir(exist_ok=True)
        (self.root / "source/graphics.toml").write_bytes((repository / "source/graphics.toml").read_bytes())
        (self.root / "build").mkdir()
        (self.root / "build" / "inventory.json").write_text(
            json.dumps({"profile": "unbound-2.1.1.1", "rom_sha1": sha1, "entries": [{**WELCOME, "text": source_text("s1F0F5A6")}]}), encoding="utf-8")
        write(self.root / "po" / "a.po", [PoEntry(WELCOME["id"], source_text("s1F0F5A6"), WELCOME_RU)],
              {"Project-Id-Version": "unbound-2.1.1.1", "Language": "ru"})

    def tearDown(self):
        os.chdir(self.cwd)
        self.tmp.cleanup()

    def release(self, version: str) -> dict:
        (self.root / "translation/ru/release.toml").write_text(f'version = "{version}"\n', encoding="utf-8")
        with mock.patch("builtins.print"):
            built = main(["--rom", str(rom_path()), "--profile", str(PROFILE.path), "build", "rom", "--po-root", "po", "--no-font", "--out", "build/t.gba"])
            checked = main(["--rom", str(rom_path()), "--profile", str(PROFILE.path), "check", "qa", "--po-root", "po"])
            patched = main(["--rom", str(rom_path()), "--profile", str(PROFILE.path), "build", "patch", "--built", "build/t.gba", "--notes", "build/notes.md",
                            "--converter", "build/convert.py"])
        out = {"rom": (self.root / "build" / "t.gba").read_bytes(),
               "report": (self.root / "build" / "t.report.md").read_text(encoding="utf-8"),
               "qa": (self.root / "build" / "qa-report.md").read_text(encoding="utf-8"),
               "notes": (self.root / "build" / "notes.md").read_text(encoding="utf-8"),
               "patches": sorted(p.name for p in (self.root / "build").glob("*.ups"))}
        self.assertEqual((built, checked, patched), (0, 0, 0), out["report"])
        self.assertFalse((self.root / "build" / "build-report.md").exists())   # the release report is untouched
        return out

    def page(self, rom: bytes, version: str) -> bytes:
        at = int.from_bytes(rom[0x1E6F945:0x1E6F949], "little") - 0x08000000   # the loadpointer operand
        return rom[at:at + len(CM.encode(release.expand(WELCOME_RU, version)))]

    def test_a_translated_entry_is_built_and_patched_like_an_approved_one(self):
        write(self.root / "po" / "a.po",
              [PoEntry(WELCOME["id"], source_text("s1F0F5A6"), WELCOME_RU, flags=["fuzzy"])],
              {"Project-Id-Version": "unbound-2.1.1.1", "Language": "ru"})
        out = self.release("0.1.0")
        self.assertEqual(self.page(out["rom"], "0.1.0"), CM.encode(release.expand(WELCOME_RU, "0.1.0")))
        self.assertIn("| catalog: included | 1 |", out["report"])
        self.assertIn("| catalog: translated | 1 |", out["report"])
        self.assertNotIn("| catalog: approved |", out["report"])
        self.assertIn("Pokemon Unbound 2.1.1.1 [RU v0.1.0 by gen3tl].ups", out["patches"])

    def test_one_edit_changes_every_place(self):
        from gen3tl.build.graphics import lz77_decompress
        previous_picture = None
        for version, old in (("0.1.0", None), ("0.2.1", "0.1.0")):
            out = self.release(version)
            # page as written: nine lines, the last with the version
            self.assertEqual(self.page(out["rom"], version), CM.encode(release.expand(WELCOME_RU, version)))
            self.assertIn("| catalog: included | 1 |", out["report"])
            self.assertIn("| catalog: approved | 1 |", out["report"])
            self.assertNotIn("| catalog: translated |", out["report"])
            self.assertIn("| skipped by layout check | 0 |", out["report"])
            self.assertIn(f"Translation version: {version}", out["report"])
            self.assertIn("Entries checked: 1; errors: 0", out["qa"])
            self.assertIn(f"Pokemon Unbound 2.1.1.1 [RU v{version} by gen3tl].ups", out["patches"])
            self.assertIn(f"## [RU by gen3tl] {version}", out["notes"])
            self.assertIn("UPS SHA-256:", out["notes"])
            at = int.from_bytes(out["rom"][0xEC610:0xEC614], "little") - 0x08000000
            picture = lz77_decompress(out["rom"], at)[0]
            self.assertEqual(len(picture), 259 * 32)
            if previous_picture is not None:
                self.assertEqual(picture[:237 * 32], previous_picture[:237 * 32])
                self.assertNotEqual(picture[237 * 32:], previous_picture[237 * 32:])
            previous_picture = picture
            if old is not None:
                self.assertNotIn(CM.encode(f"Русская версия {old}", terminate=False), out["rom"])
                self.assertNotIn(old, out["report"])
                self.assertIn(f"## [RU by gen3tl] {old}", out["notes"])
