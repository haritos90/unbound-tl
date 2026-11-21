import re
import unittest

from gen3tl.core.charmap import Charmap, CharmapError
from gen3tl.core.rom import Rom

from rom_support import needs_rom, rom_path


BASE_CHARMAP = Charmap()


@needs_rom
class RomRoundtripTest(unittest.TestCase):
    def test_all_pointer_referenced_strings_roundtrip(self):
        rom = Rom.load(rom_path())
        cm = BASE_CHARMAP
        d = rom.data
        seen = set()
        count = 0
        for m in re.finditer(rb"[\x08\x09]", d):
            q = m.start() - 3
            if q < 0:
                continue
            t = rom.ptr_at(q)
            if t is None or t in seen:
                continue
            seen.add(t)
            for mode in ("field", "battle"):
                try:
                    text, end = cm.decode(d, t, mode=mode, limit=2000)
                except CharmapError:
                    break
                self.assertEqual(cm.encode(text), bytes(d[t:end]), hex(t))
                count += 1
        self.assertGreater(count, 10000)
