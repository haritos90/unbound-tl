import json
import tempfile
import unittest
from pathlib import Path

from gen3tl.catalog.keys import copy_source
from gen3tl.web import editordata, snapshotstore
from gen3tl.web.editorimport import import_export, read_export

from rom_support import needs_rom
from project_fixture import UNBOUND, unbound

COPIES = {"s1F2CB27-light-of-ruin": ("map:1.51/mapscript:0/21", "Адепт", 29),
          "s1F2CB34-light-of-ruin": ("map:1.100/mapscript:0/18", "Адепт А", 6),
          "s1F2CB3C-light-of-ruin": ("map:1.101/npc:29/2", "Адепт Б", 4)}


@needs_rom
class ProjectTest(unittest.TestCase):
    """The declared groups of the project, read back from its tracked data."""

    def catalog(self, language):
        from gen3tl.catalog.catalog import load_catalog
        return load_catalog(UNBOUND / "translation" / language / "po", unbound(language))

    def test_catalog_and_seeded_languages(self):
        ru = self.catalog("ru")
        for sid, (key, word, _) in COPIES.items():
            _, e = ru[sid]
            self.assertEqual((e.msgctxt, e.msgstr, e.msgid), (key, word, ru[copy_source(sid)][1].msgid))
        es = self.catalog("es")
        self.assertTrue(all(es[sid][1].state == "original" for sid in COPIES))

    def test_snapshot_and_editor_context(self):
        snap = snapshotstore.load(UNBOUND / "source/snapshot/ru.snapshot.json")
        rows = {r["id"]: r for r in snap["inventory"]}
        for sid, (key, _, count) in COPIES.items():
            self.assertEqual((rows[sid]["flags"], len(rows[sid]["refs"])), (["copy"], count))
            ats = {at for at, _ in rows[sid]["refs"]}
            self.assertTrue(ats.isdisjoint(at for at, _ in rows[copy_source(sid)]["refs"]))
            self.assertTrue({u["at"] for u in snap["context"].get(sid, {"uses": []})["uses"]} <= ats)
        _, e = self.catalog("ru")["s1F2CB27-light-of-ruin"]
        ctx = editordata.context(e.extracted, {})
        self.assertEqual(ctx["uses"], 40)
        self.assertIn("group light-of-ruin of map:1.11/mapscript:0/0: own translation for these uses",
                      ctx["comments"])

    def test_import_of_a_group_entry(self):
        catalog = self.catalog("ru")
        prof = unbound("ru")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            export = root / "edits.json"
            export.write_text(json.dumps({"profile": prof.name, "language": "ru", "pictures": [], "terms": [],
                                          "entries": [{"id": "map:1.51/mapscript:0/21", "translation": "Агент",
                                                       "note": ""}]}), encoding="utf-8")
            data = read_export(export, prof.name, "ru", prof.sha1, catalog)
            (root / "plan.json").write_text("[]")
            result = import_export(data, UNBOUND / "translation/ru/po", root / "batches", root / "plan.json", {})
            batch = root / "batches" / result["batches"][0]["name"]
            self.assertEqual(json.loads((batch / "translation.json").read_text(encoding="utf-8")),
                             {"map:1.51/mapscript:0/21": "Агент"})
