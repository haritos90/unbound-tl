from test_roots import TOOLKIT_ROOT
"""Qa gate checks and fixtures."""

import sys
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(TOOLKIT_ROOT / "src"))

from gen3tl.catalog.source import digest
from gen3tl.check import qa
from gen3tl.check.layout import Limit, Measure, key_count
from gen3tl.catalog.po import KEY_ONLY, SOURCE_FIELD, PoEntry, write

from qa_support import PACK, entry, fixed, setUpModule, tabled, tearDownModule


class SharedLimitsTest(unittest.TestCase):
    def prepared(self, catalog):
        return {"profile": SimpleNamespace(data={}), "inventory": {}, "measure": Measure(lambda b: 6, {}),
                "charmap": PACK.charmap(), "context": {}, "rom": SimpleNamespace(sha1=lambda: "a" * 40),
                "english_slots": False, "catalog": catalog, "limits": object()}

    def test_catalog_change_between_computations_invalidates_shared_limits(self):
        from gen3tl.cli.common import _share_limits, _shared_limits
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "a.po"
            write(path, [PoEntry("key", "key", "One")], {"Language": "ru"})
            catalog = {"key": (path, PoEntry("key", "key", "One"))}
            args = SimpleNamespace(runtime={}, po_root=root)
            prepared = self.prepared(catalog)
            compute = mock.Mock(return_value=prepared)

            def current():
                shared = _shared_limits(args, prepared)
                if shared is not None:
                    return shared
                result = compute()
                _share_limits(args, result)
                return result

            self.assertIs(current(), prepared)
            self.assertIs(current(), prepared)
            self.assertEqual(compute.call_count, 1)
            catalog["key"][1].msgstr = "Changed"
            self.assertIs(current(), prepared)
            self.assertEqual(compute.call_count, 2)

    def test_second_project_does_not_reuse_shared_limits(self):
        from gen3tl.cli.common import _share_limits, _shared_limits
        with tempfile.TemporaryDirectory() as tmp:
            first = Path(tmp) / "first"
            second = Path(tmp) / "second"
            for root in (first, second):
                write(root / "a.po", [PoEntry("key", "key", "One")], {"Language": "ru"})
            args = SimpleNamespace(runtime={}, po_root=first)
            catalog = {"key": (first / "a.po", PoEntry("key", "key", "One"))}
            _share_limits(args, self.prepared(catalog))
            other = SimpleNamespace(runtime=args.runtime, po_root=second)
            other_catalog = {"key": (second / "a.po", PoEntry("key", "key", "One"))}
            self.assertIsNone(_shared_limits(other, self.prepared(other_catalog)))

    def test_changed_measure_does_not_reuse_shared_limits(self):
        from gen3tl.cli.common import _share_limits, _shared_limits
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "a.po"
            write(path, [PoEntry("key", "key", "One")], {"Language": "ru"})
            catalog = {"key": (path, PoEntry("key", "key", "One"))}
            args = SimpleNamespace(runtime={}, po_root=root)
            _share_limits(args, self.prepared(catalog))
            candidate = self.prepared(catalog)
            candidate["measure"] = Measure(lambda b: 7, {})
            self.assertIsNone(_shared_limits(args, candidate))


class QaGateTest(unittest.TestCase):
    def test_instant_print_gate_names_the_restricting_consumer(self):
        sid = "s0000100"
        for shared in (False, True):
            rows = [{"name": "instant", "where": "instant window", "base": 0x10, "stride": 4,
                     "count": 1, "width": 80, "instant_print": True, "evidence": "Instant printer."}]
            if shared:
                rows.append({"name": "ordinary", "base": 0x10, "stride": 4, "count": 1,
                             "width": 60, "box": "dialogue"})
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                for text in ("A\\lB", "A\\pB", "A\\nB"):
                    with self.subTest(shared=shared, text=text):
                        write(root / "a.po", [PoEntry(sid, "A", text)], {})
                        gate = qa.run({"layout": {"table_window": rows}}, {"entries": [entry(sid, "A")]},
                                      root, PACK.charmap(), Measure(lambda b: 1, {}), set())
                        found = [f for f in gate.findings if "prints instantly" in f.message]
                        self.assertEqual(bool(found), "\\l" in text or "\\p" in text)
                        if found:
                            self.assertEqual(found[0].severity, "error")
                            self.assertIn("instant window", found[0].message)

    def test_source_glyph_collision_requires_a_built_replacement(self):
        sid = "s0012001"
        original = "{39}ñ{39}ñ{0A}ÂÉ+"
        prof = {"layout": {"dialogue_width": 208},
                "qa": {"droppable": [{"ids": [sid], "tokens": ["{39}", "{0A}"],
                                       "evidence": "Japanese literal glyphs."}]}}
        inv = {"entries": [entry(sid, original)]}
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for target, flags, expected in [("", [], True), (original, [], True),
                                             ("Круговой обмен", ["fuzzy"], False),   # translated: built alike
                                             ("Круговой обмен", [], False)]:
                write(root / "test.po", [PoEntry(sid, original, target, flags=flags)], {})
                gate = qa.run(prof, inv, root, PACK.charmap(), Measure(lambda b: 6, {}), {0x39})
                collision = any("source glyph collision" in row.message for row in gate.findings)
                self.assertEqual(collision, expected, (target, flags))

    def test_name_binding_rejects_generic_homonym(self):
        from gen3tl.lang.termbase import Term, save
        prof = {"layout": {"dialogue_width": 208}}
        inv = {"entries": [entry("s0000100", "Guy")]}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            glossary = root / "glossary.tsv"
            save(glossary, [Term("speaker:guy", "speaker", "Guy", "Мужчина", status="approved"),
                            Term("character:guy", "character", "Guy", "Гай", status="approved")])
            for target, missing in [("Гай", False), ("Мужчина", True)]:
                write(root / "names.po", [PoEntry("s0000100", "Guy", target,
                      translator=["filled from glossary character:guy"])], {})
                gate = qa.run(prof, inv, root, PACK.charmap(), Measure(lambda b: 6, {}),
                              set(PACK.glyph_slots()), glossary=glossary)
                findings = [f for f in gate.findings if "glossary" in f.message]
                self.assertEqual(bool(findings), missing, findings)

    def test_findings(self):
        prof = {"layout": {"dialogue_width": 208}, "qa": {"forbidden": {"\\.\\.\\.": "three dots"}}}
        inv = {"entries": [entry("s0000100", "Hi, {PLAYER}!"), entry("s0000200", "Box", ["save-link"]),
                           entry("s0000300", "Wait..."), entry("s0000400", "Fine.")]}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / "a.po", [
                PoEntry("s0000100", "Hi, {PLAYER}!", "Привет!"),          # placeholder lost
                PoEntry("s0000200", "Box", "Ящик"),                       # save-link: Russian allowed
                PoEntry("s0000300", "Wait...", "Стой..."),                # typography
                PoEntry("s0000400", "Fine.", "Хорошо."),                  # clean
            ], {})
            m = Measure(lambda b: 6, {"PLAYER": 42})
            gate = qa.run(prof, inv, root, PACK.charmap(), m, set(PACK.glyph_slots()))
            msgs = {(f.id, f.message.split(":")[0]) for f in gate.findings if f.severity == "error"}
            self.assertIn(("s0000100", "placeholders differ"), msgs)
            self.assertFalse(any(i == "s0000200" for i, _ in msgs))
            self.assertIn(("s0000300", "typography"), msgs)
            self.assertFalse(any(i == "s0000400" for i, _ in msgs))
            self.assertEqual(gate.checked, 4)

    def test_dropped_written_breaks_warn(self):
        # a written line wider than the window
        prof = {"layout": {"dialogue_width": 208}}
        inv = {"entries": [entry("s0000100", "A line.\\nAnother line."), entry("s0000200", "Short.\\nLines."),
                           entry("s0000300", "Enter the\\nHall.")]}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / "a.po", [
                PoEntry("s0000100", "A line.\\nAnother line.", "Это очень-очень длинная строка для этого окна\\nи вторая."),
                PoEntry("s0000200", "Short.\\nLines.", "Коротко.\\nСтроки."),
                PoEntry("s0000300", "Enter the\\nHall.", "Войти в\\nЗал."),   # short word ends a written line
            ], {})
            gate = qa.run(prof, inv, root, PACK.charmap(), Measure(lambda b: 6, {}), set(PACK.glyph_slots()))
            warned = {f.id for f in gate.findings
                      if f.severity == "warning" and "drops the written breaks" in f.message}
            self.assertEqual(warned, {"s0000100"})
            ends = {f.id for f in gate.findings if f.message.startswith("written line ends with «в»")}
            self.assertEqual(ends, {"s0000300"})

    def test_russian_letters_own_their_bytes(self):
        # look-alikes are Cyrillic; mixed words are errors
        prof = {"layout": {"dialogue_width": 208}}
        inv = {"entries": [entry("s0000200", "Box", ["save-link"]), entry("s0000300", "Cat"),
                           entry("s0000400", "Crystal-Z"), entry("s0000500", "Unown B"), entry("s0000600", "Ok")]}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / "a.po", [
                PoEntry("s0000200", "Box", "СОК"),          # look-alikes only, save-link
                PoEntry("s0000300", "Cat", "Кoт"),          # Latin o inside a Russian word
                PoEntry("s0000400", "Crystal-Z", "Кристалл-Z"),
                PoEntry("s0000500", "Unown B", "Аноун B"),
                PoEntry("s0000600", "Ok", "OK"),            # Latin only
            ], {})
            gate = qa.run(prof, inv, root, PACK.charmap(), Measure(lambda b: 6, {}), set(PACK.chars.values()))
            errors = {(f.id, f.message) for f in gate.findings if f.severity == "error"}
            self.assertEqual(errors, {("s0000300", "Latin and Cyrillic letters mixed inside a word")})

    def test_save_link_strings_take_russian(self):
        # save and link strings are translated like other text
        prof = {"layout": {"dialogue_width": 208}}
        inv = {"entries": [entry("s0000200", "Box", ["save-link"]), entry("s0000300", "Egg", ["save-link"]),
                           entry("s0000400", "Francis", ["save-link"])]}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / "a.po", [PoEntry("s0000200", "Box", "Ящик"), PoEntry("s0000300", "Egg", "Яйцо"),
                                  PoEntry("s0000400", "Francis", "Фрэнсис")], {})
            gate = qa.run(prof, inv, root, PACK.charmap(), Measure(lambda b: 6, {}), set(PACK.chars.values()))
        self.assertEqual(gate.checked, 3)
        self.assertEqual([f for f in gate.findings if f.severity == "error"], [])

    def test_centring_spaces_are_not_double_spaces(self):
        # English centring spaces stay
        prof = {"layout": {"dialogue_width": 208}, "qa": {"forbidden": {"  ": "double space"}}}
        inv = {"entries": [entry("s0000100", "    16 Years Ago"), entry("s0000200", "Go on.")]}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / "a.po", [PoEntry("s0000100", "    16 Years Ago", "    16 лет  назад"),   # inner double
                                  PoEntry("s0000200", "Go on.", "  Иди.")], {})               # English not indented
            gate = qa.run(prof, inv, root, PACK.charmap(), Measure(lambda b: 6, {}), set(PACK.glyph_slots()))
            self.assertEqual({f.id for f in gate.findings if f.message.startswith("typography")},
                             {"s0000100", "s0000200"})
            write(root / "a.po", [PoEntry("s0000100", "    16 Years Ago", "    16 лет назад"),
                                  PoEntry("s0000200", "Go on.", "Иди.")], {})
            gate = qa.run(prof, inv, root, PACK.charmap(), Measure(lambda b: 6, {}), set(PACK.glyph_slots()))
            self.assertFalse([f for f in gate.findings if f.message.startswith("typography")])

    def test_space_runs_of_the_english_are_not_double_spaces(self):
        # a space run of the English stays (s1EDD100)
        forbidden = {"  ": "double space", "\\.\\.\\.": "three dots"}
        vroom = "  FIRST   SECOND\\pExample source text!"
        self.assertEqual(qa.typography_problems(vroom, "  ВРУМ   ВРУМ\\pЧёрный Ферроторн!", forbidden), [])
        self.assertEqual(qa.typography_problems(vroom, "  ВРУМ    ВРУМ\\pЧёрный Ферроторн!", forbidden),
                         ["double space"])                                    # a longer run
        self.assertEqual(qa.typography_problems(vroom, "ВРУМ   ВРУМ  Чёрный Ферроторн!", forbidden),
                         ["double space"])                                    # one run more than the English
        self.assertEqual(qa.typography_problems("Go on now.", "Иди  же.", forbidden), ["double space"])
        self.assertEqual(qa.typography_problems("Go...", "Иди...", forbidden), ["three dots"])
        # the leading and trailing exemptions stay
        self.assertEqual(qa.typography_problems("  Go  ", "  Иди  ", forbidden), [])
        self.assertEqual(qa.typography_problems("Go", "  Иди  ", forbidden), ["double space"])
        prof = {"layout": {"dialogue_width": 208}, "qa": {"forbidden": forbidden}}
        inv = {"entries": [entry("s0000100", vroom)]}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / "a.po", [PoEntry("s0000100", vroom, "  ВРУМ   ВРУМ\\pЧёрный Ферроторн!")], {})
            gate = qa.run(prof, inv, root, PACK.charmap(), Measure(lambda b: 6, {}), set(PACK.glyph_slots()))
            self.assertFalse([f for f in gate.findings if f.message.startswith("typography")])

    def test_typography_without_english_leaves_spacing_to_the_english(self):
        forbidden = {"  ": "double space", "\\.\\.\\.": "three dots"}
        self.assertEqual(qa.typography_problems(None, "Иди  же.", forbidden), [])   # the English may share the run
        self.assertEqual(qa.spacing_undecided("Иди  же.", forbidden), ["double space"])
        self.assertEqual(qa.typography_problems(None, "Иди...", forbidden), ["three dots"])
        self.assertEqual(qa.typography_problems(None, "Иди...  же", forbidden), ["three dots"])
        self.assertEqual(qa.typography_problems(None, "Иди.", forbidden), [])
        self.assertEqual(qa.typography_problems(None, "áé      ", forbidden, keys=True), [])

    def test_facts_typography_selects_only_the_rules_marked_independent(self):
        rules = {"forbidden": {"  ": "double space", "\\.\\.\\.": "three dots"},
                 "forbidden_needs_source": {"  ": False}}
        self.assertEqual(qa.typography_without_english(rules),
                         ({"  ": "double space"}, ["three dots"]))

    def test_report_lists_skipped_typography_by_name(self):
        gate = qa.Gate()
        gate.skipped_typography = ["three dots"]
        rep = qa.report(gate)
        self.assertIn("## Skipped without the English", rep)
        self.assertIn("- three dots", rep)

    def test_facts_typography_runs_without_the_english(self):
        from gen3tl.catalog.source import digest
        prof = {"layout": {"dialogue_width": 60},
                "qa": {"forbidden": {"  ": "double space", "\\.\\.\\.": "three dots", "…\\.": "ellipsis with a dot"},
                       "forbidden_needs_source": {"  ": False, "\\.\\.\\.": False}}}
        inv = {"entries": [entry("s0000100", "Go on.")]}
        source = {"s0000100": [digest("Go on."), [], [1], [36],
                               ["dialogue", 60, 2, None, None, None, None]]}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / "a.po", [PoEntry("s0000100", "s0000100", "Иди  же...")],
                  {SOURCE_FIELD: KEY_ONLY})
            gate = qa.run(prof, inv, root, PACK.charmap(), Measure(lambda b: 6, {}),
                          set(PACK.glyph_slots()), source=source)
        self.assertEqual([f.message for f in gate.findings if f.message.startswith("typography")],
                         ["typography: three dots"])
        # the English spacing decides the run
        self.assertEqual(gate.skipped_typography, ["double space", "ellipsis with a dot"])

    def test_pack_keyboard_rows_skip_text_typography(self):
        prof = {"layout": {"dialogue_width": 208}, "qa": {"forbidden": {"  ": "double space"}},
                "keyboard": {"row_bindings": {"lower_keys_1": "s0000100"},
                             "rows": {"lower_keys_1": "A  B"}}}
        inv = {"entries": [entry("s0000100", "A B"), entry("s0000200", "Go on now.")]}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / "a.po", [PoEntry("s0000100", "A B"),
                                  PoEntry("s0000200", "Go on now.", "Иди  же.")], {})
            gate = qa.run(prof, inv, root, PACK.charmap(), Measure(lambda b: 6, {}), set(PACK.glyph_slots()))
            self.assertEqual({f.id for f in gate.findings if f.message.startswith("typography")},
                             {"s0000200"})

    def test_pack_keyboard_rows_skip_same_english_warning(self):
        prof = {"layout": {"dialogue_width": 208},
                "keyboard": {"row_bindings": {"lower_keys_1": "s0000100", "lower_keys_2": "s0000200"},
                             "rows": {"lower_keys_1": "А Б", "lower_keys_2": "В Г"}}}
        inv = {"entries": [entry("s0000100", "A B"), entry("s0000200", "A B"),
                           entry("s0000300", "Hello"), entry("s0000400", "Hello")]}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / "a.po", [PoEntry("s0000100", "A B"), PoEntry("s0000200", "A B"),
                                  PoEntry("s0000300", "Hello", "Привет"),
                                  PoEntry("s0000400", "Hello", "Здравствуй")], {})
            gate = qa.run(prof, inv, root, PACK.charmap(), Measure(lambda b: 6, {}), set(PACK.glyph_slots()))
            warned = [f for f in gate.findings
                      if f.severity == "warning" and f.message.startswith("same English")]
            self.assertEqual(len(warned), 1)
            self.assertEqual({i for i in warned[0].id.split(",")}, {"s0000300", "s0000400"})

    def test_the_blank_keys_of_a_key_row_are_no_double_spaces(self):
        from gen3tl.check.entrycheck import entry_problems
        from gen3tl.check.provenance import formatted
        forbidden = {"  ": "double space", "\\.\\.\\.": "three dots"}
        self.assertEqual(qa.typography_problems("abcdef .", "áé      ", forbidden), ["double space"])
        self.assertEqual(qa.typography_problems("abcdef .", "áé      ", forbidden, keys=True), [])
        self.assertEqual(qa.typography_problems("abcdef .", "á  ...  ", forbidden, keys=True), ["three dots"])
        for lim, problems in ((Limit("field", 0, 1, keys=8), []),
                              (Limit("field", 60, 1), ["typography: double space"])):
            with self.subTest(keys=lim.keys):
                _, found = entry_problems("abcdef .", "áé      ", lim, Measure(lambda b: 6, {}), PACK.charmap(),
                                          forbidden=forbidden)
                self.assertEqual([formatted(p) for p in found if p["code"] == "typography"], problems)

    def test_optional_tokens(self):
        prof = {"layout": {}, "qa": {"optional_tokens": ["{PK}", "{MN}"]}}
        inv = {"entries": [entry("s0000100", "{PK}{MN} Trainer"), entry("s0000200", "{PK}{MN} {PLAYER}")]}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / "a.po", [PoEntry("s0000100", "{PK}{MN} Trainer", "Тренер"),        # glyph pair dropped
                                  PoEntry("s0000200", "{PK}{MN} {PLAYER}", "Тренер")], {})  # placeholder lost
            gate = qa.run(prof, inv, root, PACK.charmap(), Measure(lambda b: 6, {"PLAYER": 42}),
                          set(PACK.glyph_slots()))
            errs = {f.id for f in gate.findings if f.severity == "error"}
            self.assertEqual(errs, {"s0000200"})

    def test_droppable_tokens(self):
        # a marked entry may drop the English article slot (s1F8220B)
        en = "A{B_COPY_VAR_2} {B_COPY_VAR_1}\\nexample text."
        ru = "Найдено: {B_COPY_VAR_1}."
        rule = {"ids": ["s0000100"], "tokens": ["{B_COPY_VAR_2}"], "evidence": "code writes 'n'"}
        prof = {"layout": {}, "qa": {"droppable": [rule]}}
        inv = {"entries": [entry("s0000100", en), entry("s0000200", en)]}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / "a.po", [PoEntry("s0000100", en, ru),                       # marked
                                  PoEntry("s0000200", en, ru)], {})                  # unmarked
            gate = qa.run(prof, inv, root, PACK.charmap(), Measure(lambda b: 6, {}), set(PACK.glyph_slots()))
            errs = {f.id for f in gate.findings if f.message.startswith("placeholders differ")}
            self.assertEqual(errs, {"s0000200"})
        # Both checks must permit the omission.
        drop = qa.droppable_tokens(prof["qa"])
        self.assertIsNone(qa.placeholders_differ(en, ru, drop.get("s0000100", set())))
        self.assertIsNotNone(qa.placeholders_differ(en, ru, drop.get("s0000200", set())))
        self.assertIsNone(qa.placeholders_differ(en, "Найдено: {B_COPY_VAR_1}{B_COPY_VAR_2}.", drop["s0000100"]))
        # a marked entry loses no other token
        self.assertIsNotNone(qa.placeholders_differ(en, "Найдено!", drop["s0000100"]))
        with self.assertRaises(ValueError):   # a rule without evidence
            qa.droppable_tokens({"droppable": [{"ids": ["s0000100"], "tokens": ["{B_COPY_VAR_2}"]}]})

    def test_addable_tokens(self):
        # a marked entry may lead with {CLEAR_TO n}
        rule = {"ids": ["s0000100", "s0000300"], "tokens": ["{CLEAR_TO}"], "window": 80, "x": 4,
                "evidence": "printer at x 4"}
        prof = {"layout": {}, "qa": {"addable": [rule]}}
        inv = {"entries": [entry("s0000100", "Exit"), entry("s0000200", "Exit"), entry("s0000300", "Exit")]}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / "a.po", [PoEntry("s0000100", "Exit", "{CLEAR_TO 15}Выход"),    # marked, leading
                                  PoEntry("s0000200", "Exit", "{CLEAR_TO 15}Выход"),    # unmarked
                                  PoEntry("s0000300", "Exit", "Вы{CLEAR_TO 15}ход")], {})   # not leading
            gate = qa.run(prof, inv, root, PACK.charmap(), Measure(lambda b: 6, {}), set(PACK.glyph_slots()))
            errs = {f.id for f in gate.findings if f.message.startswith("placeholders differ")}
            self.assertEqual(errs, {"s0000200", "s0000300"})
        # Both interfaces must permit the insertion.
        add = qa.addable_tokens(prof["qa"])
        self.assertEqual(add["s0000100"], {"{CLEAR_TO}": rule})
        self.assertIsNone(qa.placeholders_differ("Exit", "{CLEAR_TO 15}Выход", set(), add["s0000100"]))
        self.assertIsNotNone(qa.placeholders_differ("Exit", "{CLEAR_TO 15}Выход", set()))
        self.assertIsNotNone(qa.placeholders_differ("Exit", "Выход{CLEAR_TO 15}", set(), add["s0000100"]))
        self.assertIsNotNone(qa.placeholders_differ("Exit", "{CLEAR_TO 15}{CLEAR_TO 20}Выход", set(),
                                                    add["s0000100"]))
        # an English {CLEAR_TO} counts too
        self.assertIsNone(qa.placeholders_differ("A{CLEAR_TO 30}B", "{CLEAR_TO 05}А{CLEAR_TO 30}Б", set(),
                                                 add["s0000100"]))
        self.assertIsNotNone(qa.placeholders_differ("A{CLEAR_TO 30}B", "{CLEAR_TO 05}А{CLEAR_TO 30}Б{CLEAR_TO 40}",
                                                    set(), add["s0000100"]))
        with self.assertRaises(ValueError):   # a rule without evidence
            qa.addable_tokens({"addable": [{"ids": ["s0000100"], "tokens": ["{CLEAR_TO}"]}]})
        with self.assertRaises(ValueError):   # a window without the printer's x
            qa.addable_tokens({"addable": [{"ids": ["s0000100"], "tokens": ["{CLEAR_TO}"], "window": 80,
                                            "evidence": "printer"}]})

    def test_wrapped_dash_line_is_an_error(self):
        # a spaced hyphen opening a wrapped line fails the gate
        prof = {"layout": {"dialogue_width": 60}}
        inv = {"entries": [entry("s0000100", "Hi\\nthere")]}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / "a.po", [PoEntry("s0000100", "Hi\\nthere", "аааа бббб - вв")], {})
            m = Measure(lambda b: 6, {})
            gate = qa.run(prof, inv, root, PACK.charmap(), m, set(PACK.glyph_slots()))
            self.assertFalse([f for f in gate.findings if "spaced hyphen" in f.message])
            # wrap before the rule: the hyphen opens line two
            with mock.patch.object(qa, "layout", lambda text, lim, m, cm: "аааа бббб\\n- вв"):
                gate = qa.run(prof, inv, root, PACK.charmap(), m, set(PACK.glyph_slots()))
            self.assertEqual([(f.id, f.severity) for f in gate.findings if "spaced hyphen" in f.message],
                             [("s0000100", "error")])

    def test_report_counts_and_marks_the_never_shown_entries(self):
        # a tag, no finding; the report counts and marks it
        prof = {"layout": {"dialogue_width": 208}, "qa": {"forbidden": {"\\.\\.\\.": "three dots"}}}
        inv = {"entries": [entry("s0000100", "Wait..."), entry("s0000200", "Fine."), entry("s0000300", "Go.")]}
        tag = "reach: never shown (review: no caller)"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / "a.po", [
                PoEntry("s0000100", "Wait...", "Стой...", extracted=[tag]),    # tagged, typography
                PoEntry("s0000200", "Fine.", "", extracted=[tag]),             # tagged, untranslated
                PoEntry("s0000300", "Go.", "Иди."),
            ], {})
            gate = qa.run(prof, inv, root, PACK.charmap(), Measure(lambda b: 6, {}), set(PACK.glyph_slots()))
        self.assertEqual(gate.never_shown, {"s0000100": "review: no caller", "s0000200": "review: no caller"})
        self.assertEqual(gate.never_checked, {"s0000100"})
        self.assertEqual([(f.id, f.message.split(":")[0]) for f in gate.findings], [("s0000100", "typography")])
        rep = qa.report(gate)
        self.assertIn("Entries checked: 2; errors: 1; warnings: 0; never shown: 2 tagged, 1 of them checked", rep)
        self.assertIn("| review: no caller | 2 | 1 | s0000100 |", rep)
        self.assertIn("- error s0000100 (" + str(root / "a.po") + ") [never shown]: typography", rep)

    def test_spacing_codes_may_change_their_amount(self):
        en = "{CLEAR 0B}a{CLEAR 06}b{COLOR 02}"
        self.assertEqual(qa.token_counts(en), qa.token_counts("{CLEAR 0C}а{CLEAR 05}б{COLOR 02}"))
        self.assertNotEqual(qa.token_counts(en), qa.token_counts("{CLEAR 0B}аб{COLOR 02}"))   # one code lost
        self.assertNotEqual(qa.token_counts(en), qa.token_counts("{CLEAR 0B}а{CLEAR 06}б{COLOR 03}"))


class KeyboardRowTest(unittest.TestCase):
    """Naming keyboard rows: the key cells bind, not the English width."""

    # two keyboards: 8-byte key rows at 0x100.
    # 8 and 6 columns at 0x200; row pointers at 0x300.
    PROF = {"table": [{"name": "kb", "base": 0x100, "stride": 8, "count": 8, "field_length": 8,
                       "terminated": False}],
            "keyboard": {"base_pages": 2, "table": [
                {"name": "keys", "base": 0x100, "entry": 32, "index": "keyboard"},
                {"name": "columns", "base": 0x200, "entry": 1, "index": "keyboard"},
                {"name": "rows", "base": 0x300, "entry": 16, "index": "keyboard", "text": True}]}}
    ROW = "{CLEAR 0B}m{CLEAR 06}n{CLEAR 07}o{CLEAR 1A}p{CLEAR 06}q{CLEAR 07}r{CLEAR 06}s{CLEAR 1B} "
    DIGITS = "{CLEAR 0B}0{CLEAR 10}1{CLEAR 10}2{CLEAR 10}3{CLEAR 10}4{CLEAR 10} "
    INV = {"entries": [fixed("kb:2", "mnopqrs ", "kb"), fixed("kb:4", "01234   ", "kb"),
                       tabled("s0000500", ROW, 0x308), tabled("s0000600", DIGITS, 0x310)]}

    @staticmethod
    def rom():
        from gen3tl.core.rom import Rom
        data = bytearray(0x400)
        data[0x200:0x202] = bytes([8, 6])
        return Rom(data)

    def gate(self, ru: dict, prof=None):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / "system" / "a.po", [PoEntry(x["id"], x["text"], ru[x["id"]]) for x in self.INV["entries"]], {})
            return qa.run(prof or self.PROF, self.INV, root, PACK.charmap(), Measure(lambda b: 6, {}),
                          set(PACK.glyph_slots()), rom=self.rom())

    def test_key_cells(self):
        self.assertEqual(qa.keyboard_rows(self.PROF, self.INV, self.rom()),
                         {"kb:2": 8, "kb:4": 6, "s0000500": 8, "s0000600": 6})

    def test_a_letter_in_the_cell_of_the_english_space(self):
        # 48 px against English 42 px; both keyboards fit
        gate = self.gate({"kb:2": "рстуфхцч", "kb:4": "01234ё  ",
                          "s0000500": self.ROW.replace("m", "р")[:-1] + "ч", "s0000600": self.DIGITS[:-1] + "ё"})
        self.assertEqual(gate.findings, [])

    def test_a_key_past_the_grid(self):
        gate = self.gate({"kb:2": "рстуфхцч", "kb:4": "01234ёЁ ",
                          "s0000500": self.ROW[:-1] + "чш", "s0000600": self.DIGITS[:-1] + "ё"})
        self.assertEqual([(f.id, f.severity, f.message) for f in gate.findings],
                         [("kb:4", "error", "too many keys: 7 > 6: '01234ёЁ '"),
                          ("s0000500", "error", "too many keys: 9 > 8: '{CLEAR 0B}m{CLEAR 06}n{CLEAR 07}o{CLEAR '")])


    def test_a_pack_keyboard_bounds_its_rows_by_its_own_columns(self):
        # the pack keyboard reaches 3 columns, its English copy 8
        prof = {**self.PROF, "keyboard": {**self.PROF["keyboard"], "keyboards": [
            {"name": "accents", "like": 0, "columns": 3}, {"name": "latin", "like": 0, "base": True,
                                                            "columns": 2}, {"name": "digits", "like": 1}]}}
        self.assertEqual(qa.pack_columns(prof, self.INV), {"kb:2": 3, "s0000500": 3})
        three = "{CLEAR 0B}á{CLEAR 06}é{CLEAR 07}í{CLEAR 1A} {CLEAR 06} {CLEAR 07} {CLEAR 06} {CLEAR 1B} "
        digits = {"kb:4": "01234ё  ", "s0000600": self.DIGITS[:-1] + "ё"}
        self.assertEqual(self.gate({"kb:2": "áéí     ", "s0000500": three, **digits}, prof).findings, [])
        four = three.replace("{CLEAR 1A} ", "{CLEAR 1A}ó")
        gate = self.gate({"kb:2": "áéíó    ", "s0000500": four, **digits}, prof)
        self.assertEqual([(f.id, f.severity, f.message) for f in gate.findings],
                         [("kb:2", "error", "too many keys: 4 > 3: 'áéíó    '"),
                          ("s0000500", "error", "too many keys: 4 > 3: '{CLEAR 0B}á{CLEAR 06}é{CLEAR 07}í{CLEAR '")])
        self.assertEqual([f.message for f in self.gate({"kb:2": "áéíó    ", "s0000500": four, **digits}).findings],
                         [])   # the base keyboard's 8 columns

    def test_blank_keys_are_no_double_spaces(self):
        prof = {**self.PROF, "qa": {"forbidden": {"  ": "double space"}}}
        gate = self.gate({"kb:2": "р  с    ", "kb:4": "01234   ", "s0000500": self.ROW, "s0000600": self.DIGITS}, prof)
        self.assertEqual(gate.findings, [])

    def test_blank_keys_after_the_last_key_are_no_keys(self):
        self.assertEqual(key_count("{CLEAR 0B}á{CLEAR 06}é{CLEAR 06} {CLEAR 1A} {CLEAR 19} "), 2)
        self.assertEqual(key_count("{CLEAR 0B}á{CLEAR 06} {CLEAR 06}é{CLEAR 19} "), 3)
        self.assertEqual(key_count("áé      "), 2)


class TrailingSpaceCheckTest(unittest.TestCase):
    """Trailing spaces measured alike in the English and the translation."""

    # blank name of six spaces: 36 px.
    # trailing separator space: 30 px, 24 without.
    # spaces before a colour code: same.
    PROF = {"table": [{"name": "types", "field_length": 7}]}
    INV = {"entries": [fixed("types:0", "Abcde", "types"), fixed("types:1", "      ", "types"),
                       tabled("s0000300", "Abc. ", 0x1000), tabled("s0000400", "Abcd", 0x1004),
                       tabled("s0000500", "Abcd {COLOR 02}", 0x2000), tabled("s0000600", "Abc", 0x2004)]}
    RU = {"types:0": "Абвгд", "types:1": "      ", "s0000300": "Абв. ", "s0000400": "Абвг",
          "s0000500": "Абвг {COLOR 02}", "s0000600": "Абвгд"}

    def run_gate(self, source: bool):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / "system" / "a.po", [PoEntry(x["id"], x["text"], self.RU[x["id"]])
                                             for x in self.INV["entries"]], {})
            return qa.run(self.PROF, self.INV, root, PACK.charmap(), Measure(lambda b: 6, {}),
                          set(PACK.glyph_slots()), source_as_translation=source)

    def test_spaces_before_a_closing_code_set_no_width(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / "system" / "a.po", [PoEntry(x["id"], x["text"], "") for x in self.INV["entries"]], {})
            from gen3tl.catalog.catalog import load_catalog
            lim = qa.compute_limits(self.PROF, self.INV, load_catalog(root), Measure(lambda b: 6, {}),
                                    PACK.charmap())
        self.assertEqual({sid: l.width for sid, l in lim.items()}, {
            "types:0": 30, "types:1": 30, "s0000300": 24, "s0000400": 24, "s0000500": 24, "s0000600": 24})

    def test_translation_padding_counts_as_the_english(self):
        # only s0000600 is wider than its limit where it shows
        self.assertEqual([(f.id, f.severity, f.message) for f in self.run_gate(False).findings],
                         [("s0000600", "error", "line too wide: 30 > 24 px: 'Абвгд'")])

    def test_english_as_translation_is_not_too_wide(self):
        self.assertEqual(self.run_gate(True).findings, [])
