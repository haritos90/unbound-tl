import assert from "node:assert/strict";

import { readFileSync } from "node:fs";

import { test } from "node:test";

const { TARGET_LABELS, FLAG_LABELS, MOVE_LIST_LABELS } = await import(new URL("js/movelabels.js", process.env.GEN3TL_WEB_ROOT_URL));

const { EFFECT_KEYS } = await import(new URL("js/moveeffects.js", process.env.GEN3TL_WEB_ROOT_URL));

const { EGG_GROUPS, GROWTH_RATES, STAT_LABELS, TIER_LABELS, VARIANT_LABELS } = await import(new URL("js/pokedex/pokedex.js", process.env.GEN3TL_WEB_ROOT_URL));

const { CATEGORY, COUNT_LABELS, EV_LABELS, KIND_LABELS, METHOD_LABELS, POCKETS, ROD_LABELS, TRAINER_KINDS } = await import(new URL("js/pokedexdataview/pokedexdataview.js", process.env.GEN3TL_WEB_ROOT_URL));

const { CONDITION_LABELS, STATUS_LABELS } = await import(new URL("js/catchcalc.js", process.env.GEN3TL_WEB_ROOT_URL));

import { NEEDS_UNBOUND, trackedDataset } from "./fixture.mjs";

const SITE_PARTS = /<head>[^]*?<\/head>|<header class="mast"[^>]*>[^]*?<\/header>|<footer class="foot"[^>]*>[^]*?<\/footer>/g;

export function pageLabelKeys() {
  const keys = new Set();
  const html = readFileSync(new URL("pokedex.html", process.env.GEN3TL_WEB_ROOT_URL), "utf8").replace(SITE_PARTS, "");
  for (const tag of html.match(/<[a-z][^>]*>/g) ?? []) {
    if (/\sdata-ui-site[\s=>]/.test(tag)) continue; // the site catalog keys marked elements
    for (const m of tag.matchAll(/data-ui(?:-placeholder|-title|-label)?="([^"]+)"/g)) keys.add(m[1]);
  }
  for (const file of ["pokedex/species-data", "pokedex/evolutions", "pokedex/species-search", "pokedex/species-list",
    "pokedex/view-search", "pokedex/view-types", "pokedex/view-species", "pokedex/view-card",
    "pokedexdataview/items", "pokedexdataview/search", "pokedexdataview/trainers",
    "pokedexdataview/locations", "pokedexdataview/moves", "pokedexdataview/data-view", "pokedexdataview/item-view",
    "pokedexdataview/trainer-view", "pokedexdataview/location-view", "typechart", "dexpage", "movecard", "catchcalc",
    "filters", "pokedexexplorer"]) {
    const src = readFileSync(new URL(`js/${file}.js`, process.env.GEN3TL_WEB_ROOT_URL), "utf8")
      .split("\n").filter((line) => !/^\s*\/\//.test(line)).join("\n"); // keys in comments do not count
    for (const m of src.matchAll(/\bt\("((?:[^"\\]|\\.)*)"/g)) keys.add(m[1]);
  }
  for (const table of [STAT_LABELS, TIER_LABELS, VARIANT_LABELS, GROWTH_RATES, EGG_GROUPS, POCKETS, CATEGORY, COUNT_LABELS,
    KIND_LABELS, TRAINER_KINDS, EV_LABELS, METHOD_LABELS, ROD_LABELS, TARGET_LABELS, FLAG_LABELS, MOVE_LIST_LABELS,
    CONDITION_LABELS, STATUS_LABELS]) {
    for (const value of Object.values(table)) keys.add(value);
  }
  for (const key of Object.values(EFFECT_KEYS)) keys.add(`page:effect:${key}`);
  const dataset = trackedDataset("pokedex.json");
  for (const key of dataset.trainer_difficulty?.labels ?? []) keys.add(key);
  const trainerIvs = trackedDataset("trainer-ivs.json");
  for (const row of trainerIvs.ev_conditions ?? []) keys.add(row.set).add(row.clear);
  for (const row of trainerIvs.species_conditions ?? []) keys.add(row.label);
  for (const row of trainerIvs.species_rules ?? []) {
    keys.add(row.label);
    for (const label of Object.values(row.labels ?? {})) keys.add(label);
    for (const battle of row.battles ?? []) keys.add(battle.label);
  }
  for (const row of dataset.trainer_encounters ?? []) for (const variant of row.variants) if (variant.condition) keys.add(variant.condition);
  for (const row of dataset.encounters ?? []) for (const key of row.method_labels ?? []) keys.add(key);
  for (const item of dataset.items ?? []) for (const use of item.uses ?? []) {
    for (const give of use.gives) if (give.effect) keys.add(give.effect);
    for (const key of use.conditions ?? []) keys.add(key);
  }
  for (const species of dataset.species) {
    if (species.form_name?.startsWith("page:")) keys.add(species.form_name.slice(5));
    for (const edge of species.evolution ?? []) if (edge.tile) keys.add(edge.tile);
  }
  for (const item of dataset.items) {
    if (item.held_effect_key) keys.add(item.held_effect_key);
    if (item.held_effect_amount) keys.add(item.held_effect_amount.key);
    for (const key of item.held_effect_amount?.conditions ?? []) keys.add(key);
    for (const source of item.held_effect_amount?.upgrade_sources ?? []) keys.add(source.key);
    if (item.battle_usage_key) keys.add(item.battle_usage_key);
  }
  for (const move of dataset.moves) {
    if (move.effect_key) keys.add(`page:effect:${move.effect_key}`);
    if (move.power_formula) keys.add(move.power_formula);
    for (const [condition] of move.power_tiers ?? []) keys.add(condition);
    for (const condition of move.flinch_conditions ?? []) keys.add(condition);
    if (move.mechanics) {
      keys.add(move.mechanics.summary);
      for (const row of move.mechanics.rows) {
        keys.add(row.condition);
        keys.add(row.effect);
        for (const note of row.notes) keys.add(note);
      }
      if (move.mechanics.environments?.script_persistence) keys.add(move.mechanics.environments.script_persistence);
      for (const row of move.mechanics.environments?.rows ?? []) {
        keys.add(row.environment);
        keys.add(row.where);
        if (move.mechanics.environments.column === "effect") keys.add(row.value);
      }
    }
  }
  for (const map of dataset.location_maps ?? []) if (map.name) keys.add(map.name);
  return keys;
}

test("the tracked dataset maps every key the page and its modules use", { skip: NEEDS_UNBOUND }, () => {
  const keys = pageLabelKeys();
  assert.ok(keys.size > 250, `only ${keys.size} keys found`);
  const dataset = trackedDataset("pokedex.json");
  const labels = dataset.labels ?? {};
  const missing = [...keys].filter((key) => !(key in labels));
  assert.deepEqual(missing, []);
  const unused = Object.keys(labels).filter((key) => !keys.has(key));
  assert.deepEqual(unused, []);
});
