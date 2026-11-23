import json
import os
import re
import tempfile
import unittest
from pathlib import Path

from gen3tl.web import editordata
from gen3tl.check.provenance import formatted
from gen3tl.catalog import keys
from gen3tl.project import registry_scope

from rom_support import needs_rom, rom_path
from test_roots import PROJECT_ROOT as ROOT
import editordata_support
from project_fixture import UNBOUND
from editordata_support import ENTRY_KEYS, TOOLKIT_RE, TOP_KEYS, games_only, setUpModule
from editorstore_support import decoded

@needs_rom
class SplitTest(editordata_support.SplitTest, unittest.TestCase):
    def test_manifest_ships_the_tracked_pokedex_dataset(self):
        tracked = UNBOUND / "data" / "pokedex" / "pokedex.json"
        with tempfile.TemporaryDirectory() as tmp, registry_scope(UNBOUND):
            root = Path(tmp)
            editordata.write_split(root / "unbound-2.1.1.1" / "ru", dict(self.index, profile="unbound-2.1.1.1"),
                                   self.chunks)
            doc = editordata.write_languages(root)
            profile = next(p for p in doc["profiles"] if p["id"] == "unbound-2.1.1.1")
            self.assertEqual(profile["pokedex"], "pokedex/unbound-2.1.1.1/pokedex.json")
            self.assertEqual((root / profile["pokedex"]).read_bytes(), tracked.read_bytes())
            companion = tracked.with_name("trainer-ivs.json")
            self.assertEqual((root / profile["pokedex"]).with_name(companion.name).read_bytes(), companion.read_bytes())
            self.assertEqual([path.name for path in (root / "pokedex").iterdir()], ["unbound-2.1.1.1"])


@needs_rom
class EditorDataCommandTest(unittest.TestCase):
    """`gen3tl web data` on the repository data: known entries."""

    @classmethod
    def setUpClass(cls):
        import contextlib
        import io

        from gen3tl.__main__ import main
        cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "ru.json"
            try:
                os.chdir(ROOT)
                with contextlib.redirect_stdout(io.StringIO()):
                    main(["--rom", str(rom_path()), "web", "data", "--out", str(out)])
            finally:
                os.chdir(cwd)
            cls.doc = json.loads(out.read_text(encoding="utf-8"))
        cls.aliases = keys.load(cls.doc["rom"]["sha1"])   # the document names entries by key
        cls.by_id = {cls.aliases.entry_id(e["id"]): e for e in cls.doc["entries"]}

    def test_every_entry(self):
        self.assertEqual((set(self.doc), self.doc["language"], self.doc["profile"]),
                         (TOP_KEYS | {"version"}, "ru", "unbound-2.1.1.1"))
        self.assertRegex(self.doc["toolkit"], TOOLKIT_RE)
        self.assertEqual(len(self.by_id), len(self.doc["entries"]))
        self.assertTrue(all(keys.is_key(e["id"]) for e in self.doc["entries"]))
        records = {row["id"]: row for row in self.doc["notes"]["note"]}
        for e in self.doc["entries"]:
            optional = {key for key in ("owner", "note_ids") if e.get(key)}
            expected = ENTRY_KEYS | optional
            for nid in e.get("note_ids", []):
                row = records[nid]
                if row["subject"]["kind"] == "entry":
                    expected.discard("translator_notes" if row["scope"]["kind"] == "shared" else "note")
            self.assertEqual(set(e), expected)
            self.assertIn(e["status"], ("approved", "fuzzy", "untranslated", "nothing"))
            self.assertTrue(e["file"].startswith("translation/po/"))
        for t in {t for e in self.doc["entries"] for t in e["terms"]}:
            self.assertIn(t, self.doc["glossary"])

    def test_reach(self):
        # tags of the catalog and classes of build/reach.json
        teachy = self.by_id["s041B8BF"]["reach"]
        self.assertEqual((teachy["class"], teachy["source"]), ("never shown", "review"))
        self.assertIn("Teachy TV", teachy["evidence"])
        self.assertEqual(self.by_id["species:539"]["reach"], {"class": "reachable", "source": "not studied",
                                                              "evidence": ""})
        if (ROOT / "build" / "reach.json").exists():
            study = json.loads((ROOT / "build" / "reach.json").read_text(encoding="utf-8"))["strings"]
            for sid, r in study.items():
                if sid in self.by_id:
                    got = self.by_id[sid]["reach"]["class"]
                    self.assertEqual(got, "never shown" if r["class"] == "unreachable" else got, sid)
                    if got != "never shown":
                        self.assertEqual(got, r["class"], sid)

    def test_rules(self):
        # profile rules and the Russian rule list
        def sources(sid):
            return [r["source"] for r in self.by_id[sid]["rules"]]
        self.assertEqual(sources("s0A4C4BD"), [
            "profile [[layout.code_fill]] fill-20: battle text, name of the opposing trainer",
            "profile [[layout.code_fill]] fill-26: battle text, class of the opposing trainer, class 45",
            "project decision"])
        self.assertIn("The code fills {B_TRAINER1_CLASS} with text 113 px wide",
                      self.by_id["s0A4C4BD"]["rules"][1]["text"])
        self.assertEqual(sources("s03FD3C7"), ["profile [[strings.computed]] 0x9BDE20",
                                               "profile [[layout.code_fill]] fill-20: battle text, name of the opposing trainer",
                                               "profile [[layout.code_fill]] paired-first-trainer: battle message window",
                                               "project decision", "project style rules"])
        self.assertIn("The code fills {B_TRAINER1_NAME} with text measured from trainer name",
                      self.by_id["s0A4C4BD"]["rules"][0]["text"])
        self.assertIn("At most 63 bytes, the gap to s03FD407",
                      self.aliases.unkey_text(self.by_id["s03FD3C7"]["rules"][0]["text"]))
        self.assertIn(self.aliases.key("s03FD407"), self.by_id["s03FD3C7"]["rules"][0]["text"])
        self.assertIn("Begins with {STR_VAR_1}", self.by_id["s04162FF"]["rules"][0]["text"])
        self.assertEqual(sources("ability_popup_possessive:0"),
                         ["profile [[table]] ability_popup_possessive"])
        self.assertEqual(sources("species:1"), ["profile [[table]] species save_link"])
        self.assertEqual(sources("s041B8BF")[0], "review")

    def test_start_menu_label(self):
        # [layout.window_width]: start-menu label window
        w = self.by_id["s0A4E4CB"]["window"]
        self.assertEqual((w["kind"], w["width"], w["lines"], w["font"]), ("single", 76, 1, "unbound"))
        # measured, with its source
        self.assertEqual(w["sources"]["width"]["kind"], "measured")

    def test_limit_sources(self):
        # every window says where its width comes from
        kinds = {e["window"]["sources"]["width"]["kind"] for e in self.doc["entries"]}
        self.assertEqual(kinds, {"measured", "profile", "source"})
        w = self.by_id["s0A4C4BD"]["window"]["sources"]["width"]
        self.assertEqual((w["kind"], formatted(w["rule"])), ("measured", "[layout.box_width] battle: the message box, measured "
                                                              "in game ([layout.window_box] s0A4C4BD)"))
        w = self.by_id["species:539"]["window"]["sources"]
        self.assertEqual((formatted(w["width"]["rule"]), w["chars"]["kind"]),
                         ("[[table]] species window: summary screen, PC storage panel and Pokedex", "measured"))

    def test_species_name(self):
        w = self.by_id["species:539"]["window"]
        self.assertEqual((w["kind"], w["width"], w["chars"], w["font"]), ("field", 60, 10, "unbound"))
        self.assertEqual(w["other"], [{"font": "unbound-small", "width": 56, "where": "battle health box"}])

    def test_inserted_number(self):
        e = self.by_id["s1EF18E9"]
        self.assertEqual([{**x, "source": formatted(x["source"])} for x in e["context"]["inserted"]],
                         [{"token": "{STR_VAR_1}", "width": 30, "source": "number of up to 5 digits (a variable)"}])
        self.assertEqual(e["context"]["events"], ["npc"])

    def test_inserted_titles(self):
        # the Frontier titles fill {STR_VAR_1}
        ctx = self.by_id["s1F8D540"]["context"]
        self.assertIn({"slot": "{STR_VAR_1}", "id": self.aliases.key("s1F8DD26")},
                      [{k: w[k] for k in ("slot", "id")} for w in ctx["words"]])
        slot = next(x for x in ctx["inserted"] if x["token"] == "{STR_VAR_1}")
        self.assertGreater(slot["width"], 60)
        source = formatted(slot["source"])
        self.assertTrue(re.match(keys.KEY.pattern + " '", source), source)
        self.assertTrue(re.match(r"s[0-9A-F]{7} '", self.aliases.unkey_text(source)))

    def test_no_rom_bytes(self):
        for style, f in self.doc["fonts"]["styles"].items():
            self.assertEqual(set(f), {"format", "pack", "copy", "shadow", "rom"})
            self.assertLess(len(f["pack"]), 100)   # pack glyphs only
            self.assertLessEqual(set(f["shadow"]), set(f["pack"]))


@needs_rom
class SplitCommandTest(unittest.TestCase):
    """`gen3tl web data --split` on the repository data."""

    def test_split(self):
        import contextlib
        import io

        from gen3tl.__main__ import main
        cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "ru"
            try:
                os.chdir(ROOT)
                with contextlib.redirect_stdout(io.StringIO()):
                    main(["--rom", str(rom_path()), "web", "data", "--split", "--out", str(out)])
            finally:
                os.chdir(cwd)
            data = decoded(out)
            index = data["index"]
            langs = json.loads((Path(tmp) / "languages.json").read_text(encoding="utf-8"))
            self.assertEqual(games_only(langs["languages"]), [{"code": "ru", "index": "ru/index.json", "profile": "unbound-2.1.1.1",
                                                   "entries": len(index["list"]),
                                                   "progress": editordata.progress_of(index["list"]),
                                                   "texts": "ru/pokedex-texts.json"}])
            texts = json.loads((out / "pokedex-texts.json").read_text(encoding="utf-8"))
            self.assertEqual((texts["profile"], texts["language"], texts["draft"]), ("unbound-2.1.1.1", "ru", False))
            self.assertGreater(len(texts["texts"]), 5000)
            self.assertEqual(len(list((out / "entries").iterdir())), len(index["chunks"]))
            self.assertEqual(sum(c["entries"] for c in index["chunks"]), len(index["list"]))
            self.assertEqual(data["chunks"][0]["entries"][0]["id"], index["list"][0]["id"])
            terms = data["terms"]
        self.assertEqual(len(terms["terms"]), index["terms"]["count"])
        by_term = {t["id"]: t for t in terms["terms"]}
        self.assertGreater(len(by_term["term:pokemon"]["in_translation"]), 1000)
        self.assertEqual(by_term["move:x"]["in_translation"], [])   # the dash matches nothing
        self.assertRegex(index["version"], r"^\d+\.\d+\.\d+$")
        self.assertRegex(index["toolkit"], TOOLKIT_RE)
        self.assertEqual(langs["toolkit"], index["toolkit"])
        entry_id = keys.load(index["rom"]["sha1"]).entry_id   # rows carry keys
        rows = {entry_id(r["id"]): r for r in index["list"]}
        self.assertEqual(rows["s0A4E4CB"]["kind"], "single")
        self.assertTrue(all(r["problems"] == [] for r in index["list"] if r["status"] == "untranslated"))
        # the unused table slots have nothing to translate
        blank = [r for r in index["list"] if r["status"] == "nothing"]
        self.assertGreaterEqual(len(blank), 7)
        self.assertFalse(any(r["translation"] for r in blank))
        self.assertIn("items:54", {entry_id(r["id"]) for r in blank})
        for style, a in index["glyphs"].items():
            self.assertEqual(set(a["art"]), set(index["fonts"]["styles"][style]["pack"]))
