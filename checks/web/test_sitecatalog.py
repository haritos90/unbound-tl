import html
import json
import tempfile
import unittest
from pathlib import Path

from gen3tl.web import sitecatalog
from gen3tl.catalog.po import PoEntry, read, write

def catalog(code: str, entries: list[PoEntry], directory: Path) -> Path:
    path = directory / f"{code}.po"
    write(path, entries, {"Project-Id-Version": "site", "Language": code,
                          "Content-Type": "text/plain; charset=UTF-8"})
    return path

def site(root: Path) -> Path:
    """A small site: a page, a module and its catalogs' directory."""
    web = root / "web"
    (web / "js").mkdir(parents=True)
    (web / "i18n").mkdir()
    (web / "index.html").write_text('<html><head><title data-ui="Home">Home</title></head><body>'
                                    '<p data-ui="Kept &amp; used">Kept &amp; used</p></body></html>', encoding="utf-8")
    (web / "js" / "page.js").write_text('// t("Commented out")\nshow(t("Loading {game}…", { game }));\n'
                                        'const KEPT = N_("Kept & used");\n', encoding="utf-8")
    return web

class SyncTest(unittest.TestCase):
    """The sync brings each catalog to the keys of the pages; lang init seeds a new one."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.web = site(Path(self.tmp.name))

    def test_shell_slots_keep_guide_labels_separate_from_document_text(self):
        (self.web / "guide.html").write_text(
            '<header class="mast" data-site-mast=""><nav><a data-ui="Home">Home</a></nav></header>'
            '<main><p data-ui="Document text">Document text</p></main>'
            '<footer class="foot" data-site-footer="static"><a data-ui="Licence">Licence</a></footer>',
            encoding="utf-8")
        keys = sitecatalog.page_keys(self.web)
        self.assertEqual(keys["Home"], ["index.html", "guide.html"])
        self.assertEqual(keys["Licence"], ["guide.html"])
        self.assertNotIn("Document text", keys)

    def test_site_marks_accept_bare_and_quoted_attributes(self):
        (self.web / "pokedex.html").write_text(
            '<main><span data-ui="Bare" data-ui-site>Bare</span>'
            '<span data-ui="Quoted" data-ui-site="">Quoted</span>'
            '<span data-ui="Game label">Game label</span></main>', encoding="utf-8")
        keys = sitecatalog.page_keys(self.web)
        self.assertEqual(keys["Bare"], ["pokedex.html"])
        self.assertEqual(keys["Quoted"], ["pokedex.html"])
        self.assertNotIn("Game label", keys)


    def test_keys_are_added_kept_and_dropped(self):
        catalog("xx", [PoEntry("site:Stale", "Stale", "Старое", extracted=["index.html"]),
                       PoEntry("site:Kept & used", "Kept & used", "Оставлено", extracted=["js/gone.js", "a note"],
                               translator=["source: project style rules"], flags=["fuzzy"])], self.web / "i18n")
        self.assertEqual(sitecatalog.page_keys(self.web),
                         {"Home": ["index.html"], "Kept & used": ["index.html", "js/page.js"],
                          "Loading {game}…": ["js/page.js"]})
        [synced] = sitecatalog.sync(self.web / "i18n", self.web)
        self.assertEqual((synced.added, synced.dropped, synced.keys), (["Home", "Loading {game}…"], ["Stale"], 3))
        entries = sitecatalog.load(self.web / "i18n" / "xx.po")
        self.assertEqual([(e.msgid, e.msgstr, e.extracted) for e in entries],
                         [("Kept & used", "Оставлено", ["a note", "index.html, js/page.js"]),
                          ("Home", "", ["index.html"]), ("Loading {game}…", "", ["js/page.js"])])
        self.assertEqual((entries[0].source_note, entries[0].flags), ("project style rules", ["fuzzy"]))
        before = (self.web / "i18n" / "xx.po").read_bytes()
        [again] = sitecatalog.sync(self.web / "i18n", self.web)
        self.assertEqual((again.added, again.dropped), ([], []))
        self.assertEqual((self.web / "i18n" / "xx.po").read_bytes(), before)

    def test_a_new_language_starts_with_every_key_empty(self):
        path = sitecatalog.seed("yy", self.web / "i18n", self.web)
        self.assertEqual(path, self.web / "i18n" / "yy.po")
        self.assertEqual([(e.msgid, e.msgstr) for e in sitecatalog.load(path)],
                         [("Home", ""), ("Kept & used", ""), ("Loading {game}…", "")])
        header, entries = read(path)
        self.assertEqual((header["Project-Id-Version"], header["Language"]), ("site", "yy"))
        entries[0].msgstr = "Дом"
        write(path, entries, header)
        before = path.read_bytes()
        self.assertIsNone(sitecatalog.seed("yy", self.web / "i18n", self.web))
        self.assertEqual(path.read_bytes(), before)
        with self.assertRaisesRegex(sitecatalog.SiteCatalogError, "not a language code"):
            sitecatalog.seed("Not a code", self.web / "i18n", self.web)


class CompletenessTest(unittest.TestCase):
    """Every key the pages show has a translation in every site catalog; no catalog keeps a stale key."""

    def test_the_collector_sees_the_pages(self):
        keys = sitecatalog.page_keys()
        self.assertGreater(len(keys), 400)
        for key in ("Patch", "Site and game language", "Toggle dark mode", "Play Pokémon ROM hacks in your language.",
                    "{by} letter over the {limit} the game allows", "{by} letters over the {limit} the game allows"):
            self.assertIn(key, keys)
        self.assertNotIn("Base stats", keys)   # a Pokédex label: a game string

    def test_a_translated_guide_is_listed_and_guide_families_share_chrome(self):
        self.assertIn("ru", sitecatalog.guides())
        keys = sitecatalog.page_keys()
        self.assertIn("guide.html", keys["Contributor guide"])
        self.assertFalse([key for key, where in keys.items() if any(sitecatalog.GUIDE.fullmatch(w) for w in where)])
        with tempfile.TemporaryDirectory() as tmp:
            web = site(Path(tmp))
            for name in ("guide.yy.html", "save-guide.html", "save-guide.yy.html"):
                (web / name).write_text('<html><head><title data-ui="Only here">Тут</title></head></html>',
                                       encoding="utf-8")
            self.assertNotIn("Only here", sitecatalog.page_keys(web))
            self.assertEqual(sitecatalog.guides(web), ["yy"])

    def test_every_catalog_translates_every_key(self):
        keys = sitecatalog.page_keys()
        codes = sitecatalog.catalogs()
        self.assertIn("ru", codes)
        for code, path in codes.items():
            with self.subTest(code=code):
                entries = sitecatalog.load(path)
                have = {e.msgid: e for e in entries}
                self.assertEqual(sorted(k for k in keys if k not in have), [])
                self.assertEqual(sorted(k for k in have if k not in keys), [])
                self.assertEqual(sorted(k for k, e in have.items() if not e.msgstr), [])

    def test_location_comments_name_the_files_that_use_each_key(self):
        keys = sitecatalog.page_keys()
        for code, path in sitecatalog.catalogs().items():
            for entry in sitecatalog.load(path):
                with self.subTest(code=code, key=entry.msgid):
                    where = [c for c in entry.extracted if sitecatalog.is_location(c)]
                    self.assertEqual(where, [sitecatalog.location(keys.get(entry.msgid, []))])
                    forms = {entry.msgid, html.escape(entry.msgid), html.escape(entry.msgid, quote=False),
                             json.dumps(entry.msgid, ensure_ascii=False)[1:-1]}
                    for name in where[0].split(", "):
                        if name == "registry":
                            continue
                        source = (sitecatalog.WEB / name).read_text(encoding="utf-8")
                        self.assertTrue(any(form in source for form in forms), f"{name} does not hold the key")
