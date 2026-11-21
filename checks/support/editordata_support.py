from pathlib import Path
import tempfile
import unittest
import re

from gen3tl import __version__
from gen3tl.web import editordata
from gen3tl.check import qa
from gen3tl.catalog.catalog import load_catalog
from gen3tl.lang.langpack import load_styles
from gen3tl.check.layout import Measure
from gen3tl.catalog.po import PoEntry, write
from gen3tl.profile.profile import Profile
from gen3tl.lang.termbase import Term

from test_roots import TOOLKIT_ROOT
from project_fixture import shared_profiles

ROOT = TOOLKIT_ROOT


def setUpModule():
    unittest.enterModuleContext(shared_profiles())

PROF = Profile({
    "rom": {"sha1": "ab" * 20},
    "maps": {"mapsec_names": 0x200000, "mapsec_count": 3},
    "font": [{"name": "font0", "glyphs": 0x1000, "widths": 0x9000, "count": 512},
             {"name": "small", "glyphs": 0xA000, "widths": 0xE000, "count": 512, "style": "unbound-small",
              "format": "8x16"}],
    "font_style": {"style": "unbound", "cell_height": 14},
    "font_styles": {"unbound-small": {"top": 1, "rows": 12}},
    "layout": {"dialogue_width": 208, "placeholders": {"PLAYER": 42, "STR_VAR_1": 60},
               "window_width": {"s0000300": 76}},
    "table": [{"name": "species", "base": 0x5000, "stride": 11, "count": 2, "field_offset": 0, "field_length": 11,
               "windows": [{"style": "unbound", "width": 60, "where": "summary"},
                           {"style": "unbound-small", "width": 51, "where": "health box",
                            "entries": {"species:1": 56}}]}],
}, Path("test.toml"))

def entry(sid, text, kind="script:loadpointer", category="script"):
    return {"id": sid, "offset": int(sid[1:], 16), "length": len(text) + 1, "kind": "pointer",
            "category": category, "mode": "field", "text": text, "table": None, "index": None,
            "refs": [{"at": 0x10 + int(sid[1:], 16), "kind": kind}], "flags": []}

INV = {"entries": [
    entry("s0000100", "Hi, {PLAYER}! Take this {STR_VAR_1}."),
    entry("s0000200", "Potion", "script:bufferstring"),
    entry("s0000300", "Bag", "table", "data-table"),
    entry("s0000400", "Potion"),
    entry("s0000500", "Potion"),
    entry("s0000600", "s"),
    {**entry("s0000900", "Bellin Town", "table", "data-table"), "refs": [{"at": 0x200004, "kind": "table"}]},
    entry("s0000A00", "Sally", "table", "table:trainer_names"),
    {"id": "species:1", "offset": 0x5000 + 11, "length": 11, "kind": "fixed", "category": "table:species",
     "mode": "field", "text": "Ivysaur", "table": "species", "index": 1, "refs": [], "flags": []},
]}

CTX = {"strings": {
    "s0000100": {"uses": [], "inferred_map": None, "speakers": [],
                 "slots": {"{STR_VAR_1}": {"fills": [["string", "s0000200"]], "uses": 1, "unfilled": 0}},
                 "slot_refs": {"unwalked": 0, "code": 0}},
    "s0000200": {"uses": [], "inferred_map": None, "speakers": [], "fills": [["s0000100", "{STR_VAR_1}"]]},
}}

PO = {
    "maps/bellin-town.po": [
        PoEntry("s0000100", "Hi, {PLAYER}! Take this {STR_VAR_1}.", "Привет, {PLAYER}! Держи {STR_VAR_1}.",
                extracted=["category: script; mode: field",
                           "used: Bellin Town, npc, sprite 1, speaker colour female, box default (script 0x10, line 0)",
                           "speaker label: Ann (female)",
                           "trainer: Sally (Lass, female)",
                           "{STR_VAR_1} may be s0000200: 'Potion'",
                           "original lines: 1, widths px: 150"]),
        PoEntry("s0000200", "Potion", "Зелье",
                extracted=["category: script; mode: field",
                           "probable map (inferred from neighbours): Bellin Town",
                           "inserted as {STR_VAR_1} into s0000100: Hi, {PLAYER}! Take this {STR_VAR_1}."]),
        PoEntry("s0000400", "Potion", ""),
        PoEntry("s0000500", "Potion", "Микстура", flags=["fuzzy"]),
        PoEntry("s0000600", "s", "", flags=["empty"]),
    ],
    "system/table-0003000.po": [PoEntry("s0000300", "Bag", "Сумка",
                                        extracted=["reach: never shown (review: no caller)"])],
    "tables/names.po": [
        PoEntry("s0000900", "Bellin Town", "Беллин Таун",
                extracted=["category: data-table; mode: field"]),
        PoEntry("s0000A00", "Sally", "Салли",
                extracted=["category: table:trainer_names; mode: field"]),
    ],
    "tables/species.po": [PoEntry("species:1", "Ivysaur", "Ивизавр")],
}

REACH = {"strings": {
    "s0000100": {"class": "reachable", "group": "script", "evidence": [{"kind": "map-walk", "at": "0x10"}]},
    "s0000300": {"class": "reachable", "group": "system", "evidence": []},
    "s0000400": {"class": "possibly reachable", "group": "script",
                 "evidence": [{"kind": "unaligned", "at": "0x10b2e53"}]},
    "s0000500": {"class": "unreachable", "group": "system", "evidence": []},
}}

RULES = {"s0000300": [{"text": "Keep it short.", "source": "profile test", "evidence": "measured"}]}

WORDING = {"s0000300": [{"text": "Use the noun.", "source": "project style rules", "evidence": ""}],
           "s0000100": [{"text": "Address with вы.", "source": "project style rules", "evidence": ""}]}

TERMS = [Term("item:potion", "item", "Potion", "Зелье", forms={"nomn.sing": "Зелье", "gent.sing": "Зелья"}),
         Term("item:bag", "item", "Bag", "Сумка", gender="femn"),
         Term("item:ether", "item", "Ether", "Эфир")]

TOP_KEYS = {"fill_sources", "map_order", "language_rules", "engine_rules", "term_columns", "schema", "toolkit", "language", "profile", "rom", "fonts", "charmap", "placeholders", "glossary",
            "entries", "graphics", "check_rules", "keyboard", "font_sheets", "where_texts", "notes", "research"}

ENTRY_KEYS = {"id", "file", "tokens", "translation", "flags", "status", "context", "window", "terms",
              "approved", "note", "reach", "rules", "translator_notes", "source_sha256"}

TOOLKIT = f"{__version__}+1a2b3c4"

def games_only(languages):
    """The languages of the game projects, the site's own catalog aside."""
    return [lang for lang in languages if lang["profile"] != "site"]

class EditorDataTest:
    """The editor document of a language."""

    @classmethod
    def setUpClass(cls):
        cls.packs = load_styles("ru", PROF)
        main, small = (cls.packs[s].glyph_slots() for s in ("unbound", "unbound-small"))
        cls.cm = cls.packs["unbound"].charmap()
        # 6 px and 5 px stand for the ROM widths
        cls.measure = Measure(lambda b: main[b].width if b in main else 6, PROF["layout"]["placeholders"],
                              styles={"unbound-small": lambda b: small[b].width if b in small else 5})
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, es in PO.items():
                write(root / name, es, {})
            cls.catalog = load_catalog(root)
            cls.root = root.as_posix()
        cls.limits = qa.compute_limits(PROF, INV, cls.catalog, cls.measure, cls.cm, CTX)
        notes = {"s0000100": ["speaker: female, trainer class 5 (Lass) (record 2 of gym-leaders)"]}
        cls.doc = editordata.build("ru", PROF, cls.catalog, cls.limits, cls.measure, cls.cm, cls.packs, TERMS,
                                   notes, qa.Windows(PROF, INV), TOOLKIT, REACH, RULES, WORDING, inv=INV)
        cls.by_id = {e["id"]: e for e in cls.doc["entries"]}

class SplitTest:
    """The split form the editor page loads."""

    @classmethod
    def setUpClass(cls):
        EditorDataTest.setUpClass.__func__(cls)   # the same document
        from gen3tl.web.editorcheck import Checker
        latin = {s: bytes([6] * 512) for s in cls.doc["fonts"]["styles"]}
        cls.checker = Checker(cls.doc, latin, {}, "1.2.3")
        cls.problems = editordata.data_problems(cls.doc, cls.checker)
        cls.art = editordata.glyph_art(PROF, cls.packs)
        cls.index, cls.chunks = editordata.split(cls.doc, "1.2.3", cls.art, cls.problems)


TOOLKIT_RE = rf"^{re.escape(__version__)}(\+[0-9a-f]{{7,}}(\.dirty)?)?$"
