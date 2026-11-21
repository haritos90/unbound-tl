import json
import unittest

from gen3tl.web import editordata
from gen3tl.lang import termedit
from gen3tl.web.editorcheck import Checker

from editorstore_support import decoded_slots
import editordata_support as fx
from test_renamecheck import ELIXIR, MAX_ELIXIR, NECTAR
from project_fixture import select_language

def setUpModule():
    select_language("ru")

LONG = "Очень длинное целебное зелье здоровья"

class PreviewTest(unittest.TestCase):
    """The editor's rename preview: lang rename's report from the editor data."""

    @classmethod
    def setUpClass(cls):
        class Doc:
            pass
        fx.EditorDataTest.setUpClass.__func__(Doc)
        cls.doc = Doc.doc
        cls.data = editordata.terms_data(fx.TERMS, Doc.doc, Doc.catalog)
        cls.checker = Checker(Doc.doc, {s: bytes([6] * 512) for s in Doc.doc["fonts"]["styles"]}, {}, "1.2.3")
        cls.items = [{"entry": e, "text": e["translation"]} for e in Doc.doc["entries"]]
        cls.potion = cls.data["terms"][0]

    def run_preview(self, new, items=None):
        return termedit.preview(self.checker, self.potion, new, items or self.items, decoded_slots(self.data["slots"]))

    def test_rename_overflows_its_line_and_the_line_it_fills(self):
        rep = self.run_preview({**self.potion, "translation": LONG,
                                "forms": {"nomn.sing": LONG, "gent.sing": "Зелья"}})
        self.assertEqual((rep["format"], rep["renames"][0]["old"], rep["renames"][0]["new"]),
                         ("gen3tl-term-rename", "Зелье", LONG))
        by_id = {e["id"]: e for e in rep["entries"]}
        self.assertEqual(set(by_id), {"s0000100", "s0000200"})
        word = by_id["s0000200"]
        self.assertEqual((word["before"], word["after"], word["changed"]), ("Зелье", LONG, True))
        self.assertTrue(word["added"][0]["message"].startswith("line too wide: 219 > 208 px"))
        host = by_id["s0000100"]   # the line {STR_VAR_1} of s0000100 holds the renamed word
        self.assertEqual((host["changed"], host["before"], host["after"]), (False,) + ("Привет, {PLAYER}! Держи {STR_VAR_1}.",) * 2)
        self.assertIn(f"{{STR_VAR_1}} = 219 px (s0000200 '{LONG}')", host["added"][0]["message"])
        s = rep["summary"]
        self.assertEqual((s["changed"], s["limit_checked"], s["error_lines"], s["blocked"]), (1, 1, 2, True))

    def test_the_page_edits_are_renamed(self):
        items = [dict(x, text="Зелье и Зелья") if x["entry"]["id"] == "s0000500" else x for x in self.items]
        rep = self.run_preview({**self.potion, "translation": "Снадобье",
                                "forms": {"nomn.sing": "Снадобье", "gent.sing": "Снадобья"}}, items)
        by_id = {e["id"]: e for e in rep["entries"]}
        self.assertEqual(by_id["s0000500"]["after"], "Снадобье и Снадобья")
        self.assertEqual(rep["summary"]["limit_checked"], 1)   # s0000100's wider slot still fits
        self.assertNotIn("s0000100", by_id)
        self.assertEqual(rep["summary"]["errors"], 0)

    def test_lines_the_rename_leaves_are_dropped(self):
        items = [dict(x, text="Нет Зелья") if x["entry"]["id"] == "s0000500" else x for x in self.items]
        rep = self.run_preview({**self.potion, "translation": "Снадобье",
                                "forms": {"nomn.sing": "Снадобье", "gent.sing": "Зелья"}}, items)
        self.assertEqual([e["id"] for e in rep["entries"] if e["changed"]], ["s0000200"])

    def test_a_gender_change_keeps_every_line(self):
        bag = self.data["terms"][1]
        rep = termedit.preview(self.checker, bag, {**bag, "gender": "male"}, self.items, self.data["slots"])
        self.assertEqual(rep["renames"][0]["grammar"]["changes"], [{"property": "gender", "old": "femn", "new": "masc"}])
        self.assertEqual([(e["id"], e["before"] == e["after"]) for e in rep["entries"]], [("s0000300", True)])

    def test_form_only_lines_are_left_out_unless_included(self):
        # lower-case «зелья» is the noun
        items = [dict(x, text="Нет зелья, только Зелье") if x["entry"]["id"] == "s0000500" else x for x in self.items]
        new = {**self.potion, "translation": "Снадобье", "forms": {"nomn.sing": "Снадобье", "gent.sing": "Снадобья"}}
        by_id = lambda rep: {e["id"]: e["after"] for e in rep["entries"] if e["changed"]}   # noqa: E731
        self.assertEqual(by_id(self.run_preview(new, items))["s0000500"], "Нет зелья, только Снадобье")
        rep = termedit.preview(self.checker, self.potion, new, items, self.data["slots"], {"include": ["s0000500"]})
        self.assertEqual(by_id(rep)["s0000500"], "Нет Снадобья, только Снадобье")
        noun = {**self.potion, "id": "term:potion", "category": "term", "translation": "зелье",
                "forms": {"nomn.sing": "зелье", "gent.sing": "зелья"}}   # a row of the noun: never the item's
        rep = termedit.preview_json(self.checker, self.potion, new, items, self.data["slots"],
                                    json.dumps({"rows": [noun], "include": ["s0000500"]}, ensure_ascii=False))
        self.assertEqual(by_id(json.loads(rep))["s0000500"], "Нет зелья, только Снадобье")

    def test_notes_and_sources_rename_nothing(self):
        self.assertIsNone(self.run_preview({**self.potion, "notes": "x", "sources": "y"}))
        self.assertEqual(termedit.preview_json(self.checker, json.dumps(self.potion),
                                               {**self.potion, "notes": "x"}, "[]", None), "null")

    def test_rename_bytes_ignore_missing_and_multiline_projections(self):
        new = {**self.potion, "translation": LONG, "forms": {"nomn.sing": LONG}}
        expected = termedit.preview_json(self.checker, self.potion, new, self.items, self.data["slots"])
        for notes in (None, "First line.\nSecond line.\nstatus: unreviewed"):
            with self.subTest(notes=notes):
                old = {k: v for k, v in self.potion.items() if k != "notes"}
                old["note_ids"] = ["term-context"]
                if notes is not None:
                    old["notes"] = notes
                edited = {**old, "translation": LONG, "forms": {"nomn.sing": LONG}}
                self.assertEqual(termedit.preview_json(self.checker, old, edited, self.items, self.data["slots"]), expected)
                self.assertEqual(termedit.preview_json(self.checker, old, {**old, "sources": "context"},
                                                     self.items, self.data["slots"]), "null")

    def test_preview_preserves_enclosing_terms_even_in_included_entries(self):
        old = {"id": ELIXIR.id, "category": "item", "source_text": "Elixir", "translation": "Эликсир",
               "forms": ELIXIR.forms, "label": ELIXIR.label}
        other = {"id": MAX_ELIXIR.id, "category": "item", "source_text": "Max Elixir",
                 "translation": "Эликсир макс", "forms": MAX_ELIXIR.forms, "label": MAX_ELIXIR.label}
        new = {**old, "translation": "Нектар", "forms": NECTAR, "label": "Нект."}
        entry = {**self.items[0]["entry"], "source_text": "Max Elixir and Elixir"}
        for text, expected in (("Эликсир макс и Эликсир", "Эликсир макс и Нектар"),
                               ("Эликсир макс", None)):
            with self.subTest(text=text):
                rep = termedit.preview(self.checker, old, new, [{"entry": entry, "text": text}], {},
                                       {"rows": [other], "include": [entry["id"]]})
                changed = [e["after"] for e in rep["entries"] if e["changed"]]
                self.assertEqual(changed, [] if expected is None else [expected])
