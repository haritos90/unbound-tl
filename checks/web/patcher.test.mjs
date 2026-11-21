import assert from "node:assert/strict";

import { createHash } from "node:crypto";

import { readdirSync, readFileSync } from "node:fs";

import { test } from "node:test";

import { fakeDocument, stubPage } from "./fixture.mjs";

const { loadReleaseNotes, languagesOf, noteItems, patchName, romProblem, sizeLabel, versionsOf } = await import(new URL("js/patch.js", process.env.GEN3TL_WEB_ROOT_URL));

const { digest, patchRelease, reverseRelease, validateManifest } = await import(new URL("js/patcher-core.js", process.env.GEN3TL_WEB_ROOT_URL));

await import(new URL("test/patch-fixture.mjs", process.env.GEN3TL_WEB_ROOT_URL));

const { fillPage, setCatalog, setUiLanguage, t } = await import(new URL("js/ui.js", process.env.GEN3TL_WEB_ROOT_URL));

const release = (language, version) => ({
  profile: "unbound-2.1.1.1", profile_name: "Pokemon Unbound 2.1.1.1", language, version,
  source_sha1: "b".repeat(40), source_size: 33554432, result_sha1: "e".repeat(40), result_size: 33554432,
  patch: `unbound-2.1.1.1/${language}/${version}.ups`, patch_sha256: "4".repeat(64), patch_size: 1332576,
  output: `unbound-2.1.1.1-${language}-${version}.gba`,
});

async function upsFixture() {
  const source = new Uint8Array([1, 2, 3]), result = new Uint8Array([1, 8, 3]);
  const patch = new Uint8Array(Buffer.from("555053318383810a001d80bc55976853afdc2279fe", "hex"));
  const row = { ...release("ru", "1.0.0"), source_sha1: await digest(source), source_size: source.length,
    result_sha1: await digest(result), result_size: result.length,
    patch_sha256: await digest(patch, "SHA-256"), patch_size: patch.length };
  return { source, result, patch, row };
}

test("reverse releases verify every declared hash and size", async () => {
  const { source, result, patch, row } = await upsFixture();
  for (const field of ["source_sha1", "result_sha1", "patch_sha256"]) {
    await assert.rejects(reverseRelease(result, patch, { ...row, [field]: "0".repeat(row[field].length) }));
  }
  for (const field of ["source_size", "result_size", "patch_size"]) {
    await assert.rejects(reverseRelease(result, patch, { ...row, [field]: row[field] + 1 }));
  }
  await assert.rejects(reverseRelease(source, patch, row), /Patched ROM differs/);
  await assert.rejects(reverseRelease(result, patch, { ...row, patch: "../wrong.ups" }), /filename/);
});

const withNotes = (row, notes) => {
  const data = new TextEncoder().encode(JSON.stringify({ schema: 1, profile: row.profile, language: row.language,
    version: row.version, release_label: "RU by gen3tl", notes }));
  return { row: { ...row, notes: `${row.profile}/${row.language}/${row.version}.notes.json`,
    notes_sha256: createHash("sha256").update(data).digest("hex") }, data };
};

test("languages by name and versions newest first", () => {
  const rows = [release("ru", "0.1.9"), release("ru", "0.1.17"), release("de", "0.0.1")];
  assert.deepEqual(languagesOf(rows), [{ code: "de", name: "German" }, { code: "ru", name: "Russian" }]);
  assert.deepEqual(versionsOf(rows, "ru").map((r) => r.version), ["0.1.17", "0.1.9"]);
  assert.equal(patchName(rows[1]), "unbound-2.1.1.1-ru-0.1.17.ups");
});

test("patch language choices keep English names in every site language", (ctx) => {
  ctx.after(() => setUiLanguage("en"));
  const rows = ["ru", "de", "es", "fr"].map((code) => release(code, "0.1.0"));
  for (const locale of ["en", "ru", "de"]) {
    setUiLanguage(locale);
    assert.deepEqual(languagesOf(rows).map((l) => l.name), ["French", "German", "Russian", "Spanish"]);
  }
});

test("a wrong ROM names the expected hash", () => {
  const r = release("ru", "0.1.17");
  assert.equal(romProblem(r.source_size, r.source_sha1, r), null);
  assert.match(romProblem(r.source_size, "c".repeat(40), r),
    new RegExp(`SHA-1 c{40} is not the original Pokemon Unbound 2.1.1.1 ROM\\. Expected SHA-1 b{40}\\.`));
  assert.match(romProblem(16777216, null, r), /has 16 MiB; the original .* has 32 MiB\. Expected SHA-1 b{40}\./);
});

test("the release list accepts optional notes with or without name tables", () => {
  const plain = release("ru", "0.1.17");
  const noted = withNotes(release("ru", "0.1.25"), ["Translated the menus."]).row;
  const both = { ...noted, names: "unbound-2.1.1.1/ru/0.1.25.names.json", names_sha256: "5".repeat(64) };
  assert.equal(validateManifest({ schema: 1, releases: [plain, noted] }).length, 2);
  assert.equal(validateManifest({ schema: 1, releases: [both] }).length, 1);
  const bad = (change) => ({ schema: 1, releases: [{ ...noted, ...change }] });
  assert.throws(() => validateManifest(bad({ notes: "elsewhere.json" })), /release notes/);
  assert.throws(() => validateManifest(bad({ notes_sha256: "x" })), /release notes/);
  const half = { ...noted };
  delete half.notes_sha256;
  assert.throws(() => validateManifest({ schema: 1, releases: [half] }), /fields/);
});

const siteCatalogs = [{ code: "en", strings: null }, ...readdirSync(new URL("i18n/", process.env.GEN3TL_WEB_ROOT_URL))
  .filter((name) => name.endsWith(".po")).map((name) => ({ code: name.slice(0, -3), strings: Object.fromEntries(
    [...readFileSync(new URL(`i18n/${name}`, process.env.GEN3TL_WEB_ROOT_URL), "utf8")
      .matchAll(/^msgid ("[^\n]*")\nmsgstr ("[^\n]*")$/gm)].map((m) => [JSON.parse(m[1]), JSON.parse(m[2])])) }))];

async function patchPage(context) {
  const page = stubPage(context, "patch");
  for (const id of ["game", "language", "release"]) {
    const node = page.$(id);
    let selected = "";
    Object.defineProperty(node, "value", {
      get: () => node.options.find((option) => option.value === selected)?.value ?? node.options[0]?.value ?? "",
      set: (value) => { selected = value; },
    });
  }
  for (const id of ["patch-link", "download"]) {
    const node = page.$(id);
    Object.defineProperty(node, "href", {
      get: () => node.getAttribute("href") ?? "",
      set: (value) => node.setAttribute("href", value),
    });
    node.focus = () => { document.activeElement = node; };
  }
  const source = readFileSync(new URL("js/patch.js", process.env.GEN3TL_WEB_ROOT_URL), "utf8")
    .replace(/from "(\.\/[^\"]+)"/g, (_, path) => `from "${new URL(`js/${path.slice(2)}`, process.env.GEN3TL_WEB_ROOT_URL).href}"`)
    .replaceAll("import.meta.url", JSON.stringify(new URL("js/patch.js", process.env.GEN3TL_WEB_ROOT_URL).href))
    .replace(/if \(typeof document !== "undefined"[^\n]+main\(\);/, "export { state, chooseGame, chooseRelease, checkFile, apply, relabel, wire };");
  const patcher = await import(`data:text/javascript;base64,${Buffer.from(source).toString("base64")}#${encodeURIComponent(context.name)}`);
  patcher.wire();
  return { ...page, ...patcher };
}

for (const { code, strings } of siteCatalogs) {
  test(`${code}: patch choices keep verification, release selection and cleared downloads`, async (context) => {
    context.after(() => { setCatalog(null); setUiLanguage("en"); });
    const page = await patchPage(context), { $, state } = page;
    setCatalog(strings);
    setUiLanguage(code);
    fillPage();
    for (const key of ["Choose how to apply the translation", "Patch in this page", "Download the patch",
      "For emulators and patchers that apply UPS files."]) {
      const node = document.querySelectorAll("[data-ui]").find((node) => node.dataset.ui === key);
      assert.equal(node.textContent, strings?.[key] ?? key);
      if (strings) assert.ok(strings[key]);
    }
    const fixture = await upsFixture();
    const latest = { ...fixture.row, profile: "fixture", profile_name: "Fixture game", language: "xx", version: "2.0.0",
      patch: "fixture/xx/2.0.0.ups", output: "Fixture game [2.0.0].gba" };
    const older = { ...latest, version: "1.0.0", patch: "fixture/xx/1.0.0.ups", output: "Fixture game [1.0.0].gba" };
    const other = { ...latest, profile: "other", profile_name: "Other fixture", patch: "other/xx/2.0.0.ups",
      output: "Other fixture.gba", source_sha1: "0".repeat(40) };
    const languages = { ...latest, language: "yy", patch: "fixture/yy/2.0.0.ups", output: "Fixture game [yy].gba" };
    const base = "https://site.test/data/";
    state.games = [{ id: "fixture", name: "Fixture game", data: base }, { id: "other", name: "Other fixture", data: base }];
    state.sources = new Map([[base, { releases: [older, latest, other, languages] }]]);
    $("game").replaceChildren(...state.games.map((game) => new Option(game.name, game.id)));
    assert.equal($("release-summary").hasAttribute("data-loading"), true);
    assert.equal($("rom-expected").hasAttribute("data-loading"), true);
    assert.equal($("rom-expected-placeholder").hasAttribute("data-loading"), true);
    assert.equal($("release-summary-placeholder").hasAttribute("data-loading"), true);
    assert.equal($("release-notes-loading").hasAttribute("data-loading"), true);
    page.chooseGame(state.games[0], latest.language);
    assert.equal($("release-summary").hasAttribute("data-loading"), false);
    assert.equal($("rom-expected").hasAttribute("data-loading"), false);
    assert.equal($("rom-expected-placeholder").hasAttribute("data-loading"), false);
    assert.equal($("release-summary-placeholder").hasAttribute("data-loading"), false);
    await new Promise((resolve) => setImmediate(resolve));
    assert.equal($("release-notes-loading").hasAttribute("data-loading"), false);
    assert.deepEqual($("release").options.map((option) => option.value), ["2.0.0", "1.0.0"]);
    assert.equal($("patch-link").download, patchName(latest));
    assert.equal($("patch-link").textContent, t("Download UPS patch"));
    assert.equal($("apply").disabled, true);
    assert.equal($("download").hidden, true);
    const file = (bytes) => ({ name: "Original.gba", size: bytes.length, arrayBuffer: async () => bytes.slice().buffer });
    await page.checkFile(file(new Uint8Array([3, 2, 1])));
    assert.equal(state.check.ok, false);
    assert.equal($("apply").disabled, true);
    assert.equal($("rom-error").textContent, romProblem(3, state.check.sha1, latest));
    assert.equal($("patch-link").download, patchName(latest));
    await page.checkFile(file(fixture.source));
    assert.equal(state.check.ok, true);
    assert.equal($("apply").disabled, false);
    assert.equal($("result-sha1").textContent, latest.result_sha1);
    const workerDescriptor = Object.getOwnPropertyDescriptor(globalThis, "Worker"), workers = [];
    Object.defineProperty(globalThis, "Worker", { configurable: true, value: class {
      constructor(url, options) { this.url = url; this.options = options; workers.push(this); }
      postMessage(message) { this.message = message; }
      terminate() { this.terminated = true; }
    } });
    context.after(() => {
      if (workerDescriptor) Object.defineProperty(globalThis, "Worker", workerDescriptor);
      else delete globalThis.Worker;
      if (state.url) URL.revokeObjectURL(state.url);
    });
    page.apply();
    const worker = workers.at(-1);
    assert.ok(worker.url.href.endsWith("/js/patcher-worker.js"));
    assert.deepEqual(worker.options, { type: "module" });
    assert.equal(worker.message.patchURL, `${base}releases/${latest.patch}`);
    assert.equal($("apply").disabled, true);
    const result = await patchRelease(new Uint8Array(await worker.message.file.arrayBuffer()), fixture.patch, worker.message.release);
    worker.onmessage({ data: { result } });
    assert.equal(worker.terminated, true);
    assert.equal($("apply").hidden, true);
    assert.equal($("download").hidden, false);
    assert.equal($("download").download, latest.output);
    assert.equal(document.activeElement, $("download"));
    assert.match($("status").textContent, new RegExp(latest.result_sha1));
    const resultURL = $("download").href;
    page.relabel();
    fillPage();
    assert.equal($("download").href, resultURL);
    assert.equal($("download").textContent, t("Download {file}", { file: latest.output }));
    $("release").value = older.version;
    $("release").listeners.change();
    await new Promise((resolve) => setImmediate(resolve));
    assert.equal(state.release, older);
    assert.equal($("patch-link").href, `${base}releases/${older.patch}`);
    assert.equal($("patch-link").download, patchName(older));
    assert.equal($("result-name").textContent, `${older.output} · ${sizeLabel(older.result_size)}`);
    assert.equal($("download").hidden, true);
    assert.equal($("download").getAttribute("href"), null);
    assert.equal($("apply").hidden, false);
    await page.checkFile(file(fixture.source));
    page.apply();
    const cancelled = workers.at(-1);
    $("cancel").listeners.click();
    assert.equal(cancelled.terminated, true);
    cancelled.onmessage({ data: { result } });
    assert.equal($("download").hidden, true);
    $("release").value = latest.version;
    $("release").listeners.change();
    $("language").value = languages.language;
    $("language").listeners.change();
    assert.equal(state.release, languages);
    assert.equal($("patch-link").download, patchName(languages));
    assert.equal($("download").getAttribute("href"), null);
    $("game").value = other.profile;
    $("game").listeners.change();
    await page.checkFile(file(fixture.source));
    assert.equal(state.release, other);
    assert.equal(state.check.ok, false);
    assert.equal($("apply").disabled, true);
    assert.equal($("patch-link").download, patchName(other));
    assert.equal($("download").getAttribute("href"), null);
  });
}

test("the patch page loads the selected version's notes as a plain list", async () => {
  const html = readFileSync(new URL("patch.html", process.env.GEN3TL_WEB_ROOT_URL), "utf8");
  assert.match(html, /<span data-ui="Release notes">Release notes<\/span>/);
  assert.match(html, /<ul class="summary" id="release-notes-list"><\/ul>/);
  const older = withNotes(release("ru", "0.1.17"), ["Older change."]);
  const selected = withNotes(release("ru", "0.1.25"), ["First change.", "Second change."]);
  const base = "https://example.org/data/releases/releases.json";
  const files = new Map([[new URL(older.row.notes, base).href, older.data],
    [new URL(selected.row.notes, base).href, selected.data]]);
  const calls = [];
  const fetcher = async (url) => {
    calls.push(url);
    return files.has(url) ? { ok: true, arrayBuffer: async () => files.get(url).buffer } : { ok: false, status: 404 };
  };
  assert.deepEqual(await loadReleaseNotes(older.row, base, fetcher), ["Older change."]);
  assert.deepEqual(await loadReleaseNotes(selected.row, base, fetcher), ["First change.", "Second change."]);
  assert.equal(calls[1], "https://example.org/data/releases/unbound-2.1.1.1/ru/0.1.25.notes.json");
  assert.deepEqual(await loadReleaseNotes(release("ru", "0.1.9"), base, fetcher), []);
  await assert.rejects(loadReleaseNotes({ ...selected.row, notes_sha256: "0".repeat(64) }, base, fetcher), /differ/);
  const previous = globalThis.document;
  globalThis.document = fakeDocument();
  try {
    const items = noteItems(await loadReleaseNotes(selected.row, base, fetcher));
    assert.deepEqual(items.map((item) => [item.tagName, item.textContent]),
      [["LI", "First change."], ["LI", "Second change."]]);
  } finally {
    globalThis.document = previous;
  }
});

test("descriptive release filenames are shared by ROM and UPS downloads", () => {
  const row = { ...release("ru", "1.0.0"), output: "Pokemon Unbound 2.1.1.1 [RU by gen3tl].gba" };
  const early = { ...release("ru", "0.2.18"), output: "Pokemon Unbound 2.1.1.1 [RU v0.2.18 by gen3tl].gba" };
  assert.deepEqual(validateManifest({ schema: 1, releases: [early, row] }), [early, row]);
  assert.equal(patchName(row), "Pokemon Unbound 2.1.1.1 [RU by gen3tl].ups");
  assert.equal(patchName(early), "Pokemon Unbound 2.1.1.1 [RU v0.2.18 by gen3tl].ups");
  for (const output of ["../Other.gba", "dir/Other.gba", "dir\\Other.gba", "https://host/Other.gba",
    "Other\n.gba", "Other\0.gba", ".gba", " .gba", "Other.ups"]) {
    assert.throws(() => validateManifest({ schema: 1, releases: [{ ...row, output }] }), /filename/);
  }
});
