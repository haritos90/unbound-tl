import assert from "node:assert/strict";

import { test } from "node:test";

const { pokedexRouteURL, speciesCardURL, speciesShareURL } = await import(new URL("js/pokedexshareurl.js", process.env.GEN3TL_WEB_ROOT_URL));

test("species share targets and card routes use the canonical public page", () => {
  const base = "https://site.test/pokedex";
  assert.equal(speciesShareURL(new URL("data/", base).href, "unbound-2.1.1.1", "ru", 978),
    "https://site.test/share/unbound-2.1.1.1/ru/species/978/");
  assert.equal(speciesCardURL(base, "unbound-2.1.1.1", "en", 978),
    "https://site.test/pokedex#unbound-2.1.1.1/en/species/978");
});

test("project share routes follow published slots and preserve the selected language", () => {
  const base = "https://site.test/";
  const pages = { en: "all", ru: "all", es: [981], de: [981], fr: [981] };
  for (const language of ["es", "de", "fr"]) {
    assert.equal(speciesShareURL(new URL("data/", base).href, "unbound-2.1.1.1", language, 978, pages),
      `https://site.test/share/unbound-2.1.1.1/en/species/978/?lang=${language}`);
    assert.equal(speciesShareURL(new URL("data/", base).href, "unbound-2.1.1.1", language, 981, pages),
      `https://site.test/share/unbound-2.1.1.1/${language}/species/981/`);
    const hash = `#unbound-2.1.1.1/${language}/species/978`;
    assert.equal(pokedexRouteURL(base, `${base}pokedex${hash}`, hash,
      { data: new URL("data/", base).href, game: "unbound-2.1.1.1", language, slot: 978, pages }),
    `https://site.test/share/unbound-2.1.1.1/en/species/978/?lang=${language}${hash}`);
  }
});

test("displayed routes retain queries without accumulating share paths", () => {
  const base = "https://site.test/subpath/";
  const hash = "#unbound-2.1.1.1/ru/species/981";
  const current = `${base}pokedex?share=1${hash}`;
  const species = { data: new URL("data/", base).href, game: "unbound-2.1.1.1", language: "ru", slot: 981 };
  const shared = `${base}share/unbound-2.1.1.1/ru/species/981/?share=1${hash}`;
  assert.equal(pokedexRouteURL(base, current, hash, species), shared);
  const moves = pokedexRouteURL(base, shared, "#unbound-2.1.1.1/ru/moves/174");
  assert.equal(moves, `${base}pokedex?share=1#unbound-2.1.1.1/ru/moves/174`);
  assert.equal(pokedexRouteURL(base, moves, hash, species), shared);
  const legacy = `${base}pokedex.html?share=1${hash}`;
  assert.equal(pokedexRouteURL(base, legacy, hash, species), shared);
  assert.equal(pokedexRouteURL(base, legacy, hash), current);
});
