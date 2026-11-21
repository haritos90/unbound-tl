import unittest

from gen3tl.core.charmap import Charmap
from gen3tl.discover.context import build_context, inline_speakers
from gen3tl.discover.maps import Walker
from gen3tl.core.rom import Rom, ptr_bytes

from rom_support import needs_rom
from project_fixture import UNBOUND

CM = Charmap()


class FakeProfile(dict):
    def __init__(self, groups, names, trainers):
        super().__init__({
            "maps": {"groups": groups, "mapsec_names": names, "mapsec_first": 0x58, "mapsec_count": 1},
            "table": [{"name": "trainer_names", "base": trainers, "stride": 40, "count": 2,
                       "field_offset": 4, "field_length": 12, "gender_offset": 2, "class_offset": 1}],
        })


@needs_rom
class WalkerTest(unittest.TestCase):
    def test_npc_text_colour_and_trainer(self):
        d = bytearray(b"\xff" * 0x3000)

        def put(off, blob):
            d[off:off + len(blob)] = blob

        text1, text2, text3, name = 0x2000, 0x2100, 0x2200, 0x2300
        put(text1, CM.encode("Hi!"))
        put(text2, CM.encode("Example battle."))
        put(text3, CM.encode("Example result."))
        put(name, CM.encode("Bellin Town"))
        put(0x2400, ptr_bytes(name))                          # map section names
        trainers = 0x2500
        put(trainers + 40, bytes([0, 7, 0x80, 0]) + CM.encode("Heidi").ljust(12, b"\xff"))
        # script: textcolor, msgbox, trainerbattle, end
        script = 0x1000
        put(script, b"\xc7\x01" + b"\x0f\x00" + ptr_bytes(text1) + b"\x09\x06"
            + b"\x5c\x00\x01\x00\x00\x00" + ptr_bytes(text2) + ptr_bytes(text3) + b"\x02")
        layout, events, objs, header, bank, groups = 0x600, 0x700, 0x800, 0x900, 0xA00, 0xB00
        put(layout, (10).to_bytes(4, "little") + (10).to_bytes(4, "little") + ptr_bytes(0x10) * 4)
        obj = bytearray(24)
        obj[0], obj[1] = 1, 40
        obj[16:20] = ptr_bytes(script)
        put(objs, bytes(obj))
        put(events, bytes([1, 0, 0, 0]) + ptr_bytes(objs) + b"\x00" * 12)
        hdr = bytearray(28)
        hdr[0:4], hdr[4:8], hdr[8:12] = ptr_bytes(layout), ptr_bytes(events), ptr_bytes(0x2FF0)
        hdr[20] = 0x58
        put(header, bytes(hdr))
        put(0x2FF0, b"\x00")                                 # empty map script list
        put(bank, ptr_bytes(header))
        put(groups, ptr_bytes(bank))
        w = Walker(Rom(d), FakeProfile(groups, 0x2400, trainers))
        ctx = w.walk_all()
        u1 = ctx.uses[text1][0]
        self.assertEqual((u1.map_name, u1.event, u1.sprite, u1.textcolor, u1.box),
                         ("Bellin Town", "npc", 40, 1, "autoclose"))
        u2 = ctx.uses[text2][0]
        self.assertEqual(u2.trainer["name"], "Heidi")
        self.assertEqual(u2.trainer["gender"], "female")
        self.assertIn(text3, ctx.uses)
        self.assertEqual((u2.trainer_role, u2.at), ("intro", script + 16))
        self.assertEqual(ctx.uses[text3][0].trainer_role, "defeat")

    def test_trainer_roles_and_continuations(self):
        from gen3tl.profile.profile import Profile

        prof = Profile.by_name("unbound-2.1.1.1")
        expected = {
            0: ("intro", "defeat"), 1: ("intro", "defeat"), 2: ("intro", "defeat"),
            3: ("defeat",), 4: ("intro", "defeat", "cannot-battle"), 5: ("intro", "defeat"),
            6: ("intro", "defeat", "cannot-battle"), 7: ("intro", "defeat", "cannot-battle"),
            8: ("intro", "defeat", "cannot-battle"), 9: ("defeat", "victory"),
            10: ("defeat", "defeat"),
            11: ("intro", "intro", "defeat", "defeat", "cannot-battle", "cannot-battle"),
            12: ("defeat",), 13: ("intro", "defeat"), 14: ("intro", "defeat", "cannot-battle"),
            15: ("defeat",),
            16: ("intro", "intro", "defeat", "defeat", "cannot-battle", "cannot-battle"),
        }
        for typ, roles in expected.items():
            with self.subTest(typ=typ):
                d = bytearray(b"\xff" * 0x1000)
                w = Walker(Rom(d), {"script": prof["script"]})
                d = w.d
                d[0x100:0x106] = bytes([0x5C, typ, 1, 0, 0, 0])
                for i, off in enumerate(w.tb[typ]):
                    d[0x100 + off:0x104 + off] = ptr_bytes(0x800 + i * 32)
                end = 0x104 + max(w.tb[typ])
                if typ in (1, 2, 6, 8):
                    d[end:end + 4] = ptr_bytes(0x200)
                    d[0x200:0x206] = b"\x67" + ptr_bytes(0xF00) + b"\x03"
                    end += 4
                d[end:end + 6] = b"\x67" + ptr_bytes(0xF20) + b"\x02"
                w.walk_script(0x100, "0.0", "Test", "npc", 1, 1)
                self.assertEqual(tuple(w.ctx.uses[0x800 + i * 32][0].trainer_role
                                       for i in range(len(roles))), roles)
                self.assertEqual(w.ctx.uses[0xF20][0].trainer_role, "after-battle")
                if typ in (1, 2, 6, 8):
                    self.assertEqual(w.ctx.uses[0xF00][0].trainer_role, "after-battle")

    def test_changed_trainer_formats_require_explicit_roles(self):
        prof = {"script": {"trainerbattle_text_offsets": {"0": [8, 12], "20": [6]}}}
        w = Walker(Rom(bytes(256)), prof)
        self.assertNotIn(0, w.tb_roles)
        self.assertNotIn(20, w.tb_roles)
        prof["script"]["trainerbattle_text_roles"] = {"20": ["intro", "defeat"]}
        with self.assertRaisesRegex(ValueError, "invalid trainerbattle text roles"):
            Walker(Rom(bytes(256)), prof)

    def test_post_battle_phase_returns_only_from_unconditional_calls(self):
        for op in (0x04, 0x06, 0x07):
            with self.subTest(op=op):
                d = bytearray(b"\xff" * 0x1000)
                call = bytes([op]) + (b"\x01" if op != 0x04 else b"") + ptr_bytes(0x200)
                script = call + b"\x67" + ptr_bytes(0x400) + b"\x02"
                d[0x100:0x100 + len(script)] = script
                d[0x200:0x20B] = b"\x5c\x03\x01\x00\x00\x00" + ptr_bytes(0x500) + b"\x03"
                w = Walker(Rom(d), {})
                w.walk_script(0x100, "0.0", "Test", "npc", 1, 1)
                self.assertEqual(w.ctx.uses[0x500][0].trainer_role, "defeat")
                self.assertEqual(w.ctx.uses[0x400][0].trainer_role,
                                 "after-battle" if op == 0x04 else None)

    def test_buffer_fills_follow_the_paths_of_the_script(self):
        # each buffer command's fill reaches the texts on its path
        d = bytearray(b"\xff" * 0x3000)

        def put(off, blob):
            d[off:off + len(blob)] = blob

        text1, text2, word_a, word_b, name = 0x2000, 0x2100, 0x2200, 0x2300, 0x2400
        put(text1, CM.encode("{STR_VAR_1} got {STR_VAR_2} x{STR_VAR_3}."))
        put(text2, CM.encode("{STR_VAR_1}: {STR_VAR_3}!"))
        put(word_a, CM.encode("Ace"))
        put(word_b, CM.encode("Bee"))
        put(name, CM.encode("Bellin Town"))
        put(0x2480, ptr_bytes(name))
        script, sub, branch = 0x1000, 0x1100, 0x1200
        # bufferstring, setvar, bufferitemname, call SUB.
        # goto_if BR; message TEXT1; end.
        put(script, b"\x85\x00" + ptr_bytes(word_a) + b"\x16\x04\x80\x0c\x00" + b"\x80\x01\x04\x80"
            + b"\x04" + ptr_bytes(sub) + b"\x06\x01" + ptr_bytes(branch) + b"\x67" + ptr_bytes(text1) + b"\x02")
        put(sub, b"\x83\x02\x01\x40" + b"\x03")    # SUB: buffernumberstring 2 0x4001; return
        # BR: bufferstring, call SUB (walked), message TEXT2
        put(branch, b"\x85\x00" + ptr_bytes(word_b) + b"\x04" + ptr_bytes(sub) + b"\x67" + ptr_bytes(text2) + b"\x02")
        layout, events, objs, header, bank, groups = 0x600, 0x700, 0x800, 0x900, 0xA00, 0xB00
        put(layout, (10).to_bytes(4, "little") + (10).to_bytes(4, "little") + ptr_bytes(0x10) * 4)
        obj = bytearray(24)
        obj[0], obj[1] = 1, 40
        obj[16:20] = ptr_bytes(script)
        put(objs, bytes(obj))
        put(events, bytes([1, 0, 0, 0]) + ptr_bytes(objs) + b"\x00" * 12)
        hdr = bytearray(28)
        hdr[0:4], hdr[4:8], hdr[8:12] = ptr_bytes(layout), ptr_bytes(events), ptr_bytes(0x2FF0)
        hdr[20] = 0x58
        put(header, bytes(hdr))
        put(0x2FF0, b"\x00")
        put(bank, ptr_bytes(header))
        put(groups, ptr_bytes(bank))

        def pointer(off, text, *refs):
            return {"id": f"s{off:07X}", "offset": off, "kind": "pointer", "text": text,
                    "refs": [{"at": at, "kind": kind} for at, kind in refs]}
        inv = {"entries": [
            pointer(text1, "{STR_VAR_1} got {STR_VAR_2} x{STR_VAR_3}.", (script + 27, "script:message")),
            pointer(text2, "{STR_VAR_1}: {STR_VAR_3}!", (branch + 12, "script:message"), (0x2F00, "table")),
            pointer(word_a, "Ace", (script + 2, "script:bufferstring")),
            pointer(word_b, "Bee", (branch + 2, "script:bufferstring"))]}
        ctx = build_context(Rom(d), FakeProfile(groups, 0x2480, 0x2500), inv)["strings"]
        t1, t2 = ctx[f"s{text1:07X}"], ctx[f"s{text2:07X}"]
        self.assertEqual(t1["slots"], {
            "{STR_VAR_1}": {"fills": [["string", f"s{word_a:07X}"]], "uses": 1, "unfilled": 0},   # not B: a branch
            "{STR_VAR_2}": {"fills": [["item", 12]], "uses": 1, "unfilled": 0},                    # the setvar value
            "{STR_VAR_3}": {"fills": [["number", None]], "uses": 1, "unfilled": 0}})               # any variable value
        self.assertEqual(t2["slots"], {
            "{STR_VAR_1}": {"fills": [["string", f"s{word_b:07X}"]], "uses": 1, "unfilled": 0},
            "{STR_VAR_3}": {"fills": [["number", None]], "uses": 1, "unfilled": 0}})   # SUB walked before
        self.assertEqual(t1["slot_refs"], {"unwalked": 0, "code": 0})
        self.assertEqual(t2["slot_refs"], {"unwalked": 0, "code": 1})
        self.assertEqual(ctx[f"s{word_a:07X}"]["fills"], [[f"s{text1:07X}", "{STR_VAR_1}"]])
        self.assertEqual(ctx[f"s{word_b:07X}"]["fills"], [[f"s{text2:07X}", "{STR_VAR_1}"]])

    def npc_context(self, d, script, texts, words):
        """Context of one NPC running `script`; texts and words: {offset: (text, ref at)}."""
        def put(off, blob):
            d[off:off + len(blob)] = blob
        put(0x2400, CM.encode("Bellin Town"))
        put(0x2480, ptr_bytes(0x2400))
        layout, events, objs, header, bank, groups = 0x600, 0x700, 0x800, 0x900, 0xA00, 0xB00
        put(layout, (10).to_bytes(4, "little") + (10).to_bytes(4, "little") + ptr_bytes(0x10) * 4)
        obj = bytearray(24)
        obj[0], obj[1] = 1, 40
        obj[16:20] = ptr_bytes(script)
        put(objs, bytes(obj))
        put(events, bytes([1, 0, 0, 0]) + ptr_bytes(objs) + b"\x00" * 12)
        hdr = bytearray(28)
        hdr[0:4], hdr[4:8], hdr[8:12] = ptr_bytes(layout), ptr_bytes(events), ptr_bytes(0x2FF0)
        hdr[20] = 0x58
        put(header, bytes(hdr))
        put(0x2FF0, b"\x00")
        put(bank, ptr_bytes(header))
        put(groups, ptr_bytes(bank))
        entries = []
        for table, kind in ((texts, "script:message"), (words, "script:bufferstring")):
            for off, (text, at) in table.items():
                put(off, CM.encode(text))
                entries.append({"id": f"s{off:07X}", "offset": off, "kind": "pointer", "text": text,
                                "refs": [{"at": at, "kind": kind}]})
        return build_context(Rom(d), FakeProfile(groups, 0x2480, 0x2500), {"entries": entries})["strings"]

    def test_values_reach_texts_along_the_code_after_a_join(self):
        # a path joining walked code follows that code
        d = bytearray(b"\xff" * 0x3000)
        script, fill, menu, text, old, new = 0x1000, 0x1100, 0x1200, 0x2000, 0x2200, 0x2300
        # SCRIPT: goto_if FILL; bufferstring; goto MENU
        d[script:script + 17] = b"\x06\x01" + ptr_bytes(fill) + b"\x85\x00" + ptr_bytes(old) + b"\x05" + ptr_bytes(menu)
        # FILL: bufferstring; goto_if MENU; message TEXT; end
        d[fill:fill + 18] = (b"\x85\x00" + ptr_bytes(new) + b"\x06\x01" + ptr_bytes(menu)
                             + b"\x67" + ptr_bytes(text) + b"\x02")
        d[menu:menu + 5] = b"\x05" + ptr_bytes(fill)   # MENU: goto FILL
        ctx = self.npc_context(d, script, {text: ("Set to {STR_VAR_1}.", fill + 13)},
                               {old: ("Old", script + 8), new: ("New", fill + 2)})
        # the first path reaches TEXT only through the fill
        self.assertEqual(ctx[f"s{text:07X}"]["slots"]["{STR_VAR_1}"]["fills"], [["string", f"s{new:07X}"]])

    def test_a_result_pair_of_call_ifs_always_fills(self):
        # two call_ifs on one compare run one of them
        d = bytearray(b"\xff" * 0x3000)
        script, sub, a, b, text, boy, man, lady = 0x1000, 0x1100, 0x1200, 0x1300, 0x2000, 0x2200, 0x2300, 0x2380
        # SCRIPT: bufferstring 0 BOY; call SUB; message TEXT; end
        d[script:script + 17] = (b"\x85\x00" + ptr_bytes(boy) + b"\x04" + ptr_bytes(sub)
                                 + b"\x67" + ptr_bytes(text) + b"\x02")
        # SUB: two compares, two call_ifs, return
        d[sub:sub + 23] = (b"\x21\x0d\x80\x00\x00\x07\x01" + ptr_bytes(a)
                           + b"\x21\x0d\x80\x01\x00\x07\x01" + ptr_bytes(b) + b"\x03")
        d[a:a + 7] = b"\x85\x00" + ptr_bytes(man) + b"\x03"
        d[b:b + 7] = b"\x85\x00" + ptr_bytes(lady) + b"\x03"
        ctx = self.npc_context(d, script, {text: ("Example {STR_VAR_1}.", script + 12)},
                               {boy: ("boy", script + 2), man: ("man", a + 2), lady: ("lady", b + 2)})
        slot = ctx[f"s{text:07X}"]["slots"]["{STR_VAR_1}"]
        self.assertEqual(slot, {"fills": [["string", f"s{man:07X}"], ["string", f"s{lady:07X}"]],
                                "uses": 1, "unfilled": 0})

    def test_bufferitemnameplural_is_six_bytes(self):
        # the walk continues after bufferitemnameplural.
        # five bytes would read 0x40 as an opcode.
        d = bytearray(b"\xff" * 0x3000)

        def put(off, blob):
            d[off:off + len(blob)] = blob

        text = 0x2000
        put(text, CM.encode("{STR_VAR_2} for you."))
        put(0x2480, ptr_bytes(0x2400))
        put(0x2400, CM.encode("Bellin Town"))
        script = 0x1000
        # bufferitemnameplural 1 item 12 quantity 0x4000; message TEXT; end
        put(script, b"\xd4\x01\x0c\x00\x00\x40" + b"\x67" + ptr_bytes(text) + b"\x02")
        layout, events, objs, header, bank, groups = 0x600, 0x700, 0x800, 0x900, 0xA00, 0xB00
        put(layout, (10).to_bytes(4, "little") + (10).to_bytes(4, "little") + ptr_bytes(0x10) * 4)
        obj = bytearray(24)
        obj[0], obj[1] = 1, 40
        obj[16:20] = ptr_bytes(script)
        put(objs, bytes(obj))
        put(events, bytes([1, 0, 0, 0]) + ptr_bytes(objs) + b"\x00" * 12)
        hdr = bytearray(28)
        hdr[0:4], hdr[4:8], hdr[8:12] = ptr_bytes(layout), ptr_bytes(events), ptr_bytes(0x2FF0)
        hdr[20] = 0x58
        put(header, bytes(hdr))
        put(0x2FF0, b"\x00")
        put(bank, ptr_bytes(header))
        put(groups, ptr_bytes(bank))
        inv = {"entries": [{"id": f"s{text:07X}", "offset": text, "kind": "pointer", "text": "{STR_VAR_2} for you.",
                            "refs": [{"at": script + 7, "kind": "script:message"}]}]}
        ctx = build_context(Rom(d), FakeProfile(groups, 0x2480, 0x2500), inv)["strings"]
        t = ctx[f"s{text:07X}"]
        self.assertTrue(t["uses"])
        self.assertEqual(t["slots"]["{STR_VAR_2}"]["fills"], [["item", 12]])

    @staticmethod
    def map_image(maps, scripts=True):
        """An image with one map per entry of `maps`."""
        d = bytearray(b"\xff" * 0x3000)

        def put(off, blob):
            d[off:off + len(blob)] = blob

        put(0x2480, ptr_bytes(0x2400))
        put(0x2400, CM.encode("Bellin Town"))
        put(0x2FF0, b"\x00")
        layout = 0x600
        put(layout, (10).to_bytes(4, "little") + (10).to_bytes(4, "little") + ptr_bytes(0x10) * 4)
        for i, (header, text) in enumerate(maps):
            script, events, objs = 0x1000 + 0x40 * i, 0x700 + 0x20 * i, 0x800 + 0x20 * i
            put(text, CM.encode(f"Hi {i}!"))
            put(script, b"\x0f\x00" + ptr_bytes(text) + b"\x09\x06\x02")
            obj = bytearray(24)
            obj[0], obj[1] = 1, 40
            obj[16:20] = ptr_bytes(script)
            put(objs, bytes(obj))
            put(events, bytes([1, 0, 0, 0]) + ptr_bytes(objs) + b"\x00" * 12)
            hdr = bytearray(28)
            hdr[0:4], hdr[4:8] = ptr_bytes(layout), ptr_bytes(events)
            if scripts:
                hdr[8:12] = ptr_bytes(0x2FF0)
            hdr[20] = 0x58
            put(header, bytes(hdr))
        return d, put

    def test_header_without_map_script_list(self):
        # a header with a null map script list is walked.
        # as in the base ROM at 0x3511E8.
        d, put = self.map_image([(0x900, 0x2000)], scripts=False)
        w = Walker(Rom(d), FakeProfile(0x2F00, 0x2480, 0x2500))   # an empty bank table
        w.walk_all()
        self.assertEqual(w.find_headers(), [0x900])
        ctx = w.walk_structural()
        self.assertEqual([(u.map, u.event) for u in ctx.uses[0x2000]], [("h0000900", "npc")])

    def test_bank_list_ends_at_the_bank_table(self):
        # the bank list before the table holds one header.
        # reading on takes bank pointers for headers.
        d, put = self.map_image([(0x900, 0x2000), (0x940, 0x2040), (0x980, 0x20C0)])
        bank0, groups, bank1 = 0xA00, 0xA04, 0xB00
        put(bank0, ptr_bytes(0x900))
        put(groups, ptr_bytes(bank0) + ptr_bytes(bank1))
        put(bank1, ptr_bytes(0x940) + ptr_bytes(0x980))
        w = Walker(Rom(d), FakeProfile(groups, 0x2480, 0x2500))
        ctx = w.walk_all()
        self.assertEqual((ctx.maps, w.walked), (3, {0x900, 0x940, 0x980}))
        self.assertEqual([u.map for t in (0x2000, 0x2040, 0x20C0) for u in ctx.uses[t]], ["0.0", "1.0", "1.1"])

    def test_inline_speakers(self):
        sp = inline_speakers("{COLOR 02}Alice: {COLOR 04}Example.\\pBob: {COLOR 08}Reply.", {"04": "female", "08": "male"})
        self.assertEqual([(s["name"], s["gender"]) for s in sp], [("Alice", "female"), ("Bob", "male")])

    def test_leading_colour_sets_the_speaker(self):
        # the text's own colour wins
        from gen3tl.discover.context import leading_gender
        colours = {"04": "female", "08": "male", "06": "neutral"}
        for text, gender in (("{COLOR 04}Example speaker text.", "female"), ("{COLOR 08}Example reply.", "male"),
                             ("{COLOR 04}Example…{PAUSE 18} pause…?", "female"),
                             ("{COLOR 08} XX.", None),                       # a fragment
                             ("{COLOR 04}Ah{COLOR 08} said Bob.", None),     # a coloured word
                             ("{COLOR 06}Hoopa{COLOR 08} is here.", None),   # a highlight
                             ("{COLOR 02}Ivory: {COLOR 04}Zeph!", None),     # a speaker label
                             ("Hello {COLOR 04}there.", None)):
            with self.subTest(text=text):
                self.assertEqual(leading_gender(text, colours), gender)
        # textcolor 0 is set once, two lines before
        d = bytearray(b"\xff" * 0x3000)

        def put(off, blob):
            d[off:off + len(blob)] = blob

        red, plain, name = 0x2000, 0x2100, 0x2300
        put(red, CM.encode("{COLOR 04}Example speaker text."))
        put(plain, CM.encode("Hi there!"))
        put(name, CM.encode("Frozen Heights"))
        put(0x2400, ptr_bytes(name))
        script = 0x1000
        put(script, b"\xc7\x00" + b"\x0f\x00" + ptr_bytes(red) + b"\x09\x06"
            + b"\x0f\x00" + ptr_bytes(plain) + b"\x09\x06" + b"\x02")
        layout, events, objs, header, bank, groups = 0x600, 0x700, 0x800, 0x900, 0xA00, 0xB00
        put(layout, (10).to_bytes(4, "little") + (10).to_bytes(4, "little") + ptr_bytes(0x10) * 4)
        obj = bytearray(24)
        obj[0], obj[1] = 1, 40
        obj[16:20] = ptr_bytes(script)
        put(objs, bytes(obj))
        put(events, bytes([1, 0, 0, 0]) + ptr_bytes(objs) + b"\x00" * 12)
        hdr = bytearray(28)
        hdr[0:4], hdr[4:8], hdr[8:12] = ptr_bytes(layout), ptr_bytes(events), ptr_bytes(0x2FF0)
        hdr[20] = 0x58
        put(header, bytes(hdr))
        put(0x2FF0, b"\x00")
        put(bank, ptr_bytes(header))
        put(groups, ptr_bytes(bank))
        prof = FakeProfile(groups, 0x2400, 0x2500)
        prof["context"] = {"speaker_colours": colours, "textcolor_genders": {"0": "male", "1": "female"}}
        inv = {"entries": [
            {"id": f"s{off:07X}", "offset": off, "kind": "pointer", "text": text,
             "refs": [{"at": at, "kind": "script:message"}]}
            for off, text, at in ((red, "{COLOR 04}Example speaker text.", script + 4),
                                  (plain, "Hi there!", script + 12))]}
        ctx = build_context(Rom(d), prof, inv)["strings"]
        self.assertEqual([u["textcolor"] for u in ctx[f"s{red:07X}"]["uses"]], [0])
        self.assertEqual([u["textcolor_gender"] for u in ctx[f"s{red:07X}"]["uses"]], ["female"])
        self.assertEqual([u["textcolor_gender"] for u in ctx[f"s{plain:07X}"]["uses"]], ["male"])
        sources = ctx[f"s{red:07X}"]["identity"]["speaker"]["sources"]
        self.assertEqual([(s["gender"], s["value"]) for s in sources if s["source"] == "text colour"],
                         [("female", "04")])

    def test_frozen_heights_scene_speaks_in_its_own_colour(self):
        # the catalog hint of the scene
        from gen3tl.catalog.catalog import load_catalog
        catalog = load_catalog(UNBOUND / "translation/ru/po")
        hint = lambda sid: {line for line in catalog[sid][1].extracted if "speaker colour" in line}   # noqa: E731
        for sid in ("s1F2F9D7", "s1F2FAC9"):
            with self.subTest(sid=sid):
                self.assertTrue(hint(sid) and all("speaker colour female" in line for line in hint(sid)))

    def test_engine_coordinates_keep_context_ids_and_aliases(self):
        d, put = self.map_image([(0x900, 0x2000), (0x940, 0x2040), (0x980, 0x20C0)])
        put(0xA00, ptr_bytes(0x900) + ptr_bytes(0x940))
        put(0xA08, ptr_bytes(0xA00))
        put(0xB00, ptr_bytes(0x940))
        put(0xB08, ptr_bytes(0x900))
        put(0xB10, ptr_bytes(0x900))
        mask = 0x12345678
        for i, bank in enumerate((0xB00, 0xB08, 0xB10, 0xA00)):
            put(0xC00 + 4 * i, ((0x08000000 + bank) ^ mask).to_bytes(4, "little"))
        prof = FakeProfile(0xA08, 0x2480, 0x2500)
        prof["maps"]["engine"] = {"groups": 0xC00, "count": 3, "bank_xor": mask}
        inv = {"entries": [{"id": f"s{at:07X}", "offset": at, "kind": "pointer",
                            "text": f"Hi {i}!", "refs": []}
                           for i, at in enumerate((0x2000, 0x2040, 0x20C0))]}
        put(0xB0C, b"\xf7" * 4)
        ctx = build_context(Rom(d), prof, inv)
        self.assertEqual(ctx["maps"]["0.0"]["engine_maps"], ["1.0", "2.0"])
        self.assertEqual(ctx["maps"]["0.1"]["engine_maps"], ["0.0"])
        self.assertEqual(ctx["maps"]["h0000980"]["engine_maps"], [])
        for sid, mid in (("s0002000", "0.0"), ("s0002040", "0.1"), ("s00020C0", "h0000980")):
            use = ctx["strings"][sid]["uses"][0]
            self.assertEqual(use["map"], mid)
            self.assertEqual(use["engine_maps"], ctx["maps"][mid]["engine_maps"])

        del prof["maps"]["engine"]
        unverified = build_context(Rom(d), prof, inv)
        self.assertTrue(all(m["engine_maps"] is None for m in unverified["maps"].values()))

    def test_runtime_map_banks_require_valid_bounds(self):
        d, put = self.map_image([(0x900, 0x2000)])
        prof = FakeProfile(0xA00, 0x2480, 0x2500)
        prof["maps"]["engine"] = {"groups": len(d) - 2, "count": 1}
        with self.assertRaisesRegex(ValueError, "table exceeds ROM"):
            Walker(Rom(d), prof).engine_map_ids()
        prof["maps"]["engine"]["groups"] = 0xA00
        with self.assertRaisesRegex(ValueError, "invalid runtime map bank"):
            Walker(Rom(d), prof).engine_map_ids()
