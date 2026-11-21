import json
import shutil
import tempfile
import unittest
from pathlib import Path

from gen3tl.web import snapshotstore as snapshot_store, editorkeyboard, editorsnapshot
from gen3tl.catalog.catalog import load_catalog
from gen3tl.check.layout import Limit, Measure
from gen3tl.core.charmap import Charmap
from gen3tl.build.graphics import inventory_rows

from rom_support import needs_rom, rom_path
from test_roots import TOOLKIT_ROOT
from project_fixture import UNBOUND, unbound, shared_profiles


def setUpModule():
    unittest.enterModuleContext(shared_profiles())


@needs_rom
class PackTest(unittest.TestCase):
    """Every page of the four packs, from the project catalogs and snapshots."""

    LANGUAGES = ("ru", "es", "de", "fr")

    @classmethod
    def setUpClass(cls):
        cls.documents = {}
        cls.addClassCleanup(cls.documents.clear)

    def test_chat_pages_use_each_loaded_pack_and_its_small_font(self):
        for code in self.LANGUAGES:
            with self.subTest(code=code):
                prof, doc = self.document(code)
                chat = doc["chat"]
                self.assertEqual(chat["style"], "unbound-small")
                self.assertEqual((chat["columns"], chat["column_width"]), (5, 8))
                self.assertEqual([p["name"] for p in chat["pages"]], ["chat_upper", "chat_lower", "chat_symbols"])
                from gen3tl.lang.langpack import load_styles
                cm = load_styles(code, prof)[chat["style"]].charmap()
                for page in chat["pages"]:
                    self.assertEqual(len(page["rows"]), 10)
                    for row in page["rows"]:
                        self.assertEqual(row["text"], prof["keyboard"]["rows"][row["name"]])
                        self.assertEqual(row["id"], prof["keyboard"]["row_bindings"][row["name"]])
                        self.assertTrue(row["widths"])
                        self.assertGreaterEqual(row["bytes"], 5)
                        measure = Measure(lambda b: row["widths"][f"{b:02X}"], {})
                        self.assertEqual(editorkeyboard.chat_problems(row["text"], chat, row["bytes"], measure, cm), [])
                upper = chat["pages"][0]["rows"][0]
                self.assertEqual(upper["text"], "АБВГД" if code == "ru" else "ABCDE")
                if code == "ru":
                    self.assertEqual(upper["widths"]["37"], 5)

    def document(self, code):
        if code not in self.documents:
            self.documents[code] = self.load_document(code)
        return self.documents[code]

    def load_document(self, code):
        from gen3tl.project import Registry
        prof = unbound(code)
        project = Registry.load(UNBOUND).resolve("unbound-2.1.1.1", code)
        with tempfile.TemporaryDirectory() as tmp:
            for name in ("tables/naming_keyboard.po", "system/table-03E264C.po"):
                (Path(tmp) / name).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(project.catalog / name, Path(tmp) / name)
            catalog = load_catalog(Path(tmp), prof)
        snapshot = snapshot_store.load(project.snapshot)
        inv, _, _, facts = editorsnapshot.inputs(snapshot, catalog, prof)
        measure, cm, _ = editorsnapshot.measures(prof, code, snapshot["fonts"])
        limits = {sid: Limit("field", 0, 1, keys=n) for sid, n in facts["keys"].items()}
        from gen3tl.lang.langpack import load_styles
        main = prof["font_style"]["style"]
        return prof, editorkeyboard.keyboard_data(prof, catalog, inv, limits, measure, cm,
                                                  load_styles(code, prof)[main], cursor=facts["cursor"])

    def test_every_page_lays_out_its_keys(self):
        for code in self.LANGUAGES:
            with self.subTest(code=code):
                prof, doc = self.document(code)
                kb = prof["keyboard"]
                self.assertEqual(len(doc["pages"]), len(kb["pages"]))
                self.assertEqual(doc["first_page"], kb["first_page"])
                for board, declared in zip(doc["keyboards"], kb["keyboards"]):
                    self.assertEqual(len(board["rows"]), 4)
                    self.assertEqual(board["columns"], declared.get("columns", 6 if declared["like"] == 2 else 8))
                    self.assertEqual(len(board["column_x"]), board["columns"])
                    if declared.get("base"):
                        for row in board["rows"]:
                            self.assertIsNone(row["keys"]["text"])
                            self.assertIsNone(row["display"]["text"])
                            self.assertEqual(row["cells"], [])
                        continue
                    for row in board["rows"]:
                        self.assertTrue(row["keys"]["text"] and row["display"]["text"])
                        cells = row["cells"][:board["columns"]]
                        self.assertTrue(all(c["key"] and c["key"]["code"] for c in cells), row["keys"])
                        self.assertTrue(all(c["key"]["source"] != "none" for c in cells), row["keys"])
                        self.assertTrue(all(c["glyph"] for c in cells), row["display"])
                        xs = [c["glyph"]["x"] for c in cells]
                        self.assertEqual(xs, sorted(xs))
                        self.assertLessEqual(xs[-1] + cells[-1]["glyph"]["width"], doc["window"]["width"])
                    rows = [row["keys"]["text"] for row in board["rows"]]
                    names = [f"{('lower', 'upper', 'symbols')[declared['like']]}_keys_{r}" for r in range(1, 5)]
                    self.assertEqual(rows, [kb["rows"][n] for n in names])
                    self.assertEqual([row["keys"]["name"] for row in board["rows"]], names)
                    self.assertEqual([kb["rows"][row["display"]["name"]] for row in board["rows"]],
                                     [row["display"]["text"] for row in board["rows"]])

    def test_the_opening_pages_use_the_keyboards_the_screen_prints_first(self):
        for code in self.LANGUAGES:
            with self.subTest(code=code):
                _, doc = self.document(code)
                first = doc["first_page"]
                self.assertEqual([doc["pages"][first]["keyboard"], doc["pages"][first + 1]["keyboard"]], [1, 0])
                self.assertEqual(doc["opening"], [{"page": first, "keyboard": 1, "look": 1},
                                                 {"page": first + 1, "keyboard": 0, "look": 2}])
                self.assertEqual([doc["pages"][p["page"]]["look"] for p in doc["opening"]], [1, 2])

    def test_no_reachable_key_of_an_accent_page_enters_a_space(self):
        for code in ("es", "de", "fr"):
            with self.subTest(code=code):
                prof, doc = self.document(code)
                accents = [b for b in doc["keyboards"] if b["like"] in (0, 1) and not b["base"]]
                self.assertEqual(len(accents), 2)
                for board in accents:
                    keys = [c["key"]["char"] for row in board["rows"] for c in row["cells"][:board["columns"]]]
                    self.assertEqual(len(keys), 4 * board["columns"])
                    self.assertNotIn(" ", keys, board["name"])
                    unreachable = {c["key"]["char"] for row in board["rows"] for c in row["cells"][board["columns"]:]}
                    self.assertEqual(unreachable, {" "})
                    shown = [c["glyph"]["char"] for row in board["rows"] for c in row["cells"][:board["columns"]]]
                    self.assertEqual(shown, keys)

    def test_every_page_names_a_label_graphic_of_the_inventory(self):
        for code in self.LANGUAGES:
            with self.subTest(code=code):
                prof, doc = self.document(code)
                ids = {row["id"] for row in inventory_rows(UNBOUND / prof["graphics"]["inventory"])}
                self.assertEqual(doc["labels"], ["G23", "G21", "G22"])
                self.assertTrue(all(doc["labels"][page["look"]] in ids for page in doc["pages"]))

    def test_every_reachable_glyph_sits_in_its_cursor_frame(self):
        for code in self.LANGUAGES:
            with self.subTest(code=code):
                _, doc = self.document(code)
                frame = doc["window"]["cursor"]
                for board in doc["keyboards"]:
                    if board["base"]:
                        continue
                    for r, row in enumerate(board["rows"]):
                        for column, x in enumerate(board["column_x"]):
                            glyph = row["cells"][column]["glyph"]
                            left = x + frame["left"]
                            self.assertTrue(left <= glyph["x"] and glyph["x"] + glyph["width"] <= left + frame["width"],
                                            (board["name"], r, column, glyph))

    def test_cyrillic_pages_use_pack_bytes_at_the_cursor_columns(self):
        prof, doc = self.document("ru")
        upper = next(k for k in doc["keyboards"] if k["like"] == 1 and not k["base"])
        first = upper["rows"][0]["cells"]
        self.assertEqual([c["glyph"]["x"] for c in first], [11, 23, 35, 67, 79, 91, 103, 134])
        self.assertEqual(first[0]["key"], {"char": "А", "code": "87", "source": "copy", "copy": "BB"})
        self.assertEqual(first[1]["key"]["source"], "glyph")
        latin = next(k for k in doc["keyboards"] if k["like"] == 1 and k["base"])
        self.assertIsNone(latin["rows"][0]["keys"]["text"])
        self.assertEqual(latin["rows"][0]["cells"], [])


@needs_rom
class RoundTripTest(unittest.TestCase):
    """An editor export of a keyboard change goes through web import into the pack and back to the tab."""

    @classmethod
    def setUpClass(cls):
        # a clean checkout has no build/
        if (UNBOUND / "build/inventory.json").is_file():
            return
        from gen3tl.discover import inventory
        from gen3tl.project import build_scope
        build = Path(cls.enterClassContext(tempfile.TemporaryDirectory()))
        prof = unbound("ru")
        inventory.save(inventory.build(prof, prof.load_rom(rom_path()), Charmap()), build / "inventory.json")
        cls.enterClassContext(build_scope(build))

    def test_a_key_change_and_a_page_move_reach_the_pack_and_the_tab(self):
        import contextlib
        import io
        from unittest.mock import patch

        from gen3tl.__main__ import main
        from gen3tl.build import keyboard
        prof = unbound("ru")
        rows, names = prof["keyboard"]["rows"], [p["name"] for p in prof["keyboard"]["pages"]]
        moved = names[:3] + [names[4], names[3]]
        # as the tab's draft exports it
        edit = {"rows": {"upper_keys_1": "Ё" + rows["upper_keys_1"][1:],
                         "upper_display_1": rows["upper_display_1"].replace("А", "Ё", 1)},
                "base": {"rows": {k: rows[k] for k in ("upper_keys_1", "upper_display_1")}, "pages": names},
                "pages": moved}
        with tempfile.TemporaryDirectory() as tmp:
            pack = Path(tmp) / "ru"
            shutil.copytree(TOOLKIT_ROOT / "assets/lang/ru", pack)
            export = Path(tmp) / "export.json"
            export.write_text(json.dumps({"profile": "unbound-2.1.1.1", "language": "ru", "entries": [],
                                          "pictures": [], "terms": [], "keyboard": edit}, ensure_ascii=False))
            original = (pack / "keyboard.toml").read_bytes()
            with patch.object(keyboard, "layout_path", lambda code, filename, root=None: pack / filename):
                for dry, status in ((True, "planned"), (False, "applied")):
                    with contextlib.redirect_stdout(io.StringIO()) as out:
                        self.assertEqual(main(["--rom", str(rom_path()), "--project-root", str(UNBOUND), "--lang", "ru", "web", "import",
                                               str(export)] + (["--dry-run"] if dry else [])), 0)
                    self.assertIn(f"status       {status}", out.getvalue())
                    self.assertIn("rows         2 rows\npages        reordered", out.getvalue())
                    if dry:
                        self.assertEqual((pack / "keyboard.toml").read_bytes(), original)
                written = (pack / "keyboard.toml").read_text(encoding="utf-8")
                self.assertEqual(written.count("\n"), original.decode("utf-8").count("\n"))
                _, doc = PackTest().load_document("ru")
                with contextlib.redirect_stdout(io.StringIO()) as out:   # the base is stale now
                    self.assertEqual(main(["--rom", str(rom_path()), "--project-root", str(UNBOUND), "--lang", "ru", "web", "import",
                                           str(export)]), 1)
                self.assertIn("changed after the edit", out.getvalue())
        self.assertEqual([p["name"] for p in doc["pages"]], moved)
        upper = next(k for k in doc["keyboards"] if k["like"] == 1 and not k["base"])
        cell = upper["rows"][0]["cells"][0]
        self.assertEqual((cell["key"]["char"], cell["glyph"]["char"], cell["glyph"]["x"]), ("Ё", "Ё", 11))

    def test_chat_edits_round_trip_and_invalid_rows_leave_the_pack_unchanged(self):
        import contextlib
        import io
        from unittest.mock import patch

        from gen3tl.__main__ import main
        from gen3tl.build import keyboard
        rows = unbound("ru")["keyboard"]["rows"]
        with tempfile.TemporaryDirectory() as tmp:
            pack = Path(tmp) / "ru"
            shutil.copytree(TOOLKIT_ROOT / "assets/lang/ru", pack)
            export = Path(tmp) / "export.json"
            layout = pack / "keyboard.toml"
            original = layout.read_bytes()
            with patch.object(keyboard, "layout_path", lambda code, filename, root=None: pack / filename):
                for text, expected in (("АБВГДЕ", "expected 5 keys"), ("АБВГ", "expected 5 keys"),
                                       ("{F9 F1}БВГД", "in-place overflow"),
                                       ("{PLAYER}БВГД", "not a keyboard glyph"), ("ДГВБА", None)):
                    edit = {"rows": {"chat_upper_1": text, "chat_lower_1": "дгвба", "chat_symbols_1": "BACDE"},
                            "base": {"rows": {name: rows[name] for name in
                                              ("chat_upper_1", "chat_lower_1", "chat_symbols_1")}}}
                    export.write_text(json.dumps({"profile": "unbound-2.1.1.1", "language": "ru", "entries": [],
                                                  "keyboard": edit}, ensure_ascii=False))
                    with contextlib.redirect_stdout(io.StringIO()) as out:
                        result = main(["--rom", str(rom_path()), "--project-root", str(UNBOUND), "--lang", "ru", "web", "import", str(export)])
                    with self.subTest(text=text):
                        if expected:
                            self.assertEqual(result, 1, out.getvalue())
                            self.assertIn(expected, out.getvalue())
                            self.assertEqual(layout.read_bytes(), original)
                        else:
                            self.assertEqual(result, 0, out.getvalue())
                            self.assertIn("rows         3 rows", out.getvalue())
                            _, doc = PackTest().load_document("ru")
                            self.assertEqual([p["rows"][0]["text"] for p in doc["chat"]["pages"]],
                                             ["ДГВБА", "дгвба", "BACDE"])

    def test_import_refuses_correct_opening_keyboards_with_wrong_looks(self):
        import contextlib
        import io
        from unittest.mock import patch

        from gen3tl.__main__ import main
        from gen3tl.build import keyboard
        kb = unbound("ru")["keyboard"]
        row = kb["rows"]["upper_keys_1"]
        with tempfile.TemporaryDirectory() as tmp:
            pack = Path(tmp) / "ru"
            shutil.copytree(TOOLKIT_ROOT / "assets/lang/ru", pack)
            layout = pack / "keyboard.toml"
            original = layout.read_text(encoding="utf-8")
            export = Path(tmp) / "export.json"
            export.write_text(json.dumps({"profile": "unbound-2.1.1.1", "language": "ru", "entries": [],
                                          "keyboard": {"rows": {"upper_keys_1": "Ё" + row[1:]},
                                                       "base": {"rows": {"upper_keys_1": row}}}}, ensure_ascii=False))
            with patch.object(keyboard, "layout_path", lambda code, filename, root=None: pack / filename):
                for slot, look in ((1, 2), (2, 1)):
                    pages = [dict(p) for p in kb["pages"]]
                    pages[slot]["look"] = look
                    text = keyboard.edit_layout(original, {}, pages)
                    layout.write_text(text, encoding="utf-8")
                    for dry in (True, False):
                        with self.subTest(slot=slot, dry=dry), contextlib.redirect_stdout(io.StringIO()) as out:
                            self.assertEqual(main(["--rom", str(rom_path()), "--project-root", str(UNBOUND), "--lang", "ru", "web", "import",
                                                   str(export)] + (["--dry-run"] if dry else [])), 1)
                        self.assertIn(f"opening page {slot}: keyboard {pages[slot]['keyboard']} uses look {look}; "
                                      f"the fade-in draws base page look {slot}", out.getvalue())
                        self.assertEqual(layout.read_text(encoding="utf-8"), text)

    def test_a_moved_key_is_checked_with_the_glyphs_the_export_redraws(self):
        import contextlib
        import io
        from unittest.mock import patch

        from gen3tl.__main__ import main
        from gen3tl.build import keyboard
        from gen3tl.lang.langpack import load_styles
        from gen3tl.web.editorfonts import art_rows
        prof = unbound("ru")
        row = prof["keyboard"]["rows"]["upper_display_1"]
        glyph = load_styles("ru", prof)["unbound"].glyphs["Б"]   # 6 px; column 1's frame x 20 to 32
        rows = art_rows(glyph, 0, 14)
        moved = row.replace("{CLEAR 06}Б{CLEAR 06}В", "{CLEAR 08}Б{CLEAR 04}В")
        with tempfile.TemporaryDirectory() as tmp:
            pack = Path(tmp) / "ru"
            shutil.copytree(TOOLKIT_ROOT / "assets/lang/ru", pack)
            export = Path(tmp) / "export.json"
            with patch.object(keyboard, "layout_path", lambda code, filename, root=None: pack / filename):
                for width, problem in ((None, None), (8, "upper_display_1 column 1 Б"), (7, None)):
                    redrawn = [{"style": "unbound", "char": "Б", "width": width, "rows": [r.ljust(width, "_") for r in rows],
                                "base": {"width": glyph.width, "rows": rows}}] if width else []
                    export.write_text(json.dumps({"profile": "unbound-2.1.1.1", "language": "ru", "entries": [],
                                                  "glyphs": redrawn, "keyboard": {
                                                      "rows": {"upper_display_1": moved},
                                                      "base": {"rows": {"upper_display_1": row}}}},
                                                 ensure_ascii=False))
                    with contextlib.redirect_stdout(io.StringIO()) as out:
                        code = main(["--rom", str(rom_path()), "--project-root", str(UNBOUND), "--lang", "ru", "web", "import", str(export),
                                     "--dry-run"])
                    with self.subTest(width=width):
                        if problem is None:
                            self.assertEqual(code, 0, out.getvalue())
                        else:   # its right edge at 33
                            self.assertEqual(code, 1)
                            self.assertIn(f"glyphs outside the cursor frame of their column: {problem}\n",
                                          out.getvalue())

    def test_a_glyph_outside_its_cursor_frame_is_refused(self):
        import contextlib
        import io
        from unittest.mock import patch

        from gen3tl.__main__ import main
        from gen3tl.build import keyboard
        rows = unbound("ru")["keyboard"]["rows"]
        row = rows["upper_display_1"]
        with tempfile.TemporaryDirectory() as tmp:
            pack = Path(tmp) / "ru"
            shutil.copytree(TOOLKIT_ROOT / "assets/lang/ru", pack)
            export = Path(tmp) / "export.json"
            with patch.object(keyboard, "layout_path", lambda code, filename, root=None: pack / filename):
                for shift, problem in (("{CLEAR 0E}А{CLEAR 03}Б", None),   # its right edge at 20
                                       ("{CLEAR 0F}А{CLEAR 02}Б", "upper_display_1 column 0 А")):
                    edit = {"rows": {"upper_display_1": row.replace("{CLEAR 0B}А{CLEAR 06}Б", shift)},
                            "base": {"rows": {"upper_display_1": row}}}
                    export.write_text(json.dumps({"profile": "unbound-2.1.1.1", "language": "ru", "entries": [],
                                                  "keyboard": edit}, ensure_ascii=False))
                    with contextlib.redirect_stdout(io.StringIO()) as out:
                        code = main(["--rom", str(rom_path()), "--project-root", str(UNBOUND), "--lang", "ru", "web", "import", str(export),
                                     "--dry-run"])
                    with self.subTest(shift=shift):
                        if problem is None:
                            self.assertEqual(code, 0, out.getvalue())
                            self.assertIn("status       planned", out.getvalue())
                        else:
                            self.assertEqual(code, 1)
                            self.assertIn(f"glyphs outside the cursor frame of their column: {problem}\n",
                                          out.getvalue())
