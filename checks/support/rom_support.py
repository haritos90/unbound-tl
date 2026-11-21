"""Optional base-ROM inputs for the project checks."""

import functools
import os
from pathlib import Path
import subprocess
import sys
import unittest

from test_roots import PROJECT_ROOT

ROM_REASON = "needs the base ROM: pass --rom"


def needs_rom(test):
    """Skip each ROM-dependent test before its fixtures run."""
    return unittest.skipUnless(os.environ.get("GEN3TL_TEST_ROM"), ROM_REASON)(test)


def rom_path():
    """Resolve the explicit input without probing unrelated directories."""
    value = os.environ.get("GEN3TL_TEST_ROM")
    if not value:
        raise unittest.SkipTest(ROM_REASON)
    path = Path(value).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"ROM: {path}")
    return path


@functools.cache
def source_text(sid):
    """Read an original expectation from the generated source catalog."""
    from gen3tl.catalog import keys
    from gen3tl.profile.profile import Profile

    profile = Profile.load(PROJECT_ROOT / "profile")
    alias = keys.for_profile(profile)
    return _source_catalog()[alias.key(sid)]


@functools.cache
def _source_catalog():
    from gen3tl.catalog import po

    return {entry.msgctxt: entry.msgid
            for entry in po.read(PROJECT_ROOT / "build/catalog.pot")[1]}


def prepare_inputs():
    """Generate missing discovery inputs using the public commands."""
    from gen3tl.profile.profile import Profile

    path = rom_path()
    Profile.load(PROJECT_ROOT / "profile").load_rom(path)
    required = ("inventory.json", "context.json", "reach.json", "catalog.pot")
    if all((PROJECT_ROOT / "build" / name).is_file() for name in required):
        return
    prefix = [sys.executable, "-m", "gen3tl", "--project-root", str(PROJECT_ROOT), "--rom", str(path)]
    for command in (("discover", "inventory"), ("discover", "context"),
                    ("discover", "reach"), ("catalog", "extract")):
        subprocess.run([*prefix, *command], cwd=PROJECT_ROOT, check=True)
