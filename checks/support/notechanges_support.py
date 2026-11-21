from pathlib import Path
import base64
import contextlib
import hashlib
import io
import json
import subprocess
import tempfile
from copy import deepcopy
from unittest.mock import patch

from gen3tl.web import snapshotstore as snapshot_store
from gen3tl import __version__
from gen3tl.__main__ import main
from gen3tl.catalog.po import KEY_ONLY, SOURCE_FIELD, PoEntry, write
from gen3tl.catalog.source import digest
from gen3tl.check import prcheck
from gen3tl.core import notes
from gen3tl.profile.profile import Profile
from gen3tl.project import Registry
from gen3tl.project.manifest import Manifest
from gen3tl.web import editorsave, submission

from test_roots import PROJECT_ROOT
from project_fixture import literal, write_policy

ROOT = PROJECT_ROOT

def change(record, base=None, operation=None):
    return {"operation": operation or ("edit" if base else "add"), "id": record["id"],
            "subject": record["subject"], "scope": record["scope"],
            **({"binding": record["binding"]} if "binding" in record else {}),
            "base": deepcopy(base), "base_revision": json.dumps(base, sort_keys=True, separators=(",", ":")),
            "proposed": None if operation == "remove" else deepcopy(record)}

class NoteSubmissionTest:
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        data = {"rom": {"sha1": "ab" * 20}, "font_style": {"style": "main", "cell_height": 14},
                "layout": {"dialogue_width": 60, "placeholders": {}}}
        self.raw = Profile(data, self.root / "sample.toml")
        self.raw.path.write_text("\n".join(f"{key} = {literal(value)}" for key, value in data.items()))
        write_policy(self.root, self.raw, language="xx")
        (self.root / "project.toml").write_text(
            Manifest(self.root / "project.toml", "sample", "ab" * 20, __version__, ("xx",), "xx").text())
        (self.root / "projects.toml").write_text('[defaults]\nprofile="sample"\nlanguage="xx"\n'
                                               '[[project]]\nprofile="sample"\nlanguage="xx"\nroot="."\npolicy="policy.toml"\n')
        self.registry = Registry.load(self.root)
        self.project = self.registry.projects[0]
        self.prof = self.project.effective(self.raw)
        self.po = self.project.catalog / "entries.po"
        write(self.po, [PoEntry("key", "key", "Old"),
                        PoEntry("legacy", "legacy", "Old", translator=["source: Historical reference"])],
              {"Project-Id-Version": "sample", "Language": "xx", SOURCE_FIELD: KEY_ONLY})
        self.project.snapshot.parent.mkdir(parents=True)
        snapshot_store.write(self.project.snapshot, {"source": {"key": [digest("Example.")],
                                                                "legacy": [digest("Legacy.")]}})
        self.path = self.root / "export.json"
        self.note = {"id": "note:example", "subject": {"kind": "entry", "id": "key"},
                     "scope": {"kind": "language", "language": "xx"},
                     "binding": {"kind": "entry", "id": "key", "source_sha256": digest("Example.")},
                     "guidance": ["Preserve the context."], "status": "proposed"}
        self.entries = self.project.translation / "notes" / "entries.toml"
        self.original = self.po.read_bytes(), self.project.policy.read_bytes()

    def export(self, changes, entries=None, **extra):
        doc = {"profile": "sample", "language": "xx", "entries": entries or [],
               "note_changes_schema": "3.0.0", "note_changes": changes, **extra}
        self.path.write_text(json.dumps(doc, ensure_ascii=False))
        return doc

    def apply(self, check=False):
        with patch.object(Profile, "by_name", return_value=self.raw):
            return submission.apply(self.path, self.registry, check=check, author="contributor",
                                    created="2026-01-02T03:04:05Z")

    def stored(self, path=None):
        return {note["id"]: note for note in notes.read_notes(path or self.entries)["note"]}

    def published(self):
        base = {**self.note, "status": "accepted"}
        notes.write_notes(self.entries, {"schema": notes.SCHEMA, "note": [base]})
        return base, self.entries

    def legacy_proposal(self, operation="edit"):
        from gen3tl.catalog import guidance

        base = {"id": "key", "source_sha256": digest("Example."),
                "text": "Legacy guidance. Legacy observation.", "evidence": "Recorded location."}
        guidance.write_notes(self.project.notes, [base])
        self.prof = self.project.effective(self.raw)
        proposed = {**self.note, "scope": {"kind": "shared"}, "facts": ["The menu uses this label."],
                    "sources": [{"kind": "rom", "name": "Base ROM", "address": "sha1:" + self.raw.sha1,
                                 "locator": "offset 0x100", "verification": "unresolved"}]}
        if operation == "remove":
            proposed["id"] = base["id"]
        return change(proposed, base, operation)

    def event(self, document, sender="contributor", author="contributor"):
        event = self.root / "event.json"
        event.write_text(json.dumps({"sender": {"login": sender}, "issue": {
            "number": 7, "user": {"login": author}, "body": "### Editor export\n" + json.dumps(document)}}))
        return event

    def run_event(self, document, **logins):
        out = self.root / "out"
        with patch.object(Profile, "by_name", return_value=self.raw), contextlib.redirect_stdout(io.StringIO()):
            code = submission.run(self.event(document, **logins), out, self.registry)
        return code, out

    def check(self, files, before=None):
        """The pull request check of `files` against their original contents."""
        before = before or {}
        out = self.root / "check"

        def show(_root, *args):
            relative = args[1].split(":", 1)[1]
            data = before.get(self.root / relative)
            return subprocess.CompletedProcess(args, 0 if data is not None else 128, data or b"", b"")

        with patch.object(Profile, "by_name", return_value=self.raw), \
                patch.object(prcheck, "changed_files", return_value=sorted(files)), \
                patch.object(prcheck, "changes", return_value=[]), \
                patch.object(prcheck, "_git", side_effect=show), \
                contextlib.redirect_stdout(io.StringIO()):
            code = prcheck.run("HEAD", out, self.registry)
        return code, (out / "report.md").read_text(encoding="utf-8")

    def note_for(self, kind, sid, scope=None, binding=None, **fields):
        note = {"id": f"note:{kind}-{sid}", "subject": {"kind": kind, "id": sid},
                "scope": scope or self.note["scope"], "guidance": ["Preserve the context."], "status": "proposed",
                **fields}
        if binding:
            note["binding"] = binding
        return note

    def containers(self, legacy=False):
        """A glossary, research table, rule list and graphics inventory, migrated unless `legacy`."""
        prose = "Legacy prose" if legacy else ""
        self.project.glossary.write_text("id\tcategory\tsource_text\ttranslation\tnotes\nterm:one\tmisc\tOne\tOne\t"
                                         + prose + "\n")
        research = self.project.translation / "research"
        research.mkdir(exist_ok=True)
        (research / "sample.tsv").write_text(f"record_id\tnote_ids\tnotes\nresearch:one\t\t{prose}\n")
        rule = ('rule="Keep context."\nsource="Record"\n' if legacy else
                '\n[[rule.notes]]\nid="note:rule-old"\nsubject={kind="wording_rule",id="rule:one"}\n'
                'scope={kind="language",language="xx"}\nguidance=["Keep context."]\nstatus="unreviewed"\n')
        (self.project.translation / "rules.toml").write_text('schema="3.0.0"\n[[rule]]\nid="rule:one"\n'
                                                             'ids=["key"]\n' + rule)
        container = 'reason = "Legacy reason"\n' if legacy else 'notes_schema = "3.0.0"\nnotes = []\n'
        self.project.graphics.parent.mkdir(exist_ok=True)
        self.project.graphics.write_text(f'version = "2.0.0"\n\n[[graphic]]\nid = "G1"\n{container}')
        (self.project.source / "notes.toml").write_text(
            'schema = "3.0.0"\n\n[[note]]\nid = "legacy"\nsource_sha256 = "' + digest("Legacy.")
            + '"\ntext = "Legacy guidance."\nevidence = "Recorded."\n')
        self.prof = self.project.effective(self.raw)
        term_source = [{"kind": "publication", "name": "Reference", "address": "ref:one", "quoted_term": "One",
                        "verification": "unresolved"}]
        graphic = {"kind": "graphic", "id": "G1"}
        shared_entry = {**self.note["binding"]}
        return [self.note_for("term", "term:one", sources=term_source),
                self.note_for("research", "research:one"),
                self.note_for("wording_rule", "rule:one"),
                self.note_for("graphic", "G1", {"kind": "shared"}, graphic),
                self.note_for("graphic", "G1", binding=graphic, id="note:graphic-language"),
                self.note_for("entry", "key", {"kind": "shared"}, shared_entry)]

    def capture_change(self, raw=b"\x89PNG\r\n\x1a\nimage"):
        captures, attachments = [], []
        for role in ("original", "proposed"):
            item = {"id": role, "name": "../capture.png", "type": "image/png", "size": len(raw),
                    "sha256": hashlib.sha256(raw).hexdigest(), "data": base64.b64encode(raw).decode(),
                    "role": role, "build": "1.0.0", "context": "Main menu"}
            attachments.append(item)
            captures.append({"address": "attachment:" + role, "sha256": item["sha256"],
                             "locator": " · ".join(item[k] for k in ("role", "build", "context"))})
        candidate = change({**self.note, "evidence": [{"method": "screenshot", "verification": "unresolved",
                                                       "captures": captures}]})
        candidate["attachments"] = attachments
        return candidate

    def local_store(self):
        def refresh(catalog, destination):
            destination.mkdir()
            (destination / "index.json").write_text(json.dumps({"profile": "sample", "language": "xx",
                                                                "rom": {"sha1": self.raw.sha1}}))
        editor = self.root / "view"
        editor.mkdir()
        (editor / "index.json").write_text('{"previous":true}')
        store = editorsave.DraftStore(self.project.catalog, editor, "sample", "xx", self.raw.sha1, refresh,
                                      self.project.build, effective_profile=self.prof, project=self.project)
        store.source = [PoEntry("key", "Example."), PoEntry("legacy", "Legacy.")]
        return store, editor

    def local_document(self, changes, entries=None):
        document = self.export(changes, entries)
        document["rom_sha1"] = self.raw.sha1
        return document

    def local_import(self, *options):
        write(self.project.build / "catalog.pot", [PoEntry("key", "Example."), PoEntry("legacy", "Legacy.")], {})
        args = ["--project-root", str(self.root), "--profile", str(self.raw.path), "--lang", "xx",
                "web", "import", str(self.path), *options]
        with patch("gen3tl.cli.web._limits_and_matcher", return_value=({}, None)), \
                patch("gen3tl.web.editorfonts.glyph_edits", return_value=[]), \
                contextlib.redirect_stdout(io.StringIO()) as out:
            status = main(args)
        return status, out.getvalue()
