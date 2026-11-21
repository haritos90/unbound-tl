"""Written editor data as the page decodes it (web/js/editorstore.js)."""

import json
import shutil
import subprocess
import unittest
from pathlib import Path

from test_roots import TOOLKIT_ROOT

NODE = shutil.which("node")

DECODE = '''
import fs from "node:fs";
import { fileURLToPath, pathToFileURL } from "node:url";
const store = await import(process.argv[1]);
const read = (url) => JSON.parse(fs.readFileSync(fileURLToPath(url), "utf8"));
const url = pathToFileURL(process.argv[2]).href;
const stored = read(url);
const index = store.decodeIndex(stored, read(new URL(stored.shared, url)), url);
const chunks = index.chunks.map((chunk, n) =>
  store.decodeChunk(index, n, read(new URL(chunk.path, url)), read(store.chunkPartUrl(index, n))));
const terms = index.terms ? store.decodeTerms(index, read(new URL(index.terms.path, url))) : null;
const source = store.sourceUrl(index) ? store.decodeSource(read(store.sourceUrl(index))) : null;
process.stdout.write(JSON.stringify({ index, chunks, terms, source }));
'''

SLOTS = '''
const store = await import(process.argv[1]);
const slots = JSON.parse(process.argv[2]);
process.stdout.write(JSON.stringify(store.decodeTerms({}, { terms: [], slots }).slots));
'''


def decoded(directory, web=None) -> dict:
    """The index, chunks, terms and source of a written language directory."""
    if NODE is None:
        raise unittest.SkipTest("node is unavailable")
    store = Path(web or TOOLKIT_ROOT / "web") / "js" / "editorstore.js"
    result = subprocess.run([NODE, "--input-type=module", "-e", DECODE, store.as_uri(),
                             str(Path(directory) / "index.json")], capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def decoded_slots(slots: dict, web=None) -> dict:
    """The {word id: [[line, slot]]} map the page rebuilds from the slots of terms_data."""
    if NODE is None:
        raise unittest.SkipTest("node is unavailable")
    store = Path(web or TOOLKIT_ROOT / "web") / "js" / "editorstore.js"
    result = subprocess.run([NODE, "--input-type=module", "-e", SLOTS, store.as_uri(), json.dumps(slots)],
                            capture_output=True, text=True, check=True)
    return json.loads(result.stdout)
