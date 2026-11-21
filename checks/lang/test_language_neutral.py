import unittest

from gen3tl.lang import language
from gen3tl.profile.profile import Profile
from gen3tl.verify.savefile import transliterate

from project_fixture import select_language

def setUpModule():
    select_language("ru")

class NeutralCoreTest(unittest.TestCase):

    def test_save_and_filler_rules_follow_each_seeded_pack(self):
        from gen3tl.cli.common import _save_layout_and_charmap
        from gen3tl.verify.savefile import Charset
        from gen3tl.cli.build import pseudo_localize
        for code, name in (("es", "Ñandú"), ("de", "Bär"), ("fr", "Élodie")):
            with self.subTest(code=code), language.use(code):
                _, table, shared = _save_layout_and_charmap(Profile.by_name("unbound-2.1.1.1"), code)
                charset = Charset(table, shared)
                encoded = charset.encode(name, True)
                self.assertEqual(encoded, charset.encode(name, False))
                self.assertIsNone(charset.transliterate(encoded))
                self.assertEqual(transliterate(name), name)
                self.assertNotRegex(pseudo_localize("Welcome", 0.5), "[А-Яа-яЁё]")
        with language.use("ru"):
            self.assertEqual(transliterate("Ёжик Щука"), "Yozhik Schuka")
            self.assertEqual(transliterate("ЖЕНЯ"), "ZHENYA")
