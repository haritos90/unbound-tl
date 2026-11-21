import contextlib
import functools
import hashlib
import json
import os
import tomllib
import unittest
from pathlib import Path

from gen3tl.profile.profile import Profile, TOOLKIT_ROOT

from rom_support import rom_path
from test_roots import TEST_ROOT

def rom_evidence(offset, value):
    """Describe synthetic fixture bytes by their digest."""
    raw = bytes.fromhex(value) if isinstance(value, str) else value
    return {"offset": offset, "size": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}

UNBOUND = Path(os.environ.get("GEN3TL_UNBOUND_PROJECT", TOOLKIT_ROOT))

def _project_scope(method):
    @functools.wraps(method)
    def scoped(*args, **kwargs):
        if Path.cwd() != TOOLKIT_ROOT:
            return method(*args, **kwargs)
        with contextlib.chdir(UNBOUND):
            return method(*args, **kwargs)
    return scoped

def needs_unbound(test):
    test = unittest.skipUnless((UNBOUND / "project.toml").is_file(),
                               "no Unbound project at the repository root (project.toml)")(test)
    if not isinstance(test, type):
        return _project_scope(test)
    test.run = _project_scope(test.run)
    for name in ("setUpClass", "tearDownClass"):
        method = vars(test).get(name)
        if isinstance(method, classmethod):
            setattr(test, name, classmethod(_project_scope(method.__func__)))
    return test

FIXTURES = TEST_ROOT / "fixtures"

CATALOG_STAGE = FIXTURES / "sample-hack"

SAMPLE = "sample-hack-1.0"

def unbound(language="ru"):
    """The effective Unbound profile of a language of the project."""
    return Profile.load(UNBOUND / "profile").for_project(language, UNBOUND)

@contextlib.contextmanager
def shared_profiles():
    """Parse repository profiles once; give each caller an isolated copy."""
    import copy
    from unittest.mock import patch

    from gen3tl.profile.profile import profile_paths

    paths = {path.resolve() for path in profile_paths()}
    profiles = {}
    original = Profile.load.__func__

    def load(cls, path):
        absolute = Path(path).resolve()
        if absolute not in paths:
            return original(cls, path)
        key = (cls, absolute)
        if key not in profiles:
            profiles[key] = original(cls, path)
        result = copy.deepcopy(profiles[key])
        result.path = Path(path)
        return result

    with patch.object(Profile, "load", classmethod(load)):
        yield

def recorded_substitutions(profile):
    """Keep isolated window fixtures independent of complete source catalogs."""
    import copy
    selected = copy.copy(profile)
    data = dict(profile.data) if hasattr(profile, "data") else dict(profile)
    declared = data.get("layout", {}).get("code_slot_source", {})
    data["layout"] = {k: v for k, v in data.get("layout", {}).items()
                      if k not in ("fill_source", "slot_source", "code_slot_source",
                                   "slot_context", "window_slot_context")}
    # Source-only rules have no recorded number.
    policy = tomllib.loads((UNBOUND / "translation" / "ru" / "policy.toml").read_text(encoding="utf-8"))
    numbered = policy.get("layout", {}).get("code_fill", {})
    if "code_fill" in data["layout"]:
        data["layout"]["code_fill"] = [
            rule for rule in data["layout"]["code_fill"]
            if rule.get("name") not in declared or rule.get("name") in numbered
            or any({"digits", "width", "strings"} & set(slot) for slot in rule["slots"].values())]
    if hasattr(selected, "data"):
        selected.data = data
        return selected
    return data

def select_language(code):
    """Select a language pack for the rest of a test module."""
    from gen3tl.lang import language
    token = language.ACTIVE.set(language.load(code))
    unittest.addModuleCleanup(language.ACTIVE.reset, token)

def literal(value):
    if isinstance(value, dict):
        return "{ " + ", ".join(f"{json.dumps(k)} = {literal(v)}" for k, v in value.items()) + " }"
    if isinstance(value, list):
        return "[" + ", ".join(literal(v) for v in value) + "]"
    return json.dumps(value, ensure_ascii=False)

def with_profile_notes(value, status="unreviewed"):
    """Load synthetic prose migrations through validated fact bindings."""
    import copy
    import tempfile

    from gen3tl.core import notes
    from gen3tl.profile import schema

    value = copy.deepcopy(value)
    fields = []

    def clear(item, path=""):
        if isinstance(item, dict):
            for key, child in item.items():
                pointer = path + "/" + key.replace("~", "~0").replace("/", "~1")
                if schema.is_prose(key) and isinstance(child, str):
                    fields.append((pointer, child))
                    item[key] = ""
                else:
                    clear(child, pointer)
        elif isinstance(item, list):
            for index, child in enumerate(item):
                clear(child, f"{path}/{index}")

    clear(value)
    data = {"table": [value]}
    fact = schema.facts(data)[0]
    statuses = (status,) if isinstance(status, str) else status
    records = [{"id": f"proof-{index}-{ordinal}", "subject": {"kind": "profile_fact", "id": fact.id},
                "scope": {"kind": "shared"}, "status": review, "facts": [text or "Measured reader."],
                "binding": {"kind": "profile_fact", "id": fact.id,
                            "value_sha256": schema.value_digest(value), "field": field}}
               for index, (field, text) in enumerate(fields) for ordinal, review in enumerate(statuses)]
    data["fact"] = [{"id": fact.id, "notes_schema": notes.SCHEMA, "notes": records}]
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "profile.toml"
        path.write_text("\n".join(f"{key} = {literal(item)}" for key, item in data.items()), encoding="utf-8")
        return schema.load(path)["table"][0]

def write_policy(root, profile, language="ru", **sections):
    identity = {"version": "2.0.0", "profile": profile.name, "language": language, "rom_sha1": profile.sha1}
    doc = {"policy": identity, **sections}
    (root / "policy.toml").write_text("\n".join(f"{k} = {literal(v)}" for k, v in doc.items()), encoding="utf-8")


ENGLISH = UNBOUND / "build" / "catalog.pot"


FLINCH_MOVES = {
    13: 1, 23: 31, 27: 31, 29: 31, 44: 31, 125: 11, 127: 21,
    157: 31, 158: 11, 173: 31, 239: 21, 252: 100, 290: 31,
    302: 31, 310: 31, 326: 11, 356: 31, 367: 21, 382: 31,
    401: 21, 408: 31, 413: 31, 420: 1, 431: 11, 432: 11,
    433: 11, 486: 31, 624: 31, 673: 31, 737: 21, 751: 31,
}


def project_wording_rows():
    from gen3tl.check.rules import list_path, load_list
    return load_list(list_path(UNBOUND / "translation" / "ru"), code="ru")


def buffered_stat_fixture():
    """Load the project's verified stat readers and their catalog dependencies."""
    from gen3tl.catalog.catalog import load_catalog
    from gen3tl.check.layout import Measure
    from gen3tl.cli.common import _font_codes, _style_measures

    profile = unbound()
    rom = profile.load_rom(rom_path())
    catalog = load_catalog(UNBOUND / "translation" / "ru" / "po", profile=profile)
    inventory = json.loads((UNBOUND / "build/inventory.json").read_text())
    styles = _style_measures(profile, rom, "ru")
    measure, charmap = styles[profile["font_style"]["style"]]
    measure = Measure(measure.glyph_width, profile["layout"]["placeholders"],
                      styles={k: v[0].glyph_width for k, v in styles.items()}, fonts=_font_codes(profile))
    expected = {"consumers": {"s0A4E240": ("B_COPY_VAR_2", [203, 215]),
                              "s0A4E276": ("B_COPY_VAR_2", [138, 215]),
                              "s0A4E299": ("B_COPY_VAR_2", [203, 220]),
                              "s0417032": ("STR_VAR_2", [161, 190]),
                              "s1F96A74": ("STR_VAR_2", [42, 174, 195, 202]),
                              "s1F85BDD": ("STR_VAR_1", [143, 155, 161, 206, 198])},
                "items": (0x876200, 729, 44, 28, 0x08A03D11, 19),
                "table": 0x3FD5D0,
                "vitamin_pools": [0x125174, 0x125184, 0x125194, 0x1251A4, 0x1251B4, 0x1251D0],
                "script_pools": [0x8C980C + 21 * i for i in range(6)],
                "winner": "s03FD5B0", "excluded": "s03FD5B8"}
    wanted = set(expected["consumers"]) | {expected["excluded"]}
    for name in ("primary-stat-names", "short-stat-names", "vitamin-stat-names"):
        value = profile["layout"]["fill_source"][name]["value"]
        wanted.update(value.get("entries", value.get("max", {}).get("native", {}).get("entries", [])))
    catalog = {sid: row for sid, row in catalog.items() if sid in wanted}
    inventory = {**inventory, "entries": [row for row in inventory["entries"] if row["id"] in wanted]}
    return profile, rom, catalog, inventory, measure, charmap, expected


def copy_aliases(root):
    """The Unbound alias table under `root`: copied catalogs and policies name entries by key."""
    from gen3tl.catalog import keys
    sha1 = Profile.load(UNBOUND / "profile").sha1
    table = keys.alias_path(sha1, root)
    table.parent.mkdir(parents=True, exist_ok=True)
    table.write_bytes(keys.alias_path(sha1, UNBOUND).read_bytes())


def copy_profile(root, languages=("ru",)):
    """Give an isolated project its profile and identity."""
    from dataclasses import replace
    import shutil

    from gen3tl.project import Manifest

    manifest = replace(Manifest.read(UNBOUND / "project.toml"), path=root / "project.toml",
                       languages=languages, default_language=languages[0])
    shutil.copytree(UNBOUND / "profile", root / "profile")
    manifest.path.write_text(manifest.text(), encoding="utf-8")
    return manifest


def copy_policy(root, registry=None):
    """The project policy in `root` when present, else the fixture policy."""
    project_policy = UNBOUND / "translation" / "ru" / "policy.toml"
    source = project_policy if project_policy.is_file() else FIXTURES / "unbound-2.1.1.1-policy.toml"
    (root / "policy.toml").write_bytes(source.read_bytes())
    if source == project_policy or registry is not None:
        copy_aliases(registry if registry is not None else root)
