// The corner credit line: "Posters and film data from TMDB [logo] · About". TMDB's notice and the
// MovieLens citations are on the About page, and DoesTheDogDie is credited beside its own data wherever
// that shows. The TMDB logo is always smaller than Matinee's own mark.

import { openAbout } from "./about.js";
import { h } from "./dom.js";

function tmdbLogo() {
  return h(
    "a",
    { href: "https://www.themoviedb.org", target: "_blank", rel: "noopener noreferrer" },
    h("img", { class: "tmdb-logo", src: "/static/credits/tmdb.svg", alt: "TMDB", width: 62, height: 8 }),
  );
}

// Opens the About page, which gives the focus back to this link when it closes. `around` is the door
// when the line is the door's: its marquee leaves while About is open.
function aboutLink(around) {
  const button = h("button", { class: "inline-link", type: "button", onclick: () => openAbout(button, around) }, "About");
  return button;
}

export function credits({ around = null } = {}) {
  return h("p", { class: "credits" }, "Posters and film data from TMDB ", tmdbLogo(), " · ", aboutLink(around));
}
