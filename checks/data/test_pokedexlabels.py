import re
import unittest

from gen3tl.data import pokedexdata, pokedexlabels, pokedextexts
from gen3tl.profile.profile import Profile, TOOLKIT_ROOT

from rom_support import needs_rom, rom_path
from project_fixture import UNBOUND, unbound

def page_markup_keys(html):
    site = re.compile(r'<head>.*?</head>|<header class="mast"[^>]*>.*?</header>'
                      r'|<footer class="foot"[^>]*>.*?</footer>', re.S)
    markup = re.compile(r'data-ui(?:-placeholder|-title|-label)?="([^"]+)"')
    tags = re.findall(r"<[a-z][^>]*>", site.sub("", html))
    marked = [tag for tag in tags if re.search(r"\sdata-ui-site[\s=>]", tag)]
    keys = set(markup.findall("".join(tag for tag in tags if tag not in marked)))
    chrome = set(markup.findall("".join(site.findall(html)) + "".join(marked)))
    return keys, chrome

class UnboundLabelsTest(unittest.TestCase):
    """The inventory of the Unbound profile covers the page."""

    @classmethod
    def setUpClass(cls):
        cls.block = unbound()["pokedex"]["labels"]

    def test_template_is_shared_without_changing_profile_facts(self):
        from gen3tl.project import Registry
        profile = unbound()
        raw = Profile.load(profile.path)["pokedex"]["labels"]
        self.assertNotIn("unmapped", raw)
        for project in Registry.load(UNBOUND).projects:
            if project.profile == profile.name and project.stage == "translation":
                with self.subTest(language=project.language):
                    loaded = pokedexlabels.load(raw, project.pokedex_labels)
                    self.assertEqual(loaded, self.block)
                    self.assertEqual(unbound(project.language)["pokedex"]["labels"], loaded)

    def test_the_block_is_consistent(self):
        self.assertEqual(pokedexlabels.check(self.block), [])
        self.assertGreater(len(self.block["strings"]), 100)
        for key, reason in self.block["unmapped"].items():
            self.assertTrue(reason.strip(), key)


    def test_every_page_key_is_inventoried_once(self):
        html = (TOOLKIT_ROOT / "web" / "pokedex.html").read_text(encoding="utf-8")
        keys, chrome = page_markup_keys(html)
        for name in ("pokedex", "pokedexdataview", "typechart", "dexpage", "movecard", "pokedexexplorer"):
            base = TOOLKIT_ROOT / "web" / "js"
            # A feature folder replaces a single script.
            paths = sorted((base / name).glob("*.js")) if (base / name).is_dir() else [base / f"{name}.js"]
            src = "\n".join(path.read_text(encoding="utf-8") for path in paths)
            src = "\n".join(line for line in src.split("\n") if not re.match(r"\s*//", line))   # skip commented lines
            keys.update(m.group(1) for m in re.finditer(r'\bt\("((?:[^"\\]|\\.)*)"', src))
            chrome.update(m.group(1) for m in re.finditer(r'\bsiteText\("((?:[^"\\]|\\.)*)"', src))
        inventory = pokedexlabels.build(self.block)
        self.assertEqual(sorted(k for k in keys if k not in inventory), [])
        self.assertGreater(len(chrome), 20)
        self.assertTrue({"List", "Pokedex data record", "Loading {language}…"} <= chrome)
        # head, masthead, marked elements and siteText calls read it
        self.assertEqual(sorted(k for k in chrome - keys if k in inventory), [])
        # ui.test.mjs enumerates the module label tables

    def test_the_label_catalog_translates_every_user_facing_key_without_a_game_string(self):
        """Each project's pokedex-labels.po covers the unmapped keys the page shows."""
        from gen3tl.catalog.po import read
        from gen3tl.project import Registry
        hidden = {"technical record"}
        wanted = {key for key, reason in self.block["unmapped"].items() if reason not in hidden}
        self.assertIn("Flags", wanted)   # the move card's property row is user-facing
        self.assertTrue({"Technical record", "Icon", "Effect"} <= wanted)   # visible card labels
        self.assertNotIn("Effect id", wanted)   # the record's rows stay English
        projects = [p for p in Registry.load(UNBOUND).projects
                    if p.profile == "unbound-2.1.1.1" and p.stage == "translation"]
        self.assertGreater(len(projects), 1)
        for project in projects:
            with self.subTest(language=project.language):
                header, entries = read(project.translation / "pokedex-labels.po")
                self.assertEqual(header.get("Language"), project.language)
                keyed = ("page:power:", "page:effect:", "page:mechanics:")
                catalog = {e.msgctxt if e.msgctxt.startswith(keyed) else e.msgid: e.msgstr
                           for e in entries}
                self.assertEqual(len(catalog), len(entries))   # one entry per key
                self.assertEqual(sorted(wanted - catalog.keys()), [])
                self.assertEqual(sorted(catalog.keys() - wanted), [])   # no stale entries
                self.assertEqual([key for key, text in catalog.items() if not text.strip()
                                  and not (project.language != "ru" and key.startswith("page:mechanics:"))], [])
                self.assertTrue(all(e.msgctxt.startswith(keyed) or e.msgctxt == f"page:{e.msgid}"
                                    for e in entries))
                # the page fills the same placeholders
                slots = re.compile(r"\{[a-z0-9]+\}")
                self.assertEqual([entry.msgctxt for entry in entries if entry.msgstr
                                  and sorted(slots.findall(entry.msgstr)) != sorted(slots.findall(entry.msgid))], [])

    def test_joined_item_use_label_has_translations_and_shared_guidance(self):
        from gen3tl.catalog.po import read
        from gen3tl.project import Registry

        key = "Use {item}"
        reason = self.block["unmapped"][key]
        self.assertNotIn(key, self.block["symbols"])
        self.assertIn("beside another condition", reason)
        self.assertIn("item name unchanged", reason)
        notes = None
        profile = unbound().name
        for project in Registry.load(UNBOUND).projects:
            if project.profile != profile or project.stage != "translation":
                continue
            entries = {entry.msgctxt: entry for entry in read(project.translation / "pokedex-labels.po")[1]}
            entry = entries[f"page:{key}"]
            self.assertEqual(entry.msgid, key)
            self.assertTrue(entry.msgstr.strip())
            self.assertEqual(entry.extracted, [f"no game string: {reason}"])
            if notes is not None:
                self.assertEqual(entry.extracted, notes)
            notes = entry.extracted

    def test_item_condition_labels_have_translations_and_shared_guidance(self):
        from gen3tl.catalog.po import read
        from gen3tl.project import Registry

        profile = unbound()
        amounts = profile["pokedex"]["items"]["held_effects"]["amounts"].values()
        keys = {key for amount in amounts if amount.get("conditions") or amount.get("levels")
                for key in (amount["key"], *amount.get("conditions", []),
                            *(row["key"] for row in amount.get("upgrade_sources", [])))}
        keys.update(("Exchange", "Possible rewards"))
        uses = profile["pokedex"]["items"]["uses"]
        keys.update(key for name in ("rows", "recipes", "tutors", "prices")
                    for row in uses.get(name, []) for key in row.get("conditions", []))
        keys.add("Per item")
        self.assertTrue(keys)
        self.assertTrue(keys <= self.block["unmapped"].keys())
        guidance = None
        for project in Registry.load(UNBOUND).projects:
            if project.profile != profile.name or project.stage != "translation":
                continue
            entries = {entry.msgid: entry for entry in read(project.translation / "pokedex-labels.po")[1]}
            notes = {key: entries[key].extracted for key in keys}
            self.assertTrue(all(entries[key].msgstr.strip() for key in keys))
            self.assertTrue(all(notes.values()))
            if guidance is not None:
                self.assertEqual(notes, guidance)
            guidance = notes

    def test_trainer_condition_labels_share_guidance_across_languages(self):
        from gen3tl.catalog.po import read
        from gen3tl.project import Registry

        profile = unbound()
        keys = {row[key] for row in profile["pokedex"]["trainers"]["evs"]["conditions"]
                for key in ("set", "clear") if key in row}
        keys.add("Unresolved conditions")
        notes = None
        for project in Registry.load(UNBOUND).projects:
            if project.profile != profile.name or project.stage != "translation":
                continue
            entries = {entry.msgid: entry for entry in read(project.translation / "pokedex-labels.po")[1]}
            current = {key: entries[key].extracted for key in keys}
            self.assertTrue(all(current.values()))
            self.assertTrue(all(entries[key].msgstr.strip() for key in keys))
            if notes is not None:
                self.assertEqual(current, notes)
            notes = current

    def test_standalone_catalog_labels_start_with_capitals(self):
        from gen3tl.catalog.po import read
        from gen3tl.project import Registry

        fragments = {"shallow water", "in {map}", "with {item}", " with friendship",
                     " · source shown where untranslated", " (the first ability stands in for an empty slot)", "(one map)"}
        formulas = {"page:power:return", "page:power:frustration"}
        for project in Registry.load(UNBOUND).projects:
            if project.stage != "translation":
                continue
            _, entries = read(project.translation / "pokedex-labels.po")
            for entry in entries:
                for text in (entry.msgid, entry.msgstr):
                    if entry.msgctxt in formulas and text.startswith("floor("):
                        continue
                    initial = text.lstrip(" \t·(«“\"'")[:1]
                    if initial.islower():
                        self.assertIn(entry.msgid, fragments, (project.language, entry.msgctxt, text))
            labels = {entry.msgid: entry.msgstr for entry in entries}
            for key in ("Between", "Evening", "Pokédollar"):
                self.assertTrue(labels[key][:1].isupper(), (project.language, key))
            self.assertNotIn("between", labels)
            self.assertNotIn("evening", labels)

    def test_mechanics_keys_keep_english_fallback_and_branch_guidance(self):
        mechanics = Profile.by_name("unbound-2.1.1.1")["pokedex"]["moves"]["mechanics"]["174"]
        keys = {mechanics["summary"]}
        for row in mechanics["rows"]:
            keys.update((row["condition"], row["effect"], *row.get("notes", [])))
        self.assertEqual(len(keys), 9)
        sources = None
        for lang in ("ru", "es", "de", "fr"):
            from gen3tl.catalog.po import read
            path = UNBOUND / "translation" / lang / "pokedex-labels.po"
            page = pokedextexts.page_labels(path)
            selected = {key: page[key] for key in keys}
            self.assertTrue(all(len(row) == 2 and row[0] for row in selected.values()))
            english = {key: row[0] for key, row in selected.items()}
            if sources is not None:
                self.assertEqual(english, sources)
            sources = english
            self.assertTrue(all(bool(row[1]) == (lang == "ru") for row in selected.values()))
            entries = {entry.msgctxt: entry for entry in read(path)[1]}
            self.assertTrue(all(entries[key].extracted for key in keys))

    def test_formula_keys_resolve_authored_english_and_all_translations(self):
        block = Profile.by_name("unbound-2.1.1.1")["pokedex"]["moves"]["power"]
        conditions = {row["condition"] for item in block.values() for row in item.get("tiers", [])}
        self.assertEqual(len(conditions), 28)
        self.assertTrue(conditions <= self.block["unmapped"].keys())
        english = None
        for lang in ("ru", "es", "de", "fr"):
            page = pokedextexts.page_labels(UNBOUND / "translation" / lang / "pokedex-labels.po")
            formulas = {item["formula"]: page[item["formula"]] for item in block.values()}
            formulas.update({key: page[key] for key in conditions})
            self.assertTrue(all(len(texts) == 2 and all(texts) for texts in formulas.values()))
            sources = {key: texts[0] for key, texts in formulas.items()}
            if english is not None:
                self.assertEqual(sources, english)
            english = sources
        self.assertIn("(255 − friendship)", english["page:power:frustration"])
        self.assertEqual(english["page:power:cond:weight_under_10"], "Target weight under 10 kg")
        self.assertIn("1/24", english["page:power:cond:hp_under_1_24"])

    def test_effect_keys_resolve_authored_english_and_all_translations(self):
        module = (TOOLKIT_ROOT / "web/js/moveeffects.js").read_text().split("};", 1)[0]
        effects = re.findall(r'\d+: "([^"]+)"', module)
        self.assertEqual(len(effects), 249)
        wanted = {f"page:effect:{key}" for key in effects}
        overrides = unbound()["pokedex"]["moves"]["effect_overrides"]
        wanted.update(f"page:effect:{rule['key']}" for rule in overrides.values())
        self.assertTrue(wanted <= self.block["unmapped"].keys())
        self.assertTrue(all("User-facing" in self.block["unmapped"][key] for key in wanted))
        english = None
        for lang in ("ru", "es", "de", "fr"):
            page = pokedextexts.page_labels(UNBOUND / "translation" / lang / "pokedex-labels.po")
            labels = {key: page[key] for key in wanted}
            self.assertTrue(all(len(texts) == 2 and all(texts) for texts in labels.values()))
            sources = {key: texts[0] for key, texts in labels.items()}
            if english is not None:
                self.assertEqual(sources, english)
            english = sources
            if lang == "ru":
                self.assertEqual(labels["page:effect:poison_hit"][1], "Удар с отравлением")
                self.assertEqual(labels["page:effect:freeze_hit"][1], "Удар с обморожением")
                self.assertIn("Особой атаки", labels["page:effect:special_attack_up"][1])
        self.assertEqual(english["page:effect:freeze_hit"], "Frostbite hit")
        self.assertEqual(english["page:effect:eat_berry"], "Berry/Gem removal")
        self.assertEqual(english["page:effect:attack_blockers"], "Temporary target effects")
        self.assertEqual(english["page:effect:damage_set_terrain"], "Damage and terrain change")


    def test_difficulty_label_uses_the_page_catalogs(self):
        from gen3tl.catalog.po import read
        self.assertNotIn("Difficulty", self.block["strings"])
        self.assertIn("Difficulty", self.block["unmapped"])
        expected = {"ru": "Сложность", "es": "Dificultad", "de": "Schwierigkeit", "fr": "Difficulté"}
        for language, translated in expected.items():
            with self.subTest(language=language):
                _, entries = read(UNBOUND / "translation" / language / "pokedex-labels.po")
                labels = {entry.msgctxt: entry.msgstr for entry in entries}
                self.assertEqual(labels["page:Difficulty"], translated)
        _, entries = read(UNBOUND / "translation" / "ru" / "po" / "system" / "region-0A40000.po")
        source = {entry.msgctxt: entry for entry in entries}["hash:c1a6500b"]
        self.assertEqual(source.msgstr, "")
        self.assertIn("empty", source.flags)

    def test_season_form_labels_are_nominative_in_every_language(self):
        expected = {
            "ru": ["Весенняя форма", "Летняя форма", "Осенняя форма", "Зимняя форма"],
            "es": ["Forma Primavera", "Forma Verano", "Forma Otoño", "Forma Invierno"],
            "de": ["Frühlingsform", "Sommerform", "Herbstform", "Winterform"],
            "fr": ["Forme Printemps", "Forme Été", "Forme Automne", "Forme Hiver"],
        }
        names = ["Spring Form", "Summer Form", "Autumn Form", "Winter Form"]
        for language, translated in expected.items():
            with self.subTest(language=language):
                page = pokedextexts.page_labels(UNBOUND / "translation" / language / "pokedex-labels.po")
                self.assertEqual([page[name] for name in names], translated)

    def test_formes_heading_uses_the_standalone_page_catalog(self):
        from gen3tl.catalog.po import read
        self.assertNotIn("Forme", self.block["strings"])
        self.assertEqual(self.block["unmapped"]["Formes"],
                         "Standalone section heading; no game string labels the form list.")
        expected = {"ru": "Формы", "es": "Formas", "de": "Formen", "fr": "Formes"}
        for language, translated in expected.items():
            with self.subTest(language=language):
                _, entries = read(UNBOUND / "translation" / language / "pokedex-labels.po")
                labels = {entry.msgctxt: entry.msgstr for entry in entries}
                self.assertEqual(labels["page:Formes"], translated)
                self.assertNotIn("page:Forme", labels)

    def test_the_tracked_dataset_matches_the_profile(self):
        data = pokedexdata.read(UNBOUND / "data" / "pokedex" / "pokedex.json")
        self.assertEqual(data["labels"], pokedexlabels.build(self.block))


    @needs_rom
    def test_encounter_labels_reuse_catalog_text_and_shared_guidance_in_every_project(self):
        from gen3tl.catalog import catalog, guidance
        from gen3tl.project import Registry

        profile = unbound()
        declarations = profile["pokedex"]["encounters"]["method_labels"]
        names = {name for row in declarations for name in row["labels"]} - {"Surfing", "Alternate grass"}
        self.assertEqual(len(names), 7)
        labels = {name: self.block["strings"][name] for name in names}
        for project in Registry.load(UNBOUND).projects:
            if project.profile != profile.name or project.stage != "translation":
                continue
            with self.subTest(language=project.language):
                effective = unbound(project.language)
                entries = catalog.load_catalog(project.catalog, profile=effective)
                notes = guidance.entry_notes(effective, entries)
                selected = [{"id": sid, "source_text": entries[sid][1].msgid,
                             "translation": entries[sid][1].msgstr} for sid in labels.values()]
                texts = pokedextexts.select({"labels": labels}, selected)
                for name, sid in labels.items():
                    self.assertEqual(texts[sid], [name, entries[sid][1].msgstr])
                    self.assertTrue(notes[sid][0]["text"])
                page = pokedextexts.page_labels(project.translation / "pokedex-labels.po")
                self.assertTrue(page["Alternate grass"])


    @needs_rom
    def test_stat_stage_guidance_is_shared_across_language_projects(self):
        from gen3tl.catalog import catalog, guidance, keys
        from gen3tl.project import Registry

        expected = {51, 81, 107, 230, 294, 439, 452, 477, 480, 483, 491, 530, 557}
        shared = None
        profile_name = unbound().name
        for project in Registry.load(UNBOUND).projects:
            if project.profile != profile_name or project.stage != "translation":
                continue
            profile = unbound(project.language)
            entries = catalog.load_catalog(project.catalog, profile=profile)
            notes = guidance.entry_notes(profile, entries)
            aliases = keys.for_profile(profile)
            selected = {number: notes[aliases.entry_id(f"table:moves/{number}/description")]
                        for number in expected}
            if shared is not None:
                self.assertEqual(selected, shared)
            shared = selected
        self.assertIn("three stages", shared[294][0]["text"])
        self.assertIn("three stages", shared[439][0]["text"])


    @needs_rom
    def test_difficulty_labels_resolve_the_game_options(self):
        from gen3tl.catalog import keys
        from gen3tl.catalog.po import read
        from gen3tl.core.charmap import Charmap
        profile = Profile.by_name("unbound-2.1.1.1")
        rom = profile.load_rom(rom_path())
        aliases = keys.load(profile.sha1, UNBOUND)
        strings = self.block["strings"]
        translations = {}
        for name in ("frozen-heights", "battle-frontier"):
            _, entries = read(UNBOUND / "translation" / "ru" / "po" / "maps" / f"{name}.po")
            translations.update({entry.msgctxt: entry.msgstr for entry in entries})
        for label, offset, key, translated in (
            ("Difficult", 0x1F10621, 23, "Сложный"),
            ("Vanilla", 0x1F10630, 22, "Обычный"),
            ("Expert", 0x1F1063D, 24, "Эксперт"),
            ("Insane", 0x1F10644, 25, "Безумный"),
        ):
            with self.subTest(label=label):
                self.assertEqual(strings[label], f"s{offset:07X}")
                self.assertEqual(aliases.key(strings[label]), f"map:0.5/mapscript:0/{key}")
                self.assertEqual(Charmap().decode(rom.data, offset)[0], label)
                self.assertEqual(translations[f"map:0.5/mapscript:0/{key}"], translated)
        self.assertIn("Levels shown here", self.block["unmapped"])
        self.assertTrue({"Base roster", "Normal", "Easy", "Hard"}.isdisjoint(strings))
