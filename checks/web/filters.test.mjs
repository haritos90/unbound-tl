import assert from "node:assert/strict";

import { test } from "node:test";

const { DexMemory } = await import(new URL("js/dexpage.js", process.env.GEN3TL_WEB_ROOT_URL));

const { FILTER_SETS, FilterSet, targetOptions } = await import(new URL("js/filters.js", process.env.GEN3TL_WEB_ROOT_URL));

const { setLabelSource, setUiLanguage, SOURCE_LANGUAGE } = await import(new URL("js/ui.js", process.env.GEN3TL_WEB_ROOT_URL));

const { PokedexView } = await import(new URL("js/pokedex/pokedex.js", process.env.GEN3TL_WEB_ROOT_URL));

const { targetLabel } = await import(new URL("js/pokedexdataview/pokedexdataview.js", process.env.GEN3TL_WEB_ROOT_URL));

import { fakeStorage, NEEDS_UNBOUND, projectLabelEntries, STANDALONE_LABELS, stubPage, UNBOUND } from "./fixture.mjs";

const emptyContext = {
  types: [], moves: [], species: [], abilities: [], items: [], data: {},
  text: (id) => id, source: () => "", otherNames: () => [],
  speciesName: () => "", speciesNames: () => [],
};

test("target options contain only present kinds and share card labels in every catalog", { skip: NEEDS_UNBOUND }, (context) => {
  const { $ } = stubPage(context, "pokedex");
  context.after(() => { setLabelSource(null); setUiLanguage(SOURCE_LANGUAGE); });
  const kinds = [...new Set(UNBOUND.moves.map((move) => move.target_key))].sort();
  assert.equal(kinds.length, 8);
  assert.deepEqual(targetOptions([]), []);
  assert.deepEqual(targetOptions([{ target_key: "user" }, { target_key: "user" }, {}]), [{ value: "user", label: "User" }]);
  for (const { code } of STANDALONE_LABELS.languages) {
    const entries = projectLabelEntries(code);
    const labels = Object.fromEntries(Object.entries(entries).map(([key, value]) => [key.slice(5), value]));
    const view = { lang: code, texts: new Map(), host: { data: () => ({ labels: {} }), pageLabels: () => labels } };
    setUiLanguage(code);
    setLabelSource((key) => PokedexView.prototype.label.call(view, key));
    const set = new FilterSet("moves", FILTER_SETS.moves, { container: $("x-filters"), onChange() {} });
    set.render({ ...emptyContext, moves: UNBOUND.moves });
    const options = targetOptions(UNBOUND.moves);
    assert.deepEqual(options.map((option) => option.value).sort(), kinds);
    assert.deepEqual(set.controls.get("target").buttons.map((button) => button.textContent), options.map((option) => option.label));
    for (const option of options) {
      const move = UNBOUND.moves.find((row) => row.target_key === option.value);
      const english = targetLabel(move.target, move.target_key);
      assert.equal(option.label, english);
      const pair = Object.values(labels).find((value) => value[code === SOURCE_LANGUAGE ? 0 : 1] === option.label);
      assert.ok(pair?.[0] && pair?.[1], `${code} ${option.value}`);
    }
  }
});

test("a page registry extension follows controls, matching, memory, chips and Reset", { skip: NEEDS_UNBOUND }, async (context) => {
  const { $ } = stubPage(context, "pokedex");
  const extra = { key: "slot", label: "Slot", group: "Other", kind: "number", operators: [">="],
    predicate: (record, value) => record.slot >= Number(value.a) };
  FILTER_SETS.species.push(extra);
  context.after(() => FILTER_SETS.species.splice(FILTER_SETS.species.indexOf(extra), 1));
  const storage = fakeStorage();
  const memory = new DexMemory("extension", "ru", () => storage);
  const species = UNBOUND.species.filter((record) => record.slot > 0).slice(0, 2);
  const data = { species, moves: [], trainers: [], encounters: [], abilities: [], items: [],
    types: UNBOUND.types, type_effectiveness: [] };
  const view = new PokedexView({ data: () => data, load: async () => {}, memory: () => memory,
    entry: async (id) => ({ source_text: id, translation: "" }), spriteSrc: (path) => path, setHash() {},
  }, $);
  await view.load();
  view.loaded = true;
  const set = view.filterSets.species;
  const control = set.controls.get("slot");
  control.a.value = String(species[1].slot);
  control.a.listeners.input();
  assert.deepEqual(view.filtered.map((index) => species[index].slot), [species[1].slot]);
  const saved = new DexMemory("extension", "ru", () => storage);
  assert.deepEqual(saved.state.modes.species.filters.slot, { op: ">=", a: String(species[1].slot) });
  set.details.open = false;
  set.details.listeners.toggle();
  assert.equal(new DexMemory("extension", "ru", () => storage).state.modes.species.filtersOpen, false);
  assert.ok(set.chipsNode.children.some((chip) => chip.textContent.includes("Slot ≥")));
  set.chipsNode.children.find((chip) => chip.getAttribute("data-key") === "slot").listeners.click();
  assert.equal(set.values().slot, undefined);
  assert.equal(view.filtered.length, 2);
  control.a.value = String(species[1].slot);
  control.a.listeners.input();
  $("x-search").value = "query";
  set.details.querySelectorAll("button").find((button) => button.textContent === "Reset")
    .listeners.click({ preventDefault() {} });
  assert.deepEqual(set.values(), {});
  assert.equal($("x-search").value, "");
  assert.equal(memory.state.modes.species.filters.slot, undefined);
});
