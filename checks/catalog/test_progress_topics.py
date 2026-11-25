"""Every catalog file of the project counts under a named progress topic."""

import tempfile
import unittest
from pathlib import Path

from gen3tl.catalog import progress
from gen3tl.catalog.catalog import load_catalog
from gen3tl.catalog.po import PoEntry, write
from gen3tl.project import MANIFEST, Manifest

from project_fixture import UNBOUND, needs_unbound, unbound


def untopiced(po_root: Path, prof) -> list[str]:
    """Catalog files that the progress table lists by their file name."""
    files = progress.file_topics(prof)
    named = (set(progress.TABLE_TOPICS.values()) | set(progress.GROUP_TOPICS.values()) | set(files.values())
             | {progress.INTERFACE, progress.OTHER})
    out = set()
    for path, entry in load_catalog(po_root, english=False).values():
        rel = Path(path).relative_to(po_root)
        if progress.topic_of(rel, entry.extracted, files) not in named:
            out.add(rel.as_posix())
    return sorted(out)


@needs_unbound
class ProgressTopicsTest(unittest.TestCase):
    def test_every_catalog_file_has_a_topic(self):
        for code in Manifest.read(UNBOUND / MANIFEST).languages:
            with self.subTest(language=code):
                self.assertEqual(untopiced(UNBOUND / "translation" / code / "po", unbound(code)), [])

    def test_a_table_without_a_topic_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("species", "item_plural_s", "unlisted"):
                write(root / "tables" / f"{name}.po", [PoEntry(f"{name}:0", "Potion", "")], {})
            self.assertEqual(untopiced(root, unbound("ru")), ["tables/unlisted.po"])


if __name__ == "__main__":
    unittest.main()
