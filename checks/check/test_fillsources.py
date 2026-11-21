import unittest

from gen3tl.check.fillsources import Evaluator, graph

from rom_support import needs_rom
from project_fixture import buffered_stat_fixture

@needs_rom
class BufferedStatSourceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = buffered_stat_fixture()

    def test_domains_match_item_parameters_and_each_name_producer(self):
        profile, rom, catalog, inventory, measure, cm, expected = self.fixture
        base, count, stride, field, callback, parameter = expected["items"]
        indices = {rom.u8(base + i * stride + parameter) for i in range(count)
                   if rom.u32(base + i * stride + field) == callback}
        self.assertEqual(indices, set(range(6)))
        sources = profile["layout"]["fill_source"]
        primary = sources["primary-stat-names"]["value"]["entries"]
        self.assertEqual(primary, [f"s{rom.ptr_at(expected['table'] + i * 4):07X}" for i in sorted(indices)])
        short = sources["short-stat-names"]["value"]["entries"]
        self.assertEqual(short, [f"s{rom.ptr_at(at):07X}" for at in expected["script_pools"]])
        vitamins = sources["vitamin-stat-names"]["value"]["max"]
        self.assertEqual(set(vitamins["native"]["entries"]),
                         {f"s{rom.ptr_at(at):07X}" for at in expected["vitamin_pools"]})
        self.assertEqual(vitamins["wing"], {"source": "short-stat-names"})
        for name in ("primary-stat-names", "short-stat-names", "vitamin-stat-names"):
            self.assertTrue(sources[name]["evidence"])
        resolved = graph(profile, inventory, catalog)
        result = Evaluator(resolved, catalog, measure, cm).result("primary-stat-names")
        self.assertEqual((result["width"], result["contributors"][0]["id"]), (78, expected["winner"]))
        self.assertEqual(set(result["dependencies"]), set(primary))

    def test_consumers_recompute_for_a_shorter_candidate_and_ignore_excluded_stats(self):
        from dataclasses import asdict

        from gen3tl.catalog.keys import for_profile
        from gen3tl.check import qa
        from gen3tl.check.layout import entry_measure, layout, line_width, lines_of, paragraphs
        from gen3tl.web.editordata import keyed_window
        profile, rom, catalog, inventory, measure, cm, expected = self.fixture
        limits = qa.compute_limits(profile, inventory, catalog, measure, cm, rom=rom)
        aliases = for_profile(profile)
        for sid, (token, widths) in expected["consumers"].items():
            with self.subTest(consumer=sid):
                selected = entry_measure(measure, limits[sid])
                laid = layout(catalog[sid][1].msgstr, limits[sid], measure, cm)
                actual = [line_width(line, selected, cm) for par in paragraphs(laid) for line in lines_of(par)]
                self.assertEqual(actual, widths)
                window = keyed_window(asdict(limits[sid]), aliases)
                self.assertEqual(window["slot_details"][token]["state"], "computed")
                detail = window["slot_details"][token]
                self.assertIn(detail["contributors"][0]["id"], detail["dependencies"])
        primary = profile["layout"]["fill_source"]["primary-stat-names"]["value"]["entries"]
        edited = qa.compute_limits(profile, inventory, catalog, measure, cm, rom=rom,
                                   overrides={primary[0]: "A" * 20, expected["excluded"]: "A" * 30})
        for sid, (token, _) in expected["consumers"].items():
            if token != "B_COPY_VAR_2":
                continue
            detail = edited[sid].slot_details["B_COPY_VAR_2"]
            self.assertEqual(detail["contributors"][0]["id"], primary[0])
            self.assertGreater(detail["width"], limits[sid].placeholders["B_COPY_VAR_2"])
            self.assertNotIn(expected["excluded"], detail["dependencies"])
        restored = qa.compute_limits(profile, inventory, catalog, measure, cm, rom=rom)
        self.assertEqual(restored, limits)
