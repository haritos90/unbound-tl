import assert from "node:assert/strict";

import { test } from "node:test";

const { validateManifest } = await import(new URL("js/patcher-core.js", process.env.GEN3TL_WEB_ROOT_URL));

import { readFileSync } from "node:fs";

const { detectedSide, ORIGINAL, outputName, pairOf, SAME, sidesOf } = await import(new URL("js/save.js", process.env.GEN3TL_WEB_ROOT_URL));

const { onSiteLanguage, setCatalog, setUiLanguage, SITE_LANG_KEY, startSite } = await import(new URL("js/ui.js", process.env.GEN3TL_WEB_ROOT_URL));

import { fakeFetch, stubPage } from "./fixture.mjs";

const release = (language, version, names = true) => ({
  profile: "unbound-2.1.1.1", profile_name: "Pokemon Unbound 2.1.1.1", language, version,
  source_sha1: "b".repeat(40), source_size: 33554432, result_sha1: "e".repeat(40), result_size: 33554432,
  patch: `unbound-2.1.1.1/${language}/${version}.ups`, patch_sha256: "4".repeat(64), patch_size: 1332576,
  output: `unbound-2.1.1.1-${language}-${version}.gba`,
  ...(names ? { names: `unbound-2.1.1.1/${language}/${version}.names.json`, names_sha256: "5".repeat(64) } : {}),
});

test("the header supplies conversion defaults and rename-only keeps independent selections", async (context) => {
  const { $, choose, storage } = stubPage(context, "save");
  const base = "https://site.test/data/";
  globalThis.fetch = fakeFetch({
    [`${base}registry.json`]: { schema: 1, games: [{ languages: ["ru", "de", "fr"] }] },
    [`${base}site/catalogs.json`]: { schema: 1, catalogs: [{ code: "ru" }] },
    [`${base}site/ru.json`]: { schema: 1, language: "ru", strings: { "Save converter": "Save RU" } },
  });
  const source = readFileSync(new URL("js/save.js", process.env.GEN3TL_WEB_ROOT_URL), "utf8")
    .replace(/from "(\.\/[^\"]+)"/g, (_, path) => `from "${new URL(`js/${path.slice(2)}`, process.env.GEN3TL_WEB_ROOT_URL).href}"`)
    .replace(/if \(typeof document[^\n]+main\(\);\s*$/, "export { state, relabel, fillSides, wire };\n");
  const { state, relabel, fillSides, wire } = await import(`data:text/javascript;base64,${Buffer.from(source).toString("base64")}`);
  Object.assign(state, { game: { id: "unbound-2.1.1.1", name: "Test game" },
    named: [release("ru", "0.1.0"), release("de", "0.1.0")] });
  fillSides();
  wire();
  context.after(onSiteLanguage(relabel));
  context.after(() => { setCatalog(null); setUiLanguage("en"); });
  storage.setItem(SITE_LANG_KEY, "ru");
  assert.equal($("direction-summary-loading").hasAttribute("data-loading"), true);
  await startSite();
  assert.equal($("direction-summary-loading").hasAttribute("data-loading"), false);
  const pair = () => [$("from").value, $("to").value];
  assert.deepEqual(pair(), [ORIGINAL, "ru@0.1.0"]);
  assert.equal(document.documentElement.lang, "ru");
  assert.equal(document.querySelector("title").textContent, "Save RU");
  const settle = async () => { for (let i = 0; i < 20; i++) await new Promise((resolve) => setImmediate(resolve)); };
  choose("de");
  await settle();
  assert.deepEqual(pair(), [ORIGINAL, "de@0.1.0"]);
  assert.equal(document.documentElement.lang, "en");
  assert.equal(document.querySelector("title").textContent, "Save converter");
  assert.equal(storage.getItem(SITE_LANG_KEY), "de");
  choose("en");
  await settle();
  assert.deepEqual(pair(), ["de@0.1.0", ORIGINAL]);
  assert.equal(location.hash, "#unbound-2.1.1.1/en");
  choose("ru");
  await settle();
  assert.deepEqual(pair(), [ORIGINAL, "ru@0.1.0"]);
  assert.equal(document.documentElement.lang, "ru");
  choose("fr");
  await settle();
  assert.equal($("language-note").hidden, false);
  assert.match($("language-note").textContent, /No French translation/);
  assert.deepEqual(pair(), ["ru@0.1.0", ORIGINAL]);
  assert.equal(location.hash, "#unbound-2.1.1.1/fr");

  $("rename-only").checked = true;
  $("rename-only").listeners.change();
  assert.equal($("direction-pair").hidden, true);
  assert.equal($("edit-game-field").hidden, false);
  assert.equal($("from").disabled, true);
  assert.equal($("to").disabled, true);
  assert.equal($("edit-game").value, "ru@0.1.0");
  $("edit-game").value = ORIGINAL;
  $("edit-game").listeners.change();
  choose("de");
  await settle();
  assert.equal($("edit-game").value, ORIGINAL, "site language does not select the save alphabet");
  assert.deepEqual(pair(), ["ru@0.1.0", ORIGINAL]);
  $("rename-only").checked = false;
  $("rename-only").listeners.change();
  assert.equal($("direction-pair").hidden, false);
  assert.equal($("edit-game-field").hidden, true);
  assert.deepEqual(pair(), ["ru@0.1.0", ORIGINAL], "conversion selections survive the round trip");
  $("rename-only").checked = true;
  $("rename-only").listeners.change();
  assert.equal($("edit-game").value, ORIGINAL, "the rename game selection survives too");
});

test("the release list accepts name tables beside a patch", () => {
  assert.equal(validateManifest({ schema: 1, releases: [release("ru", "0.1.25"), release("ru", "0.1.17", false)] })
    .length, 2);
  const bad = (change) => ({ schema: 1, releases: [{ ...release("ru", "0.1.25"), ...change }] });
  assert.throws(() => validateManifest(bad({ names: "elsewhere.json" })), /name tables/);
  assert.throws(() => validateManifest(bad({ names_sha256: "x" })), /name tables/);
  const half = release("ru", "0.1.25");
  delete half.names_sha256;
  assert.throws(() => validateManifest({ schema: 1, releases: [half] }), /fields/);
});

test("directions: the actual English game and each release with tables", () => {
  const sides = sidesOf([release("ru", "0.1.17"), release("ru", "0.1.25"), release("ru", "0.1.9", false)]);
  assert.deepEqual(sides.map((s) => [s.id, s.label]), [[ORIGINAL, "Pokemon Unbound 2.1.1.1 · English"],
    ["ru@0.1.25", "Russian · translation 0.1.25"], ["ru@0.1.17", "Russian · translation 0.1.17"]]);
  assert.deepEqual(pairOf(ORIGINAL, "ru@0.1.25", sides), { release: sides[1].release, back: false });
  assert.deepEqual(pairOf("ru@0.1.17", ORIGINAL, sides), { release: sides[2].release, back: true });
  assert.equal(pairOf("ru@0.1.17", "ru@0.1.25", sides), null);
  assert.equal(pairOf(ORIGINAL, ORIGINAL, sides), null);
  assert.equal(outputName("Pokemon Unbound 2.1.1.1.sav"), "Pokemon Unbound 2.1.1.1-changed.sav");
  assert.equal(outputName("game"), "game-changed.sav");
});

test("output names preserve the original extension or match the selected raw encoding", () => {
  const cases = [["Unbound.sav", "Unbound-changed.sav"], ["Unbound.srm", "Unbound-changed.srm"],
    ["Unbound.fla", "Unbound-changed.fla"], ["Unbound.sps", "Unbound-changed.sps"], ["Unbound.xps", "Unbound-changed.xps"],
    ["Unbound.gsv", "Unbound-changed.gsv"], ["Unbound.SaveRAM", "Unbound-changed.SaveRAM"], ["UNBOUND.SAV", "UNBOUND-changed.SAV"],
    ["Pokemon Unbound 2.1.1.1 [Rus by haritos90].srm", "Pokemon Unbound 2.1.1.1 [Rus by haritos90]-changed.srm"],
    ["Pokemon Unbound 2.1.1.1", "Pokemon Unbound 2.1.1.1-changed.sav"], [".srm", "save-changed.srm"]];
  for (const [name, out] of cases) assert.equal(outputName(name), out, name);
  assert.equal(outputName("Unbound.srm", "sav"), "Unbound-changed.sav");
  assert.equal(outputName("Unbound.gsv", "srm"), "Unbound-changed.srm");
  assert.equal(outputName("UNBOUND.SAV", "srm"), "UNBOUND-changed.srm");
  assert.throws(() => outputName("Unbound.srm", "gsv"), /Unknown save output format/);
});

test("save language choices keep the actual game name and localize its label", (ctx) => {
  ctx.after(() => { setUiLanguage("en"); setCatalog(null); });
  const rows = ["ru", "de", "es", "fr"].map((code) => release(code, "0.1.0"));
  for (const locale of ["en", "ru", "de"]) {
    setUiLanguage(locale);
    setCatalog(locale === "ru" ? { "{game} · English": "{game} · английская версия" } : null);
    const sides = sidesOf(rows);
    assert.deepEqual(sides.map((s) => s.label.split(" · ")[0]),
      ["Pokemon Unbound 2.1.1.1", "German", "Spanish", "French", "Russian"]);
    assert.equal(sides[0].label, locale === "ru" ? "Pokemon Unbound 2.1.1.1 · английская версия"
      : "Pokemon Unbound 2.1.1.1 · English");
  }
});

test("edit only: the same game on both sides, the save's letters, nothing converted", () => {
  const sides = sidesOf([release("ru", "0.1.17"), release("ru", "0.1.25")]);
  assert.deepEqual(pairOf(ORIGINAL, SAME, sides), { release: sides[1].release, edit: true, translated: false });
  assert.deepEqual(pairOf("ru@0.1.17", SAME, sides), { release: sides[2].release, edit: true, translated: true });
  assert.equal(pairOf(ORIGINAL, SAME, sidesOf([])), null);
  assert.equal(outputName("Unbound.srm"), "Unbound-changed.srm");
  // the game whose default names alone match the most Pokémon
  assert.equal(detectedSide([0, 4], [ORIGINAL, "ru@0.1.25"]), "ru@0.1.25");
  assert.equal(detectedSide([3, 1, 0], [ORIGINAL, "ru@0.1.25", "de@0.1.0"]), ORIGINAL);
  assert.equal(detectedSide([0, 0], [ORIGINAL, "ru@0.1.25"]), null);
  assert.equal(detectedSide([2, 2], [ORIGINAL, "ru@0.1.25"]), null);
});
