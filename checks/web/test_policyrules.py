from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest

from gen3tl.catalog.po import KEY_ONLY, SOURCE_FIELD, PoEntry, write
from gen3tl.check.policy import effective
from gen3tl.profile.profile import Profile
from gen3tl.project import Registry
from gen3tl.web.editorrules import rules_data

from test_roots import PROJECT_ROOT, TOOLKIT_ROOT
from project_fixture import literal, rom_evidence, write_policy

def fixture():
    return {
        "rom": {"sha1": "ab" * 20},
        "font_style": {"style": "main"},
        "code_replacement": [{
            "name": "units", "evidence": "A printer converts the stored value in code.",
            "routines": [{"guard": rom_evidence(0x100, bytes(range(32))), "where": "value printer"}],
            "routine": {"code": bytes(range(8)).hex(), "words": ["unit", "pool"], "fallback": {"pool": 0x200}},
            "calls": [{"guard": rom_evidence(0x100, bytes(range(12))),
                       "code": bytes(range(8)).hex(), "entry": 4}],
        }],
        "text_prefixes": [{"name": "marker", "pointer": 32, "source": rom_evidence(64, "a1ff"),
                           "evidence": "Dedicated pointer.",
                           "limits": {"table": "names", "where": "list", "original_width": 40,
                                      "original_chars": 8, "width": 48, "chars": 10}}],
        "table": [{"name": "names", "windows": [{"where": "list", "indices": [0], "width": 40, "chars": 8,
                                                  "evidence": "Measured list."}]}],
        "layout": {"window_width": {"names:0": 40}},
        "language_rules": [
            {"id": "units", "kind": "policy", "title": "Units", "description": "Unit conversion.",
             "related": [], "evidence": "Verified printer.", "choices": ["original", "enabled"],
             "policies": [{"kind": "code_replacement", "name": "units", "fields": ["unit", "pool"],
                           "field_limits": {"unit": {"bytes": 4, "pixels": 18},
                                            "pool": {"bytes": 4, "pixels": 18}}}]},
            {"id": "marker", "kind": "policy", "title": "Marker", "description": "Number prefix.",
             "related": [], "evidence": "Verified pointer.", "choices": ["original", "off"],
             "policies": [{"kind": "text_prefix", "name": "marker"}]},
        ],
        "selected_code_replacements": {"units": {"unit": "m"}},
    }

def proposal(model, value):
    return {"id": model["id"], "capability_sha256": model["capability_sha256"],
            "base": deepcopy(model["policies"][0]["current"]), "value": value}

class PolicySubmissionTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.raw = Profile(fixture(), self.root / "sample.toml")
        self.raw.data.pop("selected_code_replacements")
        self.raw.path.write_text("\n".join(f"{key} = {literal(value)}" for key, value in self.raw.data.items()))
        write_policy(self.root, self.raw, "xx", code_replacements={"units": {"unit": "m"}})
        (self.root / "projects.toml").write_text('[defaults]\nprofile="sample"\nlanguage="xx"\n'
                                                '[[project]]\nprofile="sample"\nlanguage="xx"\nroot="."\npolicy="policy.toml"\n')
        self.registry = Registry.load(self.root)
        self.project = self.registry.projects[0]
        self.catalog_path = self.project.catalog / "entries.po"
        write(self.catalog_path, [PoEntry("key", "key", "Old")],
              {SOURCE_FIELD: KEY_ONLY, "Project-Id-Version": "sample", "Language": "xx"})
        self.policy = self.root / "policy.toml"
        self.prof = effective(self.raw, "xx", self.policy, self.root)
        self.models = rules_data(self.prof, [])["rules"]
        self.path = self.root / "export.json"

    def export(self, records, entries=None, **extra):
        self.path.write_text(json.dumps({"profile": "sample", "language": "xx", "rom_sha1": self.prof.sha1,
                                        "entries": entries or [], "engine_rules": records, **extra}))


    def git(self, *args):
        subprocess.run(["git", "-C", str(self.root), *args], check=True, capture_output=True)

    def base(self):
        self.git("init", "-q")
        self.git("add", ".")
        self.git("-c", "user.name=test", "-c", "user.email=test@example.invalid", "commit", "-qm", "base")


    def test_submission_script_keeps_rule_pr_draft_with_the_check_report(self):
        script = PROJECT_ROOT / ".github/scripts/submission.sh"
        if not script.is_file() or not (script.parents[1] / "workflows/pr-check.yml").is_file():
            self.skipTest("submission workflow belongs to the project repository")
        self.base()
        record = proposal(self.models[1], {"enabled": True})
        self.export([record])
        event = self.root / "event.json"
        event.write_text(json.dumps({"issue": {"number": 7, "user": {"login": "contributor"},
                                              "body": "### Editor export\n" + self.path.read_text()}}))
        wrapper = self.root / "python"
        wrapper.write_text(f"#!{sys.executable}\n" + textwrap.dedent('''\
            import sys
            from pathlib import Path
            from gen3tl.cli import main
            from gen3tl.profile import profile
            profile.PROFILE_DIR = Path.cwd()
            raise SystemExit(main.main(sys.argv[3:]))
            '''))
        wrapper.chmod(0o755)
        real_git = subprocess.run(["which", "git"], capture_output=True, text=True, check=True).stdout.strip()
        fake_git = self.root / "git"
        fake_git.write_text(f"#!{sys.executable}\n" + textwrap.dedent('''\
            import subprocess
            import sys
            from pathlib import Path
            args = sys.argv[1:]
            if args[0] == 'add':
                out = Path(args[1].split('=', 1)[1]).parent
                Path('saved-pr.md').write_bytes((out / 'pr.md').read_bytes())
            if args[0] not in ('checkout', 'add', '-c'):
                raise SystemExit(subprocess.call([REAL_GIT, *args]))
            ''').replace("REAL_GIT", repr(real_git)))
        fake_git.chmod(0o755)
        result = subprocess.run(["bash", str(script)], cwd=self.root, capture_output=True, text=True,
                                env={**os.environ, "PYTHONPATH": str(TOOLKIT_ROOT / "src"),
                                     "PATH": str(self.root) + os.pathsep + os.environ["PATH"],
                                     "PYTHON": str(wrapper), "GITHUB_EVENT_PATH": str(event),
                                     "SUBMISSION_DRY_RUN": "1"})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("--draft", result.stderr)
        body = (self.root / "saved-pr.md").read_text()
        self.assertIn("# Pull request checks", body)
        self.assertIn("Result: failed", body)
        self.assertIn("Engine language rules", body)
