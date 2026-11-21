import sys
from pathlib import Path
import csv
import json
import os
import subprocess
import tempfile
import textwrap
import unittest

from gen3tl.web import snapshotstore as snapshot_store
from gen3tl.catalog.po import PoEntry, write
from gen3tl.catalog.source import digest
from gen3tl.profile.profile import Profile

from test_roots import PROJECT_ROOT, TOOLKIT_ROOT
from project_fixture import literal, write_policy

def form(export: str = "", attachment: str = "", pictures: str = "") -> str:
    """An issue body as the submission form renders it."""
    inline = f"```json\n{export}\n```" if export else "_No response_"
    return (f"### Editor export\r\n\r\n{inline}\r\n\r\n### Export file\r\n\r\n{attachment or '_No response_'}"
            f"\r\n\r\n### Pictures\r\n\r\n{pictures or '_No response_'}")

class SubmissionTest(unittest.TestCase):
    HEADER = {}   # the form of the catalogs
    IMPORT_REFUSAL = "T1: editor base differs from the current project picture; stale picture"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.po = self.root / "translation/po"
        entries = [PoEntry("s0000100", "Fit.", "Old text"),
                   PoEntry("s0000200", "Other.", "Kept text", flags=[], translator=["source: a game"]),
                   PoEntry("s0000300", "Blank.", "", flags=["empty"])]
        self.header = {"Project-Id-Version": "test", "Language": "xx",
                       "Content-Type": "text/plain; charset=UTF-8", **self.HEADER}
        write(self.po / "map.po", entries, self.header)
        self.source_text = {}
        self.facts(entries)
        data = {"rom": {"sha1": "ab" * 20}, "font_style": {"style": "main", "cell_height": 14},
                "layout": {"dialogue_width": 60, "placeholders": {}}}
        self.profile = Profile(data, self.root / "test.toml")
        self.profile.path.write_text("\n".join(f"{k} = {literal(v)}" for k, v in data.items()), encoding="utf-8")
        write_policy(self.root, self.profile, language="xx")
        (self.root / "projects.toml").write_text(
            '[defaults]\nprofile="test"\nlanguage="xx"\n[[project]]\nprofile="test"\nlanguage="xx"\n'
            'root="."\npolicy="policy.toml"\n', encoding="utf-8")
        self.out = self.root / "answer"
        self.original = (self.po / "map.po").read_bytes()

    def facts(self, entries):
        """The snapshot digests of a key-only catalog's English."""
        if not self.HEADER:
            return
        self.source_text.update({e.msgctxt: e.msgid for e in entries})
        snapshot = self.root / "translation/editor-inputs.json"
        snapshot_store.write(snapshot, {"source": {sid: [digest(text)] for sid, text in self.source_text.items()}})

    def export(self, entries, **extra):
        return json.dumps({"language": "xx", "profile": "test", "entries": entries, **extra}, ensure_ascii=False)


    # a glossary term and the lines using it
    GLOSSARY = ("id\tcategory\tsource_text\ttranslation\tlabel\tgender\tdeclension\tforms\tsources\tvariants\t"
                "confidence\taddress\tnotes\tstatus\n"
                "term:gym\tterm\tGym\tGim\t\t\tfixed\t\t\t\t\t\t\tapproved\n"
                "item:ether\titem\tEther\tEfir\t\t\tfixed\t\t\t\t\t\t\tapproved\n")
    GYM = {"id": "term:gym", "source_text": "Gym", "base": {"translation": "Gim"}, "changes": {"translation": "Stadium"}}

    def glossary(self):
        """The glossary, a catalog file using term:gym, and a key-only catalog."""
        path = self.root / "translation/glossary.tsv"
        path.write_text(self.GLOSSARY, encoding="utf-8")
        entries = [PoEntry("s0000400", "The Gym is open.", "Gim otkryt."), PoEntry("s0000500", "Come in!", "V Gim!"),
                   PoEntry("s0000600", "Gym leaders wait.", "")]
        write(self.po / "gym.po", entries, self.header)
        self.term_index(path, self.po / "gym.po", entries)
        return path, path.read_bytes(), (self.po / "gym.po").read_bytes()

    def term_index(self, glossary, po, entries):
        """Beside a key-only catalog file, the facts its English gave: digests and term index."""
        if not self.HEADER:
            return
        from gen3tl.lang import language, termbase
        self.facts(entries)
        with language.use("xx"):
            rows = termbase.build_index(termbase.load(glossary), {e.msgctxt: (po, e) for e in entries})
        termbase.save_index(self.root / "translation/term-index.tsv", rows)


    def index_rows(self):
        with (self.root / "translation/term-index.tsv").open() as stream:
            return [(r["term"], r["string"], r["text"]) for r in csv.DictReader(stream, delimiter="\t")]


    def test_workflow_refreshes_and_stages_the_index_on_the_submission_branch(self):
        self.glossary()
        event = self.root / "event.json"
        event.write_text(json.dumps({"issue": {"number": 5, "user": {"login": "contributor"},
                                              "body": form(self.export([], terms=[self.GYM]))}}))
        wrapper = self.root / "python"
        wrapper.write_text(f"#!{sys.executable}\n" + textwrap.dedent('''\
            import json
            import sys
            from pathlib import Path
            from gen3tl.cli import main
            from gen3tl.profile import profile
            profile.PROFILE_DIR = Path.cwd()
            with Path("commands.jsonl").open("a") as stream:
                stream.write(json.dumps(["python", *sys.argv[1:]]) + "\\n")
            raise SystemExit(main.main(sys.argv[3:]))
            '''))
        wrapper.chmod(0o755)
        git = self.root / "git"
        git.write_text(f"#!{sys.executable}\n" + textwrap.dedent('''\
            import json
            import sys
            from pathlib import Path
            args = sys.argv[1:]
            with Path("commands.jsonl").open("a") as stream:
                stream.write(json.dumps(["git", *args]) + "\\n")
            if args[:2] == ["rev-parse", "--abbrev-ref"]:
                print("main")
            if args[0] == "add":
                manifest = Path(args[1].split("=", 1)[1]).read_text()
                assert "translation/term-index.tsv\\n" in manifest
                Path("staged-index.tsv").write_bytes(Path("translation/term-index.tsv").read_bytes())
            '''))
        git.chmod(0o755)
        script = PROJECT_ROOT / ".github/scripts/submission.sh"
        if not script.is_file() or not (script.parents[1] / "workflows/pr-check.yml").is_file():
            self.skipTest("submission workflow belongs to the project repository")
        result = subprocess.run(["bash", str(script)], cwd=self.root, capture_output=True, text=True,
                                env={**os.environ, "PYTHONPATH": str(TOOLKIT_ROOT / "src"),
                                     "PATH": str(self.root) + os.pathsep + os.environ["PATH"],
                                     "PYTHON": str(wrapper), "GITHUB_EVENT_PATH": str(event),
                                     "SUBMISSION_DRY_RUN": "1"})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        commands = [json.loads(line) for line in (self.root / "commands.jsonl").read_text().splitlines()]
        checkout = commands.index(["git", "checkout", "-q", "-B", "submission/5"])
        index = commands.index(["python", "-m", "gen3tl", "--profile", "test", "--lang", "xx", "lang", "index"])
        stage = next(i for i, c in enumerate(commands) if c[:2] == ["git", "add"])
        self.assertLess(checkout, index)
        self.assertLess(index, stage)
        self.assertEqual(self.index_rows(), [("term:gym", "s0000400", "Stadium")])
        from gen3tl.catalog.po import read
        self.assertEqual([(e.msgstr, e.flags) for e in read(self.po / "gym.po")[1]],   # approved lines stay approved
                         [("Stadium otkryt.", []), ("V Gim!", []), ("", [])])
        self.assertEqual((self.root / "staged-index.tsv").read_bytes(),
                         (self.root / "translation/term-index.tsv").read_bytes())
