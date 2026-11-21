import json
import subprocess
import sys
import tempfile
import unittest
import shutil
from pathlib import Path
from unittest import mock

from gen3tl.web.pokedexshare import STAT_LABELS, TIER_LABELS, ShareGenerator, png_bytes
from gen3tl.web.siteassets import write_build, write_manifest

from rom_support import needs_rom
from test_roots import PROJECT_ROOT, TOOLKIT_ROOT

class ShareGeneratorTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.data = self.root / "data"
        sprite = self.data / "pokedex/game/sprites/sprites/978-front.png"
        sprite.parent.mkdir(parents=True)
        sprite.write_bytes(png_bytes(2, 2, bytearray((20, 40, 60, 255, 0, 0, 0, 0) * 2)))
        dataset = {
            "format": "gen3tl-pokedex", "schema": 1, "profile": {"id": "game"}, "count": 1,
            "species": [{"slot": 978, "dex": 761, "name": "species:978", "types": [12], "evolution": [],
                         "base_stats": {"hp": 42, "attack": 30, "defense": 38, "sp_attack": 30, "sp_defense": 38,
                                        "speed": 32},
                         "sprite": {"front": "sprites/978-front.png"}}],
            "types": [{"id": 12, "colour": "#78C850"}],
        }
        (self.data / "pokedex/game/pokedex.json").write_text(json.dumps(dataset), encoding="utf-8")
        manifest = {
            "profiles": [{"id": "game", "name": "Test game", "pokedex": "pokedex/game/pokedex.json",
                          "source_locale": "en_US"}],
            "languages": [{"profile": "game", "code": "ru", "texts": "game/ru/texts.json"}],
        }
        (self.data / "languages.json").write_text(json.dumps(manifest), encoding="utf-8")
        texts = {
            "schema": 1, "profile": "game", "language": "ru", "dataset": "pokedex/game/pokedex.json",
            "texts": {"species:978": ["Bounsweet", "Баунсвит"], "types:12": ["Grass", "Трава"]}, "page": {},
        }
        (self.data / "game/ru").mkdir(parents=True)
        (self.data / "game/ru/texts.json").write_text(json.dumps(texts, ensure_ascii=False), encoding="utf-8")

    def generate(self, name="site"):
        out = self.root / name
        result = ShareGenerator(self.data, out, "https://site.test", "game").generate()
        return out, result


    def test_stat_labels_and_tier_names_have_font_glyphs(self):
        generator = ShareGenerator(self.data, self.root / "glyphs", "https://site.test", "game")
        keys = [*STAT_LABELS.values(), "Total", *TIER_LABELS]
        # Profiles map these keys to literal symbols or game text.
        literal = list(keys)
        from gen3tl.profile.profile import Profile, profile_paths
        for path in profile_paths():
            symbols = Profile.load(path).get("pokedex", {}).get("labels", {}).get("symbols", {})
            literal += [symbols[key] for key in keys if isinstance(symbols.get(key), str)]
        self.assertIn("Σ", literal)
        self.assertEqual(sorted({char for value in literal for char in value} - set(generator.font["glyphs"])), [])


    def test_publication_check_requires_the_image_content_hash(self):
        script = PROJECT_ROOT / ".github/scripts/site-check.py"
        if not script.is_file():
            self.skipTest("project publication guard is absent from this checkout")
        site, _ = self.generate("checked")
        self.assertEqual(list((site / "share").rglob("manifest.json")), [])
        (site / "data").mkdir()
        (site / "data/languages.json").write_text("{}")
        write_manifest(site, "1.0.0")
        write_build(site, "1.0.0")
        command = [sys.executable, str(script), str(site)]
        self.assertEqual(subprocess.run(command, capture_output=True).returncode, 0)
        image = next((site / "share/assets").glob("*.png"))
        image.write_bytes(b"not a PNG")
        self.assertEqual(subprocess.run(command, capture_output=True).returncode, 1)


NODE = shutil.which("node")


PAGE_NAMES = '''
import fs from "node:fs";
import { displayName, formLabel, megaLetter, PokedexView } from "%s/pokedex/pokedex.js";
import { textEntry } from "%s/dexpage.js";
import { setCatalog, setLabelSource, setUiLanguage } from "%s/ui.js";
const { dataset, catalogs } = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const result = {};
for (const [language, doc] of Object.entries(catalogs)) {
  const view = Object.create(PokedexView.prototype);
  view.lang = language;
  view.texts = new Map(Object.keys(doc.texts).map((key) => [key, textEntry(doc, key)]));
  view.host = { data: () => dataset, pageLabels: () => doc.page };
  setUiLanguage(language);
  setCatalog(doc.site);
  setLabelSource((key) => view.label(key));
  const text = (key) => view.text(key);
  result[language] = dataset.species.map((record) => ({
    name: displayName(record, dataset.species, text),
    form: formLabel(record, dataset.species, text),
    mega: megaLetter(record, dataset.species, text),
    types: [...new Set(record.types)].map((id) => text(`types:${id}`)),
  }));
}
fs.writeFileSync(process.argv[3], JSON.stringify(result));
'''


def page_names(generator, root):
    script, source, out = root / "names.mjs", root / "names-in.json", root / "names-out.json"
    script.write_text(PAGE_NAMES % (((TOOLKIT_ROOT / "web/js").as_uri(),) * 3), encoding="utf-8")
    catalogs = {code: {"texts": texts, "page": generator.pages[code], "site": generator.site[code]}
                for code, texts in generator.texts.items()}
    source.write_text(json.dumps({"dataset": generator.dataset, "catalogs": catalogs}), encoding="utf-8")
    run = subprocess.run([NODE, str(script), str(source), str(out)], capture_output=True, text=True)
    if run.returncode:
        raise AssertionError(run.stderr)
    return json.loads(out.read_text(encoding="utf-8"))


@needs_rom
class ProjectShareNamesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from gen3tl.catalog.catalog import load_catalog
        from gen3tl.data import pokedextexts
        from gen3tl.profile.profile import Profile
        from gen3tl.project import REGISTRY, Registry, registry_root
        from gen3tl.web import sitecatalog

        if not (registry_root() / REGISTRY).is_file():
            raise FileNotFoundError(registry_root() / REGISTRY)
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.root = Path(cls.tmp.name)
        cls.data = cls.root / "data"
        manifest = {"profiles": [], "languages": []}
        cls.datasets = {}
        for project in Registry.load().projects:
            if project.stage != "translation":
                continue
            source = pokedextexts.tracked_dataset(project.profile)
            if source is None:
                raise FileNotFoundError(f"{project.profile}: project dataset is required")
            profile = project.load_profile().for_project(project.language)
            relative = f"pokedex/{profile.name}/pokedex.json"
            dataset = json.loads(source.read_text(encoding="utf-8"))
            if profile.name not in cls.datasets:
                cls.datasets[profile.name] = source.parent
                target = cls.data / relative
                target.parent.mkdir(parents=True)
                target.write_bytes(source.read_bytes())
                manifest["profiles"].append({"id": profile.name, "name": profile["rom"]["name"], "pokedex": relative})
            catalog = load_catalog(project.catalog, profile=profile)
            rows = [{"id": sid, "source_text": entry.msgid, "translation": entry.msgstr}
                    for sid, (_, entry) in catalog.items()]
            doc = {"schema": 1, "profile": profile.name, "language": project.language, "dataset": relative,
                   "texts": pokedextexts.select(dataset, rows),
                   "page": pokedextexts.page_labels(project.translation / "pokedex-labels.po")}
            path = cls.data / profile.name / project.language / "texts.json"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps(doc), encoding="utf-8")
            manifest["languages"].append({"profile": profile.name, "code": project.language,
                                          "texts": path.relative_to(cls.data).as_posix()})
        if not cls.datasets:
            raise AssertionError("project datasets are required")
        (cls.data / "languages.json").write_text(json.dumps(manifest), encoding="utf-8")
        sitecatalog.write(cls.data)

    @unittest.skipUnless(NODE, "no node")
    def test_every_species_and_form_matches_page_names_and_font_coverage(self):
        for profile, source in self.datasets.items():
            generator = ShareGenerator(self.data, self.root / "share", "https://site.test", profile)
            expected = page_names(generator, self.root)
            missing = set()
            with mock.patch.object(generator, "sprite_path", side_effect=lambda record: source / "sprites" / record["sprite"]["front"]), \
                    mock.patch("gen3tl.web.pokedexshare.Canvas") as canvas:
                for language, rows in expected.items():
                    for record, row in zip(generator.records, rows, strict=True):
                        with self.subTest(profile=profile, language=language, slot=record["slot"]):
                            species = generator.species(language, record)
                            self.assertEqual(species["name"], row["name"])
                            self.assertEqual([item["name"] for item in species["types"]], row["types"])
                            canvas.return_value.measure.return_value = 100
                            generator.image(species)
                            drawn = [call.args[2] for call in canvas.return_value.text.call_args_list]
                            self.assertIn(row["name"], drawn)
                            missing.update(char for value in drawn for char in value if char not in generator.font["glyphs"])
                            canvas.reset_mock()
            self.assertEqual(sorted(missing), [])
