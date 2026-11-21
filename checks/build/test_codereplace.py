import tempfile
import unittest
from pathlib import Path

from gen3tl.build import codereplace as C
from gen3tl.build.inject import FreeSpace
from gen3tl.core.rom import Rom

from rom_support import needs_rom, rom_path
from project_fixture import FIXTURES, unbound
from test_spritefont import Thumb

class SelectionTest(unittest.TestCase):


    def test_policy_file_selects_by_name(self):
        from gen3tl.check.policy import PolicyError, effective
        from gen3tl.profile.profile import Profile
        prof = Profile.by_name("unbound-2.1.1.1")
        text = (FIXTURES / "unbound-2.1.1.1-policy.toml").read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "policy.toml"
            path.write_text(text + '\n[code_replacements.pokedex-metric]\nheight_unit = "m"\n', encoding="utf-8")
            chosen = effective(prof, "ru", path, FIXTURES)
            self.assertEqual(chosen[C.SELECTED], {"pokedex-metric": {"height_unit": "m"}})
            self.assertNotIn(C.SELECTED, prof.data)
            path.write_text(text + '\n[code_replacements.pokedex-imperial]\nheight_unit = "m"\n', encoding="utf-8")
            with self.assertRaises(PolicyError):
                effective(prof, "ru", path, FIXTURES)


FLAG, PRINT, SDIV, UDIV, UMOD = 0x104AB0, 0x1047C8, 0x1E4018, 0x1E460C, 0x1E4684


RETURN = 0x0FF0


PRINTERS = (("height", 0x1058C4, 36, 10000, 0x105978, None),
            ("weight", 0x105A3C, 48, 100000, 0x105CAC, 0x105CA8))


@needs_rom
class PokedexMetricTest(unittest.TestCase):
    """Metric printers draw the value the original printers read."""

    @classmethod
    def setUpClass(cls):
        from gen3tl.lang.langpack import LangPack
        cls.prof = unbound("ru")
        prof = cls.prof
        cls.base = prof.load_rom(rom_path())
        cls.charmap = LangPack.load("ru", prof["font_style"]["style"]).charmap()
        cls.plans = C.plan(prof, cls.charmap)
        cls.rom = cls.base.copy()
        cls.res = C.apply(cls.rom, cls.base, cls.plans, FreeSpace.scan(bytes(cls.base.data)))
        cls.forms = []
        at = 0xA7D20A   # the form sizes the engine's hooks read
        while cls.base.u16(at) != 0xFEFE:
            cls.forms.append(cls.base.u16(at))
            at += 6

    def run_printer(self, data: bytes, at: int, species: int, caught: bool, y: int):
        """The printed texts and the first division's dividend."""
        cpu = Thumb(data)
        cpu.r[0], cpu.r[1], cpu.r[2], cpu.r[3] = 0x301, 0x10000 + species, 0x200, 0x100 + y
        cpu.r[14] = 0x08000000 + RETURN + 1
        for i in (4, 5, 6, 7):
            cpu.r[i] = 0x1110 * i
        sp, pc, prints, scaled = cpu.r[13], at, [], []
        while True:
            pc = cpu.run(pc, {FLAG, PRINT, SDIV, UDIV, UMOD, RETURN})
            if pc == RETURN:
                break
            if pc == FLAG:
                self.assertEqual((cpu.r[1], cpu.r[2]), (1, 0))   # the caught flag, read only
                cpu.r[0] = int(caught)
            elif pc == PRINT:
                text, a = bytearray(), cpu.r[2]
                while cpu.read(a, 1) != 0xFF:
                    text.append(cpu.read(a, 1))
                    a += 1
                prints.append((cpu.r[0], cpu.r[1], cpu.r[3], cpu.read(cpu.r[13], 4), cpu.read(cpu.r[13] + 4, 4),
                               cpu.r[2], bytes(text)))
            else:
                if pc == SDIV and not scaled:
                    scaled.append(cpu.r[0])
                cpu.r[0] = cpu.r[0] % cpu.r[1] if pc == UMOD else cpu.r[0] // cpu.r[1]
            pc = (cpu.r[14] & ~1) - 0x08000000
        self.assertEqual(cpu.r[13], sp)
        self.assertEqual([cpu.r[i] for i in (4, 5, 6, 7)], [0x1110 * i for i in (4, 5, 6, 7)])
        return prints, scaled

    def text(self, rom: Rom, word: int) -> bytes:
        at = rom.u32(word) - 0x08000000
        return bytes(rom.data[at:rom.data.index(0xFF, at)])

    @staticmethod
    def metric(value: int) -> bytes:
        out, shown = bytearray(), False
        for power in (10000, 1000, 100):
            digit = value // power % 10
            shown |= digit > 0
            out.append(0xA1 + digit if shown else 0x00)
        return bytes(out) + bytes([0xA1 + value // 10 % 10, 0xB8, 0xA1 + value % 10])

    def policy_plan(self, language, texts):
        """The plans of a temporary policy, and its language pack charmap."""
        from gen3tl.check.policy import effective
        from gen3tl.lang.langpack import LangPack
        from gen3tl.profile.profile import Profile
        raw = Profile.by_name("unbound-2.1.1.1")
        charmap = LangPack.load(language, raw["font_style"]["style"]).charmap()
        policy = (FIXTURES / "unbound-2.1.1.1-policy.toml").read_text(encoding="utf-8")
        policy = policy.replace('language = "ru"', f'language = "{language}"')
        policy += "\n[code_replacements.pokedex-metric]\n"
        policy += "\n".join(f'{w} = "{t}"' for w, t in texts.items()) + "\n"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "policy.toml"
            path.write_text(policy, encoding="utf-8")
            prof = effective(raw, language, path, FIXTURES)
        return C.plan(prof, charmap), charmap

    def test_declared_routines_are_the_base_printers_and_their_only_entry(self):
        rep = C.from_profile(self.prof)[0]
        self.assertEqual(rep.name, "pokedex-metric")
        for routine in rep.routines:
            self.assertTrue(routine.guard.matches(self.base.data))
        self.assertEqual([c.at for c in rep.calls], [r.at for r in rep.routines])
        for bl, target in ((0x105F30, 0x1058C4), (0x105F44, 0x105A3C)):
            hi, lo = self.base.u16(bl), self.base.u16(bl + 2)
            off = (hi & 0x7FF) << 12 | (lo & 0x7FF) << 1
            self.assertEqual(bl + 4 + off - (1 << 23 if off & 1 << 22 else 0), target)
        self.assertEqual(self.plans[0].texts, [self.charmap.encode("м")])
        self.assertEqual(self.plans[0].replacement.words, ["height_unit"])
        self.assertEqual(set(rep.fallbacks), {"weight_unit"})
        self.assertEqual(rep.fallbacks["weight_unit"]["at"], 0x105CA8)
        self.assertEqual(rep.fallbacks["weight_unit"]["words"], ["height_unit"])
        self.assertEqual((self.res.failures, C.verify(self.rom, self.plans, self.res)), ([], []))

    def test_metric_printers_draw_the_value_the_originals_read(self):
        species = sorted(set(range(1, 1295, 5)) | set(self.forms))
        for name, at, y, scale, label, unit in PRINTERS:
            for sp in species:
                with self.subTest(printer=name, species=sp):
                    old, scaled = self.run_printer(bytes(self.base.data), at, sp, True, y)
                    new, _ = self.run_printer(bytes(self.rom.data), at, sp, True, y)
                    self.assertEqual([p[:5] for p in new], [p[:5] for p in old])
                    self.assertEqual([p[:5] for p in new], [(1, 0, 0, y, 0), (1, 0, 30, y, 0)])
                    self.assertEqual(new[0][5], self.rom.u32(label))
                    units = self.charmap.encode("м")[:-1] if unit is None else self.text(self.rom, unit)
                    self.assertEqual(new[1][6], b"\xfc\x14\x05" + self.metric(scaled[0] // scale)
                                     + b"\x00\xfc\x14\x00" + units)

    def test_uncaught_species_show_placeholders(self):
        for name, at, y, _, label, unit in PRINTERS:
            for sp in (1, 25, 150, 1020, 1294):
                with self.subTest(printer=name, species=sp):
                    old, scaled = self.run_printer(bytes(self.base.data), at, sp, False, y)
                    new, _ = self.run_printer(bytes(self.rom.data), at, sp, False, y)
                    self.assertEqual((scaled, [p[:5] for p in new]), ([], [p[:5] for p in old]))
                    units = self.charmap.encode("м")[:-1] if unit is None else self.text(self.rom, unit)
                    self.assertEqual(new[1][6], self.charmap.encode('{MIN_LETTER_SPACING 05}????,? {MIN_LETTER_SPACING 00}', terminate=False) + units)

    def test_labels_follow_the_text_build_and_the_weight_the_pool_word(self):
        rom = self.rom.copy()
        texts = {0x105978: "Рост", 0x105CAC: "Вес", 0x105CA8: "кг"}
        free = 0x1FFF000
        for word, text in texts.items():
            data = self.charmap.encode(text)
            rom.write(free, data)
            rom.write(word, (0x08000000 + free).to_bytes(4, "little"))
            free += len(data)
        height, _ = self.run_printer(bytes(rom.data), 0x1058C4, 1, True, 36)
        weight, _ = self.run_printer(bytes(rom.data), 0x105A3C, 1, True, 48)
        self.assertEqual(height[0][6], self.charmap.encode("Рост")[:-1])
        self.assertEqual(weight[0][6], self.charmap.encode("Вес")[:-1])
        self.assertEqual(height[1][6], self.charmap.encode('{MIN_LETTER_SPACING 05}   0,7 {MIN_LETTER_SPACING 00}', terminate=False)
                         + self.charmap.encode("м")[:-1])
        self.assertEqual(weight[1][6], self.charmap.encode('{MIN_LETTER_SPACING 05}   6,9 {MIN_LETTER_SPACING 00}', terminate=False)
                         + self.charmap.encode("кг")[:-1])

    def test_a_non_russian_policy_prints_its_weight_unit(self):
        plans, charmap = self.policy_plan("fr", {"height_unit": "m", "weight_unit": "kg"})
        rom = self.base.copy()
        res = C.apply(rom, self.base, plans, FreeSpace.scan(bytes(self.base.data)))
        self.assertEqual((res.failures, C.verify(rom, plans, res)), ([], []))
        height, _ = self.run_printer(bytes(rom.data), 0x1058C4, 1, True, 36)
        weight, _ = self.run_printer(bytes(rom.data), 0x105A3C, 1, True, 48)
        self.assertEqual(height[1][6], self.charmap.encode('{MIN_LETTER_SPACING 05}   0,7 {MIN_LETTER_SPACING 00}', terminate=False)
                         + charmap.encode("m")[:-1])
        self.assertEqual(weight[1][6], self.charmap.encode('{MIN_LETTER_SPACING 05}   6,9 {MIN_LETTER_SPACING 00}', terminate=False)
                         + charmap.encode("kg")[:-1])

    def test_without_a_weight_unit_the_policy_falls_back_to_the_pool_word(self):
        plans, charmap = self.policy_plan("fr", {"height_unit": "m"})
        self.assertEqual(plans[0].texts, [charmap.encode("m")])
        self.assertEqual(plans[0].replacement.words, ["height_unit"])
        rom = self.base.copy()
        res = C.apply(rom, self.base, plans, FreeSpace.scan(bytes(self.base.data)))
        self.assertEqual((res.failures, C.verify(rom, plans, res)), ([], []))
        weight, _ = self.run_printer(bytes(rom.data), 0x105A3C, 1, True, 48)
        self.assertEqual(weight[1][6], self.charmap.encode('{MIN_LETTER_SPACING 05}   6,9 {MIN_LETTER_SPACING 00}', terminate=False)
                         + self.text(self.base, 0x105CA8))                  # the pool word lbs.
        rom = self.base.copy()
        free = 0x1FFF000
        data = charmap.encode("kg")
        rom.write(free, data)
        rom.write(0x105CA8, (0x08000000 + free).to_bytes(4, "little"))
        taken = set(range(free, free + len(data))) | set(range(0x105CA8, 0x105CA8 + 4))
        res = C.apply(rom, self.base, plans, FreeSpace.scan(bytes(self.base.data)), taken)
        self.assertEqual((res.failures, C.verify(rom, plans, res)), ([], []))
        weight, _ = self.run_printer(bytes(rom.data), 0x105A3C, 1, True, 48)
        self.assertEqual(weight[1][6], self.charmap.encode('{MIN_LETTER_SPACING 05}   6,9 {MIN_LETTER_SPACING 00}', terminate=False)
                         + data[:-1])                                       # the text build's pointer

    def test_a_rom_with_other_printer_bytes_is_refused(self):
        base = self.base.copy()
        base.write(0x105A00, b"\xee")
        rom = base.copy()
        res = C.apply(rom, base, self.plans, FreeSpace.scan(bytes(base.data)))
        self.assertEqual(res.failures, ["code replacement pokedex-metric: the base ROM does not hold the "
                                        "declared routine at 0x1058c4"])
        self.assertEqual(bytes(rom.data), bytes(base.data))
