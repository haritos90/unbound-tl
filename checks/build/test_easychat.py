import re
import unittest

from gen3tl.build import easychat as E
from gen3tl.build.inject import DiffRegistry, diff_positions, verify
from gen3tl.core.rom import ROM_BASE
from gen3tl.lang.langpack import LangPack

from rom_support import needs_rom, rom_path
from project_fixture import UNBOUND, unbound

ROOT = UNBOUND


CM = LangPack.load("ru").charmap()


@needs_rom
class ProfileAlphabetTest(unittest.TestCase):
    """The declared lists are the base ROM's; English initials file each word."""

    @classmethod
    def setUpClass(cls):
        from gen3tl.core.charmap import Charmap
        from gen3tl.profile.profile import Profile
        prof = Profile.by_name("unbound-2.1.1.1")
        cls.base = prof.load_rom(rom_path())
        cls.alpha = E.from_profile(prof)
        cls.tables = {t["name"]: t for t in prof.get("table", [])}
        cls.cm = Charmap()

    def test_declared_bytes_hold_every_word_once(self):
        self.assertIsNone(E.stale(self.base, self.alpha))
        lists = E.read_lists(self.base, self.alpha)
        self.assertEqual((len(lists), sum(map(len, lists))), (27, 1745))
        words = [x for entries in lists for e in entries for x in e]
        self.assertEqual(len(words), len(set(words)))
        for g in range(self.alpha.group_count):   # the group table's word counts
            with self.subTest(group=g):
                self.assertEqual(sum(x >> 9 == g for x in words), self.base.u16(self.alpha.groups + 8 * g + 4))
        self.assertEqual(2 * sum(len(e) + 2 * (len(e) > 1) for e in (e for x in lists for e in x)),
                         self.alpha.lists.end - self.alpha.lists.at)

    def test_english_initials_file_the_words_as_the_base_lists(self):
        p = E.plan(self.alpha, self.base, self.base, self.tables, self.cm,
                   [chr(c) for c in range(ord("A"), ord("Z") + 1)])
        moved = {}
        for n, (old, new) in enumerate(zip(E.read_lists(self.base, self.alpha), p.lists)):
            for e in set(old) ^ set(new):
                moved[e] = moved.get(e, ()) + (n,)
        texts = {e: [p.texts[x] for x in e] for e in moved}
        # shown text starts elsewhere than the English filing.
        # cases: word pointers, glyph words, a move beside the type.
        self.assertEqual(sorted(t[0] for t in texts.values()),
                         ["Ental", "PSYCHIC", "PSYCHIC", "Psychic", "orldD", "{PK}RS",
                          "{POKEBLOCK_PO}{POKEBLOCK_KE}{POKEBLOCK_BL}{POKEBLOCK_OC}{POKEBLOCK_K}"])


@needs_rom
class RussianAlphabetTest(unittest.TestCase):
    """The Russian words, injected as the build writes them, regrouped by the pack's buttons."""

    @classmethod
    def setUpClass(cls):
        import json

        from gen3tl.build.inject import inject
        from gen3tl.catalog.catalog import load_catalog
        from gen3tl.lang import language
        cls.prof = unbound()
        cls.base = cls.prof.load_rom(rom_path())
        cls.alpha = E.from_profile(cls.prof)
        cls.tables = {t["name"]: t for t in cls.prof.get("table", [])}
        data = language.load("ru").data
        cls.buttons, cls.fold = data["easy_chat_alphabet"], data["fold"]
        cls.catalog = load_catalog(ROOT / "translation" / "ru" / "po")
        inv = json.loads((ROOT / "build" / "inventory.json").read_text(encoding="utf-8"))
        by_offset = {e["offset"]: e for e in inv["entries"] if e["kind"] == "pointer"}
        sids = set()
        for entries in E.read_lists(cls.base, cls.alpha):
            for x in (x for e in entries for x in e):
                g, i = x >> 9, x & 0x1FF
                if g in cls.alpha.names:
                    sids.add(f"{cls.alpha.names[g]}:{i}")
                    continue
                at = cls.base.ptr_at(cls.base.ptr_at(cls.alpha.groups + 8 * g) + 12 * i)
                if at in by_offset:
                    sids.add(by_offset[at]["id"])
        by_id = {e["id"]: e for e in inv["entries"]}
        texts = {sid: CM.encode(cls.catalog[sid][1].msgstr) for sid in sids if cls.catalog[sid][1].msgstr}
        cls.rom, cls.texts = cls.base.copy(), texts
        cls.injected = inject(cls.rom, cls.base, {"entries": [by_id[s] for s in texts]}, texts, cls.tables)
        cls.before = cls.rom.copy()
        cls.plan = E.plan(cls.alpha, cls.base, cls.rom, cls.tables, CM, cls.buttons, cls.fold)
        cls.res = E.apply(cls.rom, cls.plan)

    def test_every_word_once_under_the_button_of_its_initial(self):
        self.assertEqual(self.injected.skipped, [])
        self.assertEqual(E.verify(self.rom, self.plan, self.res), [])
        lists = E.read_lists(self.rom, self.alpha)
        words = [x for entries in lists for e in entries for x in e]
        planned = [x for entries in self.plan.lists for e in entries for x in e]
        self.assertEqual(sorted(words), sorted(planned))
        self.assertEqual(len(words), len(set(words)))
        button = {c: n + 1 for n, letters in enumerate(self.buttons) for c in letters}
        key = E.collation(self.buttons, self.fold)
        for n, entries in enumerate(lists):
            shown = [E.word_text(self.rom, self.alpha, self.tables, CM, e[0]) for e in entries]
            with self.subTest(record=n):
                self.assertLessEqual(len(entries), self.alpha.limit)
                self.assertEqual(len(shown), len(set(shown)))
                self.assertEqual({button.get(t[0].upper(), 0) for t in shown}, {n})
                self.assertEqual([key(t) for t in shown], sorted(key(t) for t in shown))
                for e in entries:   # alternatives show one text
                    self.assertEqual(len({self.plan.texts[x] for x in e}), 1)

    def test_records_and_the_guard_class(self):
        at = self.alpha.lists.at
        for n in range(self.alpha.count):
            ptr, size = self.rom.u32(self.alpha.records.at + 8 * n), self.rom.u32(self.alpha.records.at + 8 * n + 4)
            self.assertEqual(ptr, ROM_BASE + at)
            at += 2 * size
        self.assertEqual(at, self.alpha.lists.at + len(self.plan.blob))
        self.assertLessEqual(at, self.alpha.lists.end)
        written = set(range(self.alpha.lists.at, at)) | set(range(self.alpha.records.at, self.alpha.records.end))
        self.assertEqual(self.res.allowed, written)
        self.assertTrue(set(diff_positions(self.rom.data, self.before.data)) <= written)
        guard = DiffRegistry()
        self.res.register(guard)
        self.assertEqual(verify(self.rom, self.base, self.injected, self.texts, set(), guard), [])

    def test_rows_label_each_button_with_its_first_letter(self):
        """A translated cell starts where its English cell starts."""
        from gen3tl.build.font import FontTable
        fonts = FontTable.from_profile(self.prof)
        pack = LangPack.load("ru", self.prof["font_style"]["style"])
        slots = pack.glyph_slots(self.base, fonts[0])

        def width(c):
            b = CM.encode(c, terminate=False)[0]
            return slots[b].width if b in slots else fonts[0].width(self.base, b)

        def cells(text):
            out, x, cur = [], 0, None
            for clear, c in re.findall(r"\{CLEAR ([0-9A-F]{2})\}|(.)", text):
                if clear:
                    x, cur = x + int(clear, 16), None
                    continue
                if c != " " and cur is None:
                    cur = [x, ""]
                    out.append(cur)
                if cur is not None:
                    cur[1] += c
                x += width(c)
            return out

        key_map = self.alpha.keys.read(self.base.data)
        per_row = len(key_map) // len(self.alpha.rows)
        labels = {}
        for r, sid in enumerate(self.alpha.rows):
            e = self.catalog[sid][1]
            english, russian = cells(e.msgid), cells(e.msgstr)
            self.assertEqual([x for x, _ in russian], [x for x, _ in english])
            for i, (_, label) in enumerate(russian):
                labels[key_map[per_row * r + i]] = label
        self.assertEqual(sorted(labels), list(range(self.alpha.count)))
        self.assertEqual([labels[n] for n in range(1, self.alpha.count)], [b[0] for b in self.buttons])
