from pathlib import Path
import tempfile
import unittest
import re
from unittest import mock

from gen3tl.check import qa
from gen3tl.lang.langpack import LangPack
from gen3tl.check.layout import Measure
from gen3tl.catalog.po import PoEntry, write

from rom_support import needs_rom, rom_path
from project_fixture import select_language, recorded_substitutions, shared_profiles, UNBOUND, copy_policy, copy_profile, unbound

PACK = LangPack.load("ru", "unbound")

def setUpModule():
    global recorded_window_limits
    unittest.enterModuleContext(shared_profiles())
    select_language("ru")
    compute = qa.compute_limits
    recorded_window_limits = mock.patch.object(qa, "compute_limits", lambda prof, *args, **kwargs:
        compute(recorded_substitutions(prof), *args, **kwargs))
    recorded_window_limits.start()

def tearDownModule():
    recorded_window_limits.stop()

def entry(sid, text, flags=()):
    return {"id": sid, "offset": int(sid[1:], 16), "length": len(text) + 1, "kind": "pointer",
            "category": "script", "mode": "field", "text": text, "table": None, "index": None,
            "refs": [{"at": 0x10, "kind": "script:loadpointer"}], "flags": list(flags)}

def tabled(sid, text, *at):
    """A description referenced from pointer-table positions `at`."""
    e = entry(sid, text)
    e.update(category="data-table", refs=[{"at": a, "kind": "table"} for a in at])
    return e

class TableWindowTest:
    """Window measured for every string of a pointer table ([[layout.table_window]])."""

    PROF = {"layout": {
        "table_window": [{"name": "descs", "base": 0x1000, "stride": 4, "count": 4, "width": 30},
                         {"name": "other", "base": 0x2000, "stride": 8, "count": 1, "fields": [4], "width": 24}],
        "window_width": {"s0000400": 42}}}

    INV = {"entries": [tabled("s0000100", "Ab", 0x1000), tabled("s0000200", "Abc", 0x1008),
                       tabled("s0000300", "Abcdefghij", 0x1010),      # past the table's count
                       tabled("s0000400", "Ab", 0x1004),              # its own window_width
                       tabled("s0000500", "Ab", 0x100C, 0x2004),      # in both tables
                       tabled("s0000600", "Abcdef", 0x2000)]}         # not a text pointer field

def fixed(sid, text, table="names"):
    return {"id": sid, "offset": 0, "length": 11, "kind": "fixed", "category": f"table:{table}", "mode": "field",
            "text": text, "table": table, "index": int(sid.split(":")[1]), "refs": [], "flags": []}

def scripted(sid, text, kind="script:message"):
    e = entry(sid, text)
    e["refs"] = [{"at": 0x10, "kind": kind}]
    return e

def slot(*fills, uses=1, unfilled=0):
    return {"slots": {"{STR_VAR_1}": {"fills": [list(f) for f in fills], "uses": uses, "unfilled": unfilled}},
            "slot_refs": {"unwalked": 0, "code": 0}}

def battle(sid, text):
    e = entry(sid, text)
    e.update(category="battle-script", refs=[{"at": 0x10, "kind": "script:setword"}])
    return e

class BoxWidthTest:
    """Dialogue and battle limits never exceed the measured box width."""

    PROF = {"layout": {"dialogue_width": 60, "battle_width": 60,
                       "box_width": {"dialogue": 100, "sign": 90, "battle": 120},
                       "window_width": {"s0000500": 150}}}

    INV = {"entries": [entry("s0000100", "A" * 20),               # 120 px
                       entry("s0000200", "B" * 20),               # 120 px, shown on a sign
                       entry("s0000300", "Short"),                # 30 px
                       battle("s0000400", "C" * 25),              # 150 px
                       battle("s0000450", "D" * 18),              # 108 px
                       entry("s0000500", "E" * 20),               # a window measured for the id
                       entry("s0000600", "F" * 25 + "\\nG\\nH")]}  # three lines without scrolling

    CTX = {"strings": {"s0000100": {"uses": [{"event": "npc", "box": "default"}]},
                       "s0000200": {"uses": [{"event": "sign", "box": "yesno"}]}}}

    def limits(self, prof, ctx=None):
        from gen3tl.catalog.catalog import load_catalog
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / "a.po", [PoEntry(x["id"], x["text"], "") for x in self.INV["entries"]], {})
            lim = qa.compute_limits(prof, self.INV, load_catalog(root), Measure(lambda b: 6, {}), PACK.charmap(), ctx)
        return {sid: (l.kind, l.width) for sid, l in lim.items()}


def batch_messages(output):
    """Associate diagnostics with their entry identifiers."""
    messages = []
    entry_id = None
    for call in output.call_args_list:
        if not call.args:
            continue
        text = str(call.args[0])
        label, value = text.split(None, 1)
        # Window binding has separate coverage.
        value = re.sub(r"; window .*?(?= \(prefix | \[(?:unmeasured|unverified)|$)", "", value)
        if label == "entry":
            entry_id = value
        elif label in ("error", "warning") or label == "never" and value.startswith("reach:"):
            if entry_id is None:
                raise AssertionError(f"diagnostic without entry: {text}")
            messages.append(f"{entry_id}: {value}")
        else:
            messages.append(text)
    return messages


def assert_never_shown_groups(test, profile, tagged, groups):
    rows = profile.get("reach", {}).get("never_shown", [])
    selected = []
    for ids in groups:
        ids = list(ids)
        matches = [index for index, row in enumerate(rows) if ids[0] in row["ids"]]
        test.assertEqual(len(matches), 1, ids[0])
        index = matches[0]
        row = rows[index]
        test.assertLessEqual(set(ids), set(row["ids"]))
        test.assertTrue(row["evidence"].strip(), ids[0])
        expected = "review: " + " ".join(row["evidence"].splitlines())
        for sid in ids:
            test.assertEqual(tagged.get(sid), expected, sid)
        selected.append(index)
    test.assertEqual(len(set(selected)), len(selected))
    return [rows[index] for index in selected]


ROOT = UNBOUND


def batch_project(root):
    """Resolve isolated batches through their game project."""
    from gen3tl.project import Registry

    manifest = copy_profile(root)
    (root / "projects.toml").write_text(
        f'[defaults]\nprofile = "{manifest.profile}"\nlanguage = "{manifest.default_language}"\n'
        f'[[project]]\nprofile = "{manifest.profile}"\nlanguage = "{manifest.default_language}"\n'
        'root = "."\npolicy = "policy.toml"\n', encoding="utf-8")
    copy_policy(root, root)
    return Registry.load(root).resolve(manifest.profile)


@needs_rom
class LabelWindowTest(unittest.TestCase):
    """Label windows measured in game."""


    CASES = {
        "s1F5607D": (32, "unbound-small", "Готово", True),
        "s1F56082": (32, "unbound-small", "Поймано", False),
        "s1F5609A": (171, None, "Назад", True),
        "s1F81E49": (69, None, "День рождения", False),
        "s1F81E59": (111, None, "Покедекс", True),
        "s1F81E61": (93, None, "Время", True),
        "s1F80B7C": (120, "unbound-small", "{F8 0C}Ход {F8 00}Взять {F8 01}Выход", True),
        "s1F85ED4": (77, None, "сильный", True),   # room its host s1F85CB5 leaves
        "s1F8F60A": (118, None, "песчаная буря", True),
    }
    MESSAGES = ["s1F56082: line too wide: 36 > 32 px: 'Поймано'",
                "s1F81E49: line too wide: 77 > 69 px: 'День рождения'"]

    def setUp(self):
        import json
        import os

        from gen3tl.discover import inventory as inv_mod
        inv = inv_mod.load(ROOT / "build" / "inventory.json")
        es = [x for x in inv["entries"] if x["id"] in self.CASES]
        self.assertEqual(len(es), len(self.CASES))
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.cwd = os.getcwd()
        os.chdir(self.root)
        project = batch_project(self.root)
        (self.root / "build").mkdir()
        (self.root / "build" / "inventory.json").write_text(json.dumps({"profile": inv["profile"], "rom_sha1": inv["rom_sha1"], "entries": es}), encoding="utf-8")
        write(self.root / "po" / "a.po", [PoEntry(e["id"], e["text"], "") for e in es],
              {"Project-Id-Version": "unbound-2.1.1.1", "Language": "ru"})
        project.translation.mkdir(parents=True)
        project.release.write_text('version = "0.1.0"\n', encoding="utf-8")
        self.batch = project.batches / "t"
        self.batch.mkdir(parents=True)
        (self.batch / "source.json").write_text(json.dumps([{"id": e["id"], "source_text": e["text"]} for e in es]),
                                                encoding="utf-8")

    def tearDown(self):
        import os
        os.chdir(self.cwd)
        self.tmp.cleanup()

    def test_profile_windows(self):
        from gen3tl.discover import inventory as inv_mod
        from gen3tl.profile.profile import Profile
        prof = unbound()
        inv = inv_mod.load(Path("build/inventory.json"))
        catalog = qa.load_catalog(Path("po"))
        lims = qa.compute_limits(prof, inv, catalog, Measure(lambda b: 6, {}), PACK.charmap(), rom=prof.load_rom(rom_path()))
        self.assertEqual({sid: (l.width, l.style) for sid, l in lims.items()},
                         {sid: (w, s) for sid, (w, s, _, _) in self.CASES.items()})

    def test_natural_forms(self):
        import json

        from gen3tl.__main__ import main
        (self.batch / "translation.json").write_text(
            json.dumps({sid: ru for sid, (_, _, ru, _) in self.CASES.items()}, ensure_ascii=False), encoding="utf-8")
        with mock.patch("builtins.print") as out:
            main(["--rom", str(rom_path()), "check", "batch", "t", "--po-root", "po"])
        lines = batch_messages(out)
        too_wide = {l.split(":")[0] for l in lines if "line too wide" in l and not l.startswith("result ")}
        self.assertEqual(too_wide, {sid for sid, (_, _, _, fits) in self.CASES.items() if not fits}, lines)
        for m in self.MESSAGES:
            self.assertIn(m, lines)


@needs_rom
class SendOutWindowTest(LabelWindowTest):
    """Intro send-out lines print in battle window 0, two lines high."""

    MONS = "{B_OPPONENT_MON1_NAME} и {B_OPPONENT_MON2_NAME}!"
    CASES = {
        "s03FD3B1": (222, None, "{B_TRAINER1_CLASS} {B_TRAINER1_NAME}\\nвыпускает покемона "
                                "{B_OPPONENT_MON1_NAME}!{PAUSE 3C}", True),
        "s03FD3C7": (222, None, "{B_TRAINER1_CLASS} {B_TRAINER1_NAME}\\nвыпускает на поле покемонов\\l"
                     + MONS + "{PAUSE 3C}", False),
        "s03FD3F7": (222, None, "{B_LINK_OPPONENT1_NAME}\\nвыпускает покемона {B_OPPONENT_MON1_NAME}!", True),
        "s03FD407": (222, None, "{B_LINK_OPPONENT1_NAME}\\nвыпускает покемонов\\p" + MONS, False),
    }
    MESSAGES = ["s03FD3C7: too many lines: 3 > 2", "s03FD407: too many lines: 3 > 2"]
    # forms with a scroll, which stops the intro
    SCROLL = {"s03FD3C7": "{B_TRAINER1_CLASS} {B_TRAINER1_NAME}\\nвыпускает покемонов\\l" + MONS + "{PAUSE 3C}",
              "s03FD407": "{B_LINK_OPPONENT1_NAME}\\nвыпускает покемонов\\l" + MONS}
    # the two-line forms that fit
    TWO_LINES = {"s03FD3C7": "{B_TRAINER1_CLASS} {B_TRAINER1_NAME} выпускает\\nпокемонов " + MONS + "{PAUSE 3C}",
                 "s03FD407": "{B_LINK_OPPONENT1_NAME} выпускает покемонов\\n" + MONS}

    def batch_check(self, texts: dict) -> list[str]:
        import json

        from gen3tl.__main__ import main
        (self.batch / "translation.json").write_text(json.dumps(texts, ensure_ascii=False), encoding="utf-8")
        with mock.patch("builtins.print") as out:
            main(["--rom", str(rom_path()), "check", "batch", "t", "--po-root", "po"])
        return batch_messages(out)

    def limits(self, m):
        from gen3tl.discover import inventory as inv_mod
        from gen3tl.profile.profile import Profile
        prof = unbound()
        return qa.compute_limits(prof, inv_mod.load(Path("build/inventory.json")), qa.load_catalog(Path("po")),
                                 m, PACK.charmap(), rom=prof.load_rom(rom_path()))

    def test_profile_windows(self):
        lims = self.limits(Measure(lambda b: 6, {}))
        self.assertEqual({sid: (l.kind, l.width, l.lines) for sid, l in lims.items()},
                         {sid: ("multiline", 222, 2) for sid in self.CASES})

    def test_natural_forms(self):
        """A third line that the two lines cannot take is refused: a scroll or a page."""
        lines = self.batch_check({sid: ru for sid, (_, _, ru, _) in self.CASES.items()})
        errors = {l.split(":")[0] for l in lines if l.startswith("s") and "(warning)" not in l}
        self.assertEqual(errors, {sid for sid, (_, _, _, fits) in self.CASES.items() if not fits}, lines)
        for m in self.MESSAGES:
            self.assertIn(m, lines)

    def test_scroll_laid_out_in_two_lines(self):
        """The approved scroll lays out as the two-line forms, at the game font widths."""
        from gen3tl.build.font import FontTable
        from gen3tl.check.layout import layout
        from gen3tl.profile.profile import Profile
        prof = unbound()
        rom = prof.load_rom(rom_path())
        font = FontTable.from_profile(prof)[0]
        slots = PACK.glyph_slots(rom, font)
        m = Measure(lambda b: slots[b].width if b in slots else font.width(rom, b), prof["layout"]["placeholders"])
        lims = self.limits(m)
        self.assertEqual({sid: layout(t, lims[sid], m, PACK.charmap()) for sid, t in self.SCROLL.items()},
                         self.TWO_LINES)

    def test_two_line_forms(self):
        texts = {sid: ru for sid, (_, _, ru, fits) in self.CASES.items() if fits}
        lines = self.batch_check({**texts, **self.TWO_LINES})
        self.assertEqual([l for l in lines if l.startswith("s")], [], lines)
