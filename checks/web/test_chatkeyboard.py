import unittest
import string

from gen3tl.web import snapshotstore as snapshot_store
from gen3tl.check.layout import split_tokens
from gen3tl.lang.langpack import LangPack
from gen3tl.project import Registry
from gen3tl.build.inject import diff_positions, inject, verify
from gen3tl.catalog.catalog import load_catalog

from rom_support import needs_rom, rom_path
from project_fixture import UNBOUND, unbound

PROFILE = "unbound-2.1.1.1"

TABLE = 0x45A9AC   # gUnionRoomKeyboardText, ten row pointers per page

PAGES = ("upper", "lower", "symbols")

ROWS = [f"chat_{page}_{row}" for page in PAGES for row in range(1, 11)]

def project(code="ru"):
    return Registry.load(UNBOUND).resolve(PROFILE, code)

def snapshot_inventory(code="ru") -> dict:
    """The inventory of the tracked measurement snapshot."""
    rows = snapshot_store.load(project(code).snapshot)["inventory"]
    return {"entries": [{**row, "refs": [{"at": at, "kind": kind} for at, kind in row["refs"]]}
                        for row in rows]}

class ChatKeyboardTest(unittest.TestCase):
    def test_every_pack_binds_thirty_rows_of_five_keys_it_encodes(self):
        for code in ("ru", "es", "de", "fr"):
            with self.subTest(code=code):
                kb = unbound(code)["keyboard"]
                cm = LangPack.load(code).charmap()
                self.assertEqual([name for name in kb["row_bindings"] if name.startswith("chat_")], ROWS)
                for name in ROWS:
                    row = split_tokens(kb["rows"][name])
                    self.assertEqual(len(row), 5, name)
                    for key in row:   # a character or an 0xF9 symbol
                        encoded = cm.encode(key, terminate=False)
                        self.assertTrue(len(encoded) == 1 and encoded[0] < 0xF7
                                        or len(encoded) == 2 and encoded[0] == 0xF9, (name, key))

    def test_rows_are_the_table_rows_and_fit_their_slots(self):
        kb = unbound()["keyboard"]
        cm = LangPack.load("ru").charmap()
        inv = {e["id"]: e for e in snapshot_inventory()["entries"]}
        for index, name in enumerate(ROWS):
            entry = inv[kb["row_bindings"][name]]
            self.assertIn({"at": TABLE + 4 * index, "kind": "table"}, entry["refs"], name)
            self.assertLessEqual(len(cm.encode(kb["rows"][name])), entry["length"], name)


    @needs_rom
    def test_russian_pages_hold_the_recorded_layout(self):
        profile = unbound()
        kb = profile["keyboard"]
        catalog = load_catalog(project().catalog, profile)
        english = {name: catalog[sid][1].msgid for name, sid in kb["row_bindings"].items() if name in ROWS}
        upper, lower, symbols = (keys(kb["rows"], page) for page in PAGES)
        english_upper, english_lower, english_symbols = (keys(english, page) for page in PAGES)
        capitals = "АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ"
        self.assertEqual("".join(upper[:33]), capitals)
        self.assertEqual("".join(upper[35:45]), string.digits)
        self.assertEqual(upper[33:35] + upper[45:], english_upper[45:47] + english_upper[40:45])
        self.assertEqual("".join(lower[:33]), capitals.lower())
        self.assertEqual(lower[40:], english_lower[40:])
        self.assertEqual("".join(symbols[:26]), string.ascii_uppercase)
        self.assertEqual(symbols[26:], english_symbols[26:])
        for page in (upper, lower, symbols):   # the English pages end in a space key
            self.assertEqual(page[49], " ")


    @needs_rom
    def test_latin_pages_hold_their_accented_layouts(self):
        profile = unbound()
        kb = profile["keyboard"]
        catalog = load_catalog(project().catalog, profile)
        english = {name: catalog[sid][1].msgid for name, sid in kb["row_bindings"].items() if name in ROWS}
        english_pages = {page: keys(english, page) for page in PAGES}
        accents = {
            "es": "ÁÉÍÓÚÜÑ",
            "de": "ÄÖÜß",
            "fr": "ÀÂÇÈÉÊËÎÏÔŒÙÛÜ",
        }
        digits = {"es": "0123456", "de": string.digits, "fr": ""}
        for code in ("es", "de", "fr"):
            with self.subTest(code=code):
                rows = unbound(code)["keyboard"]["rows"]
                upper, lower, symbols = (keys(rows, page) for page in PAGES)
                self.assertEqual(upper, list(string.ascii_uppercase + accents[code] + digits[code])
                                 + english_pages["upper"][40:])
                self.assertEqual(lower, list(string.ascii_lowercase + accents[code].lower() + digits[code])
                                 + english_pages["lower"][40:])
                self.assertEqual(symbols, english_pages["symbols"])


    @needs_rom
    def test_the_registered_texts_are_russian_and_fit_their_save_records(self):
        profile = unbound()
        catalog = load_catalog(project().catalog, profile)
        cm = LangPack.load("ru").charmap()
        inv = {e["id"]: e for e in snapshot_inventory()["entries"]}
        for sid in PHRASES:
            entry = catalog[sid][1]
            self.assertTrue(entry.msgstr and not entry.fuzzy, sid)
            self.assertRegex(entry.msgstr, "[А-Яа-яЁё]")
            self.assertLessEqual(len(cm.encode(entry.msgstr)), SAVE_RECORD, sid)
            self.assertIn("save-link", inv[sid]["flags"])


    @needs_rom
    def test_the_build_writes_the_rows_in_place(self):
        profile = unbound()
        kb = profile["keyboard"]
        cm = LangPack.load("ru").charmap()
        inv = snapshot_inventory()
        slots = {e["id"]: (e["offset"], e["offset"] + e["length"]) for e in inv["entries"]}
        texts = {kb["row_bindings"][name]: cm.encode(kb["rows"][name]) for name in ROWS}
        base = profile.load_rom(rom_path())
        rom = base.copy()
        res = inject(rom, base, inv, texts, {t["name"]: t for t in profile.get("table", [])})
        self.assertEqual(verify(rom, base, res, texts, set()), [])
        self.assertEqual({p.id for p in res.placements}, set(texts))
        self.assertTrue(all(p.mode in ("in-place", "same") and p.new == p.old for p in res.placements))
        changed = diff_positions(rom.data, base.data)
        self.assertTrue(changed)
        self.assertTrue(all(any(lo <= at < hi for lo, hi in map(slots.get, texts)) for at in changed))
        self.assertEqual(rom.read(TABLE, 4 * len(ROWS)), base.read(TABLE, 4 * len(ROWS)))


PHRASES = ("s041B510", "s041B516", "s041B51E", "s041B524", "s041B52B",
           "s041B531", "s041B535", "s041B53B", "s041B541", "s041B54B")


SAVE_RECORD = 21   # one of the ten records at SaveBlock1 + 0x3AD4


def keys(rows: dict, page: str) -> list[str]:
    return [key for row in range(1, 11) for key in split_tokens(rows[f"chat_{page}_{row}"])]
