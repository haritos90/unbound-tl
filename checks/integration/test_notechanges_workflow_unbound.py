from test_roots import TOOLKIT_ROOT
"""Notechanges workflow unbound checks and fixtures."""

import sys
from pathlib import Path
import json
import os
import re
import subprocess
import textwrap
import unittest

sys.path.insert(0, str(TOOLKIT_ROOT / "src"))


import notechanges_support
from notechanges_support import change
from test_roots import PROJECT_ROOT as ROOT


class NoteSubmissionTest(notechanges_support.NoteSubmissionTest, unittest.TestCase):
    def test_submission_workflow_stages_notes_and_keeps_pull_request_draft(self):
        script = ROOT / ".github/scripts/submission.sh"
        if not script.is_file() or not (ROOT / ".github/workflows/pr-check.yml").is_file():
            self.skipTest("submission workflow belongs to the project repository")
        document = self.export([change(self.note)])
        event = self.root / "event.json"
        event.write_text(json.dumps({"issue": {"number": 7, "user": {"login": "contributor"},
                                              "body": "### Editor export\n" + json.dumps(document)}}))
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
        git = self.root / "git"
        git.write_text(f"#!{sys.executable}\n" + textwrap.dedent('''\
            import sys
            from pathlib import Path
            args = sys.argv[1:]
            if args[:1] == ['-C']:
                args = args[2:]
            if args[0] == 'show':
                sys.exit(128)
            if args[0] == 'ls-files':
                for path in Path.cwd().rglob('notes/*.toml'):
                    sys.stdout.write(path.relative_to(Path.cwd()).as_posix() + '\\0')
            if args[0] == 'rev-parse':
                print('main')
            if args[0] == 'add':
                out = Path(args[1].split('=', 1)[1]).parent
                Path('saved-pr.md').write_bytes((out / 'pr.md').read_bytes())
                Path('staged-files').write_bytes((out / 'files').read_bytes())
            '''))
        git.chmod(0o755)
        result = subprocess.run(["bash", str(script)], cwd=self.root, capture_output=True, text=True,
                                env={**os.environ, "PYTHONPATH": str(TOOLKIT_ROOT / "src"),
                                     "PATH": str(self.root) + os.pathsep + os.environ["PATH"],
                                     "PYTHON": str(wrapper), "GITHUB_EVENT_PATH": str(event), "SUBMISSION_DRY_RUN": "1"})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("--draft", result.stderr)
        saved = (self.root / "saved-pr.md").read_text()
        self.assertIn("1 note changes validated; review required", saved)
        self.assertIn("Result: passed", saved)
        self.assertEqual((self.root / "staged-files").read_text().splitlines(),
                         [self.entries.relative_to(self.root).as_posix()])
        self.assertEqual((self.po.read_bytes(), self.project.policy.read_bytes()), self.original)

    def test_a_submission_run_that_skips_keeps_its_own_group(self):
        text = (ROOT / ".github/workflows/submission.yml").read_text(encoding="utf-8")
        group = re.search(r"\n  group: >-\n((?:    .*\n)+)", text).group(1)
        condition = re.search(r"\n    if: >-\n((?:      .*\n)+)", text).group(1)
        applies = " ".join(condition.split())
        expected = ("submission-${{ github.event.issue.number }}-${{ " + applies
                    + " && 'apply' || github.run_id }}")
        self.assertEqual(" ".join(group.split()), expected)
        self.assertIn("  cancel-in-progress: true\n", text)

    def test_issue_form_and_workflow_include_note_review_inputs(self):
        form_path = ROOT / ".github/ISSUE_TEMPLATE/submission.yml"
        workflow_path = ROOT / ".github/workflows/pr-check.yml"
        if not form_path.is_file() or not workflow_path.is_file():
            self.skipTest("submission workflows belong to the project repository")
        form = form_path.read_text()
        for expected in ("label: Editor export", "label: Export file", "label: Pictures"):
            self.assertIn(expected, form)
        # the submission workflow reads the submission label alone
        playtest = (form_path.parent / "playtest.yml").read_text()
        self.assertIn('labels: ["playtest"]', playtest)
        for expected in ("label: Language", "label: Version", "label: What was played", "label: Problems found"):
            self.assertIn(expected, playtest)
        detect = re.search(r"grep -E '([^']+)'", workflow_path.read_text()).group(1)
        for path in ("translation/xx/notes/entries.toml", "translation/xx/notes/terms.toml",
                     "translation/xx/research/moves.notes.toml", "translation/xx/rules.toml",
                     "source/notes.toml", "source/graphics.toml"):
            self.assertRegex(path, detect)
        self.assertNotRegex("translation/xx/research/moves.tsv", detect)
