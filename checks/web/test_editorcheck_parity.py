import sys
from pathlib import Path
import copy
import json
import subprocess
import tempfile
import unittest
import zipfile

from gen3tl.web import editorcheck, editordata
from gen3tl.check import qa
from gen3tl.check.entrycheck import entry_problems
from gen3tl.lang.langpack import load_styles
from gen3tl.check.layout import entry_measure, line_width, lines_of, paragraphs
from gen3tl.catalog.po import PoEntry
from gen3tl.build.release import expand
from gen3tl.lang.termbase import TermMatcher

from project_fixture import with_profile_notes
import editorcheck_support
from editorcheck_support import PROF, ROM, TERMS, entry

class EditorCheckTest(editorcheck_support.EditorCheckTest, unittest.TestCase):
    def test_bound_token_rules_configure_exported_and_bundled_checkers(self):
        rules = copy.deepcopy(PROF["qa"])
        rules["addable"] = [{"ids": ["s0000200"], "tokens": ["{CLEAR_TO}"],
                             "window": 40, "x": 2, "evidence": "Measured printer.\nVerified origin."}]
        catalog = {sid: (Path("test.po"), PoEntry(sid, row["source_text"], ""))
                   for sid, row in self.by_id.items()}
        latin = editorcheck.latin_widths(self.doc["fonts"], ROM, self.doc["rom"]["sha1"])
        for status in ("unreviewed", "accepted"):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as tmp:
                profile = copy.deepcopy(PROF)
                profile.data["qa"] = with_profile_notes(rules, (status, "needs_review", "superseded", "proposed"))
                doc = editordata.build(self.doc["language"], profile, catalog, self.limits, self.measure,
                                       self.cm, load_styles(self.doc["language"], profile), TERMS,
                                       windows=self.windows)
                exported = json.loads(json.dumps(doc["check_rules"]))
                for kind in ("droppable", "addable"):
                    self.assertEqual(exported[kind][0]["evidence"], rules[kind][0]["evidence"])
                    self.assertIs(type(doc["check_rules"][kind][0]["evidence"]), str)
                checker = editorcheck.Checker(json.dumps(doc), latin, json.dumps(exported))
                baseline = editorcheck.Checker(self.doc, latin, rules)
                for sid, text in (("s0000100", "Hi!"), ("s0000200", "{CLEAR_TO 01}Bag")):
                    self.assertEqual(checker.check(self.by_id[sid], text), baseline.check(self.by_id[sid], text))
                root = Path(tmp)
                editorcheck.write_bundle(root / "checker.zip", profile["qa"])
                with zipfile.ZipFile(root / "checker.zip") as archive:
                    self.assertEqual(json.loads(archive.read("rules.json")), exported)
                    archive.extractall(root)
                (root / "doc.json").write_text(json.dumps(doc), encoding="utf-8")
                (root / "latin.json").write_text(json.dumps({key: list(v) for key, v in latin.items()}))
                code = '''import json, sys
from pathlib import Path
root = Path(sys.argv[1])
sys.path.insert(0, str(root))
from gen3tl.web.editorcheck import Checker
doc, latin, rules = [json.loads((root / name).read_text()) for name in ("doc.json", "latin.json", "rules.json")]
checker = Checker(doc, latin, rules)
assert checker.droppable == {"s0000100": {"{PLAYER}"}}
assert set(checker.addable["s0000200"]) == {"{CLEAR_TO}"}
assert checker.addable["s0000200"]["{CLEAR_TO}"]["evidence"] == "Measured printer.\\nVerified origin."
'''
                run = subprocess.run([sys.executable, "-I", "-c", code, tmp], capture_output=True, text=True)
                self.assertEqual((run.returncode, run.stdout, run.stderr), (0, "", ""))

    def test_exports_refuse_empty_evidence_before_serialization(self):
        from gen3tl.catalog.keys import Aliases
        from gen3tl.core.notes import BoundProse

        for kind in ("droppable", "addable"):
            for evidence in ("", BoundProse("")):
                with self.subTest(kind=kind, evidence=evidence), tempfile.TemporaryDirectory() as tmp:
                    rules = {kind: [{"ids": ["s0000100"], "tokens": ["{PLAYER}"], "evidence": evidence}]}
                    with self.assertRaisesRegex(ValueError, "has no evidence"):
                        editordata.keyed_rules(rules, Aliases())
                    with self.assertRaisesRegex(ValueError, "has no evidence"):
                        editorcheck.write_bundle(Path(tmp) / "checker.zip", rules)
                    self.assertFalse((Path(tmp) / "checker.zip").exists())

    def test_same_as_batch_check(self):
        texts = {
            "s0000100": ["Привет, {PLAYER}! Держи Зелье. Оно немного лечит покемона.",
                         "Привет! Держи Зелье...",   # droppable token, three dots
                         "Привет, {PLAYER}! Держи. " * 6,   # wraps past the English lines
                         "Привет, {STR_VAR_1}!\\nДержи эту штуку, она немного лечит покемонов и людей, верно?",
                         "Версия @VERSION@, {PLAYER}."],
            "s0000200": ["Зелье", "Лекарство от всех болезней", ""],
            "s0000300": ["Сумка", "Большая сумка", "Сумка\\nвторая"],   # small font
            "species:1": ["Ивизавр", "Ивизаврище"],   # other-style window
        }
        n = 0
        for sid, ts in texts.items():
            for t in ts:
                with self.subTest(sid=sid, text=t):
                    laid, probs = self.batch_check(sid, t)
                    r = json.loads(self.checker.check_json(json.dumps(self.by_id[sid]), t))
                    self.assertEqual([p["message"] for p in r["problems"]], probs)
                    self.assertEqual((r["laid"], r["text"]), (laid, expand(t, "1.2.3")))
                    self.assertEqual((r["errors"], r["warnings"]),
                                     (sum("(warning)" not in p for p in probs), sum("(warning)" in p for p in probs)))
                    me = entry_measure(self.measure, self.limits[sid])
                    # no line here is 1 px over
                    self.assertEqual(r["lines"], [[{"text": l, "width": line_width(l, me, self.cm), "shadow": False}
                                                   for l in lines_of(par)] for par in paragraphs(laid)])
                    n += len(probs)
        self.assertGreater(n, 10)

    def test_lines_that_wait_carry_the_arrow_room(self):
        e = json.loads(json.dumps(self.by_id["s0000100"]))
        self.assertEqual(e["window"]["kind"], "dialogue")
        e["window"]["arrow"] = 10
        e["window"].pop("consumers", None)
        room = e["window"]["width"] - 10
        r = self.checker.check(e, "Привет!\\nДержи.\\pВсё.")
        self.assertEqual([[l.get("room") for l in box] for box in r["lines"]], [[None, room], [None]])
        self.assertEqual(r["lines"][0][1]["shadow"], False)
        me = entry_measure(self.measure, self.limits["s0000100"])
        crowded = "а"
        while line_width(crowded, me, self.cm) <= room:
            crowded += "а"
        self.assertLessEqual(line_width(crowded, me, self.cm), e["window"]["width"])
        r = self.checker.check(e, "Привет!\\n" + crowded + "\\pВсё.")
        self.assertTrue(any(p["message"].startswith("line leaves no room for the prompt arrow: box 1:")
                            and p["severity"] == "error" for p in r["problems"]), r["problems"])

    def test_arrow_consumer_parity_in_every_kind(self):
        from gen3tl.check.layout import arrow_overflows
        from gen3tl.web.editorcheck import limit_of
        for kind in ("dialogue", "battle", "single", "field", "multiline"):
            for arrow in (0, 10, 18):
                e = json.loads(json.dumps(self.by_id["s0000100"]))
                e["window"] = {"kind": kind, "width": 60, "lines": 8, "arrow": arrow,
                               "consumers": [{"name": "sample window", "width": 60, "arrow": arrow,
                                              "arrow_source": "declared", "arrow_confirmed": True}]}
                for text in ("AAA\\lBBB", "AAA\\pBBB", "AAA{PAUSE_UNTIL_PRESS}", "AAA",
                             "AAA\\n" + "W" * 10 + "\\pBBB"):
                    with self.subTest(kind=kind, arrow=arrow, text=text):
                        result = self.checker.check(e, text)
                        expected = arrow_overflows(result["laid"], limit_of(e["window"]), self.measure, self.cm)
                        actual = [p["message"] for p in result["problems"] if "prompt arrow" in p["message"]]
                        self.assertEqual(actual, expected)
                        rooms = [l["room"] for box in result["lines"] for l in box if "room" in l]
                        self.assertEqual(bool(rooms), bool(arrow and ("\\l" in result["laid"] or "\\p" in result["laid"])))
                        self.assertTrue(all(room == 60 - arrow for room in rooms))

    def test_runtime_scroll_parity(self):
        from gen3tl.check.layout import waiting_windows
        from gen3tl.web.editorcheck import limit_of
        for after in (None, 0, 1, 2):
            for arrow in (0, 10):
                entry = {"id": "sample", "source_text": "A", "window": {
                    "kind": "dialogue", "width": 60, "lines": 2, "newline_scroll_after": after,
                    "consumers": [{"name": "ordinary", "width": 60, "arrow": 10},
                                  {"name": "scrolling", "width": 70, "arrow": arrow, "newline_scroll_after": after}]}}
                lim = limit_of(entry["window"])
                for text in ("A\\nBBBBBBBBB\\nC\\nD", "A\\nB\\pC\\nD", "A\\lB", "A{PAUSE_UNTIL_PRESS}",
                             "aaa bbb ccc ddddd ee"):
                    with self.subTest(after=after, arrow=arrow, text=text):
                        result = self.checker.check(entry, text)
                        laid, problems = entry_problems("A", text, lim, self.measure, self.cm)
                        self.assertEqual(result["laid"], laid)
                        self.assertEqual([p["message"] for p in result["problems"]], problems)
                        expected = [[c["width"] - c["arrow"] if c else None for c in row]
                                    for row in waiting_windows(laid, lim)]
                        self.assertEqual([[l.get("room") for l in row] for row in result["lines"]], expected)

    def test_instant_print_errors_match_entry_check(self):
        from gen3tl.web.editorcheck import limit_of
        for shared in (False, True):
            for instant in (None, False, True):
                consumers = [{"name": "banner window", "width": 80, "arrow": 10}]
                if instant is not None:
                    consumers[0]["instant_print"] = instant
                if shared:
                    consumers.insert(0, {"name": "ordinary window", "width": 60, "arrow": 10})
                entry = {"id": "sample", "source_text": "A", "window": {
                    "kind": "multiline", "width": 60 if shared else 80, "lines": 2, "consumers": consumers}}
                for text in ("A\\lB", "A\\pB", "A\\p", "A{FA}B", "A{ FB }B", "A{PAUSE FA}", "A\\nB", "A"):
                    with self.subTest(shared=shared, instant=instant, text=text):
                        laid, problems = entry_problems("A", text, limit_of(entry["window"]), self.measure, self.cm)
                        result = self.checker.check(entry, text)
                        self.assertEqual(result["laid"], laid)
                        self.assertEqual([p["message"] for p in result["problems"]], problems)
                        found = [p for p in result["problems"] if "prints instantly" in p["message"]]
                        self.assertEqual(bool(found), instant is True and any(code in text for code in ("\\l", "\\p", "{FA}", "{ FB }")))
                        if found:
                            self.assertEqual(found[0]["severity"], "error")
                            self.assertIn("banner window", found[0]["message"])

    def test_without_the_english(self):
        # tokens and box lines check as text; typography needs it
        bare = {e["id"]: e for e in self.doc["entries"]}
        for sid, t in (("s0000100", "Привет, {STR_VAR_1}! Держи Зелье..."), ("s0000100", "Привет, {PLAYER}! Зелье"),
                       ("s0000100", "Привет, {PLAYER}! Держи. " * 6), ("s0000200", ""), ("species:1", "Ивизаврище")):
            with self.subTest(sid=sid, text=t):
                full, part = self.checker.check(self.by_id[sid], t), self.checker.check(bare[sid], t)
                self.assertNotIn("unavailable", full)
                self.assertEqual(part["unavailable"], ["typography", "glossary"])
                self.assertEqual([p["message"] for p in part["problems"]],
                                 [p["message"] for p in full["problems"]
                                  if not p["message"].startswith(("typography: ", "glossary term "))])
                self.assertEqual(part["lines"], full["lines"])
        self.assertIn("placeholders differ", self.checker.check(bare["s0000100"], "Привет, {STR_VAR_1}!")
                      ["problems"][0]["message"])

    def test_problems_seen(self):
        msgs = self.msgs
        self.assertEqual(msgs("s0000100", "Привет! Держи Зелье."), [])   # {PLAYER} droppable here
        self.assertIn("typography: three dots", msgs("s0000100", "Привет, {PLAYER}! Зелье..."))
        self.assertIn("glossary term 'Potion' -> 'Зелье' not found (warning)", msgs("s0000100", "Привет, {PLAYER}!"))
        self.assertTrue(any(m.startswith("line too wide") and "(unbound-small)" in m
                            for m in msgs("species:1", "Ивизаврище")))
        # small font: narrower than the main font
        small = self.checker.check(self.by_id["s0000300"], "Сумка")["lines"][0][0]["width"]
        self.assertEqual(small, line_width("Сумка", self.measures["unbound-small"][0], self.cm))
        self.assertLess(small, line_width("Сумка", self.measure, self.cm))

    def test_checker_bytes_ignore_missing_and_multiline_term_projections(self):
        latin = editorcheck.latin_widths(self.doc["fonts"], ROM)
        expected = [self.checker.check_json(e, e["translation"]) for e in self.by_id.values()]
        for notes in (None, "First line.\nSecond line.\nstatus: unreviewed"):
            with self.subTest(notes=notes):
                doc = json.loads(json.dumps(self.doc))
                for tid, row in doc["glossary"].items():
                    row["note_ids"] = ["context:" + tid]
                    row.pop("notes")
                    if notes is not None:
                        row["notes"] = notes
                    term = editorcheck.term_of(tid, row)
                    self.assertEqual(term.note_ids, tuple(row["note_ids"]))
                checker = editorcheck.Checker(doc, latin, PROF["qa"], "1.2.3")
                self.assertEqual([checker.check_json(e, e["translation"]) for e in self.by_id.values()], expected)

    def test_isolated_bundle_accepts_omitted_projections(self):
        doc = json.loads(json.dumps(self.doc))
        for tid, term in doc["glossary"].items():
            term["note_ids"] = ["context:" + tid]
            term.pop("notes", None)
        for entry in doc["entries"]:
            entry.pop("note", None)
            entry.pop("translator_notes", None)
        latin = editorcheck.latin_widths(doc["fonts"], ROM)
        expected = [self.checker.check(e, e["translation"]) for e in self.doc["entries"]]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "checker.zip"
            editorcheck.write_bundle(archive, PROF["qa"])
            with zipfile.ZipFile(archive) as bundle:
                bundle.extractall(root)
            (root / "input.json").write_text(json.dumps({
                "doc": doc, "latin": {style: list(widths) for style, widths in latin.items()}}))
            code = '''import json, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from gen3tl.web.editorcheck import Checker
root = Path(sys.argv[1])
data = json.loads((root / "input.json").read_text())
checker = Checker(data["doc"], data["latin"], json.loads((root / "rules.json").read_text()), "1.2.3")
print(json.dumps([checker.check(e, e["translation"]) for e in data["doc"]["entries"]]))
'''
            result = subprocess.run([sys.executable, "-I", "-c", code, tmp], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout), expected)

    def test_version(self):
        # the release version replaces the token before measuring
        r = self.checker.check(self.by_id["s0000100"], "Версия @VERSION@, {PLAYER}.")
        self.assertEqual(r["text"], "Версия 1.2.3, {PLAYER}.")
        self.assertNotIn("@", r["laid"])
        # no version: the token is not encodable
        header = {k: v for k, v in self.doc.items() if k != "entries"}
        latin = editorcheck.latin_widths(self.doc["fonts"], ROM)
        r = editorcheck.Checker(header, latin, PROF["qa"]).check(self.by_id["s0000100"], "Версия @VERSION@.")
        self.assertEqual([p["severity"] for p in r["problems"]], ["error"])
        self.assertTrue(r["problems"][0]["message"].startswith("not encodable: character '@'"))

    def test_not_encodable(self):
        # batch and editor report equally
        r = self.checker.check(self.by_id["s0000100"], "Привет, {PLAYER}! 中")
        self.assertEqual([p["message"] for p in r["problems"]],
                         ["not encodable: character '中' (U+4E2D) has no byte, in 'Привет, {PLAYER}! 中'"])
        self.assertEqual(r["lines"], [[{"text": "Привет, {PLAYER}! 中", "width": None, "shadow": False}]])
        for sid in ("s0000100", "species:1"):
            text = "Привет, {PLAYER}! 中"
            laid, problems = self.batch_check(sid, text)
            self.assertEqual(laid, text)
            self.assertEqual(problems, [p["message"] for p in self.checker.check(self.by_id[sid], text)["problems"]])

    def test_no_window(self):
        r = self.checker.check({"id": "s0000900", "source_text": "Hi", "window": None}, "Привет")
        self.assertEqual([p["message"] for p in r["problems"]], ["no inventory entry for this id"])

    def test_rom_widths(self):
        latin = editorcheck.latin_widths(self.doc["fonts"], ROM, self.doc["rom"]["sha1"])
        self.assertEqual({s: (len(w), w[0], w[255]) for s, w in latin.items()},
                         {"unbound": (512, 6, 6), "unbound-small": (512, 5, 5)})
        with self.assertRaises(ValueError):
            editorcheck.latin_widths(self.doc["fonts"], ROM + b"\0", self.doc["rom"]["sha1"])

    def test_copied_letters_take_the_rom_width_of_their_glyph(self):
        # А (87) copies A (BB)
        style = self.doc["fonts"]["styles"]["unbound"]
        self.assertEqual(style["copy"]["87"], "BB")
        latin = bytes(range(256)) * 2
        table = editorcheck.glyph_table(style, latin)
        self.assertEqual((table[0x87], table[0xBB], table[0x88], table[0x86]), (0xBB, 0xBB, 0xBC, 0x86))
        self.assertEqual(table[0x37], style["pack"]["37"])
        self.assertEqual(editorcheck.glyph_table({"pack": {}}, latin), list(latin))   # data without copies

    def test_extended_pack_width_and_shadow_are_available(self):
        style = {"pack": {"105": 10}, "shadow": ["105"], "format": "16x16", "rom": {"count": 512}}
        latin = bytes([6] * 512)
        widths = editorcheck.glyph_table(style, latin)
        shadows = editorcheck.shadow_table(style, latin)
        self.assertEqual((len(widths), widths[0x105], widths[0x106]), (512, 10, 6))
        self.assertTrue(shadows[0x105])
        self.assertFalse(shadows[0x106])

    def test_leading_clear_to(self):
        # a marked entry may lead with {CLEAR_TO n}.
        # n centres it in the rule's window.
        self.assertIn("addable", editorcheck.RULES)   # the bundle's rules.json carries the rule
        rule = {"ids": ["s0000200"], "tokens": ["{CLEAR_TO}"], "window": 40, "x": 2, "evidence": "test"}
        rules = dict(PROF["qa"], addable=[rule])
        header = {k: v for k, v in self.doc.items() if k != "entries"}
        latin = editorcheck.latin_widths(self.doc["fonts"], ROM, self.doc["rom"]["sha1"])
        checker = editorcheck.Checker(json.dumps(header), latin, json.dumps(rules), "1.2.3")
        lim = self.limits["s0000200"]
        n = (40 - line_width("Зелье", entry_measure(self.measure, lim), self.cm)) // 2 - 2
        self.assertGreater(n, 1)

        def msgs(sid, text):
            return [p["message"] for p in checker.check(self.by_id[sid], text)["problems"]]
        self.assertEqual(msgs("s0000200", f"{{CLEAR_TO {n:02X}}}Зелье"), [])
        self.assertEqual(msgs("s0000200", f"{{CLEAR_TO {n - 1:02X}}}Зелье"),
                         [f"not centred in the 40 px window: lead with {{CLEAR_TO {n:02X}}} (warning)"])
        self.assertEqual(msgs("s0000200", "Зелье"),
                         [f"not centred in the 40 px window: lead with {{CLEAR_TO {n:02X}}} (warning)"])
        self.assertIn("placeholders differ", msgs("s0000200", f"Зелье{{CLEAR_TO {n:02X}}}"))   # not leading
        self.assertIn("placeholders differ", msgs("s0000100", "{CLEAR_TO 05}Привет, {PLAYER}! Держи Зелье."))
        # Both paths must report identical problems.
        leading = qa.addable_tokens(rules)
        for sid, t in (("s0000200", f"{{CLEAR_TO {n - 1:02X}}}Зелье"), ("s0000200", "Зелье"),
                       ("s0000100", "{CLEAR_TO 05}Привет, {PLAYER}! Держи Зелье.")):
            with self.subTest(sid=sid, text=t):
                optional = set(rules["optional_tokens"]) | qa.droppable_tokens(rules).get(sid, set())
                _, probs = entry_problems(self.by_id[sid]["source_text"], t, self.limits[sid], self.measure, self.cm,
                                          optional, rules["forbidden"], self.windows.other(sid), self.measures,
                                          TermMatcher(TERMS), leading.get(sid))
                self.assertEqual(msgs(sid, t), probs)
