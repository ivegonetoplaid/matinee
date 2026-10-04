import assert from "node:assert/strict";
import { test } from "node:test";

import { backdropUrl, posterPaths, posterUrl } from "../../src/matinee/web/static/js/pictures.js";

test("a film without a TMDB path keeps Matinee's image route at every size", () => {
  const paths = posterPaths({ source: "jellyfin", posters: {} });
  for (const size of ["xs", "s", "m", "l"]) assert.equal(posterUrl(paths, 5, size), `/img/poster/5/${size}`);
  assert.equal(backdropUrl(5, "l", null), "/img/backdrop/5/l");
});

test("a film with a TMDB path loads from TMDB at the nearest TMDB width", () => {
  const paths = posterPaths({ source: "tmdb", posters: { 5: "/p5.jpg" } });
  assert.equal(posterUrl(paths, 5, "xs"), "https://image.tmdb.org/t/p/w92/p5.jpg");
  assert.equal(posterUrl(paths, 5, "s"), "https://image.tmdb.org/t/p/w154/p5.jpg");
  assert.equal(posterUrl(paths, 5, "m"), "https://image.tmdb.org/t/p/w342/p5.jpg");
  assert.equal(posterUrl(paths, 5, "l"), "https://image.tmdb.org/t/p/w780/p5.jpg");
  assert.equal(posterUrl(paths, 6, "m"), "/img/poster/6/m");
  assert.equal(backdropUrl(5, "l", "/b5.jpg"), "https://image.tmdb.org/t/p/w1280/b5.jpg");
  assert.equal(backdropUrl(5, "m", "/b5.jpg"), "https://image.tmdb.org/t/p/w780/b5.jpg");
});

test("a missing or failed reply leaves no TMDB paths", () => {
  assert.equal(posterPaths(undefined).size, 0);
  assert.equal(posterPaths({ error: "offline" }).size, 0);
});
