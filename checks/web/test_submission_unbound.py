from test_roots import TOOLKIT_ROOT
"""Submission unbound checks and fixtures."""

import sys
from pathlib import Path
import json
import unittest

sys.path.insert(0, str(TOOLKIT_ROOT / "src"))

from gen3tl.web import submission

from project_fixture import needs_unbound, unbound


@needs_unbound
class ProjectPicturesTest(unittest.TestCase):
    """The pictures of the Unbound policy, as a submission would bring them again."""

    def test_each_project_picture_passes_and_rewrites_its_entry_in_place(self):
        from gen3tl.build.graphics import GraphicsConfig, area_check
        from gen3tl.check.render import read_png_image
        prof = unbound()
        cfg = GraphicsConfig.from_profile(prof)
        text = prof.policy_path.read_text(encoding="utf-8")
        edits = [e for e in prof["graphics"]["edit"] if "png" in e]
        self.assertGreater(len(edits), 30)
        for e in edits:
            with self.subTest(graphic=e["id"]):
                entry = {k: e[k] for k in ("id", "png", "form", "areas", "tiles") if k in e}
                self.assertEqual(submission.policy_with(text, entry), text)
                img = read_png_image(cfg.root / e["png"])
                self.assertEqual(area_check(cfg, e["id"], img, e["areas"], e.get("tiles")), [])
        moved = submission.policy_with(text, {**entry, "areas": [[0, 0, 8, 8]]}).split("\n")
        self.assertEqual([n for n, (a, b) in enumerate(zip(text.split("\n"), moved)) if a != b],
                         [text.split("\n").index(f"areas = {json.dumps(entry['areas'])}")])
