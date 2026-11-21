import unittest

from gen3tl.cli import data as cli
from gen3tl.data import pokedexsources as ps

from rom_support import needs_rom, rom_path

@needs_rom
class UnboundSourceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profile = cli.Profile.by_name("unbound-2.1.1.1")
        rom = cls.profile.load_rom(rom_path())
        pokedex = cls.profile["pokedex"]
        cls.rows = ps.build(pokedex["sources"], rom.data, cls.profile,
                            pokedex["species"]["count"], pokedex["items"]["count"])

    def test_bulbasaur_has_day_care_eggs(self):
        rows = [row for row in self.rows if row["kind"] == "egg" and row["species"] == 1]
        self.assertEqual({row["offset"] for row in rows}, {"0x1E7B3A6", "0x1E7B41F", "0x1E7B48C"})
        self.assertTrue(all(row["map_section"] == 0x9B for row in rows))

    def test_hitmontop_name_comes_from_the_live_table_without_npc_inference(self):
        trade = next(row for row in self.rows if row["species"] == 237 and row["kind"] == "trade")
        self.assertEqual(trade["wanted"], 108)
        self.assertEqual(trade["original_trainer"], "s1F81E2A")
        self.assertEqual(trade["original_trainer_offset"], "0x1FB70C4")
        self.assertEqual(trade["offset"], "0x1FB70C4")
        self.assertNotIn("speaker", trade)
        self.assertNotIn("partner", trade)
        self.assertEqual(sum("original_trainer" in row for row in self.rows), 39)

    def test_battleground_is_an_alternative_context_for_the_same_trade(self):
        rows = [row for row in self.rows if row.get("trade_index") == 1]
        self.assertEqual(len(rows), 2)
        self.assertEqual({row["map"] for row in rows}, {"49.3", "33.6"})
        self.assertEqual({(row["species"], row["wanted"], row["offset"]) for row in rows},
                         {(101, 95, "0x1FB709C")})
        alternative = next(row for row in rows if row["map"] == "33.6")
        self.assertEqual((alternative["map_section"], alternative["script"], alternative["availability"]),
                         (187, "0x1E53171", "alternate_trade"))
        self.assertEqual(len({row["original_trainer"] for row in rows}), 1)

    def test_visiting_trade_speakers_come_from_their_name_boxes(self):
        trades = [row for row in self.rows if row["kind"] == "trade"]
        self.assertEqual(sum("speaker" in row for row in trades), 24)
        for row in trades:
            if 15 <= row["trade_index"] <= 38:
                self.assertIn("speaker", row)
            else:
                self.assertNotIn("speaker", row)
        expected = {15: "s1F15C64", 18: "s1F164B9", 21: "s1F16D88", 24: "s1F17512",
                    27: "s1F17ADA", 30: "s1F18108", 33: "s1F187A9", 36: "s1F18D94"}
        for first, speaker in expected.items():
            self.assertEqual({row["speaker"] for row in trades
                              if first <= row["trade_index"] < first + 3}, {speaker})
        benjamin = next(row for row in trades if row["trade_index"] == 36)
        self.assertEqual((benjamin["speaker"], benjamin["original_trainer"]), ("s1F18D94", "s1F18D9D"))

    def test_starters_and_a_trade(self):
        starters = [row for row in self.rows if row["kind"] == "starter"]
        self.assertEqual([row["species"] for row in starters], [548, 551, 554])
        self.assertTrue(all(row["level"] == 15 and row["item"] == 0 for row in starters))
        first = next(row for row in self.rows if row["kind"] == "trade")
        self.assertEqual((first["species"], first["wanted"], first["offset"]), (633, 1023, "0x1FB7074"))
        self.assertEqual(first["script"], "0x1E68859")
        self.assertEqual(first["map"], "7.7")
        trades = [r for r in self.rows if r["kind"] == "trade"]
        self.assertEqual({r["trade_index"] for r in trades}, set(range(39)) - {14})
        self.assertEqual(sum(r.get("availability") == "visiting_trader" for r in trades), 31)
        self.assertFalse(any(r["species"] in (86, 114) for r in trades))
