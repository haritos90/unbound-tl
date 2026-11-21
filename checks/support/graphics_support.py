from pathlib import Path
import random

from gen3tl.build.graphics import lz77_compress
from gen3tl.core.rom import Rom, ptr_bytes
from gen3tl.build.inject import DiffRegistry

HEAD = ["id", "screen", "source_text", "category", "reason", "rom_offset", "compressed", "size_bytes", "tiles",
        "palette", "pointer_at", "seen_on_screen", "image"]

LZ_AT, RAW_AT, PAL_AT = 0x1000, 0x3000, 0x4000

def tiles(n: int, seed: int) -> bytes:
    """4bpp tiles with a frame in colour 1 and a few letters' worth of colour 2 pixels."""
    rnd = random.Random(seed)
    out = bytearray()
    for _ in range(n):
        px = [[1 if r in (0, 7) or c in (0, 7) else 3 for c in range(8)] for r in range(8)]
        for _ in range(6):
            px[rnd.randrange(2, 6)][rnd.randrange(2, 6)] = 2
        for r in range(8):
            out += bytes(px[r][2 * c] | px[r][2 * c + 1] << 4 for c in range(4))
    return bytes(out)

def literal_lz77(data: bytes) -> bytes:
    """An LZ77 stream of literals only, as a weaker compressor would leave it."""
    out = bytearray([0x10]) + len(data).to_bytes(3, "little")
    for i in range(0, len(data), 8):
        out += b"\x00" + data[i:i + 8]
    return bytes(out)

def fixture(tmp: Path, literal: bool = False):
    """A ROM with an LZ77 graphic (16 tiles), a raw one (4 tiles), a palette and their pointers."""
    d = bytearray(b"\x00" * 0x10000 + b"\xff" * 0x10000)
    lz_data, raw_data = tiles(16, 1), tiles(4, 2)
    blob = literal_lz77(lz_data) if literal else lz77_compress(lz_data)
    d[LZ_AT:LZ_AT + len(blob)] = blob
    d[RAW_AT:RAW_AT + len(raw_data)] = raw_data
    d[PAL_AT:PAL_AT + 32] = b"".join((k * 0x0421 + 0x0010).to_bytes(2, "little") for k in range(16))
    d[0x200:0x204] = ptr_bytes(LZ_AT)
    d[0x204:0x208] = ptr_bytes(RAW_AT)
    rows = [
        ["T1", "s", "LABEL", "translate", "", f"0x{LZ_AT:07X}", f"yes (LZ77, {len(blob)} bytes)", str(len(lz_data)),
         "16", f"raw:0x{PAL_AT:07X} (as loaded)", "0x0000200", "yes", ""],
        ["T2", "s", "TAB", "translate", "", f"0x{RAW_AT:07X}", "no", str(len(raw_data)), "4",
         "not found in ROM", "0x0000204", "yes", ""],
        ["T3", "s", "RUNTIME", "translate", "", "", "", "", "", "", "", "yes", ""],
    ]
    (tmp / "inv.tsv").write_text("\n".join("\t".join(r) for r in [HEAD] + rows) + "\n", encoding="utf-8")
    return Rom(d), lz_data, raw_data, len(blob)


def graphics_guard(res) -> DiffRegistry:
    guard = DiffRegistry()
    guard.add("graphics", res.allowed)
    return guard


def appended_sheet(sheet, n_new: int, tweak: bool = True) -> list[list[int]]:
    """The sheet with `n_new` tiles appended after the last tile."""
    g, wt = sheet.graphic, sheet.width_tiles
    height = -(-(g.tiles + n_new) // wt) * 8
    px = [row[:] for row in sheet.pixels] + [[0] * sheet.width for _ in range(height - sheet.height)]
    for i in range(n_new):
        k = g.tiles + i
        sx, sy, dx, dy = (i % wt) * 8, (i // wt) * 8, (k % wt) * 8, (k // wt) * 8
        for r in range(8):
            px[dy + r][dx:dx + 8] = sheet.pixels[sy + r][sx:sx + 8]
        if tweak:
            px[dy + 3][dx + 3] = 5
    return px
