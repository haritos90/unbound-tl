import assert from "node:assert/strict";

import { test } from "node:test";

const { setLabelSource, setUiLanguage, SOURCE_LANGUAGE } = await import(new URL("js/ui.js", process.env.GEN3TL_WEB_ROOT_URL));

const { PokedexView } = await import(new URL("js/pokedex/pokedex.js", process.env.GEN3TL_WEB_ROOT_URL));

const { moveCardContent } = await import(new URL("js/movecard.js", process.env.GEN3TL_WEB_ROOT_URL));

const { moveFields, PokedexDataView } = await import(new URL("js/pokedexdataview/pokedexdataview.js", process.env.GEN3TL_WEB_ROOT_URL));

const { basePower, powerLabel } = await import(new URL("js/moveeffects.js", process.env.GEN3TL_WEB_ROOT_URL));

const { FILTER_SETS } = await import(new URL("js/filters.js", process.env.GEN3TL_WEB_ROOT_URL));

import { FLINCH_MOVES, flinchLabels, NEEDS_UNBOUND, STANDALONE_LABELS, UNBOUND as DATA } from "./fixture.mjs";

const fake = () => ({
  children: [], className: "", textContent: "", title: "", attrs: {}, listeners: {}, open: false,
  addEventListener(ev, fn) { this.listeners[ev] = fn; },
  setAttribute(k, v) { this.attrs[k] = v; },
  append(...kids) { this.children.push(...kids.flat()); },
  replaceChildren(...kids) { this.children = [...kids.flat()]; },
  showModal() { this.open = true; }, close() { this.open = false; },
});

const texts = { "moves:7": "Fire Punch", "types:10": "Fire", "abilities:93": "Iron Fist", s1: "Hits with a fiery fist.\\pMay burn." };

test("every audited flinch renders its chance and conditions in every catalog", { skip: NEEDS_UNBOUND }, (context) => {
  globalThis.document = { createElement: () => fake() };
  context.after(() => { setLabelSource(null); setUiLanguage(SOURCE_LANGUAGE); delete globalThis.document; });
  assert.deepEqual(Object.fromEntries(DATA.moves.filter((move) => move.flinch_chance)
    .map((move) => [move.id, move.flinch_chance])), FLINCH_MOVES);
  for (const language of STANDALONE_LABELS.languages) {
    const labels = flinchLabels(language.code);
    assert.equal(Object.keys(labels).length, 5);
    assert.ok(Object.values(labels).every(([english, translated]) => english && translated));
    const texts = new Map(STANDALONE_LABELS.texts.map(([id, english, translated]) =>
      [id, { source_text: english, translation: language.translated ? translated : "" }]));
    const view = { lang: language.code, texts,
      host: { data: () => ({ labels: STANDALONE_LABELS.labels }), pageLabels: () => labels } };
    setUiLanguage(language.code);
    setLabelSource((key) => PokedexView.prototype.label.call(view, key));
    for (const move of DATA.moves) {
      const label = language.labels[0];
      assert.match(label, /^\p{Lu}/u);
      const field = moveFields(move).find(([key]) => key === label);
      const popup = JSON.stringify(moveCardContent(move));
      const expected = FLINCH_MOVES[move.id] || 0;
      assert.equal(!!field, expected > 0, String(move.id));
      assert.equal(popup.includes(`"${label}"`), expected > 0, String(move.id));
      if (!expected) continue;
      assert.ok(field[1].startsWith(`${expected}% · `), String(move.id));
      assert.ok(popup.includes(field[1]), String(move.id));
      assert.ok(!field[1].includes("page:mechanics:"), String(move.id));
      for (const key of move.flinch_conditions) {
        const translated = view.lang === SOURCE_LANGUAGE ? labels[key][0] : labels[key][1];
        assert.ok(field[1].includes(translated), `${language.code} ${move.id} ${key}`);
      }
    }
  }
});

test("every dataset power rule agrees across the rendered surfaces", { skip: NEEDS_UNBOUND }, (context) => {
  globalThis.document = { createElement: () => fake() };
  context.after(() => { delete globalThis.document; });
  const rules = DATA.moves.filter((move) => move.power_formula);
  const predicate = FILTER_SETS.moves.find((field) => field.key === "power").predicate;
  assert.ok(rules.length > 0);
  const view = { data: DATA, view: { text: () => "" }, categoryIcon: () => null };
  for (const move of rules) {
    assert.ok(["fixed", "computed"].includes(move.power_kind), String(move.id));
    const expected = move.power_kind === "computed" ? "—" : String(move.power_base ?? move.power);
    assert.equal(powerLabel(move), expected, String(move.id));
    assert.equal(moveCardContent(move).children[1].children[0].children[0].children[0], expected);
    assert.equal(moveFields(move)[2][1].children[0], expected);
    assert.equal(PokedexDataView.prototype.learnRow.call(view, { move: move.id }, "").children[4].children[0], expected);
    assert.equal(predicate(move, { kind: "fixed", a: basePower(move) ?? 0 }), move.power_kind === "fixed");
    assert.equal(predicate(move, { kind: "formula" }), move.power_kind === "computed");
  }
});
