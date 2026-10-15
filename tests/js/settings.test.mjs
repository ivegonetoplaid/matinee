import { test } from "node:test";
import assert from "node:assert/strict";

import { FLOORS, LANGUAGES_FIRST, RATED, ROWS, heardWords, languageName, languageOrder, languagesFirst } from "../../src/matinee/web/static/js/settings.js";

test("a language is named in the viewer's language, and TMDB's Cantonese code, which browsers do not name, as Cantonese", () => {
  assert.equal(languageName("fr", "en-GB"), "French");
  assert.equal(languageName("fr", "fr-FR"), "Français");
  assert.equal(languageName("cn", "en-GB"), "Cantonese");
});

test("the browser's own language is offered first, the rest keep the server's order", () => {
  const held = [{ code: "en" }, { code: "fr" }, { code: "ja" }];
  assert.deepEqual(languageOrder(held, "ja-JP").map((l) => l.code), ["ja", "en", "fr"]);
  assert.deepEqual(languageOrder(held, "").map((l) => l.code), ["en", "fr", "ja"]);
});

test("only the languages most films are in show before \"+ More languages\", with the browser's own and every ticked one", () => {
  const held = Array.from({ length: LANGUAGES_FIRST + 3 }, (_, i) => ({ code: `l${i}` }));
  const shown = (locale, chosen) => {
    const ordered = languageOrder(held, locale);
    return ordered.filter((_, i) => languagesFirst(ordered, held, locale, new Set(chosen))[i]).map((l) => l.code);
  };
  const most = held.slice(0, LANGUAGES_FIRST).map((l) => l.code);
  assert.deepEqual(shown("", []), most);
  assert.deepEqual(shown("l16", []), ["l16", ...most]); // a rare browser language shows, and takes no common one's place
  assert.deepEqual(shown("", ["l17"]), [...most, "l17"]);
});

test("the floor and the rated-films ladders run best first, as the store keeps their values", () => {
  assert.deepEqual(FLOORS.map((f) => f.value), ["well_liked", "above_middle", "middle", "above_bottom", "anything"]);
  assert.deepEqual(RATED.map((r) => r.value), [5, 4, 3, 2, 1, 0]);
  assert.equal(RATED[0].band, "Everything I've rated");
});

test("the topics' explanation names only gentle examples, spiders and needles, at both widths", () => {
  for (const words of [ROWS.topics.help, ROWS.topics.short]) {
    assert.match(words, /^Choose topics like spiders or needles\. /);
    assert.doesNotMatch(words.slice("Choose topics like spiders or needles.".length), /\b(like|such as|e\.g\.)/i);
  }
});

test("a film heard in ticked languages names its own and each of them, joined as a sentence", () => {
  assert.deepEqual(heardWords({ original: "th", audio: ["en"] }, "en-US"), ["Original language: Thai", "Your copy has English audio"]);
  assert.deepEqual(heardWords({ original: "ja", audio: ["en", "es", "fr"] }, "en-US"), [
    "Original language: Japanese",
    "Your copy has English, Spanish, and French audio",
  ]);
});
