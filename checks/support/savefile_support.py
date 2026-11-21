from pathlib import Path
import contextlib
import io
import struct
import tempfile

from gen3tl.verify.savefile import EOS, Charset, Layout, SaveFile, blank_save, checksum, find_name, main
from gen3tl.verify.savefixture import TestMon, compressed_pokemon, party_pokemon
from gen3tl.profile.profile import Profile
from gen3tl.lang import language

from project_fixture import select_language

def setUpModule():
    select_language("ru")

SAVE = Profile.by_name("unbound-2.1.1.1")["save"]

LAYOUT = Layout.from_dict(SAVE)

def _tables():
    from gen3tl.cli.common import _save_layout_and_charmap
    from gen3tl.profile.profile import Profile
    _, table, shared = _save_layout_and_charmap(Profile.by_name("unbound-2.1.1.1"), "ru")
    return table, shared

with language.use("ru"):   # the charset reads the pack's letters
    TABLE, SHARED = _tables()
    CS = Charset(TABLE, SHARED)

PLAYER_ID = 0xE8842CDC

def ru(text: str) -> bytes:
    return CS.encode(text, True)

def en(text: str) -> bytes:
    return CS.encode(text, False)

def padded(name: bytes, size: int) -> bytes:
    return (name + bytes([EOS]) * size)[:size]

def put_hof(raw: bytearray, team: list[tuple[int, int, int, bytes]]) -> None:
    """A Hall of Fame of one team in sectors 28 and 29, as the game writes it."""
    h = LAYOUT.hall_of_fame
    data = bytearray(h["data_size"] * len(h["sectors"]))
    for k, (species, pid, tid, nick) in enumerate(team):
        o = k * h["mon_size"]
        struct.pack_into("<I", data, o + h["trainer_id"], tid)
        struct.pack_into("<I", data, o + h["personality"], pid)
        struct.pack_into("<H", data, o + h["species"], species)
        data[o + h["nickname"]:o + h["nickname"] + h["nickname_size"]] = padded(nick, h["nickname_size"])
    for i, n in enumerate(h["sectors"]):
        o = n * LAYOUT.sector_size
        raw[o:o + LAYOUT.sector_size] = bytes(LAYOUT.sector_size)
        raw[o:o + h["data_size"]] = data[i * h["data_size"]:(i + 1) * h["data_size"]]
        struct.pack_into("<HHI", raw, o + 0xFF4, checksum(bytes(raw[o:o + h["data_size"]]), h["data_size"]), 0,
                         h["signature"])

class NameFieldTest:
    """A Russian-ROM save with names in every kind of field, in both slots."""

    def make(self, nickname2: str = "Щекочущий") -> SaveFile:
        raw = bytearray(blank_save(LAYOUT, counter=5, slot=0, rotation=2))
        raw[14 * 0x1000:28 * 0x1000] = blank_save(LAYOUT, counter=6, slot=1, rotation=9)[14 * 0x1000:28 * 0x1000]
        put_hof(raw, [(25, 1, PLAYER_ID, ru("Шустрик")), (25, 2, PLAYER_ID, ru(nickname2))])
        s = SaveFile(bytes(raw), LAYOUT)
        boxes = {rng["first"]: rng["ram"] for rng in LAYOUT.boxes}
        mail = LAYOUT.mail
        for slot in s.slots:
            p = LAYOUT.player
            s.write(slot, p["name"], padded(ru("Женя"), p["size"]))
            s.write(slot, p["trainer_id"], struct.pack("<I", PLAYER_ID))
            s.write(slot, LAYOUT.rival["name"], padded(ru("Юра"), LAYOUT.rival["size"]))
            s.write(slot, LAYOUT.party["count"], bytes([3]))
            base = LAYOUT.party["base"]
            s.write(slot, base, party_pokemon(TestMon("party", 0, 25, ru("Шустрик"), personality=1, otid=PLAYER_ID),
                                              ru("Женя")))
            s.write(slot, base + 100, party_pokemon(TestMon("party", 1, 25, ru(nickname2), personality=2,
                                                            otid=PLAYER_ID), ru("Женя")))
            s.write(slot, base + 200, party_pokemon(TestMon("party", 2, 25, en("Sparky"), personality=3,
                                                            otid=0x1234), ru("Женя")))      # traded: other id
            s.write(slot, boxes[1], compressed_pokemon(TestMon("box", 0, 4, ru("ЩУКА"), personality=5,
                                                               otid=PLAYER_ID), ru("Вася")))  # other OT name
            s.write(slot, LAYOUT.box_names["addresses"][2], padded(ru("Хижина"), LAYOUT.box_names["size"]))
            m = mail["base"]
            s.write(slot, m + mail["author"], padded(ru("Юра") + b"\x00\x00\x00", mail["author_size"]))
            s.write(slot, m + mail["trainer_id"], struct.pack("<I", 0x4321))
            s.write(slot, m + mail["item"], struct.pack("<H", 121))
            k = LAYOUT.link_records
            s.write(slot, k["base"], padded(ru("Щукарь"), k["name_size"]))
        # box 20 lives in sector 30, which both slots share
        s.write(s.slots[0], boxes[20], compressed_pokemon(TestMon("box", 0, 4, ru("Ёжик"), personality=4,
                                                                  otid=PLAYER_ID), ru("Женя")))
        s.fix_checksums()
        return SaveFile(s.to_bytes(), LAYOUT)

    def names(self, s: SaveFile) -> dict[tuple[int | None, str], bytes]:
        return {(f.slots[0] if f.slots else None, f.label): s.field_name(f) for f in s.name_fields()}

def fake_rom(species: list[bytes], egg: bytes) -> bytes:
    """A ROM with only the name tables of FAKE_NAMES."""
    data = bytearray(0x200)
    struct.pack_into("<I", data, 0x10, 0x08000180)
    data[0x180:0x180 + 11] = padded(egg, 11)
    for i, n in enumerate(species):
        data[0x40 + 11 * i:0x40 + 11 * i + 11] = padded(n, 11)
    return bytes(data)

FAKE_NAMES = {"species_table": 0x40, "species_stride": 11, "species_count": 4, "egg_pointer": 0x10}

class BrowserConvertTest:
    """The save page's conversion: main() without files, over published name tables."""

    RU = fake_rom([b"", ru("Бульбазавр"), ru("Ивизавр"), ru("Венузавр")], ru("Яйцо"))

    EN = fake_rom([b"", en("BULBASAUR"), en("IVYSAUR"), en("VENUSAUR")], en("EGG"))

    def main_bytes(self, save: bytes, src: bytes, dst: bytes, extra: list[str]) -> bytes | None:
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "in.sav").write_bytes(save)
            (d / "src.gba").write_bytes(src)
            (d / "dst.gba").write_bytes(dst)
            argv = [str(d / "in.sav"), str(d / "out.sav"), "--from-rom", str(d / "src.gba"), "--to-rom",
                    str(d / "dst.gba")] + extra
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                rc = main(argv, layout=dict(SAVE, names=FAKE_NAMES), charmap=TABLE, charmap_target=SHARED,
                          interactive=False)
            return (d / "out.sav").read_bytes() if rc == 0 else None

    def browser(self, save: bytes, src: bytes, dst: bytes, requested=(), output="original"):
        from gen3tl.verify.savefile import browser_convert, name_table, names_of
        layout = dict(SAVE, names=FAKE_NAMES)
        tables = [names_of(name_table(rom, Layout.from_dict(layout))) for rom in (src, dst)]
        return browser_convert(save, layout, *tables, {str(k): v for k, v in TABLE.items()}, SHARED, requested, output)

class EditOnlyTest:
    """The save page's same-ROM pass: requested names only, in the save's own letters."""

    CHARMAP = {str(k): v for k, v in TABLE.items()}

    def edit(self, save: bytes, translated: bool, requested=()):
        from gen3tl.verify.savefile import browser_edit
        return browser_edit(save, SAVE, self.CHARMAP, SHARED, translated, requested)

    def ranges(self, save: bytes, place: str) -> set[int]:
        """The bytes a rename at `place` may change: every field of its name, and the checksums."""
        s = SaveFile(save, LAYOUT)
        fields = s.name_fields()
        key = find_name(fields, place, s.slots[0].index).key
        allowed = {o for f in fields if f.key == key for start, n in f.segments or [(f.offset, f.size)]
                   for o in range(start, start + n)}
        for slot in s.slots:
            for n in slot.sectors.values():
                allowed.update(range(n * 0x1000 + 0xFF6, n * 0x1000 + 0xFF8))
        for n in LAYOUT.hall_of_fame["sectors"]:
            allowed.update(range(n * 0x1000 + 0xFF4, n * 0x1000 + 0xFF6))
        return allowed
