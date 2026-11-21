import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from test_roots import TOOLKIT_ROOT

ROOT = TOOLKIT_ROOT

from gen3tl.check import commitmsg

ENV = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
       "GIT_AUTHOR_NAME": "test", "GIT_AUTHOR_EMAIL": "test@example.invalid",
       "GIT_COMMITTER_NAME": "test", "GIT_COMMITTER_EMAIL": "test@example.invalid",
       "PYTHONPATH": str(TOOLKIT_ROOT / "src") + os.pathsep + os.environ.get("PYTHONPATH", "")}

FIFTEEN = " ".join(["word"] * 14)

SUBMISSION = ("fix(translation): apply editor submission (#42)\n\n- Project: unbound-2.1.1.1/ru\n- Entries: 3\n\n"
              "Signed-off-by: contributor <contributor@users.noreply.github.com>\n")

def run(*args, cwd=None):
    return subprocess.run(args, cwd=cwd, env=ENV, capture_output=True, text=True)

class RulesTest(unittest.TestCase):
    def assertAccepted(self, message):
        self.assertEqual(commitmsg.problems(message), [], message)


    def test_public_messages_are_accepted(self):
        for message in ("feat(editor): show the window width in pixels\n",
                        "fix(po): keep the plural forms of the header (#12)\n",
                        "refactor(core)!: read pointers through one table\n",
                        "chore(release): first public release v1.0.0\n",
                        "perf(data/pokedex): load the learnsets on demand\n",
                        f"docs(readme): show {FIFTEEN} (#7)\n",
                        "test(layout): cover the sign window\n\n- the window keeps two lines\n\n- a second paragraph\n",
                        SUBMISSION):
            self.assertAccepted(message)


class CommandTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def check(self, *args):
        return run(sys.executable, "-m", "gen3tl", "check", "commit-message", *args, cwd=self.root)

    def message(self, text):
        path = self.root / "message"
        path.write_text(text, encoding="utf-8")
        return str(path)


    def test_message_file_accepts_and_rejects(self):
        accepted = self.check(self.message(SUBMISSION))
        self.assertEqual(accepted.returncode, 0, accepted.stderr)
        rejected = self.check(self.message("fix(po): correct the plural forms (task-42)\n"))
        self.assertEqual(rejected.returncode, 1)
        self.assertIn("names a local record identifier 'task-42'", rejected.stderr)
        self.assertIn("CONTRIBUTING.md", rejected.stderr)
        self.assertEqual(self.check().returncode, 2)
        self.assertEqual(self.check(str(self.root / "missing")).returncode, 2)
