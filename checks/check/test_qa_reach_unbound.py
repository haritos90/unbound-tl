import re
import tempfile
import unittest
from pathlib import Path

from gen3tl.catalog.source import digest
from gen3tl.check import qa
from gen3tl.check.layout import Measure
from gen3tl.catalog.po import write

from rom_support import needs_rom, rom_path
from test_roots import PROJECT_ROOT as ROOT
from project_fixture import unbound
from qa_support import PACK, assert_never_shown_groups, entry, setUpModule, tearDownModule

@needs_rom
class FireRedNeverShownTest(unittest.TestCase):
    """Unreached lists are never shown; live lists stay checked."""

    OAK = ["s01A6D6D", "s01A6DDF", "s01A6E36", "s01A6EA4", "s01A6F0B", "s01A6F71", "s01A6FAB", "s01A6FF1",
           "s01A7031", "s01A7063", "s01A70A5", "s01A70D8", "s01A7108"]
    LISTS = {0x2372C0: 8, 0x237400: 16, 0x237584: 11}
    SEAGALLOP = ["s0417E16", "s0417E22", "s0417E2E", "s0417E39"]
    SHOWN = ["s0417E46", "s0417DF3", "s0417DFE", "s0417E09"]   # Vermilion, One to Three Island

    @classmethod
    def setUpClass(cls):
        import json

        from gen3tl.catalog.catalog import never_shown
        from gen3tl.profile.profile import Profile
        cls.prof = unbound()
        cls.never = never_shown(None, cls.prof.get("reach", {}).get("never_shown", []))
        cls.inv = json.loads((ROOT / "build" / "inventory.json").read_text(encoding="utf-8"))
        cls.rom = cls.prof.load_rom(rom_path())

    def items(self, base, count):
        """Ids of the strings the pointers base .. base + 4 * count point at."""
        return {e["id"] for e in self.inv["entries"] for r in e["refs"] if base <= r["at"] < base + 4 * count}

    def test_rules(self):
        """Each list is checked against the live table 0x1FB196C before it is tagged."""
        rom = self.rom
        self.assertEqual([rom.ptr_at(0x8A3F50 + 4 * k) for k in range(4)], [*self.LISTS, 0x238D00])
        # list [var 0x8000, up to 31]: {items, count byte}
        live = [(rom.ptr_at(0x1FB196C + 8 * k), rom.u8(0x1FB196C + 8 * k + 4)) for k in range(32)]
        self.assertEqual(live[29], (0x238D00, 7))   # the appliance list is shown
        self.assertFalse(set(self.LISTS) & {p for p, _ in live})
        for base, n in self.LISTS.items():
            ids = self.items(base, n)
            self.assertEqual(len(ids), n)
        groups = [self.items(base, n) for base, n in self.LISTS.items()]
        assert_never_shown_groups(self, self.prof, self.never,
                                 [set().union(*groups), self.OAK, self.SEAGALLOP])
        shown = set().union(*(self.items(p, n) for p, n in live if p is not None))
        self.assertIn("s0238D20", shown)
        self.assertEqual(sorted(shown & set(self.never)), [])
        self.assertEqual(self.items(0x3E17E0, 8), set(self.SEAGALLOP) | set(self.SHOWN))
        for sid in self.SHOWN:
            self.assertNotIn(sid, self.never)

    def test_qa_counts_and_marks_them(self):
        """qa counts the export's tags; the Seagallop overflows carry the marker."""
        from gen3tl.catalog.catalog import load_catalog
        po = ROOT / "translation" / "ru" / "po"
        catalog = load_catalog(po)
        tagged = self.OAK + sorted(set().union(*(self.items(b, n) for b, n in self.LISTS.items()))) + self.SEAGALLOP
        ru = {"s0417E16": "Четвёртый остров", "s0417E22": "Пятый остров", "s0417E2E": "Шестой остров",
              "s0417E39": "Седьмой остров", "s0417E46": "Вермилион", "s0417DF3": "Первый остров",
              "s0417DFE": "Второй остров", "s0417E09": "Третий остров"}
        entries = []
        for sid in tagged + self.SHOWN:
            e = catalog[sid][1]
            e.msgstr = ru.get(sid, e.msgstr)
            entries.append(e)
        inv = {"entries": [e for e in self.inv["entries"] if e["id"] in set(tagged + self.SHOWN)]}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / "a.po", entries, {})
            gate = qa.run(self.prof, inv, root, PACK.charmap(), Measure(lambda b: 6, {}), set(PACK.glyph_slots()),
                          rom=self.rom)
            rep = qa.report(gate)
            self.assertEqual(sorted(gate.never_shown), sorted(tagged))
            self.assertIn("never shown: 52 tagged", rep)
            wide = {f.id for f in gate.findings if "line too wide" in f.message}
            self.assertEqual(wide & set(self.SEAGALLOP + self.SHOWN), {"s0417E16", "s0417E39"})
            self.assertIn(f"- error s0417E16 ({root / 'a.po'}) [never shown]: line too wide: 96 > 80 px", rep)


@needs_rom
class OlderCopyNeverShownTest(unittest.TestCase):
    """Orphaned older hook copies are never shown; live lines stay checked."""

    ORPHANS = {
        "older whiteout picker": ["s07649D7"],
        "older stat-adverb hook": ["s0883590", "s08835A0"],
        "older TM shop code": ["s0893A04", "s0893A1F"],
        "Dodrio Berry Picking debug names": ["s0475638"],
    }
    ENGINE = {
        "FireRed BufferStringBattle 0x80D7274": ["s08854B0", "s08BD140"],
        "trainer out-of-balls lines": ["s08C0DE8", "s08C0E2D"],
        "older battle command 0x77": ["s08A985E", "s08A9876", "s08A9898"],
        "older resultmessage hook": ["s08A98D0", "s08A98E9", "s08A9903", "s08A991F"],
        "older printfromtable hook": ["s0884620"],
        "older Mega Evolution messages": ["s082FFEC", "s083001C", "s083003C", "s0830068", "s083008C"],
        "older move-effect scripts": ["s08BC450", "s08BC470", "s08BC630", "s0906619", "s09068A0", "s09068E0",
                                      "s0906BF0", "s090B2A0", "s090C850", "s090CAE0", "s090FC0B", "s090FC30",
                                      "s090FC60", "s090FC80", "s090FCB0", "s090FCF0"],
        "older swap-move messages": ["s090F8F0", "s090F920", "s090F960", "s090F9A0", "s090F9C0", "s090F9F0",
                                     "s090FA20"],
    }
    LIVE = ["s096C05C", "s096C080", "s096C0BB", "s096C0F7", "s096C112", "s096C134", "s096C159", "s096C1D7",
            "s096C1F2", "s096C213", "s096DB7C", "s096DB97", "s096DBBB"]
    TWINS = ["s1F11D25", "s0A4D8A4", "s0A4C603", "s0A4C610", "s0A4E00D", "s0A4E02C", "s0A4C4BD", "s0A4C5C8"]

    @classmethod
    def setUpClass(cls):
        from gen3tl.catalog.catalog import never_shown
        from gen3tl.profile.profile import Profile
        cls.prof = unbound()
        cls.never = never_shown(None, cls.prof.get("reach", {}).get("never_shown", []))
        cls.rom = cls.prof.load_rom(rom_path())

    def assertTagged(self, groups):
        rows = assert_never_shown_groups(self, self.prof, self.never, groups.values())
        for ids, row in zip(groups.values(), rows):
            self.assertEqual(set(ids), set(row["ids"]))

    def test_groups_resolve_to_distinct_rows(self):
        self.assertTagged({**self.ORPHANS, **self.ENGINE})

    def words_into(self, lo, hi):
        """Aligned words of the ROM whose value lies in [lo, hi) as a ROM address."""
        import re
        data = bytes(self.rom.data)
        top = {(v >> 16) & 0xFF for v in range(lo, hi, 0x100)} | {((hi - 1) >> 16) & 0xFF}
        pat = re.compile(b"(?s)(?=..[" + b"".join(re.escape(bytes([t])) for t in sorted(top)) + b"]\x08)")
        return [m.start() for m in pat.finditer(data)
                if m.start() % 4 == 0 and lo <= self.rom.u32(m.start()) - 0x8000000 < hi]

    def test_orphaned_copies(self):
        """The FireRed hook sites of the copies point at the live twins; no word reaches the copies."""
        self.assertTagged(self.ORPHANS)
        rom = self.rom
        self.assertEqual(rom.ptr_at(0x7F548), 0x9A3345)   # whiteout, picks s0A4D8A4
        self.assertEqual(rom.ptr_at(0xD848C), 0x9A32C1)   # stat adverbs s0A4C603 / s0A4C610
        self.assertEqual([rom.ptr_at(a) for a in (0x9BC44, 0x9BC80, 0x9BEC0)], [0x9A449D, 0x9A446D, 0x9A4477])
        self.assertEqual(rom.ptr_at(0x153A90), 0x475648)   # Dodrio debug names, read at 0x8153A12
        for lo, hi in ((0x883420, 0x88346C), (0x883550, 0x883588), (0x893960, 0x8939E2), (0x153A04, 0x153A8C)):
            self.assertEqual(self.words_into(lo, hi), [], hex(lo))

    def test_older_engine(self):
        """The live dispatcher and move-effect table name none of the older engine's entries."""
        self.assertTagged(self.ENGINE)
        rom = self.rom
        self.assertEqual(rom.ptr_at(0x15A28), 0x99FFFC)   # live command table
        self.assertEqual(rom.ptr_at(0x16364), 0x9A05EC)   # live move-effect table
        for cmd, fn in {0x0F: 0x1FBA1, 0x13: 0x1FE31, 0x77: 0x26F69}.items():
            self.assertEqual([rom.ptr_at(0x25011C + 4 * cmd), rom.ptr_at(0x95F480 + 4 * cmd)], [fn, fn])
            self.assertNotEqual(rom.ptr_at(0x99FFFC + 4 * cmd), fn)
        self.assertEqual([rom.ptr_at(a) for a in (0x1FBD4, 0x1FE60, 0x26F6C)], [0x8A957D, 0x884641, 0x8A9351])
        self.assertEqual(rom.ptr_at(0x95F480 + 4 * 0xFF), 0x908411)
        self.assertEqual({k: rom.ptr_at(0x903B6C + 4 * k) for k in (113, 228, 233, 240)},
                         {113: 0x271A20, 228: 0x8BB8D0, 233: 0x8BC5F0, 240: 0x9066F0})
        self.assertEqual(rom.ptr_at(0xD7274 + 4), 0x9BDA89)   # BufferStringBattle entry
        self.assertEqual(rom.ptr_at(0xD77F0), 0x8C0D95)   # default-case hook in its body
        for lo, hi in ((0x903B6C, 0x903F6C), (0x95F480, 0x95F880), (0x82EAF0, 0x82EB44)):
            self.assertEqual(self.words_into(lo, hi), [], hex(lo))

    def test_live_lines_stay_checked(self):
        """The live CFRU lines print in the battle box; they and the live twins carry no tag."""
        box = self.prof["layout"]["window_box"]
        self.assertEqual({sid: box.get(sid) for sid in self.LIVE}, {sid: "battle" for sid in self.LIVE})
        for sid in self.LIVE + self.TWINS:
            self.assertNotIn(sid, self.never)


@needs_rom
class FireRedOakRatingRestNeverShownTest(unittest.TestCase):
    """The last three FireRed Oak ratings are never shown."""

    POOLS = {"s01A7137": 0xCA4FC, "s01A6D17": 0xCA510, "s01A7175": 0xCA520}
    LIVE = ["s1F2542A", "s1F25482", "s1F254F0", "s1F2554E", "s1F2558D"]

    def test_rules(self):
        import json
        import re

        from gen3tl.catalog.catalog import never_shown
        from gen3tl.profile.profile import Profile
        prof = unbound()
        never = never_shown(None, prof.get("reach", {}).get("never_shown", []))
        assert_never_shown_groups(self, prof, never, [self.POOLS])
        for sid in self.LIVE:
            self.assertNotIn(sid, never)
        rom = prof.load_rom(rom_path())
        self.assertEqual(rom.ptr_at(0xCA428), 0x1ECA839)   # entry jumps to Unbound's ratings
        inv = {e["id"]: e for e in json.loads((ROOT / "build" / "inventory.json").read_text(encoding="utf-8"))
               ["entries"]}
        data = bytes(rom.data)
        for sid, pool in self.POOLS.items():
            off = inv[sid]["offset"]
            self.assertEqual(rom.ptr_at(pool), off)
            hits = [m.start() for m in re.finditer(re.escape((off + 0x8000000).to_bytes(4, "little")), data)]
            self.assertEqual(hits, [pool], sid)   # the pool is the only pointer
        body = [m.start() for m in re.finditer(b"(?s)(?=..\x0c\x08)", data)
                if m.start() % 4 == 0 and 0xCA42C <= rom.u32(m.start()) - 0x8000000 < 0xCA524]
        self.assertEqual(body, [])


@needs_rom
class OlderStringLoaderNeverShownTest(unittest.TestCase):
    """Strings stored only to the older engine's loader are never shown."""

    LOADER = 0x0203C020
    SCRIPTS = "s08A9963"
    CODE = "s0271C3E"
    INTROS = "s03FD297"
    # string pool -> (load, loader store, loader pool)
    STORES = {0x271B9C: (0x271B22, 0x271B26, 0x271B94), 0x271C30: (0x271BBE, 0x271BC6, 0x271C2C),
              0x277920: (0x2778AE, 0x2778B6, 0x27791C), 0x277924: (0x2778B2, 0x2778B6, 0x27791C),
              0x82564C: (0x82562C, 0x825630, 0x825648), 0x8A3CFC: (0x8A3CC8, 0x8A3CCA, 0x8A3CF4),
              0x8B7188: (0x8B7170, 0x8B7174, 0x8B7184), 0x906604: (0x906592, 0x9065D2, 0x9065F0),
              0x908678: (0x90866C, 0x90866E, 0x908674), 0x90FFA8: (0x90FF18, 0x90FF7E, 0x90FFA0),
              0x90FFAC: (0x90FF36, 0x90FF7E, 0x90FFA0), 0x90FFB0: (0x90FF54, 0x90FF7E, 0x90FFA0),
              0x90FFB4: (0x90FF72, 0x90FF7E, 0x90FFA0)}
    # stores of the engine without an inventory string
    OTHER_STORES = [0x271AF8, 0x8846B8, 0x8A94A4, 0x8A9690, 0x8BC5A4, 0x90FB80, 0x90FE30]
    REMNANT = 0x90A983   # setword whose start the goto at 0x90A97B overwrote
    CODE_IDS = ["s0271C3E", "s027792C", "s027795D", "s0277999", "s0825680", "s08A3D40", "s08B9F80", "s08BA000",
                "s08BA080", "s0906810", "s0907070", "s090D780"]
    BODY = {"s03FD297": 0xD73F8, "s03FD2AA": 0xD7424, "s03FD2BF": 0xD7408}
    NAMED = ["s0271C3E", "s027795D", "s0906810", "s08A9963"]
    LIVE = ["s03FC090", "s0A4C52A", "s0A4C5B1", "s0A4C5C8", "s096C05C", "s096DB7C"]

    @classmethod
    def setUpClass(cls):
        import json

        from gen3tl.catalog.catalog import never_shown
        from gen3tl.profile.profile import Profile
        cls.prof = unbound()
        cls.never = never_shown(None, cls.prof.get("reach", {}).get("never_shown", []))
        cls.rom = cls.prof.load_rom(rom_path())
        cls.data = bytes(cls.rom.data)
        cls.inv = {e["id"]: e for e in json.loads((ROOT / "build" / "inventory.json").read_text(encoding="utf-8"))
                   ["entries"]}

    def find_all(self, value: int) -> list[int]:
        pat, out = value.to_bytes(4, "little"), []
        i = self.data.find(pat)
        while i >= 0:
            out.append(i)
            i = self.data.find(pat, i + 1)
        return out

    def stored(self, ref: dict) -> bool:
        """A setword operand to the older loader, or the remnant of one."""
        return (ref["kind"] == "script:setword" and self.rom.u32(ref["at"] - 4) == self.LOADER) or \
            ref["at"] == self.REMNANT

    def tagged(self, anchor: str) -> set[str]:
        rows = assert_never_shown_groups(self, self.prof, self.never, [[anchor]])
        return set(rows[0]["ids"])

    def assertTagged(self, anchor: str, ids):
        assert_never_shown_groups(self, self.prof, self.never, [[anchor, *ids]])

    def test_groups_resolve_to_distinct_rows(self):
        assert_never_shown_groups(self, self.prof, self.never,
                                 [[self.SCRIPTS], [self.CODE], list(self.BODY)])

    def test_loader_read_only_from_dead_body(self):
        """Only the dead FireRed body reads the string loader address."""
        self.assertTagged(self.SCRIPTS, ["s08A9963"])
        self.assertTagged(self.CODE, ["s0271C3E", "s027795D", "s0906810"])
        rom, data = self.rom, self.data
        occ = self.find_all(self.LOADER)
        setword = [p for p in occ if data[p - 1] == 0xFA]
        self.assertEqual(len(setword), 291)
        self.assertEqual([p for p in occ if data[p - 1] == 0x2E], [0x90C8B5])   # setbyte
        code = sorted({s[2] for s in self.STORES.values()} | set(self.OTHER_STORES) | {0x908080})
        self.assertEqual(sorted(p for p in occ if data[p - 1] not in (0xFA, 0x2E)), code)
        self.assertEqual((rom.u16(0x908040), rom.u16(0x908042), rom.u16(0x908044)), (0x20C2, 0x0040, 0x42B0))
        self.assertEqual((rom.u16(0x908048), rom.u16(0x90804A)), (0x480D, 0x6807))   # ldr r0, =loader; ldr r7, [r0]
        self.assertEqual(self.find_all(0x08908041), [0xD77CC])
        self.assertEqual(rom.ptr_at(0xD7278), 0x9BDA89)   # FireRed BufferStringBattle entry
        self.assertEqual(rom.u32(0x9BDD8C), 0x0203E020)
        for lo, hi in ((0xD727C, 0xD77F4), (0x908040, 0x908090)):
            words = [p for p in range(0, len(data) - 3, 4)
                     if data[p + 3] == 0x08 and data[p + 2] in (0x0D, 0x90) and lo <= rom.u32(p) - 0x8000001 < hi
                     and rom.u32(p) & 1 and not lo <= p < hi]
            # older hook returns, tile data; the body's pool
            self.assertEqual(words, {0xD727C: [0x8C0DE4, 0x908084, 0x908088, 0x1D7E5F8], 0x908040: [0xD77CC]}[lo])

    def test_stores(self):
        """The tagged strings' pointers are setword operands to the loader or loads stored to it."""
        self.assertTagged(self.CODE, self.CODE_IDS)
        scripts = {sid for sid, e in self.inv.items() if e["refs"] and all(self.stored(r) for r in e["refs"])}
        self.assertEqual(len(scripts), 226)
        self.assertTagged(self.SCRIPTS, scripts)
        self.assertEqual(self.tagged(self.SCRIPTS), scripts)
        self.assertEqual(self.tagged(self.CODE), set(self.CODE_IDS))
        rom = self.rom
        for sid in self.CODE_IDS:
            refs = self.inv[sid]["refs"]
            self.assertTrue(all(self.stored(r) or r["at"] in self.STORES for r in refs), sid)
            self.assertTrue(any(r["at"] in self.STORES for r in refs), sid)
        for pool, (load, store, loader) in self.STORES.items():
            h = rom.u16(load)
            self.assertEqual((h >> 11, ((load + 4) & ~3) + 4 * (h & 0xFF)), (0b01001, pool), hex(load))
            s = rom.u16(store)
            self.assertEqual((s & 0xFFC0, s & 7), (0x6000, (h >> 8) & 7), hex(store))   # str rd, [rn]
            self.assertEqual(rom.u32(loader), self.LOADER)
        self.assertEqual((self.data[0x90A97B], self.data[0x90A980:0x90A983]), (0x28, b"\xc0\x03\x02"))
        self.assertEqual(rom.ptr_at(self.REMNANT), self.inv["s090A780"]["offset"])

    def test_body_intros_and_live_strings(self):
        """The wild intros of the dead body are tagged; CFRU's intros and the live lines are not."""
        self.assertTagged(self.INTROS, self.BODY)
        self.assertEqual(self.tagged(self.INTROS), set(self.BODY))
        for sid, pool in self.BODY.items():
            self.assertEqual([r["at"] for r in self.inv[sid]["refs"]], [pool])
            self.assertEqual(self.find_all(self.inv[sid]["offset"] + 0x8000000), [pool])
        for sid in self.LIVE:
            self.assertNotIn(sid, self.never)
        self.assertIn(0x3FE15C, [r["at"] for r in self.inv["s03FC090"]["refs"]])   # gBattleStringsTable
        self.assertEqual([self.rom.ptr_at(p) for p in (0x9BDDE8, 0x9BDDF0, 0x9BDE00)],
                         [self.inv[s]["offset"] for s in ("s0A4C52A", "s0A4C5B1", "s0A4C5C8")])


@needs_rom
class ComputedGroupShownTest(unittest.TestCase):
    """BufferStringBattle reaches every computed group member."""

    SHOWN = ["s03FD3B1", "s03FD3C7", "s03FD497", "s03FD50D", "s03FD535", "s03FCD92"]
    BODY = ["s03FD2D9", "s03FD30D", "s03FD383", "s03FD397"]
    DEAD = "review: FireRed BufferStringBattle 0x80D7274 jumps to CFRU 0x89BDA88"

    def test_members_are_not_tagged(self):
        import json
        import re

        from gen3tl.catalog.catalog import never_shown
        from gen3tl.profile.profile import Profile
        prof = unbound()
        never = never_shown(None, prof.get("reach", {}).get("never_shown", []))
        rom = prof.load_rom(rom_path())
        inv = {e["id"]: e for e in json.loads((ROOT / "build" / "inventory.json").read_text(encoding="utf-8"))
               ["entries"]}
        groups = prof.get("strings", {}).get("computed", [])
        self.assertEqual(len(groups), 7)
        for g in groups:
            # the evidence's ldr loads the pool word of a member
            load = int(re.search(r"ldr r\d at 0x8([0-9A-F]+)", g["evidence"]).group(1), 16)
            h = rom.u16(load)
            self.assertEqual((h >> 11, ((load + 4) & ~3) + 4 * (h & 0xFF)), (0b01001, g["pointer"]), hex(load))
            self.assertIn(rom.ptr_at(g["pointer"]), {inv[sid]["offset"] for sid in g["ids"]})
        members = {sid for g in groups for sid in g["ids"]}
        self.assertEqual(len(members), 14)
        self.assertLessEqual(set(self.SHOWN), members)
        self.assertEqual(sorted(members & set(never)), [])
        for sid in self.BODY:
            self.assertTrue(never.get(sid, "").startswith(self.DEAD), sid)


@needs_rom
class TableMemberNeverShownTest(unittest.TestCase):
    """Unreached table-base members are never shown; the rest stay checked."""

    EV_IV = ["s0834B0C", "s0834B14", "s0834B38"]
    TRADES = ["s026CFB7", "s026CFC8", "s026CFF3", "s026D004", "s026D02F", "s026D040", "s026D06B",
              "s026D07C", "s026D0A7", "s026D0B8", "s026D0E3", "s026D0F4", "s026D11F", "s026D130",
              "s026D15B", "s026D16C", "s026D197"]
    ENIGMA = "s03DFC80"
    HOOKS = {0x50E24: 0x09ED80DD, 0x53A9C: 0x09ED81DD, 0x53AE4: 0x09ED8235, 0x53B48: 0x09ED82AD}

    @classmethod
    def setUpClass(cls):
        import json

        from gen3tl.catalog.catalog import never_shown
        from gen3tl.profile.profile import Profile
        cls.prof = prof = unbound()
        cls.never = never_shown(None, prof.get("reach", {}).get("never_shown", []))
        cls.inv = {e["id"]: e for e in json.loads((ROOT / "build" / "inventory.json").read_text(encoding="utf-8"))["entries"]}
        cls.rom = prof.load_rom(rom_path())

    def test_groups_resolve_to_distinct_rows(self):
        assert_never_shown_groups(self, self.prof, self.never,
                                 [self.EV_IV, self.TRADES, [self.ENIGMA]])

    def test_ev_iv_module_unreached(self):
        rom = self.rom
        self.assertEqual(rom.ptr_at(0x834580), 0x834B04)              # base of 'EVs:'
        self.assertEqual(rom.ptr_at(0x833CC8), 0x833C31)              # 0x8833CA8 sets the callback
        self.assertEqual(rom.read(0x7C8ADD, 5), bytes.fromhex("23a93c8308"))   # callasm 0x8833CA9
        data = bytes(rom.data)
        self.assertEqual(data.find((0x08833CA9).to_bytes(4, "little")), 0x7C8ADE)
        self.assertEqual(data.count((0x08833CA9).to_bytes(4, "little")), 1)
        self.assertEqual(data.find((0x087C8AC8).to_bytes(4, "little")), -1)    # script 0x7C8AC8
        self.assertEqual(rom.u8(0x7C8AC7), 0xFF)                      # a string ends before it
        assert_never_shown_groups(self, self.prof, self.never, [self.EV_IV])

    def test_trade_readers_hooked(self):
        rom = self.rom
        for entry, target in self.HOOKS.items():
            ldr, bx = rom.u16(entry), rom.u16(entry + 2)
            self.assertEqual((ldr >> 11, ldr & 0xFF, bx & 0xFF87), (0b01001, 0, 0x4700), hex(entry))
            self.assertEqual(rom.u32(entry + 4), target)
        for pool in (0x50EFC, 0x53AD4, 0x53B30, 0x53CA4):
            self.assertEqual(rom.ptr_at(pool), 0x26CF8C)
        self.assertEqual(rom.ptr_at(0x1FB7074), self.inv["s1F81D28"]["offset"])   # Unbound's table
        self.assertEqual(len(self.TRADES), 17)
        assert_never_shown_groups(self, self.prof, self.never, [self.TRADES])

    def test_berries(self):
        rom = self.rom
        self.assertEqual(rom.ptr_at(0x14E294), 0x3DF7E8)              # Berry Crush results
        self.assertEqual((rom.u8(0x876200 + 0xAF * 44), rom.u8(0x876200 + 0xAF * 44 + 26)), (0xFF, 0))
        self.assertEqual(rom.u8(0x876200 + 0x76 * 44 + 26), 5)        # Unbound's Enigma Berry pocket
        rows = assert_never_shown_groups(self, self.prof, self.never, [[self.ENIGMA]])
        self.assertEqual(rows[0]["ids"], [self.ENIGMA])
        shown = [f"s{0x3DF7E8 + 0x1C * k:07X}" for k in range(42)]
        self.assertEqual(self.inv[shown[41]]["text"], "STARF")
        self.assertEqual([sid for sid in shown if sid in self.never], [])


@needs_rom
class DeadReaderRestNeverShownTest(unittest.TestCase):
    """Remaining EV-IV labels and a nickname: only dead code points at them."""

    EV_IV = {"s0834AF4": 0x834270, "s0834B04": 0x834580, "s0834B18": 0x83459C,
             "s0834B20": 0x8345A0, "s0834B28": 0x8345A4, "s0834B30": 0x8345A8}
    TRADE_POOLS = [0x50EFC, 0x53AD4, 0x53B30, 0x53CA4]

    @classmethod
    def setUpClass(cls):
        import json

        from gen3tl.catalog.catalog import never_shown
        from gen3tl.profile.profile import Profile
        cls.prof = prof = unbound()
        cls.never = never_shown(None, prof.get("reach", {}).get("never_shown", []))
        cls.inv = {e["id"]: e for e in json.loads((ROOT / "build" / "inventory.json").read_text(encoding="utf-8"))["entries"]}
        cls.data = bytes(prof.load_rom(rom_path()).data)

    def words_to(self, sid):
        """Every offset holding a pointer into the string, aligned or not."""
        e, out = self.inv[sid], []
        for k in range(e["length"]):
            pat, at = (0x8000000 + e["offset"] + k).to_bytes(4, "little"), -1
            while (at := self.data.find(pat, at + 1)) >= 0:
                out.append(at)
        return sorted(out)

    def test_ev_iv_title_and_labels(self):
        assert_never_shown_groups(self, self.prof, self.never, [self.EV_IV, ["s026CF8C"]])
        for sid, pool in self.EV_IV.items():
            with self.subTest(sid=sid):
                self.assertEqual(self.words_to(sid), [pool])
                self.assertTrue(0x833C30 <= pool < 0x834A88)          # inside the module

    def test_trade_record_0_nickname(self):
        self.assertEqual(digest(self.inv["s026CF8C"]["text"]),
                         "b56150b7c1f5c456fae27ac8f72277de8834c698634ce74c2730b6973cef5207")
        self.assertEqual(self.words_to("s026CF8C"), self.TRADE_POOLS)
        rows = assert_never_shown_groups(self, self.prof, self.never, [["s026CF8C"]])
        self.assertEqual(rows[0]["ids"], ["s026CF8C"])
