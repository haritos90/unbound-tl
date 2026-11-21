import gzip
import struct
import sys
import unittest
import zlib
from pathlib import Path

from test_roots import PROJECT_ROOT, TEST_ROOT

ROOT = PROJECT_ROOT

from gen3tl.verify.savefile import CONTAINERS, SaveError, SaveFile, accepted, rle_decode, rle_encode, sharkport_checksum, standalone_source, unwrap

import savefile_support as base
from savefile_support import FAKE_NAMES, LAYOUT, SAVE, SHARED, TABLE
from project_fixture import select_language

FIXTURES = TEST_ROOT / "fixtures" / "saves"

S = LAYOUT.size

ROM_HEADER = b"POKEMON FIREBPRE" + bytes([0, 0, 0x68, 0x30, 1]) + bytes(7)   # 0x1C bytes from 0xA0

def setUpModule():
    select_language("ru")

def signed_sum(payload: bytes) -> int:
    """mGBA's SharkPort writer: c += (char) byte << (c % 24)."""
    c = 0
    for b in payload:
        c = (c + ((b - 256 if b > 127 else b) << (c % 24))) % (1 << 32)
    return c

def sharkport(flash: bytes) -> bytes:
    """As mGBA's GBASavedataExportSharkPort writes it."""
    def text(s: bytes) -> bytes:
        return struct.pack("<I", len(s)) + s
    payload = ROM_HEADER + flash
    return (b"\x0d\x00\x00\x00SharkPortSave" + struct.pack("<I", 0x000F0000) + text(b"POKEMON FIRE")
            + text(b"11/05/2026 12:34:56 PM") + text(b"") + struct.pack("<I", len(payload)) + payload
            + struct.pack("<I", signed_sum(payload)))

def gsv(flash: bytes) -> bytes:
    """Synthetic GameShark SP data with a preserved identity and a payload CRC."""
    head = (b"ADVSAVEG" + struct.pack("<I", 0x5A5A1234) + b"POKEMON FIRE"
            + struct.pack("<IIIII", 0, 6, ccitt_false(flash), len(flash), 0)
            + b"Unbound fixture".ljust(0x400, b"\x00") + b"xV4\x12")
    assert len(head) == 0x430
    return head + flash

def ccitt_false(data: bytes) -> int:
    """Bitwise reference independent of the converter's standard-library implementation."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ (0x1021 if crc & 0x8000 else 0)) & 0xFFFF
    return crc

def nocash(flash: bytes, method: int) -> bytes:
    """A NO$GBA battery file: header with a date, the SRAM entry (stored or run-length), STOP."""
    head = b"NocashGbaBackupMediaSavDataFile\x1a" + b"05.11.2026 12:34:56".ljust(0x20, b"\x00")
    stored = flash.rstrip(b"\xff")       # stored up to the last byte the game wrote
    if method == 0:
        entry = struct.pack("<4sII", b"SRAM", 0, len(stored)) + stored
    else:
        code = rle_encode(stored)
        entry = struct.pack("<4sIII", b"SRAM", 1, len(code) + 4, len(stored)) + code
    return head + entry + b"STOP" + bytes(8)

def rzip(save: bytes, chunk: int = 0x20000) -> bytes:
    """As RetroArch writes a save with SaveRAM Compression: a header, then one zlib stream per 128 KiB."""
    chunks = [zlib.compress(save[i:i + chunk], 6) for i in range(0, len(save), chunk)]
    return (b"#RZIPv\x01#" + struct.pack("<IQ", chunk, len(save))
            + b"".join(struct.pack("<I", len(c)) + c for c in chunks))

CLOCK = bytes([0x26, 0x11, 0x05, 0x04, 0x12, 0x34, 0x56, 0x40]) + struct.pack("<Q", 1793881296)   # mGBA RTC

CONTAINER = {
    "raw": ("raw.sav", lambda f: f),
    "clock": ("clock.sav", lambda f: f + CLOCK),
    "mister": ("mister.sav", lambda f: f + struct.pack("<QI", 0x2A5B3C4D, 1793881296).ljust(0x200, b"\x00")),
    "meteor": ("meteor.srm", lambda f: f + struct.pack("<I", S)),
    "libretro": ("libretro.srm", lambda f: f + b"\xff" * 0x2000),
    "padded": ("padded.sav", lambda f: f + bytes(0x40000 - S)),
    "bizhawk": ("bizhawk.SaveRAM", lambda f: b"GBABATT\x00" + struct.pack("<ii", S, 0x2000) + f + b"\xff" * 0x2000),
    "sharkport": ("sharkport.sps", sharkport),
    "gsv": ("gameshark-sp.gsv", gsv),
    "nocash": ("nocash.sav", lambda f: nocash(f, 0)),
    "nocash-rle": ("nocash-rle.sav", lambda f: nocash(f, 1)),
    "rzip": ("rzip.srm", rzip),   # the mGBA core's 128 KiB, compressed
}

def fixture(name: str) -> bytes:
    return gzip.decompress((FIXTURES / f"{name}.gz").read_bytes())

class ContainerTest(unittest.TestCase):
    RAW = fixture("raw.sav")

    def convert(self, data: bytes, output="original"):
        """The save page's conversion from the Russian to the English ROM."""
        return base.BrowserConvertTest.browser(self, data, base.BrowserConvertTest.RU, base.BrowserConvertTest.EN,
                                               output=output)

    def test_the_fixtures_are_the_raw_save_wrapped(self):
        self.assertEqual(len(self.RAW), S)
        self.assertEqual(SaveFile(self.RAW, LAYOUT).container.kind, "raw")
        for kind, (name, wrap) in CONTAINER.items():
            with self.subTest(kind=kind):
                self.assertEqual(fixture(name), wrap(self.RAW))
        self.assertEqual({k.split("-")[0] for k in CONTAINER}, set(CONTAINERS))

    def test_every_container_unwraps_and_writes_back_unchanged(self):
        for kind, (name, _wrap) in CONTAINER.items():
            with self.subTest(kind=kind):
                data = fixture(name)
                save = SaveFile(data, LAYOUT)
                self.assertEqual(save.container.kind, kind.split("-")[0])
                self.assertEqual(bytes(save.raw), self.RAW)
                self.assertEqual(save.to_bytes(), data)

    def test_every_container_round_trips_a_conversion(self):
        report, converted = self.convert(self.RAW)
        self.assertEqual(report["over"], [])
        self.assertNotEqual(converted, self.RAW)
        for kind, (name, wrap) in CONTAINER.items():
            with self.subTest(kind=kind):
                report, out = self.convert(fixture(name))
                self.assertEqual(report["container"], kind.split("-")[0])
                self.assertEqual(report["output"], {"format": "original", "container": kind.split("-")[0],
                                                    "extension": None})
                self.assertEqual(out, wrap(converted))
                self.assertEqual(bytes(SaveFile(out, LAYOUT).raw), converted)

    def test_raw_sav_and_srm_outputs_strip_every_container_and_round_trip(self):
        converted = self.convert(self.RAW)[1]
        for kind, (name, _wrap) in CONTAINER.items():
            for output in ("sav", "srm"):
                with self.subTest(kind=kind, output=output):
                    report, out = self.convert(fixture(name), output)
                    self.assertEqual(report["output"], {"format": output, "container": "raw",
                                                        "extension": f".{output}"})
                    self.assertEqual(out, converted)
                    reparsed = SaveFile(out, LAYOUT)
                    self.assertEqual(reparsed.container.kind, "raw")
                    self.assertEqual(self.convert(out)[1], converted)

    def test_rename_only_can_change_the_envelope_without_changing_names(self):
        from gen3tl.verify.savefile import browser_edit
        data = fixture("rzip.srm")
        report, out = browser_edit(data, SAVE, {str(k): v for k, v in TABLE.items()}, SHARED, False, (), "sav")
        self.assertEqual(report["renamed"], 0)
        self.assertEqual(report["output"], {"format": "sav", "container": "raw", "extension": ".sav"})
        self.assertEqual(out, self.RAW)
        report, same = browser_edit(data, SAVE, {str(k): v for k, v in TABLE.items()}, SHARED, False)
        self.assertEqual((report["renamed"], same), (0, data))
        with self.assertRaisesRegex(SaveError, "unknown output format 'gsv'"):
            self.convert(self.RAW, "gsv")

    def test_sav_and_srm_dumps_give_the_same_bytes(self):
        srm = fixture("raw.sav")   # RetroArch's .srm of a raw core holds the same bytes
        self.assertEqual(self.convert(srm)[1], self.convert(self.RAW)[1])

    def test_sharkport_checksum(self):
        self.assertEqual(sharkport_checksum(b"\x01\x02"), 5)
        self.assertEqual(sharkport_checksum(b"\xff\x01"), 32767)            # bytes are sign-extended
        self.assertEqual(sharkport_checksum(b"\xff\x01", True), 33023)      # mGBA's reader: header unsigned
        data = fixture("sharkport.sps")
        self.assertEqual(struct.unpack_from("<I", data, len(data) - 4)[0], signed_sum(ROM_HEADER + self.RAW))
        # a complement check of 0x80 or more keeps the rule
        header = ROM_HEADER[:0x12] + b"\x98" + ROM_HEADER[0x13:]
        start = len(data) - 4 - len(ROM_HEADER) - S
        data = data[:start] + header + self.RAW + struct.pack("<I", sharkport_checksum(header + self.RAW, True))
        save = SaveFile(data, LAYOUT)
        self.assertTrue(save.container.extra["header_unsigned"])
        save.raw[0x10] ^= 1
        out = save.to_bytes()
        self.assertEqual(struct.unpack_from("<I", out, len(out) - 4)[0],
                         sharkport_checksum(header + bytes(save.raw), True))


    def test_gsv_coherent_tail_is_preserved_and_checked(self):
        tail = bytes(range(64))
        data = bytearray(gsv(self.RAW + tail))
        data[0x22:0x24] = b"\x12\xab"
        held, flash = unwrap(data, S)
        changed = bytes([flash[0] ^ 1]) + flash[1:]
        result = held.wrap(changed)
        self.assertEqual(result[-len(tail):], tail)
        self.assertEqual(result[:0x20], data[:0x20])
        self.assertEqual(result[0x22:0x430], data[0x22:0x430])
        self.assertEqual(struct.unpack_from("<H", result, 0x20)[0], ccitt_false(changed + tail))
        self.assertNotEqual(ccitt_false(changed), ccitt_false(changed + tail))

    def test_gsv_inconsistent_shapes_only_round_trip_unchanged(self):
        for declared in (0, S - 1, S + 1):
            with self.subTest(declared=declared):
                data = bytearray(gsv(self.RAW))
                struct.pack_into("<I", data, 0x24, declared)
                held, flash = unwrap(data, S)
                self.assertEqual(held.wrap(flash), data)
                with self.assertRaisesRegex(SaveError, "payload size differs"):
                    held.wrap(bytes([flash[0] ^ 1]) + flash[1:])
        held, flash = unwrap(gsv(self.RAW) + b"unproved tail", S)
        self.assertEqual(held.wrap(flash), gsv(self.RAW) + b"unproved tail")
        with self.assertRaisesRegex(SaveError, "payload size differs"):
            held.wrap(bytes([flash[0] ^ 1]) + flash[1:])


    def test_gsv_selected_flash_cannot_change_length(self):
        held, flash = unwrap(gsv(self.RAW), S)
        for changed in (flash[:-1], flash + b"\x00"):
            with self.assertRaisesRegex(SaveError, "payload size differs"):
                held.wrap(changed)

    def test_gsv_noop_does_not_repair_an_existing_crc(self):
        data = bytearray(gsv(self.RAW))
        data[0x20:0x22] = b"\x12\x34"
        held, flash = unwrap(data, S)
        self.assertEqual(held.wrap(flash), data)

    def test_standalone_updates_gsv_and_rejects_inconsistent_shapes(self):
        import subprocess
        import tempfile
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            script = directory / "converter.py"
            script.write_text(standalone_source(dict(SAVE, names=FAKE_NAMES), TABLE, SHARED))
            source, target = directory / "source.gsv", directory / "target.gsv"
            source.write_bytes(gsv(self.RAW))
            for name, contents in (("ru.gba", base.BrowserConvertTest.RU),
                                   ("en.gba", base.BrowserConvertTest.EN)):
                (directory / name).write_bytes(contents)
            command = [sys.executable, "-I", str(script), str(source), str(target),
                       "--from-rom", str(directory / "ru.gba"), "--to-rom", str(directory / "en.gba")]
            result = subprocess.run(command, cwd=temp, capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(target.read_bytes(), gsv(self.convert(self.RAW)[1]))
            target.unlink()
            source.write_bytes(gsv(self.RAW) + b"unproved tail")
            result = subprocess.run(command, cwd=temp, capture_output=True, text=True, timeout=20)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("payload size differs", result.stderr)
            self.assertFalse(target.exists())

    def test_nocash_run_length_code(self):
        code = bytes([0x02, 1, 2, 0x83, 7, 0x80, 9, 0x00, 0x01, 0x01, 5, 0x00])
        self.assertEqual(rle_decode(b"xx" + code + b"tail", 2, 262),
                         (b"\x01\x02" + b"\x07" * 3 + b"\x09" * 256 + b"\x05", 2 + len(code)))
        with self.assertRaisesRegex(SaveError, "damaged"):
            rle_decode(code, 0, 10)                              # the code holds another length
        for data in (b"", b"a", b"aab", b"abc" * 100, bytes(70000), self.RAW):
            encoded = rle_encode(data)
            self.assertEqual(rle_decode(encoded, 0, len(data)), (data, len(encoded)))
        save = SaveFile(fixture("nocash-rle.sav"), LAYOUT)
        self.assertEqual(save.container.extra["stored"], len(self.RAW.rstrip(b"\xff")))
        save.raw[-1] = 0                                          # a write past the stored bytes stores them all
        stored = rle_decode(save.to_bytes(), 0x50, S)[0]
        self.assertEqual(len(stored), S)

    def test_retroarch_compression(self):
        data = fixture("rzip.srm")
        self.assertEqual(data[:8], b"#RZIPv\x01#")
        self.assertEqual(struct.unpack_from("<IQI", data, 8)[:2], (0x20000, S))
        self.assertEqual(data[24:26], b"\x78\x9c")                       # zlib at level 6
        # the inner container reads as uncompressed, in chunks
        inner = self.RAW + b"\xff" * 0x2000
        data = rzip(inner, 0x8000)
        save = SaveFile(data, LAYOUT)
        self.assertEqual((save.container.kind, save.container.extra["inner"].kind), ("rzip", "libretro"))
        self.assertEqual((bytes(save.raw), save.to_bytes()), (self.RAW, data))
        _report, out = self.convert(data)
        self.assertEqual(out, rzip(self.convert(inner)[1], 0x8000))   # chunk size kept
        for damaged in (data[:-1], data[:20] + b"\x00" * 4 + data[24:], b"#RZIPv\x01#" + struct.pack("<IQ", 0, S) + data[20:],
                        data[:12] + struct.pack("<Q", len(inner) + 1) + data[20:], data + b"\x00"):
            with self.assertRaisesRegex(SaveError, "the RetroArch compressed save is damaged"):
                unwrap(damaged, S)
        with self.assertRaisesRegex(SaveError, "holds 3145728 bytes in no save format"):
            unwrap(data[:12] + struct.pack("<Q", 3 << 20) + data[20:], S)
        with self.assertRaisesRegex(SaveError, "the file holds 65536 bytes"):
            unwrap(rzip(self.RAW[:0x10000]), S)

    def test_an_unknown_file_names_the_accepted_formats(self):
        for data in (bytes(S // 2), b"\x11" * (S + 3), b"\x11" * (S + 0x100)):
            with self.subTest(size=len(data)):
                with self.assertRaises(SaveError) as caught:
                    SaveFile(data, LAYOUT)
                message = str(caught.exception)
                self.assertIn(f"{len(data)} bytes", message)
                self.assertTrue(message.endswith(accepted(S)))
        for part in ("131072 bytes (raw .sav, .srm, .fla)", "131088 from mGBA", "131584 bytes (MiSTer)",
                     "131076 bytes (meteor .srm)", "139264 bytes (VBA Next, Beetle GBA .srm)", "padding of 00 or FF",
                     ".sps and .xps", "GameShark SP .gsv", "NO$GBA .sav", "BizHawk 1.x .SaveRAM",
                     "RetroArch compressed .srm"):
            self.assertIn(part, accepted(S))

    def test_refused_containers_say_what_to_do(self):
        lz = bytearray(fixture("nocash.sav"))
        struct.pack_into("<I", lz, 0x44, 2)
        cases = {bytes(lz): "Uncompressed or Raw", sharkport(self.RAW[:0x10000]): "65536 bytes of save data",
                 gsv(self.RAW[:0x10000]): "65536 bytes"}
        for data, words in cases.items():
            with self.assertRaisesRegex(SaveError, words):
                unwrap(data, S)

    def test_the_container_reaches_the_command_line(self):
        import contextlib
        import io
        import tempfile

        from gen3tl.verify.savefile import main
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "in.gsv").write_bytes(fixture("gameshark-sp.gsv"))
            (d / "ru.gba").write_bytes(base.BrowserConvertTest.RU)
            (d / "en.gba").write_bytes(base.BrowserConvertTest.EN)
            out = io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
                rc = main([str(d / "in.gsv"), str(d / "out.gsv"), "--from-rom", str(d / "ru.gba"), "--to-rom",
                           str(d / "en.gba")], layout=dict(SAVE, names=FAKE_NAMES), charmap=TABLE,
                          charmap_target=SHARED, interactive=False)
            self.assertEqual(rc, 0)
            self.assertIn("container    GameShark SP file", out.getvalue().splitlines())
            self.assertEqual((d / "out.gsv").read_bytes(), gsv(self.convert(self.RAW)[1]))
