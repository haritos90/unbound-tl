import struct

from gen3tl.core.rom import Rom, ptr_bytes
from gen3tl.discover import graphics as gfx

def words(*values):
    return struct.pack("<" + "H" * len(values), *values)

def bl_bytes(at: int, target: int) -> bytes:
    """A Thumb BL from `at` to `target`."""
    offset = target - (at + 4)
    assert -2**22 <= offset < 2**22, (hex(at), hex(target), offset)
    return struct.pack("<HH", 0xF000 | ((offset >> 12) & 0x7FF), 0xF800 | ((offset >> 1) & 0x7FF))

CPUSET, FASTSET, LZV = 0x9000, 0x9010, 0x9020

class ProbeAsm:
    def __init__(self, rom: Rom, at: int, pool_at: int):
        self.rom, self.pc, self.pool_at = rom, at, pool_at
        self.pool = {}
        self.fixups = []
        self.labels = {}

    def h(self, *halfwords: int):
        for half in halfwords:
            self.rom.write(self.pc, struct.pack("<H", half))
            self.pc += 2
        return self

    def ldr(self, rd: int, value: int):
        if value not in self.pool:
            self.pool[value] = self.pool_at + 4 * len(self.pool)
        slot = self.pool[value]
        imm = (slot - ((self.pc + 4) & ~3)) // 4
        assert 0 <= imm <= 255
        return self.h(0x4800 | rd << 8 | imm)

    def mov(self, rd: int, imm: int):
        return self.h(0x2000 | rd << 8 | imm)

    def bl(self, target: int):
        self.rom.write(self.pc, bl_bytes(self.pc, target))
        self.pc += 4
        return self

    def label(self, name: str):
        self.labels[name] = self.pc
        return self

    def b(self, name: str, cond: int | None = None):
        self.fixups.append((self.pc, cond, name))
        return self.h(0)

    def done(self):
        for at, cond, name in self.fixups:
            off = (self.labels[name] - (at + 4)) // 2
            half = 0xE000 | off & 0x7FF if cond is None else 0xD000 | cond << 8 | off & 0xFF
            self.rom.write(at, struct.pack("<H", half))
        for value, slot in self.pool.items():
            self.rom.write(slot, value.to_bytes(4, "little"))
        return self.pc

def probe_rom() -> Rom:
    rom = Rom(b"\x00" * 0x10000)
    rom.write(CPUSET, words(0xDF0B, 0x4770))
    rom.write(FASTSET, words(0xDF0C, 0x4770))
    rom.write(LZV, words(0xDF12, 0x4770))
    return rom

def probe_palette(seed: int) -> bytes:
    values = [(seed * 97 + 31 * k) & 0x7FFF for k in range(16)]
    if values[0] & 0xFF == 0x10:
        values[0] ^= 1
    return struct.pack("<16H", *values)

class FlaggingTest:
    def document(self):
        return ('version = "2.0.0"\n'
                '\n'
                '[[graphic]]\n'
                'id = "G01"\n'
                'rom_offset = "0x1000"\n'
                'compressed = "no"\n'
                'size_bytes = "128"\n'
                'tiles = "4"\n'
                'palette = "not found in ROM"\n'
                'pointer_at = "0x0200"\n'
                'category = "keep"\n'
                'reason = "old reason"\n'
                '\n'
                '[[views.G01]]\n'
                'label = "Complete tilemap"\n'
                'width = 32\n'
                'height = 32\n'
                'cells = [[0, 0, 0, 0]]\n')

    def discovery_record(self):
        return {"id": "g0002000", "offset": 0x2000, "compression": "none", "block_length": 128,
                "decoded_size": 128, "shape": {"bpp4_tiles": 4, "bpp8_tiles": 2},
                "render_modes": [{"mode": "tile-sheet-4bpp", "bpp": 4, "tiles": 4}],
                "palette": "raw:0x3000", "palette_source": "rom-evidence", "palette_bpp": 4,
                "palette_variants": [{"spec": "raw:0x3000", "bpp": 4, "bank": 0, "tier": "consumer"}],
                "refs": [{"at": 0x200, "kind": "pool", "aligned": True},
                         {"at": 0x201, "kind": "unaligned", "aligned": False}],
                "relocation_ambiguous": True}

    def proved_raw_rom(self):
        rom = probe_rom()
        for at, target in ((0x400, 0x2000), (0x408, 0x2080), (0x410, 0x2100)):
            rom.write(at, ptr_bytes(target) + struct.pack("<I", 128))
            rom.write(target, bytes(range(128)))
        rom.write(0x200, ptr_bytes(0x2000))
        rom.write(0x206, ptr_bytes(0x2000))
        rom.write(0x3000, probe_palette(1))
        a = ProbeAsm(rom, 0x600, 0x700)
        a.ldr(0, 0x08003000).ldr(1, 0x05000000).mov(2, 16).bl(CPUSET)
        a.ldr(0, 0x08002000).ldr(1, 0x06000000).ldr(2, 0x04000020).bl(CPUSET).h(0x4770).done()
        return rom


def candidate(rom: Rom, offset: int):
    return next(c for c in gfx.scan(rom)["candidates"] if c.offset == offset)
