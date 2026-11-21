import assert from "node:assert/strict";

import { test } from "node:test";

const { speciesListFields, sortSpeciesIndices, DEX_ROW, displayName, evolutionCondition, edgeItems, evolutionGrid, evolutionTree, filterSpecies, formLabel, itemKeys, speciesMatches, recordIds, rowLabel, spritePath, datasetPath, inlineLearnsets, numberedName, statRanks, sourceParts, speciesSources, baseSlot, formesOf, formSectionRecords, createSpeciesSearch, speciesFamilyIndex } = await import(new URL("js/pokedex/pokedex.js", process.env.GEN3TL_WEB_ROOT_URL));

import { stubPage, NEEDS_UNBOUND, UNBOUND } from "./fixture.mjs";

const { setLabelSource } = await import(new URL("js/ui.js", process.env.GEN3TL_WEB_ROOT_URL));

const { chartTypes, defenseGroups, effectivenessMap, offenseGroups } = await import(new URL("js/typechart.js", process.env.GEN3TL_WEB_ROOT_URL));

const DATA = UNBOUND;

test("actual Mega, regional and other form families keep distinct Forms membership", { skip: NEEDS_UNBOUND }, () => {
  const records = DATA.species;
  const index = speciesFamilyIndex(records);
  const family = dex => records.filter(r => r.dex === dex);
  for (const record of family(531)) {
    assert.deepEqual(formSectionRecords(record, records, index).map(r => r.slot), [584]);
    assert.ok(evolutionGrid(evolutionTree(record, records)).cells.some(c => c.kind === "species" && c.slot === 917));
  }
  for (const record of family(6)) {
    assert.deepEqual(formSectionRecords(record, records, index).map(r => r.slot), [6, 1261]);
    const slots = evolutionGrid(evolutionTree(record, records)).cells.filter(c => c.kind === "species").map(c => c.slot);
    assert.ok(slots.includes(870) && slots.includes(871));
  }
  for (const record of family(80)) {
    assert.deepEqual(formSectionRecords(record, records, index).map(r => r.slot), [80, 1216]);
  }
  const regional = family(80).find(r => r.slot === 1216);
  assert.ok(!evolutionGrid(evolutionTree(regional, records)).cells.some(c => c.kind === "species" && c.slot === 876));
  for (const record of family(384)) assert.deepEqual(formSectionRecords(record, records, index).map(r => r.slot), [406]);
  for (const dex of [201, 382, 383, 386, 479, 493, 773, 800]) {
    for (const record of family(dex)) assert.deepEqual(formSectionRecords(record, records, index), formesOf(record, records, index));
  }
  assert.equal(index.megaTargets.size, 48);
});

const records = [
  {
    slot: 1, dex: 1, name: "species:1", types: [12, 3], base_stats: {
      hp: 45, attack: 49, defense: 49, speed: 45, sp_attack: 65, sp_defense: 65,
    },
    ev_yield: { hp: 0, attack: 0, defense: 0, speed: 2, sp_attack: 1, sp_defense: 0 },
    abilities: [65], height: 7, weight: 69, category: "pokedex_categories:1",
    catch_rate: 45, base_exp: 64, growth: 3, egg_groups: [1, 7], gender_ratio: 31,
    evolution: [{ method: 4, parameter: 16, target: 2, extra: 0 }],
    entry: ["s0444CB2"], offset: "0x19e0cb8", dex_offset: "0x1a357f0",
  },
  {
    slot: 25, dex: 25, name: "species:25", types: [13, 13], base_stats: {
      hp: 35, attack: 55, defense: 40, speed: 90, sp_attack: 50, sp_defense: 50,
    },
    abilities: [9, 9], height: 4, weight: 60, category: "pokedex_categories:25",
    entry: ["s044561D"],
  },
  {
    slot: 1292, dex: 892, name: "species:1292", types: [2, 17], base_stats: {
      hp: 100, attack: 130, defense: 100, speed: 97, sp_attack: 63, sp_defense: 60,
    },
    abilities: [33], height: 19, weight: 1050, category: "pokedex_categories:892",
    entry: ["s044B30B"],
  },
];

const ivysaur = {
  slot: 2, dex: 2, name: "species:2", types: [12, 3], base_stats: records[0].base_stats,
  abilities: [65], category: "pokedex_categories:2", entry: [], evolution: [],
  sprite: { front: "sprites/2-front.png", back: "sprites/2-back.png", shiny: "sprites/2-shiny.png", back_shiny: "sprites/2-back-shiny.png" },
};

test("scripted sources include Bulbasaur's egg, the starters and a trade", { skip: NEEDS_UNBOUND }, () => {
  const eggs = speciesSources(DATA.sources, 1);
  assert.equal(eggs.length, 3);
  assert.ok(eggs.every((source) => source.kind === "egg" && source.map_section === 155));
  assert.equal(speciesSources(DATA.sources, null).length, 0);
  for (const slot of [548, 551, 554]) {
    assert.deepEqual(speciesSources(DATA.sources, slot).map((source) => [source.kind, source.level, source.map_section]),
      [["starter", 15, 105]]);
  }
  const trade = speciesSources(DATA.sources, 470);
  assert.deepEqual(trade.map((source) => [source.kind, source.wanted]), [["trade", 338]]);
  const names = (id) => ({
    "mapsec:155": "Day Care", "mapsec:105": "Route 5", "mapsec:88": "Frozen Heights", "mapsec:96": "Tarmigan Town",
    "species:338": "Manectric", "items:460": "Mewtwonite Y",
  })[id] ?? "";
  assert.deepEqual(sourceParts(eggs[0], names), [{ text: "Egg from an NPC in Day Care" }]);
  assert.deepEqual(sourceParts(speciesSources(DATA.sources, 548)[0], names), [{ text: "Starter in Route 5" }]);
  assert.deepEqual(sourceParts(trade[0], names), [{ text: "Trade for " }, { species: 338, text: "Manectric" }, { text: " in Tarmigan Town" }]);
  assert.equal(trade[0].map, "12.2");
  assert.equal(trade[0].trade_index, 3);
  const gift = speciesSources(DATA.sources, 150).find((source) => source.item === 460);
  assert.deepEqual(sourceParts(gift, names), [
    { text: "Gift at level 75 in Frozen Heights with " }, { item: 460, text: "Mewtwonite Y" },
  ]);
});

const text = (id) => ({
  "species:1": "Бульбазавр", "species:2": "Ивизавр", "species:25": "", "species:1292": "Уршифу",
  "species:6": "Чаризард", "species:870": "Чаризард", "species:871": "Чаризард", "species:1261": "Чаризард",
  "items:447": "Чаризардит X", "items:448": "Чаризардит Y",
  "types:1": "Боевой", "types:12": "Трава", "types:3": "Яд", "types:13": "Электро",
  "types:2": "Летающий", "types:17": "Тёмный",
  "abilities:65": "Зарастание", "abilities:9": "Статика", "abilities:33": "Невидимый кулак",
  "pokedex_categories:1": "Семя", "pokedex_categories:25": "Мышь", "pokedex_categories:892": "",
  "s0444CB2": "С самого рождения он носит на спине семя.", "s044561D": "",
})[id] ?? "";

test("sprite paths include the extractor's sprite directory", () => {
  assert.equal(spritePath("pokedex/unbound-2.1.1.1/pokedex.json", "sprites/1-front.png"),
    "pokedex/unbound-2.1.1.1/sprites/sprites/1-front.png");
});

test("named forms remain searchable and precursor links keep distinct targets", { skip: NEEDS_UNBOUND }, () => {
  const records = DATA.species;
  const named = new Map([[752, "Kyurem"], [1209, "Zarude"], [1210, "Calyrex"],
    [1211, "Calyrex"], [1036, "Exeggcute"], [1038, "Cubone"]]);
  const names = id => named.get(Number(id.split(":")[1])) ?? id;
  assert.deepEqual(records.filter(record => /^Form \d+$/.test(formLabel(record, records, names))), []);
  for (const [query, slot] of [["Black Kyurem", 752], ["Dada", 1209], ["Ice Rider", 1210], ["Shadow Rider", 1211]]) {
    const record = records.find(row => row.slot === slot);
    assert.ok(filterSpecies(records, query, names).includes(records.indexOf(record)));
    const representative = record.form_browsing?.separate ? record : records.find(row => row.slot === baseSlot(record, records));
    assert.ok(filterSpecies(records, query, names, null, () => "", () => [], true).includes(records.indexOf(representative)));
  }
  for (const [slot, base, target] of [[1036, 102, 1037], [1038, 104, 1039]]) {
    const record = records.find(row => row.slot === slot);
    assert.equal(displayName(record, records, names), names(record.name));
    assert.ok(formesOf(records.find(row => row.slot === base), records).includes(record));
    assert.deepEqual(record.evolution.map(edge => edge.target), [target]);
  }
});

test("ordinary-name precursors retain separate form buttons", { skip: NEEDS_UNBOUND }, async (context) => {
  const { $ } = stubPage(context, "pokedex");
  const { PokedexView } = await import(new URL("js/pokedex/pokedex.js", process.env.GEN3TL_WEB_ROOT_URL));
  const opened = [];
  const records = DATA.species;
  const names = new Map([[102, "Эксегкьют"], [1036, "Эксегкьют"], [104, "Кьюбон"], [1038, "Кьюбон"]]);
  const view = { records, $, familyIndex: () => speciesFamilyIndex(records),
    host: { spriteSrc: path => path }, text: id => names.get(Number(id.split(":")[1])) ?? id,
    open: slot => opened.push(slot) };
  for (const [base, precursor] of [[102, 1036], [104, 1038]]) {
    PokedexView.prototype.renderFormes.call(view, records.find(record => record.slot === base));
    const buttons = $("x-formes").children;
    const first = buttons.find(button => button.getAttribute("data-key") === `species:${base}`);
    const second = buttons.find(button => button.getAttribute("data-key") === `species:${precursor}`);
    assert.equal(first.children.at(-1).textContent, second.children.at(-1).textContent);
    first.listeners.click();
    second.listeners.click();
  }
  assert.deepEqual(opened, [102, 1036, 104, 1038]);
});

test("Silvally keeps a plain default name, typed alternates and both numeric searches", { skip: NEEDS_UNBOUND }, () => {
  const records = DATA.species;
  const forms = records.filter((record) => record.dex === 773);
  const bySlot = new Map(records.map((record) => [record.slot, record]));
  const russian = (id) => ({
    "species:990": "Силвалли", "species:1056": "Силвалли", "types:10": "Огонь",
  })[id] ?? "";
  const base = bySlot.get(990), fire = bySlot.get(1056);
  assert.equal(forms.length, 18);
  assert.equal(base.form_name, null);
  assert.equal(formLabel(base, forms, russian), "");
  assert.deepEqual(forms.slice(1).map((record) => formLabel(record, forms, (id) => id)),
    forms.slice(1).map((record) => `types:${record.types[0]}`));
  assert.equal(displayName(base, records, russian), "Силвалли");
  assert.equal(numberedName(base, records, russian), "#990 Силвалли");
  assert.equal(numberedName(fire, records, russian), "#1056 Силвалли Огонь");
  assert.equal(displayName(fire, records, russian), "Силвалли Огонь");
  assert.deepEqual(rowLabel(base, russian), { dex: "990", name: "Силвалли" });
  assert.deepEqual(rowLabel(bySlot.get(773), () => "Spewpa"), { dex: "773", name: "Spewpa" });
  assert.deepEqual(filterSpecies(records, "990", russian).map((i) => records[i].slot), [990]);
  const numeric = filterSpecies(records, "773", russian).map((i) => records[i].slot);
  for (const slot of [773, ...forms.map((record) => record.slot)]) assert.ok(numeric.includes(slot), slot);
  const grouped = filterSpecies(records, "773", russian, null, russian, () => [], true).map((i) => records[i].slot);
  for (const slot of [773, 990]) assert.ok(grouped.includes(slot), slot);
});

test("the Formes block opens each named forme card with its own stats", async (context) => {
  const { $ } = stubPage(context, "pokedex");
  const { PokedexView } = await import(new URL("js/pokedex/pokedex.js", process.env.GEN3TL_WEB_ROOT_URL));
  const stats = (hp) => ({ hp, attack: 95, defense: 95, speed: 95, sp_attack: 95, sp_defense: 95 });
  const forms = [
    { slot: 990, dex: 773, base_species: 990, name: "species:990", types: [0], base_stats: stats(95), learnset: [],
      sprite: { front: "990.png" } },
    { slot: 1048, dex: 773, base_species: 990, name: "species:1048", form_name: "types:1", types: [1], base_stats: stats(100), learnset: [],
      sprite: { front: "1048.png" } },
    { slot: 1049, dex: 773, base_species: 990, name: "species:1049", form_name: "types:10", types: [10], base_stats: stats(110), learnset: [],
      sprite: { front: "1049.png" } },
  ];
  const names = {
    "species:990": "Silvally", "species:1048": "Silvally", "species:1049": "Silvally",
    "types:0": "Normal", "types:1": "Fighting", "types:10": "Fire",
  };
  const view = new PokedexView({
    data: () => ({ species: forms, abilities: [], moves: [], items: [], types: [{ id: 0 }, { id: 1 }, { id: 10 }] }), load: async () => {},
    entry: async (id) => ({ source_text: names[id] ?? "", translation: "" }),
    profile: () => ({ id: "unbound-2.1.1.1", name: "Pokemon Unbound 2.1.1.1" }),
    spriteSrc: (path) => `sprites/${path}`, setHash: () => {},
  }, $);
  await view.show();
  assert.deepEqual(view.filtered, [0]);
  assert.equal($("x-count").textContent, "1 of 1 species");
  assert.equal($("x-formes-block").hidden, false);
  assert.deepEqual($("x-facts").children.slice(0, 4).map((node) => node.textContent),
    ["Pokemon Unbound 2.1.1.1 internal ID", "990", "Offset", ""]);
  const buttons = $("x-formes").children;
  assert.deepEqual(buttons.map((button) => button.children.at(-1).textContent),
    ["Silvally", "Silvally Fighting", "Silvally Fire"]);
  assert.deepEqual(buttons.map((button) => button.children[0].getAttribute("src")),
    ["sprites/990.png", "sprites/1048.png", "sprites/1049.png"]);
  await buttons[2].listeners.click();
  assert.equal(view.cur, 1049);
  assert.equal($("x-name").textContent, "#1049 Silvally Fire");
  assert.equal($("x-stats").children[0].children[2].textContent, "110");
  assert.equal($("x-formes").children[2].getAttribute("aria-current"), "true");
  const filters = view.filterSets.species;
  const type = filters.controls.get("type").select;
  const stat = filters.controls.get("stat");
  type.value = "10";
  type.listeners.change();
  stat.a.value = "105";
  stat.a.listeners.input();
  assert.deepEqual(view.filtered, [0]);
  assert.equal(view.cur, 1049);
  assert.equal(filters.countNode.textContent, "1 / 1");
  type.value = "1";
  type.listeners.change();
  assert.deepEqual(view.filtered, []);
  type.value = "10";
  type.listeners.change();
  $("x-search").value = "Silvally Fighting";
  view.applyFilters();
  assert.deepEqual(view.filtered, []);
  filters.clear();
  assert.deepEqual(view.filtered, [0]);
  assert.equal(view.cur, 1049);
  $("x-search").value = "Silvally Fighting";
  view.applyFilters();
  assert.deepEqual(view.filtered, [0]);
  assert.equal(view.openFirst(), true);
  assert.equal(view.cur, 990);
  await $("x-formes").children[1].listeners.click();
  assert.equal(view.cur, 1048);
  assert.equal($("x-stats").children[0].children[2].textContent, "100");
});

test("item-at-tile evolution names known terrain and retains unknown numbers", { skip: NEEDS_UNBOUND }, () => {
  const edge = { method: 34, parameter: 96, target: 1022, extra: 23, tile: "shallow water" };
  const item = (id) => id === "items:96" ? "Thunder Stone" : "";
  assert.equal(evolutionCondition(edge, item), "Use Thunder Stone on shallow water");
  assert.equal(evolutionCondition({ ...edge, tile: undefined, extra: 99 }, item),
    "Use Thunder Stone at tile behavior 99");
  const pikachu = DATA.species.find((species) => species.slot === 25);
  assert.deepEqual(pikachu.evolution.find((evolution) => evolution.method === 34), edge);
});

test("every item-triggered evolution reference resolves through its declared key", { skip: NEEDS_UNBOUND }, () => {
  const items = DATA.items;
  for (const record of DATA.species) {
    for (const edge of record.evolution ?? []) {
      for (const id of edgeItems(edge)) {
        const item = items.find((row) => row.id === id);
        assert.equal(itemKeys(id, items)[0], item?.name ?? `items:${id}`);
        assert.ok(itemKeys(id, items).includes(`items:${id}`));
      }
    }
  }
  // The same declared-key resolution serves held, source and move-flag items.
  const referenced = new Set();
  for (const source of DATA.sources ?? []) if (source.item > 0) referenced.add(source.item);
  for (const trainer of DATA.trainers ?? []) for (const mon of trainer.party ?? []) if (mon.item) referenced.add(mon.item);
  for (const entry of Object.values(DATA.move_readers ?? {})) for (const item of entry?.readers?.items ?? []) referenced.add(item);
  for (const id of referenced) {
    const item = items.find((row) => row.id === id);
    assert.equal(itemKeys(id, items)[0], item?.name ?? `items:${id}`);
    assert.ok(itemKeys(id, items).includes(`items:${id}`));
  }
  const slowpoke = DATA.species.find((record) => record.slot === 1215);
  assert.ok(recordIds(slowpoke, items).includes("s0EB9283"));
  assert.ok(recordIds(slowpoke, items).includes("s0EB9291"));
  const rayquaza = DATA.species.find((record) => record.slot === 406);
  const megaEdge = rayquaza.evolution[0];
  assert.equal(megaEdge.parameter_kind, "move");
  assert.deepEqual(edgeItems(megaEdge), []);
  assert.ok(!recordIds(rayquaza, items).includes("items:559"));
  assert.ok(recordIds(rayquaza, items).includes("moves:559"));
  assert.equal(evolutionCondition(megaEdge, (id) => id === "moves:559" ? "DragonAscent" : "", items),
    "Mega · Knows DragonAscent");
});

test("effectiveness retains grouped values for every extracted species form", { skip: NEEDS_UNBOUND }, async (context) => {
  const { $ } = stubPage(context, "pokedex");
  const { PokedexView } = await import(new URL("js/pokedex/pokedex.js", process.env.GEN3TL_WEB_ROOT_URL));
  const view = new PokedexView({ data: () => DATA }, $);
  const map = effectivenessMap(DATA.type_effectiveness), ids = chartTypes(DATA.types);
  const labels = new Map([[0, "0"], [0.25, "¼"], [0.5, "½"], [1, "1"], [2, "2"], [4, "4"]]);
  for (const record of DATA.species) {
    const types = [...new Set(record.types ?? [])];
    const blocks = view.effectivenessBlocks(record);
    if (!types.length) { assert.deepEqual(blocks, []); continue; }
    const groups = [defenseGroups(map, types, ids), ...types.map((type) => offenseGroups(map, type, ids))];
    assert.equal(blocks.length, groups.length * 2, `species:${record.slot}`);
    for (const [index, grouped] of groups.entries()) {
      const expected = new Map(ids.map((id) => [id, "1"]));
      for (const { factor, ids: affected } of grouped) {
        for (const id of affected) expected.set(id, labels.get(factor));
      }
      const actual = blocks[index * 2 + 1].children.map((cell) =>
        [Number(cell.children[0].children[0].title.split(":")[1]), cell.children[1].textContent]);
      assert.deepEqual(actual, [...expected], `species:${record.slot} block:${index}`);
    }
  }
});

test("the view renders every field and navigates evolution targets", { skip: NEEDS_UNBOUND }, async () => {
  const fake = () => ({
    children: [], className: "", textContent: "", title: "", value: "", hidden: false,
    disabled: false, style: { setProperty(key, value) { this[key] = String(value); } }, scrollTop: 0, clientHeight: 400, listeners: {},
    addEventListener(ev, fn) { this.listeners[ev] = fn; },
    setAttribute(k, v) { this[k] = v; }, click() { this.listeners.click?.(); },
    append(...kids) { this.children.push(...kids.flat()); },
    replaceChildren(...kids) { this.children = [...kids.flat()]; },
    classList: { set: new Set(), toggle(c, on) { on ? this.set.add(c) : this.set.delete(c); } },
  });
  globalThis.document = { createElement: () => fake(), createTextNode: (t) => ({ text: t }) };
  const { el } = await import(new URL("js/dom.js", process.env.GEN3TL_WEB_ROOT_URL));
  const { PokedexView } = await import(new URL("js/pokedex/pokedex.js", process.env.GEN3TL_WEB_ROOT_URL));
  const { setLabelSource, t } = await import(new URL("js/ui.js", process.env.GEN3TL_WEB_ROOT_URL));
  const elements = new Map();
  const $ = (id) => {
    if (!elements.has(id)) elements.set(id, fake());
    return elements.get(id);
  };
  const data = {
      species: [
        { ...records[0], ability_details: [{ id: 65, regular: false, hidden: true }],
          sprite: { front: "sprites/1-front.png", back: "sprites/1-back.png", shiny: "sprites/1-shiny.png", back_shiny: "sprites/1-back-shiny.png" } },
        ivysaur,
      ],
      abilities: [{ id: 65, name: "abilities:65", description: "s ability 65" }],
      encounters: [],
      sources: [
        speciesSources(DATA.sources, 1)[0],
        { kind: "gift", species: 1, level: 75, item: 460, map_section: 155, script: "0x1", offset: "0x2" },
        { ...speciesSources(DATA.sources, 470)[0], species: 1 },
        { ...speciesSources(DATA.sources, 548)[0], species: 1, map_section: 155 },
      ],
      items: [{ id: 460, name: "items:460" }],
      map_sections: [{ id: 155, name: "s map 155" }],
      // chart types and some raw effectiveness pairs
      types: [{ id: 12, colour: "#7bce52" }, { id: 3, colour: "#a542a5" }, { id: 10, colour: "#f75231" }],
      type_effectiveness: [{ attack: 10, defense: 12, multiplier: 20 }, { attack: 10, defense: 3, multiplier: 0 },
        { attack: 12, defense: 12, multiplier: 5 }, { attack: 3, defense: 3, multiplier: 5 }],
  };
  const view = new PokedexView({
    data: () => data,
    entry: async (id) => ({ translation: "", source_text: ({
      "species:1": "Bulbasaur", "species:2": "Ivysaur", "types:12": "Grass", "types:3": "Poison",
      "abilities:65": "Overgrow", "pokedex_categories:1": "Seed",
      s0444CB2: "First line\\nSecond line\\lThird line\\pNext paragraph.",
    })[id] ?? "" }),
    draft: () => true,
    spriteSrc: (p) => `data/${p}`,
    setHash: () => {},
  }, $);
  view.texts = new Map([
    ["species:1", { translation: "Бульбазавр", source_text: "Bulbasaur" }],
    ["species:2", { translation: "Ивизавр", source_text: "Ivysaur" }],
    ["types:12", { translation: "Трава", source_text: "Grass" }],
    ["types:3", { translation: "Яд", source_text: "Poison" }],
    ["abilities:65", { translation: "Зарастание", source_text: "Overgrow" }],
    ["pokedex_categories:1", { translation: "Семя", source_text: "Seed" }],
    ["s0444CB2", { translation: "Первая строка\\nВторая строка\\lТретья строка\\pНовый абзац.",
      source_text: "First line\\nSecond line\\lThird line\\pNext paragraph." }],
    ["s ability 65", { translation: "Усиливает травяные приёмы.", source_text: "Boosts Grass moves." }],
    ["s map 155", { translation: "", source_text: "Day Care" }],
    ["species:338", { translation: "", source_text: "Manectric" }],
    ["items:460", { translation: "", source_text: "Mewtwonite Y" }],
    ["s1F56089", { translation: "Найден", source_text: "Found" }],
  ]);
  view.applyFilters();
  view.open(1);
  assert.equal($("x-name").textContent, "#001 Бульбазавр"); // the number before the name
  assert.equal($("x-id").textContent, "#001"); // the internal ID leads
  assert.equal($("x-dex").textContent, "species:1");
  assert.equal($("x-abilities").children[0].children[0].children[1].children[0], "hidden");
  assert.equal($("x-abilities").children[0].children[1].title, "s ability 65");
  assert.equal($("x-abilities").children[0].children[1].children[0].text, "Усиливает травяные приёмы.");
  const entry = $("x-entry-text").children[0];
  assert.equal(entry.children.filter((child) => child.className === "br").length, 0);
  assert.equal(entry.children[0].text, "Первая строка Вторая строка Третья строка");
  assert.equal(entry.children[1].className, "dex-para");
  assert.equal(entry.children[2].text, "Новый абзац.");
  // a bar per stat and a total row.
  // tiers against two dex species, plus a legend.
  assert.equal($("x-stats").children.length, 7);
  assert.equal($("x-stats").children[0].children[0].children[0], "HP");
  assert.equal($("x-stats").children[0].children[1].children[0].style, "width:17.6%");
  assert.equal($("x-stats").children[0].children[1].children[0].className, "dex-bar t2"); // equal stats: average
  assert.equal($("x-stats").children[0].children[1].children[0].title, "average: better than 50% of species");
  assert.equal($("x-stats").children[0].children[2].children[0], "45");
  assert.equal($("x-stats").children[6].className, "total");
  assert.equal($("x-stats").children[6].children[1].children[0].className, "dex-tier t2");
  assert.equal($("x-stats").children[6].children[2].children[0], "318");
  assert.equal($("x-ev-yield").textContent, "+1 Sp. Atk +2 Spd");
  assert.equal($("x-stats-legend").children.length, 5);
  assert.equal($("x-stats-legend").children[0].children[1], "worst");
  assert.equal($("x-catch-rate").textContent, "45 / 255");
  assert.equal($("x-base-exp").textContent, "64");
  assert.equal($("x-growth").textContent, "Medium Slow");
  assert.equal($("x-egg-groups").textContent, "Monster / Grass");
  // labels from the shown language's game strings; symbols unchanged
  data.labels = { HP: "s04169C2", Total: "Σ", "Catch rate": null, Obtained: "s1F56089" };
  view.texts.set("s04169C2", { translation: "ОЖ", source_text: "HP" });
  view.useLabels();
  view.open(1);
  assert.equal($("x-stats").children[0].children[0].children[0], "ОЖ");
  assert.equal($("x-stats").children[6].children[0].children[0], "Σ");
  assert.deepEqual(view.label("Obtained"), { text: "Найден", game: true });
  const obtained = $("x-locations").children[0];
  assert.equal(obtained.children[0].children[0], "Найден");
  const sourceRows = obtained.children[1].children;
  assert.equal(sourceRows.length, 4);
  assert.equal(sourceRows[0].children[0], "Egg from an NPC in Day Care");
  assert.match(sourceRows[0].title, /0x1E7B3A6/);
  assert.equal(sourceRows[1].children[0], "Gift at level 75 in Day Care with ");
  assert.equal(sourceRows[1].children[1].className, "dex-link dex-item-link");
  assert.equal(sourceRows[1].children[1].children[0], "Mewtwonite Y");
  assert.equal(sourceRows[2].children[0], "Trade for ");
  assert.equal(sourceRows[2].children[1].className, "dex-link dex-source-species");
  assert.equal(sourceRows[2].children[1].children[0], "Manectric");
  let requestedSpecies = null;
  const openSpecies = view.openSpecies;
  view.openSpecies = (slot) => { requestedSpecies = slot; };
  sourceRows[2].children[1].listeners.click();
  assert.equal(requestedSpecies, 338);
  view.openSpecies = openSpecies;
  assert.equal(sourceRows[3].children[0], "Starter in Day Care");
  view.open(2);
  assert.equal($("x-locations").children.length, 0);
  assert.equal($("x-locations-empty").textContent, "Not found in the wild");
  view.open(1);
  view.lang = "en";
  view.open(1);
  assert.equal($("x-stats").children[0].children[0].children[0], "HP");
  assert.equal($("x-locations").children[0].children[0].children[0], "Found");
  view.lang = "translation";
  // a key without a game string takes the label catalog
  // English mode stays English
  view.host.pageLabels = () => ({ "Catch rate": "Шанс поимки", Filters: "Фильтры", "Move name…": "Название приёма…",
    HP: "Label catalog HP", "Sp. Atk": "Ос. атака", Spd: "Скор", "No such key": "",
    "page:power:return": ["By friendship", "По дружбе"] });
  assert.deepEqual(view.label("page:power:return"), { text: "По дружбе", game: false });
  assert.deepEqual(view.label("Catch rate"), { text: "Шанс поимки", game: false });
  assert.deepEqual(view.label("Filters"), { text: "Фильтры", game: false });
  assert.deepEqual(view.label("Move name…"), { text: "Название приёма…", game: false });
  assert.deepEqual(view.label("HP"), { text: "ОЖ", game: true });
  view.texts.get("s04169C2").translation = "";
  assert.deepEqual(view.label("HP"), { text: "HP", game: true });
  view.texts.get("s04169C2").translation = "ОЖ";
  assert.equal(view.label("No such key"), null);
  assert.equal(t("No such key"), "No such key");
  view.lang = "en";
  assert.equal(view.label("Catch rate"), null);
  assert.deepEqual(view.label("page:power:return"), { text: "By friendship", game: false });
  view.lang = "translation";
  view.open(1);
  assert.equal($("x-ev-yield").textContent, "+1 Ос. атака +2 Скор");
  setLabelSource(null);
  view.open(1);
  assert.equal($("x-gender").textContent, "87.8% male / 12.2% female");
  const defense = $("x-defense").children;
  assert.equal(defense.length, 6);
  assert.equal(defense[0].children[0], "Defense: a move of the listed type hits Бульбазавр");
  assert.deepEqual(defense[1].children.map((cell) => cell.children[0].children[0].title), ["types:10", "types:12", "types:3"]);
  assert.deepEqual(defense[1].children.map((cell) => cell.children[1].children[0]), ["2", "½", "½"]);
  assert.equal(defense[1].children[0].children[1].className, "dex-eff-value double");
  assert.equal(defense[1].children[0].children[1].title, "Weak ×2");
  assert.equal(defense[2].children[0], "Attack: Бульбазавр uses a Трава-type move");
  assert.equal(defense[2].className, "dex-eff-title");
  assert.deepEqual(defense[3].children.map((cell) => cell.children[1].children[0]), ["1", "½", "1"]);
  assert.equal($("x-evolutions").children.length, 1);
  assert.equal($("x-facts").children.length, 14); // 7 dt/dd pairs
  assert.equal($("x-sprite").children.length, 1);
  assert.equal($("x-sprite").children[0].src, "data/sprites/1-front.png"); // front by default
  assert.equal($("x-list-space").children.length, 2);
  assert.equal(view.list.row, DEX_ROW);
  assert.equal(view.row(1).style, `top:${DEX_ROW}px`);
  view.setVariant("back");
  assert.equal($("x-sprite").children[0].src, "data/sprites/1-back.png");
  view.setVariant("front-shiny");
  assert.equal($("x-sprite").children[0].src, "data/sprites/1-shiny.png");
  view.setVariant("back-shiny");
  assert.equal($("x-sprite").children[0].src, "data/sprites/1-back-shiny.png");
  // Front/Back keeps Shiny; Shiny keeps the side
  $("x-shiny").click();
  assert.equal(view.variant, "back");
  assert.equal($("x-shiny")["aria-pressed"], "false");
  $("x-front").click();
  assert.equal($("x-sprite").children[0].src, "data/sprites/1-front.png");
  $("x-shiny").click();
  assert.equal(view.variant, "front-shiny");
  assert.ok($("x-shiny").classList.set.has("on"));
  assert.ok($("x-front").classList.set.has("on"));
  view.setVariant("front");
  view.list.list.scrollTop = 500;
  view.renderList();
  assert.equal(view.list.list.scrollTop, 500);
  // family grid: species in odd columns.
  // one row per branch.
  const grid = $("x-evolutions").children[0];
  assert.equal(grid.className, "dex-grid");
  assert.equal(grid.style, "grid-template-columns:repeat(3,max-content)");
  assert.equal(grid.children[0].className, "dex-evo-target cur");
  assert.equal(grid.children[0].style, "grid-column:1;grid-row:1 / span 1");
  const fork = grid.children[1];
  assert.equal(fork.className, "dex-evo-fork");
  const branch = fork.children[0];
  assert.equal(branch.className, "dex-evo-branch");
  const meta = branch.children[0];
  assert.equal(meta.className, "dex-evo-meta");
  assert.equal(meta.style, "grid-column:2;grid-row:1 / span 1");
  assert.equal(meta.children[0].children[0], "Level 16");
  const target = branch.children[1];
  assert.equal(target.className, "dex-evo-target");
  assert.equal(target.style, "grid-column:3;grid-row:1 / span 1");
  assert.equal(target.children[0].src, "data/sprites/2-front.png");
  assert.equal(target.children[1].children[0], "#002 Ивизавр");
  target.click();
  assert.equal(view.cur, 2);
  assert.equal(view.list.list.scrollTop, DEX_ROW);
  assert.equal($("x-name").textContent, "#002 Ивизавр");
  // English shows source texts; the opened language, translations
  view.loaded = true;
  view.setLang("en");
  assert.equal($("x-name").textContent, "#002 Ivysaur");
  assert.equal($("x-types").children[0].children[0], "Grass");
  assert.equal($("x-types").children[0].className, "chip ptype");
  assert.equal(view.row(0).children[1].children[0], "Bulbasaur");
  assert.equal(view.filterSets.species.controls.get("type").select.children[1].children[0], "Poison"); // type 3 sorts first
  view.texts.set("trainer_classes:1", { translation: "Тренер покемонов", source_text: "{PK}{MN} Trainer" });
  assert.equal(view.text("trainer_classes:1"), "Pokémon Trainer"); // the glyph pair reads as the word
  view.setLang("translation");
  assert.equal($("x-name").textContent, "#002 Ивизавр");
  assert.equal(view.filterSets.species.controls.get("type").select.children[1].children[0], "Яд");
  // Types mode: the chart in the dataset's conventional order
  view.setMode("types");
  assert.equal($("x-chart-card").hidden, false);
  assert.equal($("x-species-card").hidden, true);
  assert.equal($("x-data-card").hidden, true);
  const chart = $("x-type-chart");
  assert.equal(chart.children.length, 2);
  assert.equal(chart.children[0].children[0].children.length, 4); // corner + 3 types
  const rows = chart.children[1].children;
  assert.deepEqual(rows.map((row) => row.children[0].children[0].title), ["types:10", "types:12", "types:3"]);
  assert.equal(rows[0].children[2].className, "double"); // Fire → Grass
  assert.equal(rows[0].children[2].children[0], "2");
  assert.equal(rows[0].children[3].className, ""); // Fire → Poison: no entry, normal damage
  assert.equal(rows[2].children[3].className, "half"); // Poison → Poison
  // dual chart of the first type, then a picked one.
  // species counts per pair.
  const picks = $("x-dual-pick").children;
  assert.deepEqual(picks.map((b) => [b.children[0].title, b["aria-pressed"]]), [["types:10", "true"], ["types:12", "false"], ["types:3", "false"]]);
  let dual = $("x-dual-chart").children[1].children;
  assert.equal(dual.length, 3);
  assert.deepEqual(dual.map((row) => row.children[1].children[0]), ["0", "0", "0"]);
  picks[1].listeners.click();
  assert.equal(view.dualType, 12);
  dual = $("x-dual-chart").children[1].children;
  assert.deepEqual(dual.map((row) => row.children[0].children[0].children.map((chip) => chip.title || chip.children[0])),
    [["types:12", "—"], ["types:12", "types:10"], ["types:12", "types:3"]]);
  assert.deepEqual(dual.map((row) => row.children[1].children[0]), ["0", "0", "2"]); // Bulbasaur and Ivysaur
  assert.equal(dual[2].children[2].className, "double"); // Fire against Grass/Poison
  assert.equal(dual[2].children[3].className, "half"); // Grass against Grass/Poison: ½ × 1.
                                                       // No Grass → Poison pair here.
  view.setMode("species");
  assert.equal($("x-chart-card").hidden, true);
  // a route opens its card without reloading
  view.loaded = true;
  globalThis.requestAnimationFrame = (fn) => fn();
  await view.goTo({ kind: "species", id: "2" });
  assert.equal(view.cur, 2);
  await view.goTo({ kind: "2" });
  assert.equal(view.cur, 2);
  await view.goTo({ kind: "types", id: "12" });
  assert.equal(view.mode, "types");
  assert.equal(view.dualType, 12);
  await view.goTo({ kind: "species", id: "1" });
  assert.equal(view.mode, "species");
  assert.equal(view.cur, 1);
  // Enter in the search opens the first match
  $("x-search").value = "ивиз"; // only Ivysaur matches
  view.applyFilters();
  assert.equal(view.openFirst(), true);
  assert.equal(view.cur, 2);
  $("x-search").value = "nothing here";
  view.applyFilters();
  assert.equal(view.openFirst(), false);
  assert.equal(view.cur, 2);
  $("x-search").value = "";
  view.applyFilters();
  view.host.searchAliases = (id) => id === "species:2" ? ["Ивисаур", "Ivysaurus"] : [];
  $("x-search").value = "ИВИСА";
  view.applyFilters();
  assert.equal(view.openFirst(), true);
  assert.equal(view.cur, 2);
  assert.equal($("x-name").textContent, "#002 Ивизавр");
  assert.equal($("x-facts").children[0].children[0], "Search aliases");
  assert.equal($("x-facts").children[1].children[0], "Ивисаур, Ivysaurus");
  view.setLang("en");
  for (const query of ["Ивизавр", " ИВИЗ ", "ИВИСА", "Ivysaur"]) {
    $("x-search").value = query;
    view.applyFilters();
    assert.equal(view.openFirst(), true, query);
    assert.equal(view.cur, 2);
    assert.equal($("x-name").textContent, "#002 Ivysaur");
    assert.equal(view.strong, 1);
  }
  assert.deepEqual(view.otherNames("missing"), []);
  view.texts.set("s map 155", { source_text: "Day Care", translation: "Пансион" });
  assert.deepEqual(view.otherNames("mapsec:155"), ["Day Care", "Пансион"]);
  view.setLang("translation");
  assert.deepEqual(view.otherNames("mapsec:155"), ["Day Care", "Пансион"]); // the shown language does not narrow it
  $("x-search").value = "Ivysaur";
  view.applyFilters();
  assert.equal(view.openFirst(), true);
  assert.equal($("x-name").textContent, "#002 Ивизавр");
  view.open(1);
  assert.equal($("x-facts").children.length, 14);
  delete view.host.searchAliases;
  $("x-search").value = "ИВИСА";
  view.applyFilters();
  assert.equal(view.openFirst(), false);
  delete globalThis.requestAnimationFrame;
  delete globalThis.document;
});

test("a learnsets file puts its rows back on the records in the inline form", () => {
  const data = { profile_block: "abc", species: [{ slot: 1 }, { slot: 2 }, { slot: 3 }], learnsets: "learnsets.json" };
  const doc = { format: "gen3tl-pokedex-learnsets", schema: 1, profile_block: "abc",
    columns: ["method", "move", "level", "index", "offset"],
    species: { 1: [[0, 33, 1, null, "0x000210"], [1, 264, null, 0, "0x000300"]], 2: [] } };
  inlineLearnsets(data, doc);
  assert.deepEqual(data.species[0].learnset, [
    { species: 1, method: 0, move: 33, level: 1, index: null, offset: "0x000210" },
    { species: 1, method: 1, move: 264, level: null, index: 0, offset: "0x000300" }]);
  assert.deepEqual(data.species[1].learnset, []);
  assert.equal(data.species[2].learnset, null);
  assert.equal(data.learnsets, undefined);
  // a form borrows TM, tutor and egg rows, not level-up
  const form = { slot: 900, dex: 25, learnset_species: 25 };
  const data2 = { profile_block: "abc", species: [{ slot: 25, dex: 25 }, form, { slot: 901, dex: 26, learnset_species: 25 }] };
  inlineLearnsets(data2, { ...doc, species: { 25: [[0, 33, 5, null, "0x1"], [1, 85, null, 24, "0x2"], [3, 7, null, 0, "0x3"]],
    900: [[0, 84, 1, null, "0x4"], [1, 85, null, 24, "0x5"]] } });
  assert.deepEqual(form.learnset.map((row) => [row.method, row.move, row.species, row.source ?? null]),
    [[0, 84, 900, null], [1, 85, 900, null], [3, 7, 900, 25]]);
  assert.equal(data2.species[2].learnset, null); // no rows of its own: nothing to resolve onto
  assert.equal(speciesMatches(form, { moves: new Set([7]) }), true);
  assert.equal(speciesMatches(data2.species[0], { moves: new Set([84]) }), false);
  assert.throws(() => inlineLearnsets({ profile_block: "abc", species: [] }, { ...doc, profile_block: "other" }), /not the rows/);
  assert.throws(() => inlineLearnsets({ profile_block: "abc", species: [] }, { format: "x" }), /unknown format/);
  assert.equal(datasetPath("pokedex/unbound-2.1.1.1/pokedex.json", "learnsets.json"), "pokedex/unbound-2.1.1.1/learnsets.json");
  assert.equal(spritePath("pokedex/unbound-2.1.1.1/pokedex.json", "a.png"), "pokedex/unbound-2.1.1.1/sprites/a.png");
});

test("explicit public browsing status leaves raw records, forms, ranks and saved lookup intact", { skip: NEEDS_UNBOUND }, async () => {
  const { PokedexView, speciesBrowsable } = await import(new URL("js/pokedex/pokedex.js", process.env.GEN3TL_WEB_ROOT_URL));
  const species = structuredClone(DATA.species);
  const technical = species.find((record) => record.slot === 253);
  species.push({ ...structuredClone(technical), slot: 2000, name: "species:2000" });
  const original = structuredClone(species);
  const browsing = { "253": "unreleased" };
  const names = (id) => ({ "species:253": "MISSINGNO.", "species:2000": "MISSINGNO.", "species:278": "Grovyle" })[id] ?? id;
  const raw = filterSpecies(species, "", names);
  const publicRows = filterSpecies(species, "", names, null, () => [], () => [], false, [], browsing);
  assert.deepEqual(publicRows, raw.filter((i) => species[i].slot !== 253));
  assert.ok(publicRows.some((i) => species[i].slot === 2000));
  for (const slot of [252, 254, 412, 706]) assert.ok(publicRows.some((i) => species[i].slot === slot));
  const index = speciesFamilyIndex(species);
  const grouped = createSpeciesSearch(species, names, () => [], () => [], true, index);
  const publicGrouped = createSpeciesSearch(species, names, () => [], () => [], true, index, [], browsing);
  assert.deepEqual(publicGrouped.filter(""), grouped.filter("").filter((i) => species[i].slot !== 253));
  for (const query of ["253", "278", "Grovyle"]) {
    assert.ok(publicGrouped.filter(query).some((i) => species[i].slot === 278), query);
    assert.ok(!publicGrouped.filter(query).some((i) => species[i].slot === 253), query);
  }
  assert.ok(grouped.filter("MISSINGNO.").some((i) => species[i].slot === 253));
  assert.deepEqual(publicGrouped.filter("MISSINGNO.").map((i) => species[i].slot), [2000]);
  const sorted = sortSpeciesIndices(publicRows, species, names, { key: "total", direction: "desc" });
  assert.equal(species[sorted[0]].slot, 2000);
  assert.equal(speciesListFields(species[sorted[0]], species, names).total, 1530);
  assert.deepEqual(formesOf(species.find((r) => r.slot === 201), species, index),
    formesOf(original.find((r) => r.slot === 201), original));
  assert.deepEqual(statRanks(species), statRanks(original));
  const view = Object.create(PokedexView.prototype);
  view.host = { data: () => ({ species, species_browsing: browsing }) };
  assert.equal(view.record(253), technical);
  assert.equal(view.savedRecord("species", 253), technical);
  assert.equal(speciesBrowsable(technical, browsing), false);
  assert.equal(speciesBrowsable(technical), true);
  assert.deepEqual(species, original);
});

test("every supported ROM-backed trade emits its requested species route", { skip: NEEDS_UNBOUND }, () => {
  const trades = DATA.sources.filter((source) => source.kind === "trade");
  const before = JSON.stringify(trades);
  assert.equal(trades.length, 39);
  assert.equal(trades.filter((source) => source.speaker).length, 24);
  const benjamin = trades.find((source) => source.trade_index === 36);
  assert.equal(sourceParts(benjamin, (id) => ({ "species:213": "Shuckle", s1F18D94: "Benjamin" })[id] ?? "")[0].text,
    "Benjamin: trade for ");
  assert.deepEqual([...new Set(trades.map((source) => source.trade_index))].sort((a, b) => a - b),
    Array.from({ length: 39 }, (_, i) => i).filter((i) => i !== 14));
  for (const source of trades) {
    const links = sourceParts(source, (id) => id).filter((part) => part.species != null);
    assert.deepEqual(links, [{ species: source.wanted, text: `species:${source.wanted}` }]);
    assert.ok(DATA.species.some((record) => record.slot === source.wanted));
  }
  assert.ok(trades.some((source) => source.species === 237 && source.wanted === 108));
  assert.equal(JSON.stringify(trades), before);
});
