import { test } from "node:test";
import assert from "node:assert/strict";

import { get } from "../../src/matinee/web/static/js/api.js";

const answering = (status, body) => async () => ({ ok: status < 400, status, json: async () => body });

test("a device no longer admitted is sent back to the door instead of shown a refusal", async () => {
  let reloads = 0;
  globalThis.location = { reload: () => reloads++ };
  globalThis.fetch = answering(401, { error: "not_admitted", message: "Give the word at the door." });
  const settled = await Promise.race([get("/api/door").then(() => "answered"), new Promise((r) => setTimeout(r, 50, "held"))]);
  assert.equal(reloads, 1);
  assert.equal(settled, "held"); // nothing half-done is drawn before the door shows
  globalThis.fetch = answering(401, { error: "wrong_word", message: "That's not the word." });
  assert.equal((await get("/api/admission")).data.error, "wrong_word"); // a wrong word is answered, not reloaded
  assert.equal(reloads, 1);
});
