import assert from "node:assert/strict";

import { test } from "node:test";

const { gameModel } = await import(new URL("js/landing.js", process.env.GEN3TL_WEB_ROOT_URL));

const { actionsOf, languageRows, SURFACES } = await import(new URL("js/pick.js", process.env.GEN3TL_WEB_ROOT_URL));

const { GAME_KEY, chosenGame, gameHash, pickerURL, pokedexLink, pokedexRedirect, readRegistry, recallGame, rememberGame, siteRoute } = await import(new URL("js/registry.js", process.env.GEN3TL_WEB_ROOT_URL));

import { fakeStorage } from "./fixture.mjs";

const { Trail, placeOf, tailId } = await import(new URL("js/data.js", process.env.GEN3TL_WEB_ROOT_URL));

const BASE = "https://example.org/data/registry.json";

const game = (id, stage, languages) => ({ id, name: id, stage, engine: "emerald", languages, data: "./" });

const REGISTRY = readRegistry({
  schema: 1, default: "unbound-2.1.1.1",
  games: [game("unbound-2.1.1.1", "translation", ["de", "ru"]), game("other-hack-2.0", "catalog", ["ru"]),
    game("sample-hack-1.0", "catalog", [])],
}, BASE);

test("the default game is named or the first translation game", () => {
  assert.equal(REGISTRY.default, "unbound-2.1.1.1");
  const implicit = readRegistry({ schema: 1, games: [game("a", "catalog", []), game("b", "translation", [])] }, BASE);
  assert.equal(implicit.default, "b");
  assert.equal(readRegistry({ schema: 1, games: [] }, BASE).default, null);
  assert.throws(() => readRegistry({ schema: 1, default: "x", games: [] }, BASE), /unknown default game/);
});

test("a game declares its source language, defaulting to English", () => {
  assert.equal(REGISTRY.games[0].sourceLanguage, "en");
  const source = readRegistry({ schema: 1, games: [{ ...game("a", "catalog", []), source_language: "pt-BR" }] }, BASE);
  assert.equal(source.games[0].sourceLanguage, "pt-BR");
  assert.throws(() => readRegistry({ schema: 1, games: [{ ...game("a", "catalog", []), source_language: "../en" }] }, BASE),
    /invalid source language/);
});

test("routes carry the game; older language-only links resolve to the default game", () => {
  assert.deepEqual(siteRoute("#other-hack-2.0/ru/s0000100", REGISTRY),
    { game: "other-hack-2.0", language: "ru", tail: ["s0000100"] });
  assert.deepEqual(siteRoute("#ru/s0028780", REGISTRY), { game: "unbound-2.1.1.1", language: "ru", tail: ["s0028780"] });
  assert.deepEqual(siteRoute("#ru/pictures/G09", REGISTRY),
    { game: "unbound-2.1.1.1", language: "ru", tail: ["pictures", "G09"] });
  assert.deepEqual(siteRoute("#fr/x", REGISTRY), { game: null, language: null, tail: [] });
  assert.deepEqual(siteRoute("#%E0%A4%A", REGISTRY), { game: null, language: null, tail: [] });
  assert.deepEqual(siteRoute("", REGISTRY), { game: null, language: null, tail: [] });
  assert.equal(gameHash("unbound-2.1.1.1", "ru", "pokedex", 25), "#unbound-2.1.1.1/ru/pokedex/25");
  assert.equal(gameHash("unbound-2.1.1.1"), "#unbound-2.1.1.1");
  // an entry key is one encoded segment
  const keyed = gameHash("unbound-2.1.1.1", "ru", "map:3.48/npc:0/1");
  assert.equal(keyed, "#unbound-2.1.1.1/ru/map%3A3.48%2Fnpc%3A0%2F1");
  assert.equal(tailId(siteRoute(keyed, REGISTRY).tail), "map:3.48/npc:0/1");
  assert.equal(tailId(siteRoute("#unbound-2.1.1.1/ru/map:3.48/npc:0/1", REGISTRY).tail), "map:3.48/npc:0/1");
  assert.equal(pickerURL("patch"), "pick?next=patch");
});

test("a surface opens on the hash, then the remembered game, then the default game", () => {
  const storage = fakeStorage();
  assert.equal(recallGame(storage), null);
  assert.equal(chosenGame(REGISTRY, "", storage).game.id, REGISTRY.default);
  rememberGame("other-hack-2.0", storage);
  assert.equal(storage.map.get(GAME_KEY), "other-hack-2.0");
  assert.equal(chosenGame(REGISTRY, "", storage).game.id, "other-hack-2.0");
  assert.equal(chosenGame(REGISTRY, "#unbound-2.1.1.1/ru", storage).game.id, "unbound-2.1.1.1");
  assert.deepEqual(chosenGame(REGISTRY, "#unbound-2.1.1.1/ru", storage).route.language, "ru");
  const released = (g) => g.id === "unbound-2.1.1.1";
  assert.equal(chosenGame(REGISTRY, "", storage, released).game.id, "unbound-2.1.1.1");
  assert.equal(chosenGame(REGISTRY, "", fakeStorage(), (g) => g.stage === "catalog").game, null);
  rememberGame("x", fakeStorage(true)); // a full storage keeps the page working
  assert.equal(recallGame({ getItem() { throw new Error("denied"); } }), null);
});

test("the picker offers the surfaces a game's data allows", () => {
  const manifest = {
    languages: [{ code: "ru", profile: "unbound-2.1.1.1", index: "x", entries: 10, progress: { approved: 10 } },
      { code: "de", profile: "unbound-2.1.1.1", index: "y", entries: 2, progress: { approved: 2 } },
      { code: "ru", profile: "other-hack-2.0", index: "z", entries: 5, progress: { untranslated: 5 } }],
    profiles: [{ id: "unbound-2.1.1.1", pokedex: "pokedex/unbound-2.1.1.1/pokedex.json" },
      { id: "sample-hack-1.0", pokedex: "pokedex/sample-hack-1.0/pokedex.json" }],
  };
  const release = { profile: "unbound-2.1.1.1", language: "ru", version: "0.1.17", source_sha1: "a".repeat(40) };
  const [unbound, other, sample] = REGISTRY.games.map((g) => gameModel(g, manifest, [release]));
  assert.deepEqual(actionsOf(unbound, null), ["patch", "editor", "pokedex"]);
  assert.deepEqual(actionsOf(unbound, "editor"), ["editor", "patch", "pokedex"]);
  assert.deepEqual(actionsOf(other, "patch"), ["editor"]);
  assert.deepEqual(actionsOf(sample, null), []);
  assert.equal(SURFACES.patch.url(unbound), "patch#unbound-2.1.1.1");
  assert.equal(SURFACES.pokedex.url(unbound), "pokedex#unbound-2.1.1.1/en");
  const rows = (model) => languageRows(model).map((row) => [row.name, row.tone, row.status, row.percent]);
  assert.deepEqual(rows(unbound), [["Russian", "ok", "Released", "100%"], ["German", "plain", "Open for translation", "100%"]]);
  assert.deepEqual(rows(other), [["Russian", "warn", "Drafting", "0%"]]);
  assert.deepEqual(rows(sample), []);
});

test("the editor's Pokédex link and its old hash lead to the Pokédex page", () => {
  assert.equal(pokedexLink("unbound-2.1.1.1", "ru"), "pokedex#unbound-2.1.1.1/ru");
  assert.equal(pokedexLink("unbound-2.1.1.1", "ru", ["moves", "7"]), "pokedex#unbound-2.1.1.1/ru/moves/7");
  const route = (tail) => ({ game: "unbound-2.1.1.1", language: "ru", tail });
  assert.equal(pokedexRedirect(route(["pokedex", "18"]), "unbound-2.1.1.1", "ru"), "pokedex#unbound-2.1.1.1/ru/species/18");
  assert.equal(pokedexRedirect(route(["pokedex"]), "unbound-2.1.1.1", "ru"), "pokedex#unbound-2.1.1.1/ru");
  assert.equal(pokedexRedirect(route(["s0001234"]), "unbound-2.1.1.1", "ru"), null);
  assert.equal(pokedexRedirect(route(["pokedex", "18"]), "unbound-2.1.1.1", "de"), null);
  assert.equal(pokedexRedirect({ game: "other", language: "ru", tail: ["pokedex"] }, "unbound-2.1.1.1", "ru"), null);
});

test("an editor hash names a view and its item; any other tail names a Texts entry", () => {
  const place = (hash) => placeOf(siteRoute(hash, REGISTRY).tail);
  assert.deepEqual(place(gameHash("unbound-2.1.1.1", "ru", "families", "word:trainer-class:maniac")),
    { view: "families", id: "word:trainer-class:maniac" });
  assert.deepEqual(place("#unbound-2.1.1.1/ru/terms/trainer-class:ruin-maniac"), { view: "terms", id: "trainer-class:ruin-maniac" });
  assert.deepEqual(place("#unbound-2.1.1.1/ru/pictures/G09"), { view: "pictures", id: "G09" });
  assert.deepEqual(place("#unbound-2.1.1.1/ru/keyboards/2"), { view: "keyboards", id: "2" });
  assert.deepEqual(place("#unbound-2.1.1.1/ru/fonts"), { view: "fonts", id: null });
  assert.deepEqual(place(gameHash("unbound-2.1.1.1", "ru", "map:3.48/npc:0/1")), { view: "texts", id: "map:3.48/npc:0/1" });
  assert.deepEqual(place("#unbound-2.1.1.1/ru/map:3.48/npc:0/1"), { view: "texts", id: "map:3.48/npc:0/1" });
  assert.deepEqual(place("#unbound-2.1.1.1/ru"), { view: "texts", id: null });
});

test("a place opened from another view keeps the way back in the browser history", () => {
  const entries = [{ state: null, hash: "#unbound-2.1.1.1/ru/families/word:trainer-class:maniac" }];
  let at = 0;
  const history = {
    get state() { return entries[at].state; },
    pushState(state, _title, hash) { entries.splice(++at, entries.length, { state, hash }); },
    replaceState(state, _title, hash) { entries[at] = { state, hash }; },
    back() { at -= 1; },
    forward() { at += 1; },
  };
  const trail = new Trail(history, ["texts", "pictures", "terms", "families", "keyboards", "fonts"]);
  const hash = () => entries[at].hash;
  assert.equal(trail.from, null);
  trail.leave("families", hash()); // a member opens its term
  trail.replace("#unbound-2.1.1.1/ru/terms/trainer-class:ruin-maniac");
  trail.replace("#unbound-2.1.1.1/ru/terms/trainer-class:bug-maniac"); // Prev and Next keep the way back
  assert.equal(entries.length, 2);
  assert.equal(trail.from, "families");
  trail.leave("terms", hash()); // a use opens its entry
  trail.replace("#unbound-2.1.1.1/ru/s0A4862B");
  assert.equal(trail.from, "terms");
  history.back();
  assert.equal(trail.from, "families");
  assert.deepEqual(placeOf(siteRoute(hash(), REGISTRY).tail), { view: "terms", id: "trainer-class:bug-maniac" });
  history.back();
  assert.equal(trail.from, null);
  assert.deepEqual(placeOf(siteRoute(hash(), REGISTRY).tail), { view: "families", id: "word:trainer-class:maniac" });
  history.forward();
  assert.equal(trail.from, "families");
  history.replaceState({ from: "pokedex" }, "", hash());
  assert.equal(trail.from, null); // no editor view
});
