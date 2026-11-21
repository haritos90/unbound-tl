import assert from "node:assert/strict";

import { readFileSync } from "node:fs";

import { test } from "node:test";

const { gameModel, grouped, hrefs, landingModel, languageMeta, languageRequestURL, loadSources, render } = await import(new URL("js/landing.js", process.env.GEN3TL_WEB_ROOT_URL));

const { loadRegistry, readRegistry, recallGame } = await import(new URL("js/registry.js", process.env.GEN3TL_WEB_ROOT_URL));

const { gamesModel, STAGE_DETAILS, STAGES } = await import(new URL("js/site-model.js", process.env.GEN3TL_WEB_ROOT_URL));

const { setUiLanguage } = await import(new URL("js/ui.js", process.env.GEN3TL_WEB_ROOT_URL));

import { fakeFetch, stubPage } from "./fixture.mjs";

const BASE = "https://example.org/site/data/registry.json";

const SHA1 = "b4776b82a4c7915d0fadeaa27e013523f99dfd94";

const REGISTRY = {
  schema: 1,
  games: [
    { id: "unbound-2.1.1.1", name: "Pokemon Unbound 2.1.1.1", stage: "translation", engine: "firered-cfru",
      languages: ["de", "ru"], data: "./" },
    { id: "other-hack-2.0", name: "Other Hack 2.0", stage: "catalog", engine: "firered-cfru",
      languages: ["ru"], data: "https://other.example/other/data" },
    { id: "sample-hack-1.0", name: "Sample Hack 1.0", stage: "catalog", engine: "emerald",
      languages: [], data: "./" },
  ],
};

const MANIFEST = {
  schema: 1, toolkit: "0.38.0+abc1234", bundle: "gen3tl-check.zip",
  languages: [
    { code: "ru", index: "unbound-2.1.1.1/ru/index.json", profile: "unbound-2.1.1.1", entries: 100,
      progress: { approved: 90, fuzzy: 2, nothing: 5, untranslated: 3 } },
    { code: "de", index: "unbound-2.1.1.1/de/index.json", profile: "unbound-2.1.1.1", entries: 24,
      progress: { approved: 24 } },
  ],
  profiles: [
    { id: "unbound-2.1.1.1", name: "Pokemon Unbound 2.1.1.1", support: "translation", engine: "firered-cfru",
      sha1: SHA1, pokedex: "pokedex/unbound-2.1.1.1/pokedex.json" },
    { id: "sample-hack-1.0", name: "Sample Hack 1.0", support: "catalog", engine: "emerald",
      sha1: "8bbf30c3f11e0a4371231cff8301e64e62bd4f31",
      source_catalog: { entries: 7, manifest: "sources/x/catalog.json", pot: "sources/x/source.pot" } },
  ],
};

test("language requests use configured repositories", () => {
  const game = gameModel({ ...REGISTRY.games[0], repository: "contributor/game" }, MANIFEST);
  const url = new URL(languageRequestURL(game));
  assert.equal(url.origin, "https://github.com");
  assert.equal(url.pathname, "/contributor/game/issues/new");
  assert.ok(url.searchParams.get("title").includes(game.name));
  assert.ok(url.searchParams.get("body").includes("contribute"));
  for (const repository of [null, "../game", "https://example.org/game"]) {
    assert.equal(languageRequestURL({ ...game, repository }), null);
  }
});

test("landing language rows keep English names in every site language", (ctx) => {
  ctx.after(() => setUiLanguage("en"));
  for (const locale of ["en", "ru", "de"]) {
    setUiLanguage(locale);
    const game = { ...readRegistry(REGISTRY, BASE).games[0], languages: ["ru", "de", "es", "fr"] };
    const model = gameModel(game, MANIFEST);
    assert.deepEqual(Object.fromEntries(model.languages.map((l) => [l.code, l.name])),
      { ru: "Russian", de: "German", es: "Spanish", fr: "French" });
  }
});

function release(version) {
  return {
    profile: "unbound-2.1.1.1", profile_name: "Pokemon Unbound 2.1.1.1", language: "ru", version,
    source_sha1: SHA1, source_size: 33554432, result_sha1: "e3b9411368a1e64cfbab94b8d4a6e09f400d281e",
    result_size: 33554432, patch: `unbound-2.1.1.1/ru/${version}.ups`, patch_sha256: "4".repeat(64),
    patch_size: 1332576, output: `unbound-2.1.1.1-ru-${version}.gba`,
  };
}

test("the registry resolves data URLs and rejects invalid games", () => {
  const { games } = readRegistry(REGISTRY, BASE);
  assert.deepEqual(games.map((g) => g.data), [
    "https://example.org/site/data/", "https://other.example/other/data/", "https://example.org/site/data/"]);
  assert.equal(games[0].engine, "firered-cfru");
  assert.throws(() => readRegistry({ schema: 2, games: [] }, BASE), /unknown schema/);
  const bad = (change) => ({ schema: 1, games: [{ ...REGISTRY.games[0], ...change }] });
  assert.throws(() => readRegistry(bad({ id: "../x" }), BASE), /invalid game id/);
  assert.throws(() => readRegistry(bad({ stage: "released" }), BASE), /unknown stage/);
  assert.throws(() => readRegistry(bad({ languages: "ru" }), BASE), /invalid languages/);
  assert.throws(() => readRegistry(bad({ data: 3 }), BASE), /no data URL/);
  assert.throws(() => readRegistry(bad({ name: " " }), BASE), /no name/);
  assert.throws(() => readRegistry({ schema: 1, games: [REGISTRY.games[0], REGISTRY.games[0]] }, BASE),
    /duplicate game/);
});

test("the registry loads over fetch and reports HTTP errors", async () => {
  const fetcher = fakeFetch({ [BASE]: REGISTRY });
  assert.equal((await loadRegistry(BASE, fetcher)).games.length, 3);
  await assert.rejects(loadRegistry("https://example.org/none.json", fetcher), /HTTP 404/);
});

test("a game joins its catalogs and releases", () => {
  const game = readRegistry(REGISTRY, BASE).games[0];
  const model = gameModel(game, MANIFEST, [release("0.1.9"), release("0.1.17")]);
  assert.equal(model.sha1, SHA1);
  assert.equal(model.entries, 100);
  assert.equal(model.released, true);
  assert.equal(model.engineLabel, "firered-cfru");
  assert.deepEqual(model.languages.map((l) => [l.code, l.state, l.percent]), [["ru", "released", 94], ["de", "open", 100]]);
  assert.equal(model.languages[0].release.version, "0.1.17");
  assert.deepEqual(model.languages[0].releases.map((r) => r.version), ["0.1.17", "0.1.9"]);
  assert.equal(languageMeta(model.languages[0]), "Translation 0.1.17 · 100 entries · 96% translated · 94% approved");
  assert.equal(languageMeta(model.languages[1]), "24 entries · 100% translated · 100% approved");
  assert.deepEqual(hrefs(model, model.languages[0]), {
    patch: "patch#unbound-2.1.1.1/ru", editor: "editor#unbound-2.1.1.1/ru",
    save: "save#unbound-2.1.1.1/ru", pokedex: "pokedex#unbound-2.1.1.1/ru" });
  assert.equal(grouped(SHA1), "b4776b82 a4c7915d 0fadeaa2 7e013523 f99dfd94");
});

test("a catalog-stage language drafts and a game without data stays listed", () => {
  const games = readRegistry(REGISTRY, BASE).games;
  const other = gameModel(games[1], { profiles: [], languages: [
    { code: "ru", index: "other-hack-2.0/ru/index.json", profile: "other-hack-2.0", entries: 14000,
      progress: { untranslated: 14000 } }] });
  assert.equal(other.languages[0].state, "drafting");
  assert.equal(other.entries, 14000);
  const sample = gameModel(games[2], MANIFEST);
  assert.equal(sample.languages.length, 0);
  assert.equal(sample.sourceEntries, 7);
  assert.equal(gameModel(games[1], null).sha1, null);
});

test("the landing fetches each data directory once and keeps every game in order", async () => {
  const registry = readRegistry(REGISTRY, BASE);
  const fetcher = fakeFetch({
    "https://example.org/site/data/languages.json": MANIFEST,
    "https://example.org/site/data/releases/releases.json": { schema: 1, releases: [release("0.1.17")] },
  });
  const sources = await loadSources(registry, fetcher);
  assert.equal(fetcher.calls.length, 4);
  assert.deepEqual(sources.get("https://example.org/site/data/").releases.map((r) => r.version), ["0.1.17"]);
  assert.match(sources.get("https://other.example/other/data/").error, /HTTP 404/);
  const model = landingModel(registry, sources);
  assert.deepEqual(model.games.map((g) => g.id), registry.games.map((g) => g.id));
  assert.equal(model.games[1].error, sources.get("https://other.example/other/data/").error);
  assert.equal(model.toolkit, "0.38.0+abc1234");
});

test("an invalid release list is reported and ignored", async () => {
  const registry = readRegistry({ schema: 1, games: [REGISTRY.games[0]] }, BASE);
  const sources = await loadSources(registry, fakeFetch({
    "https://example.org/site/data/languages.json": MANIFEST,
    "https://example.org/site/data/releases/releases.json": { schema: 1, releases: [{ profile: "x" }] },
  }));
  const source = sources.get("https://example.org/site/data/");
  assert.deepEqual(source.releases, []);
  assert.match(source.error, /Invalid release fields/);
});

const SHARED = {
  game: { id: "example", name: "Example", stage: "translation", engine: "custom-engine", engine_label: "Example engine",
    languages: ["de", "fr"], data: "./", source_language: "pt-BR" },
  manifest: {
    profiles: [{ id: "example", pokedex: "dex/example.json" }],
    languages: [
      { profile: "example", code: "de", entries: 10, progress: { approved: 4, untranslated: 6 }, index: "de/index.json" },
      { profile: "example", code: "es", entries: 8, texts: "es/texts.json" },
      { profile: "example", code: "it", entries: 4 },
      { profile: "elsewhere", code: "ja", index: "ja/index.json" },
    ],
  },
  releases: [
    { profile: "example", language: "ru", version: "1.1.0" },
    { profile: "example", language: "ru", version: "1.0.0", names: "ru/names.json" },
    { profile: "elsewhere", language: "zh", version: "2.0.0" },
  ],
};

function shared(stage = "translation", manifest = SHARED.manifest, releases = SHARED.releases) {
  const registry = readRegistry({ schema: 1, games: [{ ...SHARED.game, stage }] }, BASE);
  const sources = new Map([[registry.games[0].data, { manifest, releases }]]);
  return { registry, sources, game: gamesModel(registry, sources)[0] };
}

test("every stage renders the same card with game-scoped available actions", (context) => {
  const { $ } = stubPage(context, "index");
  const registry = readRegistry({ schema: 1, default: STAGES.at(-1), games: STAGES.map((stage) => ({
    ...SHARED.game, id: stage, name: stage, stage,
  })) }, BASE);
  const manifest = {
    profiles: STAGES.map((id) => ({ ...SHARED.manifest.profiles[0], id })),
    languages: STAGES.flatMap((profile) => SHARED.manifest.languages.map((language) => ({ ...language, profile }))),
  };
  const releases = STAGES.flatMap((profile) => SHARED.releases.map((release) => ({ ...release, profile })));
  const sources = new Map([[registry.games[0].data, { manifest, releases }]]);
  render(landingModel(registry, sources, "", null), $);
  assert.equal($("games-empty").hidden, true);
  assert.equal($("games-list").hidden, false);
  const cards = $("games-list").children;
  assert.equal(cards.length, registry.games.length);
  for (const [index, card] of cards.entries()) {
    const game = registry.games[index];
    assert.equal(card.tagName, "ARTICLE");
    assert.equal(card.className, "game card");
    assert.deepEqual(card.children.map((node) => node.className),
      ["game-summary", "langs", "game-language-request small muted"]);
    assert.equal(card.querySelector("h3").textContent, game.name);
    assert.equal(card.getAttribute("aria-current"), game.id === registry.default ? "true" : null);
    assert.ok(card.textContent.includes(STAGE_DETAILS[game.stage].description));
    const actions = card.firstChild.querySelectorAll("a");
    const expected = game.stage === "discovery" ? ["patch", "save", "pokedex"] : ["patch", "editor", "save", "pokedex"];
    assert.deepEqual(actions.map((link) => link.getAttribute("href")), expected.map((page) =>
      `${page}#${game.id}${page === "pokedex" ? `/${game.sourceLanguage}` : ""}`));
    assert.match(actions[0].className, /primary/);
    assert.ok(actions.slice(1).every((link) => !link.className.includes("primary")));
    for (const link of card.querySelectorAll("a")) {
      const route = new URL(link.getAttribute("href"), BASE).hash.slice(1).split("/");
      assert.equal(route[0], game.id);
    }
  }
});

test("games without surfaces retain cards, source counts and load errors", (context) => {
  const { $ } = stubPage(context, "index");
  const registry = readRegistry({ schema: 1, games: REGISTRY.games.slice(1) }, BASE);
  const sources = new Map([
    [registry.games[0].data, { error: "HTTP 503" }],
    [registry.games[1].data, { manifest: MANIFEST }],
  ]);
  render(landingModel(registry, sources, "", null), $);
  const cards = $("games-list").children;
  assert.equal(cards.length, 2);
  assert.equal($("games-empty").hidden, true);
  assert.match(cards[0].textContent, /Data unavailable: HTTP 503/);
  assert.match(cards[0].textContent, /Not available/);
  assert.match(cards[1].textContent, /7 draft source entries/);
  assert.match(cards[1].textContent, /No languages available yet\./);
  for (const card of cards) {
    assert.match(card.textContent, /No surface yet/);
    assert.deepEqual(card.querySelectorAll("a"), []);
    assert.equal(card.querySelectorAll("span").at(-1).getAttribute("aria-disabled"), "true");
  }
});

test("landing doors follow only the selected game and promote its first available tool", (context) => {
  const { $ } = stubPage(context, "index");
  const registry = readRegistry({ schema: 1, games: [SHARED.game, { ...SHARED.game, id: "released" }] }, BASE);
  const sources = new Map([[registry.games[0].data, { manifest: SHARED.manifest,
    releases: SHARED.releases.map((release) => ({ ...release, profile: "released" })) }]]);
  const visible = () => $("doors").children.filter((door) => !door.hidden);
  render(landingModel(registry, sources, "#example", null), $, "patch");
  assert.deepEqual(visible().map((door) => door.getAttribute("href")), ["editor#example", "pokedex#example/pt-BR"]);
  assert.equal(visible()[0].className, "door primary");
  assert.equal(visible()[1].className, "door");
  assert.equal($("door-patch").getAttribute("href"), null);
  assert.equal($("surface-unavailable").hidden, false);
  assert.equal($("surface-unavailable").textContent, `Patch is not available for ${SHARED.game.name}.`);
  assert.equal($("games-list").children.length, 2);
  render(landingModel(registry, sources, "#released", null), $, "patch");
  assert.deepEqual(visible().map((door) => door.getAttribute("href")), ["patch#released", "save#released"]);
  assert.equal(visible()[0].className, "door primary");
  assert.equal($("door-editor").className, "door");
  assert.equal($("surface-unavailable").hidden, true);
  const [other, selected] = $("games-list").children;
  assert.equal(other.getAttribute("aria-current"), null);
  assert.equal(selected.getAttribute("aria-current"), "true");
  const readable = shared("catalog", { profiles: SHARED.manifest.profiles, languages: [SHARED.manifest.languages[1]] }, []);
  render(landingModel(readable.registry, readable.sources, "", null), $);
  assert.deepEqual(visible().map((door) => door.getAttribute("href")), ["pokedex#example/pt-BR"]);
  assert.equal(visible()[0].className, "door primary");
});

function pageData(games = [SHARED.game], manifest = SHARED.manifest, releases = SHARED.releases) {
  return fakeFetch({
    "https://site.test/data/registry.json": { schema: 1, default: games[0]?.id, games },
    "https://site.test/data/languages.json": manifest,
    "https://site.test/data/site/catalogs.json": { schema: 1, catalogs: [] },
    "https://site.test/data/releases/releases.json": { schema: 1, releases: releases.map((row) => ({
      ...release(row.version), ...row, profile_name: row.profile,
      patch: `${row.profile}/${row.language}/${row.version}.ups`,
      ...(row.names ? { names: `${row.profile}/${row.language}/${row.version}.names.json`, names_sha256: "1".repeat(64) } : {}),
    })) },
  });
}

async function loadPage(context, page) {
  const source = readFileSync(new URL(`js/${page}.js`, process.env.GEN3TL_WEB_ROOT_URL), "utf8")
    .replace(/from "\.\/(.*?)"/g, (_, path) => `from "${new URL(`js/${path}`, process.env.GEN3TL_WEB_ROOT_URL).href}"`)
    .replace("onSiteLanguage,", "onSiteLanguage as subscribeSiteLanguage,");
  const lifecycle = `
    const subscriptions = [];
    const onSiteLanguage = (listener) => subscriptions.push(subscribeSiteLanguage(listener));
    export const dispose = () => subscriptions.forEach((unsubscribe) => unsubscribe());
  `;
  const module = await import(`data:text/javascript;base64,${Buffer.from(lifecycle + source).toString("base64")}#${encodeURIComponent(context.name)}`);
  context.after(module.dispose);
}

test("home collapses its loading sections for an empty registry", async (context) => {
  const { $ } = stubPage(context, "index");
  globalThis.location.replace = () => assert.fail("Unexpected picker redirect");
  globalThis.fetch = pageData([]);
  await loadPage(context, "home");
  assert.equal($("games-empty").hidden, false);
  assert.equal($("games-loading").hidden, true);
  assert.equal($("games-placeholders").hidden, true);
  assert.equal($("doors").hidden, true);
});

test("home opens central selection before loading game data", async (context) => {
  const { $, storage } = stubPage(context, "index");
  let target = null;
  globalThis.location.replace = (url) => { target = url; };
  globalThis.fetch = pageData([SHARED.game, { ...SHARED.game, id: "other" }]);
  await loadPage(context, "home");
  assert.equal(target, "pick?next=home");
  assert.equal($("games-list").children.length, 0);
  assert.equal(recallGame(storage), null);
  assert.ok(!globalThis.fetch.calls.some((url) => url.endsWith("releases.json")));
});

test("home remembers explicit choices, shows all cards and follows hash navigation", async (context) => {
  const { $, storage } = stubPage(context, "index", "#example");
  const listeners = {};
  globalThis.window.addEventListener = (event, listener) => { listeners[event] = listener; };
  globalThis.location.replace = () => assert.fail("Unexpected picker redirect");
  globalThis.fetch = pageData([SHARED.game, { ...SHARED.game, id: "other" }]);
  await loadPage(context, "home");
  assert.equal(recallGame(storage), "example");
  assert.equal($("games-list").children.length, 2);
  assert.equal($("door-patch").getAttribute("href"), "patch#example");
  globalThis.location.hash = "#other";
  listeners.hashchange();
  assert.equal(recallGame(storage), "other");
  assert.equal($("games-list").children[1].getAttribute("aria-current"), "true");
  assert.equal($("door-patch").hidden, true);
});

test("single-game picker opens the requested tool or explains its unavailability", async (context) => {
  const cases = [
    ["patch", SHARED.manifest, SHARED.releases, "", "patch#example"],
    ["editor", SHARED.manifest, [], "", "editor#example"],
    ["save", SHARED.manifest, SHARED.releases, "", "save#example"],
    ["pokedex", SHARED.manifest, [], "", "pokedex#example/pt-BR"],
    ["pokedex", SHARED.manifest, [], "#example/de", "pokedex#example/de"],
    ["pokedex", SHARED.manifest, [], "#example/missing", "pokedex#example/pt-BR"],
    ["patch", SHARED.manifest, [], "", "./?unavailable=patch#example"],
    ["save", SHARED.manifest, [], "", "./?unavailable=save#example"],
    ["editor", null, SHARED.releases, "", "./?unavailable=editor#example"],
    ["pokedex", null, SHARED.releases, "", "./?unavailable=pokedex#example"],
    ["home", SHARED.manifest, SHARED.releases, "", "./#example"],
    [null, null, [], "", "./#example"],
    ["toString", null, [], "", "./#example"],
  ];
  for (const [index, [next, manifest, releases, hash, target]] of cases.entries()) {
    await context.test(`${next} ${index}`, async (ctx) => {
      const { $, storage } = stubPage(ctx, "pick", hash);
      globalThis.location.search = next ? `?next=${next}` : "";
      let actual = null;
      globalThis.location.replace = (url) => { actual = url; };
      globalThis.fetch = pageData([SHARED.game], manifest, releases);
      await loadPage(ctx, "pick");
      for (let step = 0; step < 100 && !$("games-loading").hidden; step++) await new Promise((resolve) => setImmediate(resolve));
      assert.equal(actual, target);
      assert.equal(recallGame(storage), "example");
      assert.equal($("games").children.length, 0);
      assert.equal($("games-error").hidden, true);
    });
  }
});

test("central picker offers a landing choice and labels unavailable requested tools", async (context) => {
  for (const next of ["home", "patch"]) await context.test(next, async (ctx) => {
    const { $, storage } = stubPage(ctx, "pick", "#other");
    globalThis.location.search = `?next=${next}`;
    globalThis.location.replace = () => assert.fail("Unexpected tool redirect");
    globalThis.fetch = pageData([SHARED.game, { ...SHARED.game, id: "other" }], SHARED.manifest, []);
    await loadPage(ctx, "pick");
    for (let step = 0; step < 100 && !$("games-loading").hidden; step++) await new Promise((resolve) => setImmediate(resolve));
    const [first, second] = $("games").children;
    assert.equal(second.getAttribute("aria-current"), "true");
    if (next === "home") {
      const choice = second.querySelector("a");
      assert.equal(choice.getAttribute("href"), "./#other");
      assert.equal(choice.textContent, "Choose this game");
      choice.listeners.click();
      assert.equal(recallGame(storage), "other");
    } else {
      assert.match(first.textContent, /Patch is not available for/);
      assert.deepEqual(first.querySelectorAll("a").map((link) => link.getAttribute("href")),
        ["editor#example", "pokedex#example/pt-BR"]);
      assert.ok(first.querySelectorAll("a").every((link) => !link.className.includes("primary")));
    }
  });
});
