// The credits every source asks for. The short line sits under the wall; the
// counter of the box office carries it in full, with TMDB's notice and the
// MovieLens papers. The TMDB logo is always smaller than Matinee's own mark.

import { openAbout } from "./about.js";
import { h } from "./dom.js";

const TMDB_NOTICE = "This product uses the TMDB API but is not endorsed or certified by TMDB.";
const MOVIELENS =
  "Tag genome from MovieLens: Harper and Konstan (2015), The MovieLens Datasets; Vig, Sen and Riedl (2012), The Tag Genome.";

function link(href, text) {
  return h("a", { href, target: "_blank", rel: "noopener noreferrer" }, text);
}

function tmdbLogo() {
  return link(
    "https://www.themoviedb.org",
    h("img", { class: "tmdb-logo", src: "/static/credits/tmdb.svg", alt: "TMDB", width: 62, height: 8 }),
  );
}

// Opens the About page, which gives the focus back to this link when it closes.
function aboutLink() {
  const button = h("button", { class: "inline-link", type: "button", onclick: () => openAbout(button) }, "About");
  return button;
}

// "Posters and film data from TMDB [logo] · Tag genome by MovieLens · Powered by DoesTheDogDie.com · About"
export function credits({ full = false } = {}) {
  const line = h(
    "p",
    { class: "credits" },
    "Posters and film data from TMDB ",
    tmdbLogo(),
    " · Tag genome by ",
    link("https://grouplens.org/datasets/movielens/", "MovieLens"),
    " · ",
    link("https://www.doesthedogdie.com", "Powered by DoesTheDogDie.com"),
    " · ",
    aboutLink(),
  );
  if (!full) return line;
  return h("div", { class: "credits-full" }, line, h("p", { class: "credits small" }, TMDB_NOTICE, " ", MOVIELENS));
}
