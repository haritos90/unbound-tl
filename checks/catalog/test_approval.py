"""A played release approves the translated lines it holds unchanged, on files of the Russian catalog."""

import io
import subprocess
import tempfile
import unittest
from collections import Counter
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from gen3tl.catalog import entrynotes
from gen3tl.catalog.po import read, write
from gen3tl.cli import main as cli

from project_fixture import UNBOUND, copy_policy, copy_profile, needs_unbound

CHANGED, STEADY = "battle.po", "system/credits.po"


@needs_unbound
class PlayedReleaseTest(unittest.TestCase):
    """A game project in a git repository: a release tagged with translated lines, then one line edited."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        manifest = copy_profile(self.root)
        (self.root / "projects.toml").write_text(
            f'[defaults]\nprofile = "{manifest.profile}"\nlanguage = "ru"\n'
            f'[[project]]\nprofile = "{manifest.profile}"\nlanguage = "ru"\nroot = "."\npolicy = "policy.toml"\n',
            encoding="utf-8")
        copy_policy(self.root, self.root)
        source = UNBOUND / "translation/ru/po"
        self.catalog = self.root / "translation/ru/po"
        for name in (CHANGED, STEADY):
            (self.catalog / name).parent.mkdir(parents=True, exist_ok=True)
            (self.catalog / name).write_bytes((source / name).read_bytes())
        notes = entrynotes.path(self.catalog)
        notes.parent.mkdir()
        notes.write_bytes(entrynotes.path(source).read_bytes())
        self.git("init", "-q")
        self.translated = self.edit(lambda entry: entry.set_fuzzy(True))   # a merged contribution
        self.commit("release")
        self.git("tag", "ru-v1.0.7")
        self.edited = self.edit(lambda entry: setattr(entry, "msgstr", entry.msgstr + "!"), self.translated[:1])
        self.commit("later edit")
        self.before = self.files()

    def git(self, *argv):
        subprocess.run(["git", "-C", str(self.root), "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                        "-c", "commit.gpgsign=false", "-c", "tag.gpgsign=false", *argv],
                       check=True, capture_output=True)

    def commit(self, subject):
        self.git("add", ".")
        self.git("commit", "-qm", subject)

    def edit(self, change, only=None):
        """Change the lines with text of one file, or the named ones; their keys."""
        file, notes = self.catalog / CHANGED, entrynotes.path(self.catalog)
        header, entries = read(file, notes_path=notes)
        chosen = [e for e in entries if e.msgstr and (only is None or e.msgctxt in only)]
        for entry in chosen:
            change(entry)
        write(file, entries, header, notes_path=notes)
        return [e.msgctxt for e in chosen]

    def files(self):
        return {name: (self.catalog / name).read_bytes() for name in (CHANGED, STEADY)}

    def approve(self, *argv):
        output = io.StringIO()
        with redirect_stdout(output), redirect_stderr(io.StringIO()):
            status = cli.main(["--project-root", str(self.root), "--lang", "ru",
                               "catalog", "approve", "--played", "1.0.7", *argv])
        return status, output.getvalue()

    def test_the_lines_of_the_played_release_become_approved(self):
        count = len(self.translated)
        self.assertGreater(count, 100)
        status, output = self.approve()
        self.assertEqual(status, 0, output)
        self.assertEqual(output, f"tag          ru-v1.0.7\napproved     {count - 1} entries\nkept         1 entries\n"
                                 "files        1 changed\nstatus       applied\n")
        entries = read(self.catalog / CHANGED, notes_path=entrynotes.path(self.catalog))[1]
        self.assertEqual([e.msgctxt for e in entries if e.fuzzy], self.edited)
        after = self.files()
        self.assertEqual(after[STEADY], self.before[STEADY])
        was, now = (Counter(data.decode("utf-8").split("\n")) for data in (self.before[CHANGED], after[CHANGED]))
        self.assertEqual(was - now, Counter({"#, fuzzy": count - 1}))   # the flag lines alone left the file
        self.assertEqual(now - was, Counter())

    def test_a_dry_run_reports_the_counts_and_writes_nothing(self):
        status, output = self.approve("--dry-run")
        self.assertEqual(status, 0, output)
        self.assertIn(f"approved     {len(self.translated) - 1} entries\nkept         1 entries\n"
                      "files        1 changed\nstatus       planned\n", output)
        self.assertEqual(self.files(), self.before)


if __name__ == "__main__":
    unittest.main()
