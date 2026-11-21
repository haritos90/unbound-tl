import assert from "node:assert/strict";

import { test } from "node:test";

const { pageChoice, pageHash, textEntry, textsDraft, verifyProjectTexts } = await import(new URL("js/dexpage.js", process.env.GEN3TL_WEB_ROOT_URL));

test("a card's hash carries the game, the language and the id parts", () => {
  assert.equal(pageHash("unbound-2.1.1.1", "ru", 6), "#unbound-2.1.1.1/ru/species/6");
  assert.equal(pageHash("unbound-2.1.1.1", "ru", "trainers/20"), "#unbound-2.1.1.1/ru/trainers/20");
  assert.equal(pageHash("unbound-2.1.1.1", "ru", null), "#unbound-2.1.1.1/ru");
});

test("the route's language wins: English as the game text or any catalog of the game", () => {
  const profile = { languages: [{ code: "fr" }, { code: "ru" }, { code: "de" }] };
  assert.deepEqual(pageChoice(profile, "de", "ru"), { code: "de", catalog: profile.languages[2], missing: null });
  assert.deepEqual(pageChoice(profile, "fr", "ru"), { code: "fr", catalog: profile.languages[0], missing: null });
  assert.deepEqual(pageChoice(profile, "en", "ru"), { code: "en", catalog: profile.languages[0], missing: null });
  assert.equal(pageChoice({ languages: [] }, "en"), null);
  assert.equal(pageHash("unbound-2.1.1.1", "en", 94), "#unbound-2.1.1.1/en/species/94");
});

test("a texts file resolves ids to their english and translation and knows a draft catalog", () => {
  const doc = { schema: 1, profile: "unbound-2.1.1.1", language: "ru", draft: false,
    texts: { "species:94": ["Gengar", "Генгар"], s0444CB2: ["An entry", ""] } };
  assert.deepEqual(textEntry(doc, "species:94"), { source_text: "Gengar", translation: "Генгар" });
  assert.deepEqual(textEntry(doc, "s0444CB2"), { source_text: "An entry", translation: "" });
  assert.equal(textEntry(doc, "species:1"), null);
  assert.equal(textEntry(null, "species:1"), null);
  assert.equal(textsDraft(doc), false);
  assert.equal(textsDraft({ ...doc, draft: true }), true);
  verifyProjectTexts(doc, "unbound-2.1.1.1", "ru");
  assert.throws(() => verifyProjectTexts(doc, "unbound-2.1.1.1", "de"), /do not match/);
  assert.throws(() => verifyProjectTexts({ ...doc, schema: 2 }, "unbound-2.1.1.1", "ru"), /do not match/);
});
