import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from gen3tl.web import editordata, editorimport
from gen3tl.build import keyboard
from gen3tl.core.charmap import Charmap
from gen3tl.lang.langpack import LangPack
from gen3tl.check.layout import Measure
from gen3tl.catalog.po import PoEntry
from gen3tl.profile.profile import Profile

from rom_support import needs_rom, rom_path
from project_fixture import literal, unbound

class KeyboardPackTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.base = {"base_pages": 3, "first_page": 1, "opening_keyboards": [1, 0],
                     "opening_keyboard_offsets": [0x120, 0x130], "table": [],
                     "row_bindings": {"lower_keys_1": "keys:0", "lower_display_1": "s100"}}
        self.doc = {"schema": "2.0.0", "language": "xx",
                    "keyboards": [{"name": "custom", "like": 0}],
                    "pages": [{"name": "custom", "keyboard": 0, "look": 1}],
                    "rows": {"lower_keys_1": "abcdef .", "lower_display_1": "a b c"}}
        self.path = self.root / "xx/keyboard.toml"
        self.path.parent.mkdir()

    def load(self, doc=None, filename="keyboard.toml"):
        self.path.write_text("\n".join(f"{k} = {literal(v)}" for k, v in (doc or self.doc).items()))
        return keyboard.load_layout("xx", filename, self.base, self.root)

    def profile(self):
        return Profile({"rom": {"sha1": "0" * 40}, "font": [], "keyboard": {**self.base, **self.load()}},
                       self.root / "other-game.toml")


    def test_editor_ownership_reaches_chunks_and_import_is_refused(self):
        profile = self.profile()
        entry = PoEntry("keys:0", "original")
        catalog = {entry.msgctxt: (Path("translation/po/keys.po"), entry)}
        doc = editordata.build("xx", profile, catalog, {}, Measure(lambda b: 6, {}), Charmap(), {})
        self.assertEqual(doc["entries"][0]["owner"], "keyboard")
        self.assertEqual(doc["entries"][0]["translation"], "abcdef .")
        self.assertEqual(doc["entries"][0]["status"], "approved")
        index, _ = editordata.split(doc, None, {})
        self.assertEqual(index["list"][0]["owner"], "keyboard")
        export = self.root / "export.json"
        export.write_text(json.dumps({"profile": profile.name, "language": "xx",
                                      "entries": [{"id": "keys:0", "translation": "changed"}]}))
        with self.assertRaisesRegex(ValueError, "read-only"):
            editorimport.read_export(export, profile.name, "xx", profile.sha1, catalog)


class RussianKeyboardBytesTest(unittest.TestCase):
    def setUp(self):
        self.profile = unbound()
        self.kb = self.profile["keyboard"]
        self.cm = LangPack.load("ru").charmap()
        self.encoded = {key: self.cm.encode(text, terminate="_keys_" not in key).hex()
                        for key, text in self.kb["rows"].items() if not key.startswith("chat_")}   # naming rows

    def test_all_rows_match_pre_migration_encoded_bytes(self):
        self.assertEqual(len(self.encoded), 24)
        self.assertEqual(hashlib.sha256(json.dumps(self.encoded, sort_keys=True).encode()).hexdigest(),
                         "5dedac54d6afc78c699c05a3a77239347f42530cee2e3c6d78cf0e509aaba1db")


    @needs_rom
    def test_complete_keyboard_patch_matches_expected_bytes(self):
        base = self.profile.load_rom(rom_path())
        rom = base.copy()
        for key, sid in self.kb["row_bindings"].items():
            if key not in self.encoded:
                continue
            # Bindings refer to existing field and pointer entries.
            at = (0x3E22D0 + 8 * int(sid.split(":")[1]) if ":" in sid else int(sid[1:], 16))
            rom.write(at, bytes.fromhex(self.encoded[key]))
        patch = keyboard.plan(self.kb, base, rom)
        writes = [(at, blob.hex(), what) for at, blob, what in patch.writes]
        self.assertEqual(hashlib.sha256(json.dumps(writes, sort_keys=True).encode()).hexdigest(),
                         "bdff53e6634f7c9df44217d655c752e60b3993737832a8fd160c637c61b602c8")
