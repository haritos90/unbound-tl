import copy
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest.mock import patch

from gen3tl.cli import main as cli
from gen3tl.web import editordata
from gen3tl.check import qa
from gen3tl.core.charmap import Charmap
from gen3tl.check.layout import Measure
from gen3tl.check.policy import PolicyError, effective
from gen3tl.profile.profile import Profile

from project_fixture import FIXTURES, UNBOUND, literal, needs_unbound, write_policy

class PolicyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.path = self.root / "test.toml"
        self.base = {
            "rom": {"sha1": "0" * 40},
            "font": [],
            "keyboard": {"base_pages": 3, "first_page": 1, "table": []},
            "text_controls": {"droppable": {"article": {"ids": ["s1"], "tokens": ["{STR_VAR_2}"], "evidence": "source article"}}},
            "layout": {"window_width": {"physical": 208}},
            "policy_slots": {"window_width": ["budget"], "placeholders": ["PLAYER"]},
            "graphics": {"edit_facts": {"G1": {"max_tiles": 5, "evidence": "ROM capacity"}},
                         "tilemap": [{"name": "map", "size": 8, "width": 2, "offset": 32}]},
        }
        self.path.write_text("\n".join(f"{k} = {literal(v)}" for k, v in self.base.items()))
        self.raw = Profile.load(self.path)
        from gen3tl.build.keyboard import load_layout
        self.pack_root = self.root / "assets/lang"
        self.loader = patch("gen3tl.build.keyboard.load_layout",
                            side_effect=lambda code, name, base: load_layout(code, name, base, self.pack_root))
        self.loader.start()
        self.addCleanup(self.loader.stop)
        for code in ("ru", "fr"):
            directory = self.pack_root / code
            directory.mkdir(parents=True)
            layout = {"schema": "2.0.0", "language": code,
                      "keyboards": [{"name": code, "like": 0}],
                      "pages": [{"name": code, "keyboard": 0, "look": 1}], "rows": {}}
            (directory / "keyboard.toml").write_text("\n".join(f"{k} = {literal(v)}" for k, v in layout.items()))
        self.policy = {"keyboard": {"layout": "keyboard.toml"},
                       "qa": {"forbidden": {"  ": "double space"}, "droppable": ["article"]},
                       "layout": {"window_width": {"budget": 42}, "placeholders": {"PLAYER": 42}}}

    def merged(self, policy=None, language="ru"):
        write_policy(self.root, self.raw, language, **(self.policy if policy is None else policy))
        return effective(self.raw, language, self.root / "policy.toml", self.root)


    def test_typography_reasons_may_carry_their_text_in_site_languages(self):
        policy = copy.deepcopy(self.policy)
        policy["qa"]["forbidden"] = {"\\.\\.\\.": {"reason": "three dots", "ru": "три точки"}, "  ": "double space",
                                     "…\\.": {"reason": "three dots", "de": "drei Punkte"}}
        selected = self.merged(policy)
        self.assertEqual(selected["qa"]["forbidden"],
                         {"\\.\\.\\.": "three dots", "  ": "double space", "…\\.": "three dots"})
        self.assertEqual(selected["qa"]["reasons"], {"three dots": {"ru": "три точки", "de": "drei Punkte"}})
        doc = editordata.build("ru", selected, {}, {}, Measure(lambda b: 6, {}), Charmap(), {})
        self.assertEqual(doc["check_rules"]["reasons"], selected["qa"]["reasons"])
        self.assertNotIn("reasons", self.merged()["qa"])
        for rule in ({"reason": "x", "Russian": "y"}, {"ru": "y"}, {"reason": "x", "ru": ""}):
            policy["qa"]["forbidden"] = {"x": rule}
            with self.subTest(rule=rule), self.assertRaises(PolicyError):
                self.merged(policy)
        policy["qa"]["forbidden"] = {"a": {"reason": "x", "ru": "y"}, "b": {"reason": "x", "ru": "z"}}
        with self.assertRaisesRegex(PolicyError, "two texts in one language"):
            self.merged(policy)


    def test_selected_language_rules_reach_cli_qa_and_editor_without_leaks(self):
        lines = ['[defaults]', 'profile="test"', 'language="ru"']
        for language in ("ru", "fr"):
            workspace = self.root / language
            workspace.mkdir()
            policy = copy.deepcopy(self.policy)
            if language == "fr":
                policy["qa"] = {}
                policy["layout"]["window_width"]["budget"] = 30
            write_policy(workspace, self.raw, language, **policy)
            lines += ['[[project]]', 'profile="test"', f'language="{language}"',
                      f'root="{language}"', 'policy="policy.toml"']
        (self.root / "projects.toml").write_text("\n".join(lines))
        observed = []
        def handler(args):
            profile = Profile.by_name(str(self.path))
            doc = editordata.build(args.lang, profile, {}, {}, Measure(lambda b: 6, {}), Charmap(), {})
            observed.append((profile, doc, qa.droppable_tokens(profile["qa"])))
        with patch.dict(cli.COMMANDS, {"catalog tm": handler}):
            for language in ("ru", "fr", "ru"):
                cli.main(["--project-root", str(self.root), "--profile", str(self.path),
                          "--lang", language, "catalog", "tm"])
        for n in (0, 2):
            profile, doc, rules = observed[n]
            self.assertEqual(profile["keyboard"]["pages"][0]["name"], "ru")
            self.assertEqual(doc["check_rules"], profile["qa"])
            self.assertEqual(rules["s1"], {"{STR_VAR_2}"})
        profile, doc, rules = observed[1]
        self.assertEqual(profile["keyboard"]["pages"][0]["name"], "fr")
        self.assertEqual(doc["check_rules"]["forbidden"], {})
        self.assertEqual(rules, {})
        self.assertNotIn("qa", Profile.by_name(str(self.path)).data)
        self.assertEqual(Profile.by_name(str(self.path)).project_root, Path.cwd())


class UnboundFixturePolicyTest(unittest.TestCase):
    def test_policy_is_valid(self):
        path = FIXTURES / "unbound-2.1.1.1-policy.toml"
        selected = effective(Profile.by_name("unbound-2.1.1.1"), "ru", path, FIXTURES)
        self.assertEqual(selected.policy_path, path)

@needs_unbound
class RussianPolicyTest(unittest.TestCase):
    def test_raw_profile_has_facts_only_and_explicit_russian_restores_policy(self):
        raw = Profile.by_name("unbound-2.1.1.1")
        self.assertNotIn("qa", raw.data)
        self.assertNotIn("pages", raw["keyboard"])
        self.assertNotIn("edit", raw["graphics"])
        self.assertTrue(all("cells" not in row for row in raw["graphics"]["tilemap"]))
        self.assertNotIn("B_ATK_NAME_WITH_PREFIX", raw["layout"]["placeholders"])
        selected = raw.for_project("ru", UNBOUND)
        self.assertEqual(len(selected["keyboard"]["pages"]), 5)
        self.assertEqual(selected["layout"]["placeholders"]["B_ATK_NAME_WITH_PREFIX"], 143)
        policy = tomllib.loads((UNBOUND / "translation/ru/policy.toml").read_text(encoding="utf-8"))
        self.assertEqual(len(selected["graphics"]["edit"]), len(policy["graphics"]["edit"]))
        self.assertGreater(len(policy["graphics"]["edit"]), 0)
        with self.assertRaises(PolicyError):
            effective(raw, "fr", UNBOUND / "translation/ru/policy.toml", UNBOUND)

@needs_unbound
class SiteLanguagePolicyTest(unittest.TestCase):
    def test_forbidden_reasons_carry_the_policy_language_text(self):
        expected = {
            "es": {"three dots: use the ellipsis character …": "tres puntos: utiliza el carácter de puntos suspensivos …",
                   "double space": "doble espacio"},
            "de": {"three dots: use the ellipsis character …": "drei Punkte: verwende das Auslassungszeichen …",
                   "double space": "doppeltes Leerzeichen"},
            "fr": {"three dots: use the ellipsis character …":
                       "trois points : utilisez le caractère de points de suspension …",
                   "double space": "double espace"},
        }
        raw = Profile.by_name("unbound-2.1.1.1")
        for language, reasons in expected.items():
            with self.subTest(language=language):
                selected = raw.for_project(language, UNBOUND)
                self.assertEqual(selected["qa"]["reasons"],
                                 {reason: {language: text} for reason, text in reasons.items()})
