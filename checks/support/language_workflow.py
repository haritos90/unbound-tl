import io
import json
import shutil
import sys
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from gen3tl import __version__
from gen3tl.cli import main as cli
from gen3tl.build.release import build_names
from gen3tl.profile.profile import Profile
from gen3tl.project import Manifest
from gen3tl.verify.savefile import Layout, blank_save

from rom_support import rom_path
from test_roots import project_profile
from project_fixture import UNBOUND

PROFILE = Profile.by_name("unbound-2.1.1.1")


class SeededWorkflow:
    def workflow(self, code):
        with tempfile.TemporaryDirectory(prefix=f"language-{code}-") as tmp:
            root = Path(tmp)
            shutil.copytree(UNBOUND / "source", root / "source")
            shutil.copytree(UNBOUND / "translation" / code, root / "translation" / code)
            manifest = root / "project.toml"
            manifest.write_text(Manifest(manifest, PROFILE.name, PROFILE.sha1, __version__, (code,), code).text())
            (root / "projects.toml").write_text(
                f'[defaults]\nprofile = "{PROFILE.name}"\nlanguage = "{code}"\n'
                f'[[project]]\nprofile = "{PROFILE.name}"\nlanguage = "{code}"\n'
                f'root = "."\npolicy = "translation/{code}/policy.toml"\nstage = "translation"\n')
            prefix = ["--project-root", str(root), "--profile", str(project_profile(root, PROFILE.path)), "--rom", str(rom_path())]

            def run(*args):
                print(f"workflow     {code} {' '.join(args[:2])}", file=sys.stderr, flush=True)
                output = io.StringIO()
                with redirect_stdout(output), redirect_stderr(output):
                    result = cli.main(prefix + list(args))
                self.assertEqual(result or 0, 0, f"{code}: {' '.join(args)}\n{output.getvalue()}")
                return output.getvalue()

            for command in ("inventory", "context", "reach"):
                run("discover", command)
            run("catalog", "extract")
            run("catalog", "export")
            run("check", "po")
            stem = build_names(PROFILE, code, root / "translation" / code / "release.toml").output
            self.assertEqual(stem, f"Pokemon Unbound 2.1.1.1 [{code.upper()} v0.0.0 by gen3tl]")
            built = root / "build" / f"{stem}.gba"
            run("build", "rom", "--changes", "Seeded keyboard verification.")
            run("data", "pokedex", "--out", str(root / "build/pokedex" / PROFILE.name))
            run("web", "data", "--split")
            run("web", "snapshot")
            run("web", "data", "--no-rom", "--split")
            run("web", "registry")
            run("web", "site-catalog")
            run("web", "assemble", "--out", str(root / "site"))
            index = json.loads((root / "build/editor" / PROFILE.name / code / "index.json").read_text())
            self.assertEqual(index["language"], code)
            self.assertEqual(index["term_columns"]["translation"], "translation")
            self.assertEqual(index["language_rules"], {"fold": {}, "stand_ins": {}})
            patch_file = built.with_suffix(".ups")
            run("build", "patch", "--changes", "Seeded keyboard verification.")
            run("build", "patcher-data", "--built", str(built), "--patch-file", str(patch_file))
            releases = json.loads((root / "releases/releases.json").read_text())["releases"]
            self.assertEqual([(r["language"], r["output"]) for r in releases], [(code, f"{stem}.gba")])
            names = json.loads((root / "releases" / releases[0]["names"]).read_text())
            self.assertEqual(names["rules"]["transliteration"], {})
            save = root / "input.sav"
            save.write_bytes(blank_save(Layout.from_dict(PROFILE["save"])))
            converted = root / "output.sav"
            run("verify", "save-convert", str(save), str(converted), "--from-rom", str(rom_path()),
                "--to-rom", str(built), "--player-name", {"es": "Ñandú", "de": "Bär", "fr": "Élodie"}[code])
            self.assertEqual(len(converted.read_bytes()), len(save.read_bytes()))
            run("verify", "golden", "--record")
            self.assertIn("verified     passed", run("verify", "golden"))
            self.assertEqual(json.loads((root / "translation" / code / "golden.json").read_text())["language"], code)
