// The credits every source asks for, as one line of small print.

import { h } from "./dom.js";

function link(href, text) {
  return h("a", { href, target: "_blank", rel: "noopener noreferrer" }, text);
}

export function credits() {
  return h(
    "p",
    { class: "credits" },
    "Posters and film data from TMDB · Tag genome by MovieLens · ",
    link("https://www.doesthedogdie.com", "Powered by DoesTheDogDie.com"),
  );
}
