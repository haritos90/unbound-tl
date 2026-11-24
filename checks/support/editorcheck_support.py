from pathlib import Path
import hashlib
import json
import tempfile

from gen3tl.web import editorcheck, editordata
from gen3tl.check import qa
from gen3tl.catalog.catalog import load_catalog
from gen3tl.check.entrycheck import entry_problems
from gen3tl.lang.langpack import load_styles
from gen3tl.check.layout import Measure
from gen3tl.check.provenance import formatted
from gen3tl.catalog.po import PoEntry, write
from gen3tl.profile.profile import Profile
from gen3tl.build.release import expand
from gen3tl.lang.termbase import Term, TermMatcher


ROM = bytes(0x100) + bytes([6] * 512) + bytes(0x100) + bytes([5] * 512)

PROF = Profile({
    "rom": {"sha1": hashlib.sha1(ROM).hexdigest()},
    "font": [{"name": "font0", "glyphs": 0, "widths": 0x100, "count": 512},
             {"name": "small", "glyphs": 0, "widths": 0x400, "count": 512, "style": "unbound-small",
              "format": "8x16"}],
    "font_style": {"style": "unbound", "cell_height": 14},
    "font_styles": {"unbound-small": {"top": 1, "rows": 12}},
    "layout": {"dialogue_width": 208, "target_width": 190, "sentence_break": 0.5,
               "placeholders": {"PLAYER": 42, "STR_VAR_1": 60},
               "window_style": {"s0000300": "unbound-small"}},
    "table": [{"name": "species", "base": 0x5000, "stride": 11, "count": 2, "field_offset": 0, "field_length": 11,
               "windows": [{"style": "unbound", "width": 60, "where": "summary"},
                           {"style": "unbound-small", "width": 40, "where": "health box"}]}],
    "qa": {"optional_tokens": ["{PK}", "{MN}"], "forbidden": {"\\.\\.\\.": "three dots", "  ": "double space"},
           "droppable": [{"ids": ["s0000100"], "tokens": ["{PLAYER}"], "evidence": "test"}]},
}, Path("test.toml"))

def entry(sid, text, kind="script:loadpointer", category="script"):
    return {"id": sid, "offset": int(sid[1:], 16), "length": len(text) + 1, "kind": "pointer",
            "category": category, "mode": "field", "text": text, "table": None, "index": None,
            "refs": [{"at": 0x10 + int(sid[1:], 16), "kind": kind}], "flags": []}

INV = {"entries": [
    entry("s0000100", "Hi, {PLAYER}! Take this Potion. It heals your Pokémon a little."),
    entry("s0000200", "Potion", "script:bufferstring"),
    entry("s0000300", "Bag", "table", "data-table"),
    {"id": "species:1", "offset": 0x5000 + 11, "length": 11, "kind": "fixed", "category": "table:species",
     "mode": "field", "text": "Ivysaur", "table": "species", "index": 1, "refs": [], "flags": []},
]}

PO = {
    "maps/bellin-town.po": [
        PoEntry("s0000100", "Hi, {PLAYER}! Take this Potion. It heals your Pokémon a little.",
                "Привет, {PLAYER}! Держи Зелье. Оно немного лечит покемона."),
        PoEntry("s0000200", "Potion", "Зелье"),
    ],
    "system/table-0003000.po": [PoEntry("s0000300", "Bag", "")],
    "tables/species.po": [PoEntry("species:1", "Ivysaur", "Ивизавр")],
}

TERMS = [Term("item:potion", "item", "Potion", "Зелье", forms={"nomn.sing": "Зелье", "accs.sing": "Зелье"}),
         Term("item:bag", "item", "Bag", "Сумка")]

def with_english(doc: dict, catalog: dict) -> dict:
    """The document's entries by id with their English, as the page reads it from a ROM."""
    return {e["id"]: {**e, "source_text": catalog[e["id"]][1].msgid} for e in doc["entries"]}

class EditorCheckTest:
    """The browser check on synthetic editor data: check batch's code and measure."""

    @classmethod
    def setUpClass(cls):
        packs = load_styles("ru", PROF)
        main, small = (packs[s].glyph_slots() for s in ("unbound", "unbound-small"))
        cls.cm = packs["unbound"].charmap()
        # Both paths use the ROM metrics.
        cls.measure = Measure(lambda b: main[b].width if b in main else ROM[0x100 + b],
                              PROF["layout"]["placeholders"],
                              styles={"unbound": lambda b: main[b].width if b in main else ROM[0x100 + b],
                                      "unbound-small": lambda b: small[b].width if b in small else ROM[0x400 + b]})
        cls.measures = {s: (Measure(f, {}), cls.cm) for s, f in cls.measure.styles.items()}
        with tempfile.TemporaryDirectory() as tmp:
            for name, es in PO.items():
                write(Path(tmp) / name, es, {})
            catalog = load_catalog(Path(tmp))
        cls.limits = qa.compute_limits(PROF, INV, catalog, cls.measure, cls.cm)
        cls.windows = qa.Windows(PROF, INV, cls.measures)
        cls.doc = editordata.build("ru", PROF, catalog, cls.limits, cls.measure, cls.cm, packs, TERMS,
                                   windows=cls.windows)
        cls.by_id = with_english(cls.doc, catalog)
        latin = editorcheck.latin_widths(cls.doc["fonts"], ROM, cls.doc["rom"]["sha1"])
        header = {k: v for k, v in cls.doc.items() if k != "entries"}
        cls.checker = editorcheck.Checker(json.dumps(header), latin, json.dumps(PROF["qa"]), "1.2.3")

    def batch_check(self, sid, text):
        """The problems check batch reports for `text`, and the laid-out text."""
        e = self.by_id[sid]
        optional = set(PROF["qa"]["optional_tokens"]) | qa.droppable_tokens(PROF["qa"]).get(sid, set())
        return entry_problems(e["source_text"], expand(text, "1.2.3"), self.limits[sid], self.measure, self.cm,
                              optional, PROF["qa"]["forbidden"], self.windows.other(sid), self.measures,
                              TermMatcher(TERMS))

    def msgs(self, sid, text):
        """The editor check's problems of `text`, as their English text."""
        return [formatted(p["message"]) for p in self.checker.check(self.by_id[sid], text)["problems"]]
