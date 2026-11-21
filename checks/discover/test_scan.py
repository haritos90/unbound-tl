import unittest

from gen3tl.profile.profile import Profile

class IncludedLabelsTest(unittest.TestCase):

    def test_profile_includes_reviewed_short_labels(self):
        # exceptions require the ROM references documented in the profile.
        prof = Profile.by_name("unbound-2.1.1.1")
        expected = {
            0x1EF1906, 0x1EF190A, 0x1EF190D,
            0x417AB0, 0x417AB3, 0x417AB6, 0x417AB9, 0x417ABC,
            0xA44119, 0xA4411F, 0xA44125, 0x419D4F,
            0x3FCB5F, 0x3FCB6A, 0x3FCB8F, 0x3FCB9A, 0x966078, 0xA4C200,
        }
        included = set(prof["strings"]["include"]) | {row["offset"] for row in prof["strings"].get("classified", ())
                                                       if row["action"] == "include"}
        self.assertEqual(expected - included, set())
