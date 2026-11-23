from pathlib import Path
import json
import tempfile
import unittest

from gen3tl.web import editordata
from gen3tl.check.provenance import formatted
from gen3tl.build.font import shadow_end
from gen3tl.catalog.po import PoEntry
from gen3tl.profile.profile import Profile
from gen3tl.lang.termbase import Term
from gen3tl.lang import language

import editordata_support
from editordata_support import ENTRY_KEYS, PROF, TOOLKIT, TOP_KEYS, setUpModule

CONTEXT_KEYS = {"comments", "maps", "events", "boxes", "uses", "speakers", "inserted", "words", "hosts", "identity"}

class EditorDataTest(editordata_support.EditorDataTest, unittest.TestCase):
    def test_research_summaries_are_separate_from_editable_records(self):
        from gen3tl.lang import language, research, termbase
        from gen3tl.core import notes
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with language.use(language.Language("fixture", {}, root)):
                finding = research.Row({"record_id": "finding:one", "role": "Recorded role",
                                        "evidence": "Recorded evidence"})
                record = research.term_note("term:one", finding, "research-assembly", [])
                term = Term("term:one", "term", "One", "Target")
                termbase.attach_notes(term, [record], findings={finding.record_id: finding})
                doc = {"language": "fixture", "entries": []}
                editordata.attach_notes(doc, Profile({}, root / "absent.toml"), {}, [term], wording=[])
                self.assertEqual(doc["notes"]["note"], [record])
                self.assertNotIn("facts", record)
                self.assertEqual(doc["notes"]["summaries"], {
                    record["id"]: ["role: Recorded role", "evidence: Recorded evidence"]})
                notes.validate({key: doc["notes"][key] for key in ("schema", "note")})
                self.assertEqual(editordata.term_data(term)["note_ids"], [record["id"]])

    def test_schema(self):
        doc = json.loads(json.dumps(self.doc, ensure_ascii=False))   # plain JSON
        self.assertEqual(set(doc), TOP_KEYS)
        self.assertEqual((doc["schema"], doc["language"], doc["profile"], doc["rom"]),
                         (editordata.SCHEMA, "ru", "test", {"sha1": "ab" * 20}))
        self.assertEqual(doc["toolkit"], TOOLKIT)
        self.assertEqual(doc["check_rules"], {})
        self.assertEqual(doc["map_order"], {self.by_id["s0000100"]["file"]: 1})
        self.assertIsNone(doc["graphics"])   # no [graphics] section
        self.assertIsNone(doc["keyboard"])   # no [keyboard] section
        self.assertEqual([e["id"] for e in doc["entries"]], list(self.catalog))
        for e in doc["entries"]:
            self.assertEqual(set(e), ENTRY_KEYS | ({"owner"} if e.get("owner") else set()))
            self.assertEqual(set(e["context"]), CONTEXT_KEYS)
            self.assertEqual(e["note"], "")
            self.assertTrue({"kind", "width", "lines", "font"} <= set(e["window"]))

    def test_status_and_approved_elsewhere(self):
        self.assertEqual({sid: e["status"] for sid, e in self.by_id.items()},
                         {"s0000100": "approved", "s0000200": "approved", "s0000400": "untranslated",
                          "s0000500": "fuzzy", "s0000600": "approved", "s0000300": "approved",
                          "species:1": "approved", "s0000900": "approved", "s0000A00": "approved"})
        self.assertEqual(self.by_id["s0000500"]["flags"], ["fuzzy"])
        # the fuzzy Микстура is no approved translation
        for sid in ("s0000400", "s0000500"):
            self.assertEqual(self.by_id[sid]["approved"], [{"translation": "Зелье", "ids": ["s0000200"]}])
        self.assertEqual(self.by_id["s0000200"]["approved"], [])   # never its own source

    def test_context(self):
        ctx = self.by_id["s0000100"]["context"]
        self.assertEqual(ctx["identity"]["speaker"]["in_source"], "not-stated")
        self.assertIn({"source": "sprite", "gender": "unknown", "value": "1", "evidence": ""},
                      ctx["identity"]["speaker"]["sources"])
        self.assertIn({"source": "record", "gender": "female", "value": "2 / 5", "evidence": "gym-leaders"},
                      ctx["identity"]["speaker"]["sources"])
        self.assertEqual((ctx["events"], ctx["boxes"], ctx["uses"]), (["npc"], ["default"], 1))
        # names and classes are keys or absent
        self.assertEqual(ctx["maps"], ["s0000900"])
        self.assertEqual(ctx["speakers"], [
            {"gender": "female", "source": "text colour"},
            {"gender": "female", "source": "label"},
            {"name": "s0000A00", "gender": "female", "source": "trainer"},
            {"gender": "female", "source": "record"},
        ])
        self.assertEqual(ctx["comments"], ["category: script; mode: field", "original lines: 1, widths px: 150"])
        self.assertEqual(ctx["words"], [{"slot": "{STR_VAR_1}", "id": "s0000200", "translation": "Зелье"}])
        self.assertEqual(self.by_id["s0000100"]["tokens"], ["{PLAYER}", "{STR_VAR_1}"])
        word = self.by_id["s0000200"]["context"]
        self.assertEqual(word["maps"], ["s0000900"])
        self.assertEqual(word["hosts"], [{"slot": "{STR_VAR_1}", "id": "s0000100"}])
        text = json.dumps({k: v for k, v in self.doc.items() if k != "glossary"}, ensure_ascii=False)
        for line in ("Bellin Town", "Ann", "Sally", "Lass", "Take this", "Ivysaur", "Potion"):   # the term names stay
            self.assertNotIn(line, text)

    def test_map_order_uses_profile_positions_with_duplicate_names_and_snapshot_digests(self):
        from gen3tl.catalog.source import digest
        prof = {"maps": {"mapsec_names": 0x100, "mapsec_count": 3}}
        catalog = {sid: (Path("names.po"), PoEntry(sid, name)) for sid, name in
                   (("late", "Late map"), ("early", "Early map"), ("duplicate", "Early map"),
                    ("outside", "Outside map"), ("unaligned", "Unaligned map"))}
        inv = {"entries": [{"text": name, "refs": [{"at": at}]} for name, at in
                           (("Late map", 0x108), ("Early map", 0x104), ("Early map", 0x100),
                            ("Outside map", 0x10C), ("Unaligned map", 0x101))]}
        key = lambda sid: "key:" + sid
        entries = [{"file": file, "context": {"maps": maps, "uses": uses}} for file, maps, uses in
                   (("maps/late.po", ["key:late"], 1), ("maps/early.po", ["key:early"], 1),
                    ("maps/early.po", ["key:duplicate"], 2), ("maps/late.po", ["key:early", "key:late"], 2),
                    ("maps/late.po", ["key:early"], 5), ("maps/unknown.po", ["key:outside"], 1))]
        expected = {"maps/late.po": 2, "maps/early.po": 0}
        self.assertEqual(editordata.map_order(prof, catalog, inv, key, {}, entries), expected)
        source = {sid: [digest(e.msgid)] for sid, (_, e) in catalog.items()}
        for sid, (_, e) in catalog.items():
            e.msgid, e.keyed = sid, True
        for row in inv["entries"]:
            row["source_sha256"] = digest(row.pop("text"))
        self.assertEqual(editordata.map_order(prof, catalog, inv, key, source, entries), expected)
        self.assertEqual(editordata.map_order({}, catalog, inv, key, source, entries), {})
        self.assertEqual(editordata.map_order(prof, catalog, None, key, source, entries), {})

    def test_reach(self):
        # the catalog's tag first, then the study
        self.assertEqual({sid: {**e["reach"], "evidence": formatted(e["reach"]["evidence"])}
                          for sid, e in self.by_id.items()}, {
            "s0000100": {"class": "reachable", "source": "reach study",
                         "evidence": "reach study: reachable (map-walk 0x10)"},
            "s0000200": {"class": "reachable", "source": "not studied", "evidence": ""},
            "s0000300": {"class": "never shown", "source": "review", "evidence": "review: no caller"},
            "s0000400": {"class": "possibly reachable", "source": "reach study",
                         "evidence": "reach study: possibly reachable (unaligned 0x10b2e53)"},
            "s0000500": {"class": "never shown", "source": "reach study",
                         "evidence": "reach study: unreachable system text"},
            "s0000600": {"class": "reachable", "source": "not studied", "evidence": ""},
            "species:1": {"class": "reachable", "source": "not studied", "evidence": ""},
            "s0000900": {"class": "reachable", "source": "not studied", "evidence": ""},
            "s0000A00": {"class": "reachable", "source": "not studied", "evidence": ""}})
        both = "reach study: unreachable script text; review: dead code"
        self.assertEqual(editordata.reach_data("s1", [f"reach: never shown ({both})"], None),
                         {"class": "never shown", "source": "reach study, review", "evidence": both})
        self.assertEqual(editordata.reach_data("s0000400", [], None)["class"], "reachable")   # no study

    def test_rules(self):
        # never shown, profile, inserted words, wording
        src = {sid: [r["source"] for r in e["rules"]] for sid, e in self.by_id.items()}
        self.assertEqual(src, {
            "s0000100": ["catalog context", "project style rules"],
            "s0000200": ["catalog context"],
            "s0000300": ["review", "profile test", "project style rules"],
            "s0000400": [], "s0000500": ["reach study"], "s0000600": [], "species:1": [],
            "s0000900": [], "s0000A00": []})
        self.assertEqual(self.by_id["s0000300"]["rules"][0]["evidence"], "review: no caller")
        self.assertEqual(self.by_id["s0000200"]["rules"][0]["text"],
                         "Inserted as {STR_VAR_1} into 1 text (s0000100): one form serves every sentence it fills.")
        self.assertEqual(self.by_id["s0000100"]["rules"][0]["text"],
                         "{STR_VAR_1} takes 1 inserted word (s0000200): the sentence is built around their fixed forms.")
        bare = editordata.build("ru", PROF, self.catalog, self.limits, self.measure, self.cm, self.packs,
                                toolkit=TOOLKIT)
        self.assertEqual([r["source"] for r in bare["entries"][0]["rules"]], ["catalog context"])

    def test_inserted_value(self):
        # {STR_VAR_1} at the inserted word's width
        px = self.measure.width("Зелье", self.cm)
        self.assertEqual([{**x, "source": formatted(x["source"])} for x in self.by_id["s0000100"]["context"]["inserted"]], [
            {"token": "{PLAYER}", "width": 42, "source": "profile width"},
            {"token": "{STR_VAR_1}", "width": px, "source": "s0000200 'Зелье'"}])
        w = self.by_id["s0000100"]["window"]
        self.assertEqual((w["kind"], w["width"], w["lines"], w["font"], w["placeholders"]),
                         ("dialogue", 208, 2, "unbound", {"STR_VAR_1": px}))
        self.assertEqual(self.by_id["s0000300"]["context"]["inserted"], [])
        lim = self.limits["s0000100"]
        guessed = editordata.inserted(self.catalog["s0000100"][1].msgid, lim, self.measure, self.cm,
                                      frozenset({"PLAYER"}))
        self.assertEqual({**guessed[0], "source": formatted(guessed[0]["source"])},
                         {"token": "{PLAYER}", "width": 42, "source": "profile width, unverified estimate"})
        self.assertEqual(guessed[1], self.by_id["s0000100"]["context"]["inserted"][1])

    def test_measured_windows(self):
        # [layout.window_width] of the profile
        w = self.by_id["s0000300"]["window"]
        self.assertEqual((w["kind"], w["width"], w["lines"], w["font"]), ("single", 76, 1, "unbound"))
        self.assertNotIn("other", w)
        # [[table]] windows: main sets the field, other checked
        w = self.by_id["species:1"]["window"]
        self.assertEqual((w["kind"], w["width"], w["chars"], w["font"]), ("field", 60, 10, "unbound"))
        self.assertEqual(w["other"], [{"font": "unbound-small", "width": 56, "where": "health box"}])
        # an inserted word takes the window of its host
        self.assertEqual((self.by_id["s0000200"]["window"]["width"], self.by_id["s0000200"]["window"]["host"]),
                         (208, "s0000100"))

    def test_limit_sources(self):
        # where each limit comes from, in the window
        src = {sid: {k: (v["kind"], formatted(v["rule"])) for k, v in e["window"]["sources"].items()}
               for sid, e in self.by_id.items()}
        self.assertEqual(src["s0000100"], {"width": ("profile", "[layout] dialogue_width"),
                                           "lines": ("measured", "two lines per message box")})
        self.assertEqual(src["s0000300"]["width"], ("measured", "[layout.window_width] s0000300: measured in game"))
        self.assertEqual(src["species:1"], {"width": ("measured", "[[table]] species window: summary"),
                                            "lines": ("measured", "[[table]] species: a one-line field"),
                                            "chars": ("measured", "[[table]] species: a field of 11 bytes with the "
                                                                  "terminator")})
        self.assertEqual(src["s0000200"]["width"], ("profile", "the window of s0000100, which inserts it: "
                                                               "[layout] dialogue_width"))

    def test_window_is_the_limit_of_the_check(self):
        for sid, lim in self.limits.items():
            self.assertEqual(editordata.limit_of(self.by_id[sid]["window"]), lim)

    def test_glossary(self):
        self.assertEqual(self.by_id["s0000300"]["terms"], ["item:bag"])
        self.assertEqual(self.by_id["s0000400"]["terms"], ["item:potion"])
        self.assertEqual(self.by_id["s0000100"]["terms"], [])
        self.assertEqual(set(self.doc["glossary"]), {"item:bag", "item:potion"})   # only terms in use
        self.assertEqual(self.doc["glossary"]["item:potion"]["forms"], {"nomn.sing": "Зелье", "gent.sing": "Зелья"})
        self.assertEqual(self.doc["glossary"]["item:bag"]["translation"], "Сумка")

    def test_reviewed_name_identity_reaches_editor_check(self):
        from gen3tl.web.editorcheck import Checker
        terms = [Term("speaker:guy", "speaker", "Guy", "Мужчина", status="approved"),
                 Term("character:guy", "character", "Guy", "Гай", status="approved")]
        catalog = {
            "s0000100": (Path("names.po"), PoEntry("s0000100", "Guy", "Гай",
                translator=["filled from glossary character:guy"])),
            "s0000200": (Path("names.po"), PoEntry("s0000200", "Guy", "Мужчина",
                translator=["filled from glossary speaker:guy"])),
        }
        doc = editordata.build("ru", PROF, catalog, self.limits, self.measure, self.cm, self.packs, terms)
        checker = Checker(doc, {style: bytes([6] * 512) for style in self.packs})
        for e, tid, wrong in zip(doc["entries"], ["character:guy", "speaker:guy"], ["Мужчина", "Гай"]):
            self.assertEqual(e["terms"], [tid])
            e = {**e, "source_text": "Guy"}   # the English read from the ROM
            self.assertEqual(checker.check(e, e["translation"])["problems"], [])
            problems = checker.check(e, wrong)["problems"]
            self.assertTrue(any("glossary" in p["message"] for p in problems), problems)
            # without the English the glossary check needs the text
            bare = checker.check(doc["entries"][0], wrong)
            self.assertEqual((bare["problems"], bare["unavailable"]), ([], ["typography", "glossary"]))

    def test_no_rom_bytes(self):
        # pack widths and ROM offsets, no ROM values
        fonts = self.doc["fonts"]
        self.assertEqual(fonts["main"], "unbound")
        for style, f in fonts["styles"].items():
            self.assertEqual(set(f), {"format", "pack", "copy", "shadow", "rom"})
            self.assertEqual(f["pack"], {f"{b:02X}": g.width for b, g in self.packs[style].glyph_slots().items()})
            # pack glyphs only, from their art
            self.assertEqual(f["shadow"], [f"{b:02X}" for b, g in sorted(self.packs[style].glyph_slots().items())
                                           if shadow_end(g.pixels, g.width)])
            self.assertTrue(f["shadow"] and set(f["shadow"]) <= set(f["pack"]))
            # a copied letter names its ROM byte, not its width
            self.assertEqual(f["copy"]["87"], "BB")
            self.assertEqual(len(f["copy"]), 20)
            self.assertFalse(set(f["copy"]) & set(f["pack"]))
        self.assertEqual(fonts["styles"]["unbound"]["rom"],
                         {"font": "font0", "glyphs": 0x1000, "widths": 0x9000, "count": 512})
        self.assertEqual(fonts["styles"]["unbound-small"]["format"], "8x16")
        self.assertEqual(self.doc["charmap"]["Б"], f"{self.packs['unbound'].chars['Б']:02X}")
        self.assertEqual(self.doc["placeholders"], {"default": 60, "widths": {"PLAYER": 42, "STR_VAR_1": 60}})
