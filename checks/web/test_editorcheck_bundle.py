import sys
from pathlib import Path
import ast
import json
import subprocess
import tempfile
import unittest
import zipfile

from gen3tl.web import editorcheck

from editorcheck_support import PROF

class BundleTest(unittest.TestCase):
    """The bundle: the modules the check imports and the profile rules."""


    def test_modules_closed_and_reproducible(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp) / "a.zip", Path(tmp) / "b.zip"
            names = editorcheck.write_bundle(a, PROF["qa"])
            editorcheck.write_bundle(b, PROF["qa"])
            self.assertEqual(a.read_bytes(), b.read_bytes())
            self.assertEqual(names[:len(editorcheck.BUNDLE)], [f"gen3tl/{n}" for n in editorcheck.BUNDLE])
            self.assertEqual(names[-1], "rules.json")
            self.assertEqual(names[-2], "save_layouts.json")
            self.assertTrue(all(n.startswith("assets/lang/") and n.endswith((".json", ".py"))
                                for n in names[len(editorcheck.BUNDLE):-2]))
            with zipfile.ZipFile(a) as z:
                self.assertEqual(json.loads(z.read("rules.json")), PROF["qa"])
                self.assertIn("unbound-2.1.1.1", json.loads(z.read("save_layouts.json")))
                self.assertFalse(any(n.startswith(("families/", "profiles/", "gen3tl/share/"))
                                     for n in z.namelist()))
                bundled = {n[:-3].removesuffix("/__init__").replace("/", ".") for n in z.namelist()
                           if n.startswith("gen3tl/") and n.endswith(".py")}
                # names a bundled package's __init__ binds, beside its modules
                bound = {f"{n[:-12].replace('/', '.')}.{target.id}" for n in z.namelist() if n.endswith("/__init__.py")
                         for node in ast.parse(z.read(n)).body if isinstance(node, ast.Assign)
                         for target in node.targets if isinstance(target, ast.Name)}
                for n in z.namelist():
                    if not n.startswith("gen3tl/") or not n.endswith(".py"):
                        continue
                    package = n[:-3].replace("/", ".").split(".")[:-1]
                    for node in ast.walk(ast.parse(z.read(n))):
                        if isinstance(node, ast.ImportFrom) and node.level:
                            base = ".".join(package[:len(package) - node.level + 1])
                            if node.module:
                                self.assertIn(f"{base}.{node.module}", bundled, n)
                            for alias in [] if node.module else node.names:
                                if not alias.name.startswith("__"):
                                    self.assertIn(f"{base}.{alias.name}", bundled | bound, n)
                z.extractall(tmp)
            # bundle alone on sys.path: no qa
            code = ("import sys; sys.path.insert(0, sys.argv[1]); import gen3tl.web.editorcheck as c; "
                    "print(c.__file__.startswith(sys.argv[1]));\n"
                    "try:\n import gen3tl.check.qa\nexcept ImportError:\n print('no qa')")
            run = subprocess.run([sys.executable, "-I", "-c", code, tmp], capture_output=True, text=True)
            self.assertEqual((run.stdout.split(), run.stderr), (["True", "no", "qa"], ""))
