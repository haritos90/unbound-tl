#!/usr/bin/env python3
"""Refuse a site tree that holds files the publication rules exclude."""
import hashlib
import json
import os
import re
import sys
import zipfile
from pathlib import Path

# the cartridge logo every GBA ROM carries at 0x04
LOGO_SHA256 = "08a0153cfd6b0ea54b938f7d209933fa849da0d56f5a34c481060c9ff2fad818"
ROMS = {".gba", ".agb", ".gb", ".gbc", ".bin", ".mb", ".elf", ".nds", ".srl"}
SAVES = {".sav", ".srm", ".sa1", ".sa2", ".fla", ".eep", ".sram", ".dsv"}
STATES = {".state", ".sgm", *(f".ss{n}" for n in range(10)), *(f".st{n}" for n in range(10))}
ARCHIVES = {".zip", ".7z", ".rar", ".gz", ".tgz", ".tar", ".bz2", ".xz", ".zst", ".lz", ".lzma"}
ARCHIVE_MAGIC = (b"PK\x03\x04", b"7z\xbc\xaf\x27\x1c", b"Rar!", b"\x1f\x8b", b"\xfd7zXZ", b"BZh", b"\x28\xb5\x2f\xfd")
PATCHES = {".ups", ".ips", ".bps", ".xdelta", ".vcdiff", ".ppf", ".aps"}
PATCH_MAGIC = (b"UPS1", b"BPS1", b"PATCH", b"\xd6\xc3\xc4")
IMAGES = {".png", ".apng", ".gif", ".jpg", ".jpeg", ".bmp", ".webp", ".tif", ".tiff", ".ico", ".avif"}
IMAGE_MAGIC = (b"\x89PNG", b"GIF8", b"\xff\xd8\xff", b"II*\x00", b"MM\x00*")
SITE_IMAGES = {"brand.png": "086f826bf432467b23f488ddfddd549c87aaeae8e0f7d9feca569a616778db42"}
# a kept version may hold an earlier engine: add a hash, drop it later
PATCHERS = {"e59b643ef2e8498fdd783e1495f2f9ff216d4a09c778b3e6fb2d8aac6f51c2e0",
            "5b33080b984891685ffe4ed7ff04c6c255a346df93fc51df27871a9b70c57718"}
VERSION = r"[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?"
# the current version and the kept ones
VERSIONS = 3
SECTION = 0x1000
# section signatures of the games and of CFRU, little-endian
SIGNATURES = (b"\x25\x20\x01\x08", b"\x99\x19\x12\x01", b"\x98\x19\x12\x01")
KINDS = ("rom", "save", "state", "archive", "patch", "release", "image", "wasm", "version", "hidden", "link")


def say(label, value):
    print(f"{label:<12} {value}")


def head(path, size):
    with path.open("rb") as stream:
        return stream.read(size)


def is_rom(path):
    data = head(path, 0xC0)
    return len(data) == 0xC0 and data[0xB2] == 0x96 and hashlib.sha256(data[4:0xA0]).hexdigest() == LOGO_SHA256


def is_save(path):
    """Two sections in a row carry a save signature, wherever a container puts them."""
    if path.stat().st_size < 2 * SECTION:
        return False
    data = path.read_bytes()
    for signature in SIGNATURES:
        at = data.find(signature)
        while at >= 0:
            if data[at + SECTION:at + SECTION + 4] == signature:
                return True
            at = data.find(signature, at + 1)
    return False


def listed_images(data):
    """Pictures the manifests of each Pokedex sprite set name, relative to the set."""
    allowed = set()
    for sprites in sorted(data.glob("pokedex/*/sprites")):
        for manifest in sorted(sprites.rglob("manifest.json")):
            stack = [json.loads(manifest.read_text(encoding="utf-8"))]
            while stack:
                value = stack.pop()
                if isinstance(value, dict):
                    stack.extend(value.values())
                elif isinstance(value, list):
                    stack.extend(value)
                elif isinstance(value, str) and Path(value).suffix.lower() in IMAGES:
                    picture = (sprites / value).resolve()
                    if picture.is_relative_to(sprites.resolve()):
                        allowed.add(picture)
    return allowed


def listed_releases(data):
    """The files releases.json lists with their SHA-256, and its patches."""
    manifest = data / "releases" / "releases.json"
    rows = json.loads(manifest.read_text(encoding="utf-8")).get("releases", []) if manifest.is_file() else []
    files, patches = {}, set()
    for row in rows:
        for key in ("patch", "names", "notes"):
            if isinstance(row.get(key), str) and isinstance(row.get(f"{key}_sha256"), str):
                files[(data / "releases" / row[key]).resolve()] = row[f"{key}_sha256"]
                if key == "patch":
                    patches.add((data / "releases" / row[key]).resolve())
    return files, patches


def bundle_of(data):
    try:
        name = json.loads((data / "languages.json").read_text(encoding="utf-8")).get("bundle")
    except (OSError, ValueError):
        return None
    return (data / name).resolve() if isinstance(name, str) and name else None


def is_site_image(tree, path):
    """Branding must match the declared public artwork."""
    try:
        relative = path.relative_to(tree).as_posix()
    except ValueError:
        return False
    expected = SITE_IMAGES.get(relative)
    return expected is not None and hashlib.sha256(path.read_bytes()).hexdigest() == expected


def is_share_image(tree, path):
    """Content-addressed preview art must name its own SHA-256."""
    try:
        relative = path.relative_to(tree)
    except ValueError:
        return False
    if len(relative.parts) != 3 or relative.parts[:2] != ("share", "assets"):
        return False
    if not re.fullmatch(r"[0-9a-f]{64}\.png", relative.name):
        return False
    return hashlib.sha256(path.read_bytes()).hexdigest() == relative.stem


def is_site_wasm(tree, path):
    """Only a released patch engine belongs in versioned assets."""
    relative = path.relative_to(tree).as_posix()
    return bool(re.fullmatch(rf"assets/{VERSION}/js/patcher/rom-patcher\.wasm", relative)
                and hashlib.sha256(path.read_bytes()).hexdigest() in PATCHERS)


def version_problems(tree):
    """Paths that break the rule: one to three versions, each equal to its manifest."""
    record = tree / "site-build.json"
    try:
        build = json.loads(record.read_text(encoding="utf-8"))
        named = [build["version"], *build["kept"]]
        valid = len(set(named)) == len(named) <= VERSIONS and all(re.fullmatch(VERSION, name) for name in named)
    except (OSError, ValueError, KeyError, TypeError):
        valid = False
    if not valid:
        return [record]
    assets = tree / "assets"
    present = {path.name for path in assets.iterdir()} if assets.is_dir() else set()
    problems = [assets / name for name in sorted(present.symmetric_difference(named))]
    for version in sorted(present.intersection(named)):
        folder = assets / version
        try:
            manifest = json.loads((folder / "files.json").read_text(encoding="utf-8"))
            listed = dict(manifest["files"]) if manifest["version"] == version else None
        except (OSError, ValueError, KeyError, TypeError):
            listed = None
        if listed is None:
            problems.append(folder / "files.json")
            continue
        actual = {path.relative_to(folder).as_posix() for path in folder.rglob("*")
                  if not path.is_dir() and path != folder / "files.json"}
        problems += [folder / name for name in sorted(actual.symmetric_difference(listed))]
        for name in sorted(actual.intersection(listed)):
            path = folder / name
            if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != listed[name]:
                problems.append(path)
    return problems


def main(argv):
    if len(argv) != 2 or not Path(argv[1]).is_dir():
        print("usage: site-check.py TREE", file=sys.stderr)
        return 2
    tree = Path(argv[1]).resolve()
    data = tree / "data"
    images = listed_images(data)
    releases, patches = listed_releases(data)
    bundle = bundle_of(data)
    found = {kind: [] for kind in KINDS}
    found["version"] = version_problems(tree)
    files = 0
    for top, dirs, names in os.walk(tree):
        here = Path(top)
        for name in sorted(dirs):
            if name.startswith("."):
                found["hidden"].append(here / name)
            if (here / name).is_symlink():
                found["link"].append(here / name)
        for name in sorted(names):
            path = here / name
            files += 1
            if name.startswith("."):
                found["hidden"].append(path)
            if path.is_symlink():
                found["link"].append(path)
                continue
            suffix = path.suffix.lower()
            start = head(path, 8)
            resolved = path.resolve()
            if (suffix == ".wasm" or start.startswith(b"\0asm")) and not is_site_wasm(tree, path):
                found["wasm"].append(path)
            if suffix in ROMS or is_rom(path):
                found["rom"].append(path)
            if suffix in SAVES or is_save(path):
                found["save"].append(path)
            if suffix in STATES:
                found["state"].append(path)
            if suffix in ARCHIVES or start.startswith(ARCHIVE_MAGIC):
                if resolved != bundle or not zipfile.is_zipfile(path):
                    found["archive"].append(path)
                else:
                    with zipfile.ZipFile(path) as archive:
                        if any(not member.endswith((".py", ".json", "/")) for member in archive.namelist()):
                            found["archive"].append(path)
            if (suffix in PATCHES or start.startswith(PATCH_MAGIC)) and resolved not in patches:
                found["patch"].append(path)
            if resolved.is_relative_to(data / "releases") and resolved != data / "releases" / "releases.json" and (
                    resolved not in releases or hashlib.sha256(path.read_bytes()).hexdigest() != releases[resolved]):
                found["release"].append(path)
            if (suffix in IMAGES or start.startswith(IMAGE_MAGIC)) and resolved not in images \
                    and not is_share_image(tree, resolved) and not is_site_image(tree, resolved):
                found["image"].append(path)
    say("tree", tree)
    say("files", f"{files} files")
    say("patches", f"{len(patches)} listed")
    say("pictures", f"{len(images)} listed")
    for kind in KINDS:
        say(kind, f"{len(found[kind])} files")
        for path in found[kind]:
            say("file", path.relative_to(tree).as_posix())
    refused = any(found.values())
    say("verified", "failed" if refused else "passed")
    return 1 if refused else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
