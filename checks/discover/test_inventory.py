import unittest

from gen3tl.core.charmap import Charmap
from gen3tl.profile.profile import Profile
from gen3tl.catalog.progress import file_topics
from gen3tl.core.rom import ptr_bytes
from gen3tl.catalog.source import digest

from rom_support import needs_rom, rom_path
from test_roots import PROJECT_ROOT

CM = Charmap()

class PointerTableTest(unittest.TestCase):
    # credit records {heading, names, flag}, 12 bytes.
    # as at 0x1FB0DB0.
    PAGES = {0x2001: "\\n\\nHeading\\n\\n\\n\\n", 0x2101: "\\n\\n\\n Person\\n\\n\\n",
             0x2201: "Other Heading\\n\\n\\n\\n\\n\\n", 0x2301: "\\n Person\\n Person2\\n"}
    END = 0x2400  # the end record points at an empty string

    def setUp(self):
        self.data = bytearray(b"\xff" * 0x4000)
        for at, text in self.PAGES.items():
            blob = CM.encode(text)
            self.data[at:at + len(blob)] = blob
        heads, names = [0x2001, 0x2201, self.END], [0x2101, 0x2301, self.END]
        for i, (h, n) in enumerate(zip(heads, names)):
            self.data[0x800 + 12 * i:0x80C + 12 * i] = ptr_bytes(h) + ptr_bytes(n) + b"\x00" * 4
        self.table = {"name": "credits", "base": 0x800, "stride": 12, "count": 3, "fields": [0, 4],
                      "note": "keep the names", "evidence": "test table"}


    def test_profile_declares_the_credit_tables(self):
        prof = Profile.by_name("unbound-2.1.1.1")
        tables = prof["strings"]["pointer_table"]
        self.assertEqual({t["name"]: (t["base"], t["stride"], t["count"], t["fields"]) for t in tables},
                         {"credits": (0x1FB0DB0, 12, 52, [0, 4]), "credits-firered": (0x4145BC, 12, 42, [0, 4]),
                          "pokedex_entries": (0x1A357DC, 36, 906, [0])})
        self.assertTrue(all(t["evidence"] and t["note"] for t in tables))
        topics = file_topics(prof.data)
        self.assertEqual((topics["credits"], topics["credits-firered"]), ("Credits", "Credits"))
        self.assertEqual(topics["pokedex-entries"], "Pokedex entries")


@needs_rom
class ShortLabelIncludeTest(unittest.TestCase):
    """A short code string is rejected unless the include list names it."""

    def setUp(self):
        self.data = bytearray(b"\xff" * 0x4000)
        blob = CM.encode(" A-Z")
        self.data[0x2001:0x2001 + len(blob)] = blob
        self.data[0xFF8:0xFFA] = b"\x01\x49"   # ldr r1, [pc, #4]: the word at 0x1000
        self.data[0x1000:0x1004] = ptr_bytes(0x2001)


    def test_inventory_holds_the_mission_log_suffix(self):
        import json
        root = PROJECT_ROOT
        strings = Profile.by_name("unbound-2.1.1.1")["strings"]
        included = set(strings["include"]) | {row["offset"] for row in strings.get("classified", ())
                                              if row["action"] == "include"}
        self.assertIn(0x1F5604A, included)
        inv = json.loads((root / "build" / "inventory.json").read_text(encoding="utf-8"))
        e = next(x for x in inv["entries"] if x["id"] == "s1F5604A")
        self.assertEqual((e["text"], e["refs"]), (" A-Z", [{"at": 0x1EBE990, "kind": "pool"}]))


@needs_rom
class EasyChatWordsTest(unittest.TestCase):
    """Every easy chat word record points at an inventory string."""

    def test_word_records_are_catalogued(self):
        import json
        root = PROJECT_ROOT
        prof = Profile.by_name("unbound-2.1.1.1")
        rom = prof.load_rom(rom_path())
        inv = json.loads((root / "build" / "inventory.json").read_text(encoding="utf-8"))
        refs = {r["at"]: e["offset"] for e in inv["entries"] for r in e["refs"]}
        missing, words = [], 0
        for g in range(22):   # group table {words, count, enabled count}
            base = rom.ptr_at(0x3ECED4 + 8 * g)
            if base is None or rom.ptr_at(base) is None:
                continue   # species and move id lists
            for i in range(rom.u16(0x3ECED4 + 8 * g + 4)):
                words += 1
                at = base + 12 * i
                if refs.get(at) != rom.ptr_at(at):
                    missing.append(rom.ptr_at(at))
        self.assertEqual(words, 1006)
        self.assertEqual(missing, [0x3EC601])   # {POKEBLOCK_PO}...: glyphs, not text
        texts = {e["offset"]: e["text"] for e in inv["entries"]}
        self.assertEqual([texts[o] for o in (0x3E9235, 0x3EA0FB, 0x3EB622, 0x3E9774, 0x3E9789)],
                         ["I", "A", "orldD", "!", "- - -"])


@needs_rom
class ProfileTableBaseTest(unittest.TestCase):
    """The pooled table bases the profile declares, checked against the ROM."""

    def test_declarations_hold_in_the_base_rom(self):
        from gen3tl.discover.scan import table_base_members, table_base_problems
        prof = Profile.by_name("unbound-2.1.1.1")
        rom = prof.load_rom(rom_path())
        decls = {d["id"]: d for d in prof["strings"]["table_base"]}
        self.assertEqual(set(decls), {"s03DF7E8", "s026CF8C", "s0834B04"})
        self.assertEqual([t["refs"] for t in prof["keyboard"]["table"] if t["name"] == "fill"], [[0x9FA54]])   # 'zi'
        for d in decls.values():
            self.assertEqual(table_base_problems(rom, d), [])
        names = {sid: [CM.decode(rom.data, o)[0] for o in table_base_members(d)] for sid, d in decls.items()}
        self.assertEqual((len(names["s03DF7E8"]), names["s03DF7E8"][42]), (43, "ENIGMA"))
        self.assertEqual([digest(text) for text in names["s026CF8C"][:4]], [
            "b56150b7c1f5c456fae27ac8f72277de8834c698634ce74c2730b6973cef5207",
            "aac09a648fc382b6f78897595486e691d00de9dfc742f3ba1930464b56eecda6",
            "3127c70db1cce709790daac9850d25e95089dcd750204a7ec2f9c3d8526918de",
            "638178e751e6e059fcbbdd8b6ddf00ec067646570ad0911633b642c28543f93d",
        ])
        self.assertEqual(names["s0834B04"], ["EVs:", "IVs:", "hp:", "sde:"])

    def test_berry_name_field_is_seven_bytes(self):
        """name[7], the firmness byte at +7."""
        from gen3tl.discover.scan import table_base_lengths, table_base_members
        prof = Profile.by_name("unbound-2.1.1.1")
        rom = prof.load_rom(rom_path())
        decl = next(d for d in prof["strings"]["table_base"] if d["id"] == "s03DF7E8")
        fields = table_base_lengths(decl)
        self.assertEqual(sorted(fields), table_base_members(decl))
        self.assertEqual(set(fields.values()), {7})
        letters = [rom.data[o:o + 7].index(0xFF) for o in fields]
        self.assertEqual((max(letters), letters.count(6)), (6, 21))   # 6 letters fill the field
        self.assertEqual({rom.data[o + 7] for o in fields}, {0, 1, 2, 3, 4, 5})   # firmness, ENIGMA 0
        self.assertNotIn("length", next(d for d in prof["strings"]["table_base"] if d["id"] == "s026CF8C"))
