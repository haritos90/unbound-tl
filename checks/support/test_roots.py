"""Explicit roots for project checks and helpers."""
import os
from pathlib import Path

from gen3tl import TOOLKIT_ROOT
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = Path(os.environ.get("GEN3TL_UNBOUND_PROJECT", REPOSITORY_ROOT))
TEST_ROOT = Path(__file__).resolve().parents[1]
SUPPORT_ROOT = TEST_ROOT / "support"


def project_profile(root, profile):
    """Keep temporary project inputs local."""
    import shutil
    destination = root / "profile"
    shutil.copytree(profile, destination)
    return destination
