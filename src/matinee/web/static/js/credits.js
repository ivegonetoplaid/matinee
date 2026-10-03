// The corner credit line: "Posters and film data from TMDB [logo] · About", in the foot band. TMDB's notice
// and the MovieLens citations are on the About page. On a screen that shows DoesTheDogDie's data the line
// carries "Powered by DoesTheDogDie.com" too. The TMDB logo is always smaller than Matinee's own mark.

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

// DoesTheDogDie's credit, built hidden: the screen shows it before a line built on DoesTheDogDie's data
// starts to type, and it stays for as long as the screen does.
function dtddCredit() {
  return h(
    "span",
    { class: "dtdd-credit", hidden: true },
    h("a", { href: "https://www.doesthedogdie.com", target: "_blank", rel: "noopener noreferrer" }, "Powered by DoesTheDogDie.com"),
  );
}

// `dtdd` makes room for DoesTheDogDie's credit, on a screen that may show its data.
export function credits({ around = null, dtdd = false } = {}) {
  return h("p", { class: "credits" }, "Posters and film data from TMDB ", tmdbLogo(), " · ", aboutLink(around), dtdd ? dtddCredit() : null);
}
