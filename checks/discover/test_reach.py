import unittest
from pathlib import Path

from gen3tl.discover.reach import Thumb, unused_entries
from gen3tl.discover.scan import pointer_index

from rom_support import needs_rom, rom_path
from project_fixture import UNBOUND
from test_roots import PROJECT_ROOT

class StoredStudyTest(unittest.TestCase):
    """A narrower run keeps the stored build/reach.json."""


    def test_reach_command_writes_only_when_allowed(self):
        import contextlib, io, json, os, tempfile
        from argparse import Namespace
        from unittest.mock import patch

        from gen3tl.cli import discover as cli
        stored = {"strings": {"s1": {}, "s2": {}, "s3": {}}}
        with tempfile.TemporaryDirectory() as d, contextlib.ExitStack() as stack:
            cwd = os.getcwd()
            os.chdir(d)
            stack.callback(os.chdir, cwd)
            Path("build").mkdir()
            Path("build/reach.json").write_text(json.dumps(stored), encoding="utf-8")
            catalog = {sid: (Path("po", name), None) for sid, name in
                       (("s1", "script/region-1.po"), ("m1", "maps/route.po"), ("s2", "system/menu.po"))}
            for target, value in (("gen3tl.discover.reach.report", "report"), ("gen3tl.discover.inventory.load", {"entries": [{"id": "s1", "offset": 0}]}),
                                  ("gen3tl.profile.profile.Profile.load_rom", None),
                                  ("gen3tl.catalog.catalog.load_catalog", catalog)):
                stack.enter_context(patch(target, return_value=value))
            from gen3tl.discover.flow_facts import collect, project
            facts = collect("reach", {"strings": {"s1": {"class": "unknown"}}},
                            {"entries": [{"id": "s1", "offset": 0}]}, {})
            run = stack.enter_context(patch("gen3tl.discover.reach.discover", return_value=facts))
            stack.enter_context(patch("gen3tl.discover.reach.render", side_effect=lambda result, *_: project(result)))
            stack.enter_context(patch("gen3tl.discover.reach.to_json", side_effect=lambda r: r))
            args = Namespace(profile=str(UNBOUND / "profile"), rom=None, group=None, allow_fewer=False,
                             project=Namespace(build=Path("build"), catalog=Path("po")))
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()) as err:
                self.assertEqual(cli.reach(args), 1)
            self.assertEqual(run.call_args.args[3:], (["s1"], ["s2"]))   # every script and system entry
            self.assertIn("error        ", err.getvalue())
            self.assertEqual(json.loads(Path("build/reach.json").read_text(encoding="utf-8")), stored)
            args.allow_fewer = True
            with contextlib.redirect_stdout(io.StringIO()):
                cli.reach(args)
            self.assertEqual(list(json.loads(Path("build/reach.json").read_text(encoding="utf-8"))["strings"]), ["s1"])


ROOT = PROJECT_ROOT


@needs_rom
class BaseRomCodeReachTest(unittest.TestCase):
    """On the base ROM: the loads of unreached code do not count."""

    @classmethod
    def setUpClass(cls):
        from gen3tl.discover import inventory as inv_mod
        from gen3tl.profile.profile import Profile
        from gen3tl.discover.reach import code_refs
        prof = Profile.by_name("unbound-2.1.1.1")
        rom = prof.load_rom(rom_path())
        inv = inv_mod.load(ROOT / "build" / "inventory.json")
        nc = bytearray(len(rom.data))
        for e in inv["entries"]:
            if e["kind"] == "pointer":
                nc[e["offset"]:e["offset"] + e["length"]] = b"\x01" * e["length"]
        cls.th = Thumb(rom.data, pointer_index(rom), nc, unused_entries(prof))
        cls.refs = code_refs(prof)

    def test_placeholder_getters_are_unreached(self):
        # FD 07-FD 0D read Unbound's getters instead
        for ldr in range(0x91A8, 0x91E0, 8):
            with self.subTest(ldr=hex(ldr)):
                self.assertEqual((self.th.reached[ldr], self.th.load(ldr + 4)), (0, None))

    def test_code_after_hook_jumps_is_unreached(self):
        # dungeon getters, BufferStringBattle: ldr / bx at entry
        for entry, pool in ((0xC18E0, 0xC1904), (0xC1920, 0xC1940), (0xD7274, 0xD73F8)):
            with self.subTest(entry=hex(entry)):
                self.assertEqual(self.th.reached[entry], 1)
                self.assertIsNone(self.th.load(pool))

    def test_unused_specials_are_unreached(self):
        # specials 0x94 / 0x95 ([[reach.unused_entries]])
        for at in (0xCA6DC, 0xCA714):
            with self.subTest(at=hex(at)):
                self.assertEqual(self.th.reached[at], 0)

    def test_live_code_still_counts(self):
        # the special handler, a used special; jump tables; callasm
        for at in (0x69EFC, 0xCB7C4, 0xF3EC6, 0x1EBFF94, 0x1ECC0C4, 0x9B7B06):
            with self.subTest(at=hex(at)):
                self.assertEqual(self.th.reached[at], 1)

    def test_declared_code_references_are_loaded(self):
        # the FireRed trade scene code is dead (review)
        dead = {"s026CF8C"}
        for kind, pools, ids in self.refs:
            with self.subTest(ids=ids[:2]):
                loaded = any(self.th.load(p) is not None for p in pools)
                self.assertEqual(loaded, ids[0] not in dead)
