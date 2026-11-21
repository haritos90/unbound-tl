import assert from "node:assert/strict";

import { readFileSync } from "node:fs";

import { test } from "node:test";

const { battlesFor, variantConditions, difficultyLabel, encounterTables, evTraining, itemFacts, itemFields, methodLabel, PokedexDataView, speciesLocations, targetLabel, trainerGroups, trainerName } = await import(new URL("js/pokedexdataview/pokedexdataview.js", process.env.GEN3TL_WEB_ROOT_URL));

const { FILTER_SETS, FilterSet } = await import(new URL("js/filters.js", process.env.GEN3TL_WEB_ROOT_URL));

const { effectName } = await import(new URL("js/moveeffects.js", process.env.GEN3TL_WEB_ROOT_URL));

const { setLabelSource } = await import(new URL("js/ui.js", process.env.GEN3TL_WEB_ROOT_URL));

const { EntryList } = await import(new URL("js/listview.js", process.env.GEN3TL_WEB_ROOT_URL));

const { PokedexView } = await import(new URL("js/pokedex/pokedex.js", process.env.GEN3TL_WEB_ROOT_URL));

const { effectLabel, FLAG_LABELS, flagName, MOVE_LIST_LABELS, moveListName, TARGET_LABELS, targetName } = await import(new URL("js/movelabels.js", process.env.GEN3TL_WEB_ROOT_URL));

import { domPage, NEEDS_DOM, NEEDS_UNBOUND, projectLabelEntries, STANDALONE_LABELS, TRAINER_DIFFICULTY, UNBOUND } from "./fixture.mjs";

function dataRenderer(parent, $) {
  const view = new PokedexDataView(parent, $);
  parent.list ??= new EntryList($("x-list"), $("x-list-space"), (p) => view.row(p));
  parent.renderList ??= () => parent.list.render();
  return view;
}

const DATA = UNBOUND;

const text = (id) => ({
  "moves:1": "Thunderbolt", "trainer_names:1": "Joey", "trainer_classes:57": "Youngster",
  "mapsec:102": "Route 2", "species:163": "Hoothoot", "species:72": "Tentacool",
})[id] ?? "";

test("every generated move key has an English label and matches its numeric fields", { skip: NEEDS_UNBOUND }, () => {
  const targets = new Set();
  const effects = new Set();
  const lists = new Set();
  assert.equal(DATA.moves.length, 923);
  for (const record of DATA.moves) {
    targets.add(record.target_key);
    effects.add(record.effect_key);
    assert.ok(targetName(record.target_key), record.target_key);
    assert.equal(targetLabel(record.target, record.target_key), targetName(record.target_key));
    assert.ok(effectLabel(record.effect_key), record.effect_key);
    assert.equal(effectName(record.effect, record.effect_key), effectLabel(record.effect_key));
    assert.deepEqual(record.flag_keys, Object.keys(FLAG_LABELS).filter((_, bit) => record.flags & (1 << bit)));
    for (const key of record.flag_keys) {
      assert.ok(flagName(key), key);
      assert.ok(DATA.move_readers[key]?.readers, key);
    }
    for (const key of record.list_keys) {
      lists.add(key);
      assert.ok(moveListName(key), key);
      assert.ok(DATA.move_readers[key]?.readers, key);
    }
  }
  assert.deepEqual([...targets].sort(), Object.keys(TARGET_LABELS).sort());
  assert.ok(effects.size > 220);
  assert.ok(effects.has("defense_up_3"));
  assert.ok(effects.has("special_attack_up_3"));
  assert.deepEqual([...lists].sort(), Object.keys(MOVE_LIST_LABELS).sort());
  assert.equal(Object.keys(DATA.move_readers).length, 24);
  assert.deepEqual(DATA.move_readers.punching.readers, { abilities: [93], items: [] });
  assert.deepEqual(DATA.move_readers.sound.readers, { abilities: [43, 218], items: [709] });
  const smog = DATA.moves[123];
  assert.equal(smog.target_key, "selected");
  assert.equal(smog.effect_key, "poison_hit");
  assert.equal(smog.secondary_chance, 40);
  assert.deepEqual(smog.flag_keys, ["protect_affected", "mirror_move_affected"]);
  assert.ok(!smog.list_keys.includes("sheer_force"));
  assert.ok(DATA.moves[356].list_keys.includes("sheer_force"));
  assert.ok(DATA.moves[7].list_keys.includes("punching"));
  assert.ok(DATA.moves[45].list_keys.includes("sound"));
});

test("item effects name percentages, flat values, fractions, types and variants", { skip: NEEDS_UNBOUND }, () => {
  const value = (id, label) => itemFields(DATA.items[id], (key) => ({
    "types:23": "Fairy", "types:0": "Normal",
  })[key] ?? "").find(([name]) => name === label)?.[1];
  assert.equal(value(139, "Held effect"), "Restore 10 HP at 1/2 HP or less");
  assert.equal(value(183, "Held effect"), "Move first: 20% chance");
  assert.equal(value(219, "Held effect"), "Recover 1/8 of damage dealt as HP");
  assert.equal(value(512, "Held effect"), "Type plate: Fairy; boost: ×1.2");
  assert.equal(value(670, "Held effect"), "Enable Z-Moves of type: Normal");
  assert.equal(value(687, "Held effect"), "Enable Z-Moves of type: Fairy");
  assert.equal(value(688, "Held effect"), "Enable a species-specific Z-Move");
  assert.equal(value(142, "Held effect"), "Restore a quarter of maximum HP at 1/2 HP or less");
  assert.equal(value(570, "Held effect"), "Survive a hit at full HP");
  assert.equal(value(200, "Held effect"), "Restore 1/16 of maximum HP each turn");
  assert.equal(value(235, "Held effect"), "Boost supereffective damage: ×1.2");
  assert.equal(value(445, "Held effect"), "Enable Ultra Burst");
  assert.equal(value(177, "Held effect"), "Boost Sp. Atk: ×1.5; lock one move");
  assert.equal(value(244, "Held effect"), ["Boost Attack EV gain: +8; lower Speed: ×0.5.",
    ...DATA.items[244].held_effect_amount.conditions].join(" "));
  assert.equal(value(13, "Battle use"), "Healing or status cure");
  assert.equal(value(34, "Battle use"), "Restore PP");
  assert.equal(value(1, "Battle use"), "Throw a ball");
  assert.equal(value(80, "Battle use"), "Escape from battle");
  assert.equal(DATA.items[13].battle_usage, DATA.items[34].battle_usage);
  assert.equal(DATA.items.filter((row) => row.held_effect).length, 309);
  assert.equal(DATA.items.filter((row) => row.battle_usage).length, 85);
  for (const row of DATA.items) {
    if (row.held_effect) assert.ok(row.held_effect_key, `held effect on item ${row.id}`);
    if (row.battle_usage) assert.ok(row.battle_usage_key, `battle use on item ${row.id}`);
    assert.deepEqual(itemFacts(row), [["ROM offset", row.offset]]);
  }
});

test("named item effects use the Russian label catalog and translated types", { skip: NEEDS_UNBOUND }, () => {
  const po = readFileSync(new URL("../../translation/ru/pokedex-labels.po", import.meta.url), "utf8");
  const labels = new Map([...po.matchAll(/^msgid (".*")\nmsgstr (".*")/gm)]
    .map((match) => [JSON.parse(match[1]), JSON.parse(match[2])]));
  setLabelSource((key) => labels.has(key) ? { text: labels.get(key), game: false } : null);
  try {
    const fields = (id) => itemFields(DATA.items[id], (key) => key === "types:23" ? "Фея" : "");
    assert.ok(fields(139).some(([key, value]) => key === "Эффект при удержании" && value === "Восполнение 10 ОЖ при ОЖ не выше 1/2"));
    assert.ok(fields(183).some(([, value]) => value === "Ход первым: шанс 20%"));
    assert.ok(fields(512).some(([, value]) => value === "Плита типа: Фея; усиление: ×1.2"));
    assert.ok(fields(235).some(([, value]) => value === "Усиление суперэффективного урона: ×1.2"));
    assert.ok(fields(34).some(([key, value]) => key === "Использование в бою" && value === "Восполнение ОС"));
  } finally {
    setLabelSource(null);
  }
});

test("item currency survives real DOM detail rerenders and pending item locale changes", { skip: NEEDS_DOM || NEEDS_UNBOUND }, (context) => {
  domPage(context, "pokedex");
  const oldCSS = globalThis.CSS, oldImage = globalThis.Image;
  const images = [];
  globalThis.CSS = { supports: () => true };
  globalThis.Image = class { constructor() { images.push(this); } };
  let label = "Pokédollar";
  setLabelSource((key) => key === "Pokédollar" ? { text: label, game: false } : null);
  try {
    const view = Object.create(PokedexDataView.prototype);
    view.host = { data: () => UNBOUND, spriteSrc: (path) => `data/${path}` };
    view.view = { text: () => "", texts: new Map(), openMove() {} };
    view.mode = "items";
    view.$ = (id) => document.getElementById(id);
    view.itemSourceBlock = () => [];
    view.itemEvolutionBlock = () => [];
    const currency = () => document.querySelector('[data-key="pokedollar"]');
    view.renderDetail(93);
    const first = currency();
    assert.equal(first.textContent, "Pokédollar");
    label = "Покедоллар";
    view.renderDetail(93);
    assert.equal(currency(), first);
    assert.equal(first.textContent, "Покедоллар");
    view.renderDetail(133);
    const second = currency();
    assert.notEqual(second, first);
    assert.equal(second.textContent, "Покедоллар");
    label = "Pokédollar localisé";
    view.renderDetail(133);
    assert.equal(currency(), second);
    assert.equal(images.length, 1);
    images[0].onload();
    assert.equal(second.textContent, "");
    assert.equal(second.className, "dex-pokedollar-icon");
    assert.equal(second.getAttribute("aria-label"), "Pokédollar localisé");
    view.renderDetail(93);
    const cached = currency();
    assert.equal(cached.textContent, "");
    assert.equal(cached.className, "dex-pokedollar-icon");
    assert.equal(cached.getAttribute("aria-label"), "Pokédollar localisé");
    view.renderDetail(93);
    assert.equal(currency(), cached);
    assert.equal(cached.className, "dex-pokedollar-icon");
    assert.equal(images.length, 1);
  } finally {
    setLabelSource(null);
    if (oldCSS === undefined) delete globalThis.CSS; else globalThis.CSS = oldCSS;
    if (oldImage === undefined) delete globalThis.Image; else globalThis.Image = oldImage;
  }
});

const source = (id) => ({
  "trainer_names:20": "Alice", "trainer_names:76": "Alice", "trainer_names:77": "Alice", "trainer_names:1": "Joey",
})[id] ?? "";

test("the current trainer catalog preserves known names and labels its four unnamed records", { skip: NEEDS_UNBOUND }, () => {
  const po = readFileSync(new URL("../../translation/ru/po/tables/trainer_names.po", import.meta.url), "utf8");
  const names = new Map([...po.matchAll(/^msgctxt "table:trainer_names\/(\d+)"\nmsgid "[^"\n]*"\nmsgstr (".*")$/gm)]
    .map((m) => [`trainer_names:${m[1]}`, JSON.parse(m[2])]));
  const visible = DATA.trainers.filter((r) => r.party_offset !== null || r.party?.length);
  assert.deepEqual(visible.filter((r) => !names.get(r.name)?.trim()).map((r) => r.id), [53, 54, 55, 175]);
  for (const record of visible) {
    const source = names.get(record.name); assert.equal(typeof source, "string");
    assert.equal(trainerName(record, (id) => names.get(id)), source.trim() || `Trainer ${record.id}`);
  }
});

const fakeElement = () => ({
  children: [], style: {}, listeners: {}, className: "", textContent: "", value: "", hidden: false,
  title: "", disabled: false, selected: false, src: "",
  addEventListener(ev, fn) { this.listeners[ev] = fn; },
  setAttribute(k, v) { this[k] = v; },
  append(...kids) { this.children.push(...kids.flat()); },
  replaceChildren(...kids) { this.children = kids.flat(); },
  showModal() { this.open = true; },
  close() { this.open = false; },
  classList: { toggle() {} },
});

test("trainer filters combine class, kind, EV training and difficulty from one registry", { skip: NEEDS_UNBOUND }, () => {

  const po = readFileSync(new URL("../../translation/ru/pokedex-labels.po", import.meta.url), "utf8");
  const labels = Object.fromEntries([...po.matchAll(/^msgid (".*")\nmsgstr (".*")/gm)]
    .map((match) => [JSON.parse(match[1]), JSON.parse(match[2])]));
  const kinds = ["league", "story", "world", "special", "partners", "paired"];
  const english = ["Gym leaders and league", "Story characters", "World trainers", "Special buildings", "Battle partners", "Trainer pairs"];
  const russian = ["Лидеры стадионов и Лига", "Сюжетные персонажи", "Обычные тренеры", "Особые здания", "Напарники в бою", "Пары тренеров"];
  const trainers = kinds.map((kind, id) => ({ id, kind, name: `trainer_names:${id}`, class: "trainer_classes:1", party: [] }));
  trainers[3].ev_training = true;
  trainers.push({ ...trainers[0], id: 10, kind: "story", name: "trainer_names:10" });
  trainers.push({ ...trainers[3], id: 11, class: "trainer_classes:2", ev_training: false });
  const names = Object.fromEntries(trainers.map((row) => [row.name, `Trainer ${row.id}`]));
  names["trainer_names:10"] = names["trainer_names:0"];
  const parent = {
    host: { data: () => ({ trainers }), pageLabels: () => labels }, generation: 0, records: [],
    texts: new Map(Object.entries(names).map(([id, englishName]) => [id, { source_text: englishName }])),
    text: (id) => names[id] ?? id, otherNames: () => [],
  };
  const source = (id) => parent.texts.get(id)?.source_text ?? id;
  const groups = trainerGroups(trainers, source).sort((a, b) => a.id - b.id);
  const context = { data: { trainers }, text: (id) => names[id] ?? id, source, speciesNames: () => [] };
  const set = new FilterSet("trainers", FILTER_SETS.trainers, {});
  const matches = (raw) => groups.filter((group) => set.matches(group, set.prepare(raw, context), context)).map((group) => group.id);
  try {
    for (const lang of ["en", "ru"]) {
      parent.lang = lang;
      setLabelSource((key) => PokedexView.prototype.label.call(parent, key));
      const kindOptions = FILTER_SETS.trainers.find((entry) => entry.key === "kind").options(context);
      assert.deepEqual(kindOptions.map((option) => option.value), kinds);
      assert.deepEqual(kindOptions.map((option) => option.label), lang === "en" ? english : russian);
      assert.deepEqual(matches({ kind: "league" }), [0]);
      assert.deepEqual(matches({ kind: "story" }), [0, 1]);
      assert.deepEqual(matches({ kind: "world" }), [2]);
      assert.deepEqual(matches({ kind: "special" }), [3, 11]);
      assert.deepEqual(matches({ kind: "partners" }), [4]);
      assert.deepEqual(matches({ kind: "paired" }), [5]);
      assert.deepEqual(matches({ class: "trainer_classes:2" }), [11]);
      assert.deepEqual(matches({ evTraining: "yes" }), [3]);
      assert.deepEqual(matches({ class: "trainer_classes:2", kind: "special" }), [11]);
      assert.deepEqual(matches({ kind: "world", evTraining: "yes" }), []);
      assert.deepEqual(matches({}), groups.map((group) => group.id));
    }
  } finally {
    setLabelSource(null);
  }
});

test("the flower section and species locations use each table's declared trigger", { skip: NEEDS_UNBOUND }, (context) => {
  context.after(() => { delete globalThis.document; setLabelSource(null); });
  globalThis.document = { createElement: fakeElement, createTextNode: (text) => ({ text }) };
  setLabelSource(null);
  const parent = {
    host: { data: () => DATA, spriteSrc: (path) => path }, generation: 0, texts: new Map(),
    text: (id) => id, record: (slot) => DATA.species.find((record) => record.slot === slot),
    moveLink: (id) => `moves:${id}`,
  };
  const view = dataRenderer(parent, fakeElement);
  view.mode = "locations";
  const section = view.record("136");
  const expected = [
    ["Pink Flowers", "Yellow Flowers"], ["Red Flowers", "Blue Flowers"],
    ["Pink-Purple Flowers", "Blue-Yellow Flowers / Surfing"],
  ];
  assert.deepEqual(section.areas.map((area) => encounterTables(area.encounters).map((row) => row.method)), expected);
  const detail = view.locationDetail(section);
  const content = JSON.stringify(detail);
  for (const label of expected.flat()) assert.ok(content.includes(`${label} ·`), label);
  for (const area of section.areas) {
    for (const row of area.encounters) {
      const locations = speciesLocations(DATA.encounters, row.species);
      assert.ok(locations.some((location) => location.area === area.id && location.method === methodLabel(row)));
    }
  }
  const species = DATA.species.find((row) => row.dex === 764);
  assert.ok(species);
  const locations = speciesLocations(DATA.encounters, species.slot).filter((row) => row.area === "1.4");
  assert.deepEqual(locations.map((row) => [row.area, row.method]), [["1.4", "Pink Flowers"]]);
  const water = DATA.encounters.filter((row) => row.method === "water");
  assert.ok(water.every((row) => row.method_labels?.length));
  assert.equal(new Set(water.filter((row) => row.method_labels.includes("Magma")).map((row) => row.runtime_map)).size, 10);
  assert.deepEqual([...new Set(water.filter((row) => row.runtime_map === "3.73").map(methodLabel))], ["Alternate grass / Surfing"]);
});

test("the game labels select the Expert roster in both languages", { skip: NEEDS_UNBOUND }, () => {
  globalThis.document = { createElement: fakeElement, createTextNode: (text) => ({ text }) };
  const parent = {
    host: { data: () => DATA, spriteSrc: (path) => path,
      pageLabels: () => ({ "Levels shown here": "Уровни, показанные здесь" }) },
    lang: "en", text: () => "", record: () => null,
    texts: new Map([
      ["s1F10621", { source_text: "Difficult", translation: "Сложный" }],
      ["s1F10630", { source_text: "Vanilla", translation: "Обычный" }],
      ["s1F1063D", { source_text: "Expert", translation: "Эксперт" }],
      ["s1F10644", { source_text: "Insane", translation: "Безумный" }],
    ]),
  };
  const view = dataRenderer(parent, fakeElement);
  view.difficulty = "2";
  const battles = [20, 725, 726, 727].map((id) => ({ ...DATA.trainers[id], party: [] }));
  const group = { id: 20, class: "trainer_classes:84", battles };
  setLabelSource((key) => PokedexView.prototype.label.call(parent, key));
  try {
    for (const [lang, labels] of [
      ["en", ["Vanilla", "Difficult", "Expert", "Insane"]],
      ["ru", ["Обычный", "Сложный", "Эксперт", "Безумный"]],
    ]) {
      parent.lang = lang;
      const select = view.trainerDetail(group).children[0].children[1].children[0].children[1];
      assert.deepEqual(select.children.map((option) => option.children[0]), labels);
      assert.deepEqual(select.children.filter((option) => option.selected).map((option) => option.value), ["2"]);
      assert.deepEqual(battlesFor(battles, "2", TRAINER_DIFFICULTY).map((battle) => battle.id), [726]);
      assert.equal(difficultyLabel(battles[2], TRAINER_DIFFICULTY), labels[2]);
    }
  } finally {
    setLabelSource(null);
    delete globalThis.document;
  }
});

function trainerFightHeads(battles, mode) {
  globalThis.document = { createElement: fakeElement, createTextNode: (text) => ({ text }) };
  try {
    const view = dataRenderer({
      host: { data: () => ({ trainer_difficulty: TRAINER_DIFFICULTY }), spriteSrc: (path) => path }, text: () => "", record: () => null,
      abilityLink: () => fakeElement(),
    }, fakeElement);
    view.difficulty = mode;
    return view.trainerDetail({ battles }).children.filter((child) => child.className.includes("dex-encounter"))
      .map((encounter) => ({
        title: encounter.children[0].children[0].children[0],
        variants: encounter.children.slice(1).map((variant) => variant.children[0].children.map((child) => child.children[0])),
      }));
  } finally {
    delete globalThis.document;
  }
}

test("participant role labels resolve in every project catalog", { skip: NEEDS_UNBOUND }, () => {
  try {
    for (const { code } of STANDALONE_LABELS.languages) {
      const labels = projectLabelEntries(code);
      setLabelSource((key) => ({ text: labels[`page:${key}`]?.[1] || key, game: false }));
      for (const key of ["First opponent", "Second opponent", "Battle partner"]) {
        assert.ok(labels[`page:${key}`]?.[1], `${code}: ${key}`);
      }
      assert.deepEqual(variantConditions({ role: "second_opponent" }), [labels["page:Second opponent"][1]]);
      assert.deepEqual(variantConditions({ role: "partner" }), [labels["page:Battle partner"][1]]);
    }
  } finally {
    setLabelSource(null);
  }
});

test("Mel's early fight is battle 1 for every difficulty", { skip: NEEDS_UNBOUND }, () => {
  const battles = [78, 79, 416, 728, 729, 730].map((id) => DATA.trainers[id]);
  for (const [mode, early, late] of [
    ["0", [416], [78]],
    ["1", [728], [78]], ["2", [729], [78]], ["3", [730], [79]],
  ]) {
    const fights = trainerFightHeads(battles, mode);
    assert.deepEqual(fights.map((fight) => fight.title), ["Battle 1", "Battle 2"]);
    assert.deepEqual(fights.map((fight) => fight.variants.map((head) => head[1])),
      [early, late].map((ids) => ids.map((id) => `trainer ${id}`)));
  }
});
