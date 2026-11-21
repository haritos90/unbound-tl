import io
import json
import tempfile
import threading
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

class CommandOutputTest(unittest.TestCase):


    def test_editor_reports_each_data_state_without_binding(self):
        from gen3tl.cli.web import editor
        from gen3tl.web import editordata, editorsave
        for state in ("missing", "current", "stale"):
            with self.subTest(state=state), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                project = SimpleNamespace(translation=root / "translation", build=root / "build",
                                          glossary=root / "glossary.tsv", release=root / "release.toml",
                                          registry_root=root, snapshot=root / "translation/editor-inputs.json",
                                          notes=None, graphics=None, graphics_views=root / "views")
                project.build.mkdir()
                profile = SimpleNamespace(name="fixture", path=root / "profile.toml", sha1="a" * 40)
                target = root / "data/fixture/fr"
                if state != "missing":
                    target.mkdir(parents=True)
                    # present data is data of the current schema
                    (target / "index.json").write_text(json.dumps({"schema": editordata.SCHEMA}))
                    (target / editorsave.STAMP).write_text("key" if state == "current" else "old")
                server = Mock(server_address=("127.0.0.1", 8123))
                args = SimpleNamespace(project=project, profile="fixture", data=root / "data",
                                       lang="fr", po_root=root / "po", port=8123)

                def generate(command, **kwargs):
                    output = Path(command[command.index("--out") + 1])
                    output.mkdir()
                    (output / "index.json").write_text("{}")
                    return SimpleNamespace(returncode=0)

                def thread(*, target, args, kwargs, daemon):
                    worker = Mock()
                    worker.start.side_effect = lambda: target(*args, **kwargs)
                    return worker

                output = io.StringIO()
                with patch("gen3tl.cli.web.Profile.by_name", return_value=profile), \
                     patch("gen3tl.web.editordata.toolkit_fingerprint", return_value="toolkit"), \
                     patch("gen3tl.web.editordata.write_languages"), \
                     patch("gen3tl.web.editordata.write_keys"), \
                     patch("gen3tl.web.editorcheck.bundle_current", return_value=True), \
                     patch.object(editorsave, "data_key", return_value="key") as data_key, \
                     patch.object(editorsave, "local_server", return_value=server), \
                     patch("subprocess.run", side_effect=generate) as generated, \
                     patch.object(threading, "Thread", side_effect=thread), redirect_stdout(output):
                    self.assertEqual(editor(args), 0)
                self.assertIn(project.graphics_views, data_key.call_args.args[3])
                rows = [row.split(None, 1) for row in output.getvalue().splitlines()]
                self.assertTrue(all(len(row) == 2 for row in rows))
                states = [value for label, value in rows if label == "data"]
                expected = {"missing": ["missing", "generating", "generated"], "current": ["current"],
                            "stale": ["stale", "regenerating", "regenerated"]}
                self.assertEqual(states, expected[state])
                self.assertIn(["manifest", str((root / "data/languages.json").resolve())], rows)
                self.assertIn(["site", "http://127.0.0.1:8123/"], rows)
                self.assertIn(["editor", "http://127.0.0.1:8123/editor"], rows)
                self.assertRegex(dict(rows)["ready"], r"^\d+\.\d s$")
                self.assertEqual(generated.call_count, state != "current")
                self.assertEqual((target / editorsave.STAMP).read_text(), "key")
                server.server_close.assert_called_once()
