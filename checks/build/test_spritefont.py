import struct
import unittest

from gen3tl.build import spritefont as S
from gen3tl.build.inject import FreeSpace

from rom_support import source_text, needs_rom, rom_path
from project_fixture import UNBOUND, unbound


class Thumb:
    """An ARMv4T Thumb interpreter for sprite font routines."""

    def __init__(self, rom: bytes):
        self.mem = {0x08: bytearray(rom), 0x02: bytearray(0x40000), 0x03: bytearray(0x8000),
                    0x06: bytearray(0x18000)}
        self.r = [0] * 16
        self.r[13] = 0x03007E00
        self.n = self.z = self.c = self.v = False

    def _at(self, a: int, n: int):
        rom = a >> 24 in (0x08, 0x09)   # one 32 MB window
        region = self.mem[0x08 if rom else a >> 24]
        off = a - 0x08000000 if rom else a & 0xFFFFFF
        assert off + n <= len(region), hex(a)
        return region, off

    def read(self, a: int, n: int) -> int:
        region, off = self._at(a, n)
        return int.from_bytes(region[off:off + n], "little")

    def write(self, a: int, n: int, value: int) -> None:
        assert a >> 24 not in (0x08, 0x09), f"write to ROM at {a:#x}"
        assert not (a >> 24 == 0x06 and n == 1), f"byte write to VRAM at {a:#x}"
        region, off = self._at(a, n)
        region[off:off + n] = (value & ((1 << 8 * n) - 1)).to_bytes(n, "little")

    def nz(self, value: int) -> int:
        value &= 0xFFFFFFFF
        self.n, self.z = bool(value >> 31), value == 0
        return value

    def addsub(self, a: int, b: int, sub: bool) -> int:
        result = (a - b if sub else a + b) & 0xFFFFFFFF
        self.c = a >= b if sub else a + b > 0xFFFFFFFF
        self.v = bool(((a ^ b) & (a ^ result) if sub else ~(a ^ b) & (a ^ result)) >> 31)
        return self.nz(result)

    def cond(self, cc: int) -> bool:
        n, z, c, v = self.n, self.z, self.c, self.v
        return [z, not z, c, not c, n, not n, v, not v, c and not z, not c or z,
                n == v, n != v, not z and n == v, z or n != v][cc]

    def run(self, pc: int, stops, limit: int = 400000) -> int:
        r = self.r
        for _ in range(limit):
            if pc in stops:
                return pc
            h = self.read(0x08000000 + pc, 2)
            nxt = pc + 2
            top = h >> 13
            if h >> 11 in (0, 1, 2):
                rd, rm, imm = h & 7, h >> 3 & 7, h >> 6 & 31
                op = h >> 11
                if op == 0:
                    if imm:
                        self.c = bool(r[rm] >> (32 - imm) & 1)
                    r[rd] = self.nz(r[rm] << imm)
                elif op == 1:
                    imm = imm or 32
                    self.c = bool(r[rm] >> (imm - 1) & 1)
                    r[rd] = self.nz(r[rm] >> imm)
                else:
                    imm = imm or 32
                    value = r[rm] - (1 << 32) if r[rm] >> 31 else r[rm]
                    r[rd] = self.nz(value >> imm)
            elif h >> 11 == 3:
                rd, rn = h & 7, h >> 3 & 7
                val = (h >> 6 & 7) if h >> 10 & 1 else r[h >> 6 & 7]
                r[rd] = self.addsub(r[rn], val, bool(h >> 9 & 1))
            elif top == 1:
                op, rd, imm = h >> 11 & 3, h >> 8 & 7, h & 255
                if op == 0:
                    r[rd] = self.nz(imm)
                elif op == 1:
                    self.addsub(r[rd], imm, True)
                else:
                    r[rd] = self.addsub(r[rd], imm, op == 3)
            elif h >> 10 == 0x10:
                op, rd, rs = h >> 6 & 15, h & 7, h >> 3 & 7
                a, b = r[rd], r[rs]
                if op == 0:
                    r[rd] = self.nz(a & b)
                elif op == 1:
                    r[rd] = self.nz(a ^ b)
                elif op == 8:
                    self.nz(a & b)
                elif op == 9:
                    r[rd] = self.addsub(0, b, True)
                elif op == 10:
                    self.addsub(a, b, True)
                elif op == 11:
                    self.addsub(a, b, False)
                elif op == 12:
                    r[rd] = self.nz(a | b)
                elif op == 13:
                    r[rd] = self.nz(a * b)
                elif op == 14:
                    r[rd] = self.nz(a & ~b)
                elif op == 15:
                    r[rd] = self.nz(~b)
                else:
                    raise AssertionError(f"ALU operation {op} at {pc:#x}")
            elif h >> 10 == 0x11:
                op, rd, rs = h >> 8 & 3, (h & 7) | (h >> 4 & 8), h >> 3 & 15
                if op == 0:
                    r[rd] = (r[rd] + r[rs]) & 0xFFFFFFFF
                elif op == 1:
                    self.addsub(r[rd], r[rs], True)
                elif op == 2:
                    r[rd] = r[rs]
                else:
                    assert r[rs] & 1, f"bx to ARM at {pc:#x}"
                    nxt = (r[rs] & ~1) - 0x08000000
            elif h >> 11 == 9:
                r[h >> 8 & 7] = self.read(((0x08000000 + pc + 4) & ~3) + (h & 255) * 4, 4)
            elif h >> 12 == 5:
                op, rd = h >> 9 & 7, h & 7
                a = (r[h >> 3 & 7] + r[h >> 6 & 7]) & 0xFFFFFFFF
                size = [4, 2, 1, 1, 4, 2, 1, 2][op]
                if op < 3:
                    self.write(a, size, r[rd])
                else:
                    value = self.read(a, size)
                    if op == 3 and value & 0x80:
                        value -= 0x100
                    if op == 7 and value & 0x8000:
                        value -= 0x10000
                    r[rd] = value & 0xFFFFFFFF
            elif top == 3 or h >> 12 == 8:
                rd, rn, imm = h & 7, h >> 3 & 7, h >> 6 & 31
                if h >> 12 == 8:
                    size, load = 2, bool(h >> 11 & 1)
                else:
                    size, load = (1 if h >> 12 & 1 else 4), bool(h >> 11 & 1)
                a = r[rn] + imm * size
                if load:
                    r[rd] = self.read(a, size)
                else:
                    self.write(a, size, r[rd])
            elif h >> 12 == 9:
                a = r[13] + (h & 255) * 4
                if h >> 11 & 1:
                    r[h >> 8 & 7] = self.read(a, 4)
                else:
                    self.write(a, 4, r[h >> 8 & 7])
            elif h >> 12 == 10:
                base = r[13] if h >> 11 & 1 else (0x08000000 + pc + 4) & ~3
                r[h >> 8 & 7] = base + (h & 255) * 4
            elif h >> 8 == 0xB0:
                r[13] += -(h & 127) * 4 if h >> 7 & 1 else (h & 127) * 4
            elif h >> 9 in (0x5A, 0x5E):
                regs = [i for i in range(8) if h >> i & 1]
                if h >> 11 & 1:
                    for i in regs:
                        r[i] = self.read(r[13], 4)
                        r[13] += 4
                    if h >> 8 & 1:
                        nxt = (self.read(r[13], 4) & ~1) - 0x08000000
                        r[13] += 4
                else:
                    if h >> 8 & 1:
                        regs.append(14)
                    r[13] -= 4 * len(regs)
                    for k, i in enumerate(regs):
                        self.write(r[13] + 4 * k, 4, r[i])
            elif h >> 12 == 13 and h >> 8 & 15 < 14:
                if self.cond(h >> 8 & 15):
                    off = h & 255
                    nxt = pc + 4 + 2 * (off - 256 if off & 128 else off)
            elif h >> 11 == 0x1C:
                off = h & 0x7FF
                nxt = pc + 4 + 2 * (off - 0x800 if off & 0x400 else off)
            elif h >> 11 == 0x1E:
                low = self.read(0x08000000 + pc + 2, 2)
                off = (h & 0x7FF) << 12 | (low & 0x7FF) << 1
                off -= 1 << 23 if off & 1 << 22 else 0
                r[14] = (0x08000000 + pc + 4) | 1
                nxt = pc + 4 + off
            else:
                raise AssertionError(f"instruction {h:#06x} at {pc:#x} outside the interpreter")
            pc = nxt
        raise AssertionError(f"no stop reached from {pc:#x}")


VAR4, SPRITES, RETURN = 0x02021D18, 0x0202063C, 0x0FF0


@needs_rom
class ProfileSpriteFontTest(unittest.TestCase):
    """The declared choice is the base ROM's; the routine draws as modelled."""

    @classmethod
    def setUpClass(cls):
        from gen3tl.lang.langpack import LangPack
        from gen3tl.profile.profile import Profile
        prof = Profile.by_name("unbound-2.1.1.1")
        cls.base = prof.load_rom(rom_path())
        cls.font = S.from_profile(prof)[0]
        cls.pack = LangPack.load("ru", cls.font.style, rows=cls.font.cell_rows, top=0)
        cls.plan = S.plan(cls.font, cls.base, cls.pack)
        cls.rom = cls.base.copy()
        cls.res = S.apply(cls.rom, cls.base, [cls.plan], FreeSpace.scan(bytes(cls.base.data)))

    def join(self, font) -> int:
        h = struct.unpack_from("<H", font.lookup.code, len(font.lookup.code) - 2)[0]
        self.assertEqual(h >> 11, 0x1C)   # the code ends in a branch back
        off = h & 0x7FF
        return font.lookup.at + len(font.lookup.code) + 2 + 2 * (off - 0x800 if off & 0x400 else off)

    def tiles(self, data: bytes, font) -> list[int]:
        out = []
        for byte in range(256):
            cpu = Thumb(data)
            cpu.r[2] = byte
            cpu.run(font.lookup.at, {self.join(font)})
            self.assertEqual(cpu.r[3] % 32, 0)
            out.append(cpu.r[3] // 32)
        return out

    def test_declared_choice_matches_the_base_code(self):
        self.assertEqual(self.tiles(bytes(self.base.data), self.font), list(S.base_table(self.font)))

    def test_built_lookup_draws_every_pack_letter_and_keeps_the_base_ones(self):
        p = self.plan
        self.assertEqual(self.res.failures, [])
        self.assertEqual(S.verify(self.rom, self.base, [p], self.res), [])
        self.assertEqual(self.tiles(bytes(self.rom.data), self.font), list(p.table))
        letters = {b for c, b in self.pack.chars.items() if self.pack.sources[c] != "base"}
        self.assertFalse([b for b in letters if p.table[b] == self.font.fallback])
        base = S.base_table(self.font)
        self.assertEqual([b for b in range(256) if b not in letters and p.table[b] != base[b]], [])
        steps = S.base_advances(self.font)
        self.assertEqual([b for b in range(256) if b not in letters and p.advances[b] != steps[b]], [])

    def draw(self, text: bytes, size: int = 0x100, tile: int = 0x40):
        cpu = Thumb(bytes(self.rom.data))
        cpu.write(VAR4, len(text), int.from_bytes(text, "little"))
        cpu.write(SPRITES + 4, 2, tile)
        cpu.r[0], cpu.r[1], cpu.r[14] = 0, size, 0x08000000 + RETURN + 1
        for i in (4, 5, 6, 7):
            cpu.r[i] = 0x1110 * i
        sp = cpu.r[13]
        stop = cpu.run(self.font.calls[0].at, {RETURN, 0x9D7628})
        return cpu, stop, sp

    def canvas(self, cpu, size: int = 0x100, tile: int = 0x40) -> list[list[int]]:
        vram = cpu.mem[0x06][0x10000 + tile * 32:0x10000 + tile * 32 + size]
        width = size // 4
        return [[vram[(x >> 3) * 32 + y * 4 + (x & 7) // 2] >> 4 * (x & 1) & 15 for x in range(width)]
                for y in range(8)]

    def test_routine_draws_every_byte_as_the_model_or_runs_the_original(self):
        p = self.plan
        for byte in range(255):
            with self.subTest(byte=byte):
                cpu, stop, sp = self.draw(bytes([byte, 0xFF]))
                if p.table[byte] < self.font.tiles:
                    self.assertEqual(stop, 0x9D7628)   # the original routine continues
                    self.assertEqual((cpu.r[0], cpu.r[1], cpu.r[2], cpu.r[4]), (0, 0x100, 0x44, 0))
                    self.assertEqual(cpu.r[13], sp - 20)
                    self.assertEqual(cpu.read(sp - 4, 4), 0x08000000 + RETURN + 1)
                    self.assertEqual([cpu.read(sp - 20 + 4 * k, 4) for k in range(4)],
                                     [0x1110 * i for i in (4, 5, 6, 7)])
                else:
                    self.assertEqual(stop, RETURN)
                    self.assertEqual(cpu.r[13], sp)
                    self.assertEqual([cpu.r[i] for i in (4, 5, 6, 7)], [0x1110 * i for i in (4, 5, 6, 7)])
                    self.assertEqual(self.canvas(cpu), S.draw(p, bytes([byte]), 64))

    def test_routine_draws_names_and_clips_at_the_canvas(self):
        cm = self.pack.charmap()
        for text, size in (("Шум и гам/", 0x100), ("Навык связки", 0x100), ("Щит", 0x80),
                           ("Ледяные чешуйки и ещё длиннее", 0x100), ("Z-Атака 3", 0x100)):
            with self.subTest(text=text):
                data = cm.encode(text)
                cpu, stop, _ = self.draw(data, size)
                self.assertEqual(stop, RETURN)
                self.assertEqual(self.canvas(cpu, size), S.draw(self.plan, data[:-1], size // 4))
                tail = cpu.mem[0x06][0x10000 + 0x40 * 32 + size:0x10000 + 0x40 * 32 + size + 32]
                self.assertEqual(bytes(tail), bytes(32))   # nothing past the canvas

    def test_ability_position_steps_like_the_routine(self):
        cm = self.pack.charmap()
        for text in ("Uproar/", source_text('abilities:79'), "Шум и гам/", "Мозаичные глаза"):
            with self.subTest(text=text):
                data = cm.encode(text)[:-1]
                cpu = Thumb(bytes(self.rom.data))
                cpu.write(VAR4, len(data) + 3, int.from_bytes(data + b"\x00\x00\xff", "little"))
                cpu.write(SPRITES + 32, 2, 0x60)
                cpu.r[0], cpu.r[1], cpu.r[2], cpu.r[6] = 0, len(data), SPRITES, 1
                cpu.r[14] = 0x08000000 + RETURN + 1
                cpu.run(self.font.calls[1].at, {0x9D8CA6})
                expected = S.text_width(self.plan, data) - self.font.shared
                self.assertEqual(cpu.read(SPRITES + 32, 2), 0x60 + expected)
                self.assertEqual((cpu.r[0], cpu.r[6]), (0, 1))
        self.assertEqual(S.text_width(self.plan, cm.encode("Uproar/")[:-1]), 4 * 7 + 1)

    def test_name_canvases_keep_their_place(self):
        for at in (0x9D8BAC, 0x9D8C78):   # CreateSprite x of the move and ability canvases
            got = []
            for rom in (self.base, self.rom):
                cpu = Thumb(bytes(rom.data))
                cpu.run(at - 2, {at + 2})
                got.append((cpu.r[1], cpu.r[2]))
            self.assertEqual(got, [(96, 0xA4), (96, 0xA4)])

    def test_every_pair_stays_before_the_sight_icon(self):
        """No species DexNav can show draws a move and ability past the width."""
        from gen3tl.catalog.catalog import load_catalog
        from gen3tl.check import namepairs
        from gen3tl.lang.langpack import LangPack
        from gen3tl.web.editorfonts import sprite_measures
        prof = unbound()
        data = namepairs.dataset(prof)
        self.assertIsNotNone(data, "project dataset is required")
        catalog = load_catalog(UNBOUND / "translation/ru/po", prof)
        shown = {sid: e.msgstr or e.msgid for sid, (_, e) in catalog.items()}
        cm = LangPack.load("ru", prof["font_style"]["style"]).charmap()
        [res] = namepairs.results(prof, shown, {n: (m, cm) for n, m in sprite_measures(prof, "ru").items()}, data)
        self.assertGreater(len(res.widest), 300)
        self.assertEqual([namepairs.message(res, p) for p in res.over()], [])

    def test_every_translated_name_fits_its_canvas(self):
        from gen3tl.catalog.po import read
        cm = self.pack.charmap()
        wide = []
        for table, suffix in (("moves", "/"), ("abilities", "")):
            _, entries = read(UNBOUND / "translation/ru/po/tables" / f"{table}.po")
            for e in entries:
                if e.msgstr:
                    data = cm.encode(e.msgstr + suffix)[:-1]
                    # the last outline column may fall off the canvas
                    if S.text_width(self.plan, data) - self.font.shared > 64:
                        wide.append(e.msgstr)
        self.assertEqual(wide, [])
