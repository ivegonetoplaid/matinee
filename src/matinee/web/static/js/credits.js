// The corner credit line: "Posters and film data from TMDB [logo]", in the foot band. TMDB's notice and the
// MovieLens citations are on the About page, which "About Matinee" opens: at the foot's middle on a screen with
// no profile menu, and as the profile menu's last item inside the theatre. On a screen that shows DoesTheDogDie's data the line
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

// "About Matinee", which opens the About page; the page gives the focus back to this link when it closes.
// `around` is the door when the link is the door's: its marquee leaves while About is open.
export function aboutLink(around = null) {
  const button = h("button", { class: "inline-link about-link", type: "button", onclick: () => openAbout(button, around) }, "About Matinee");
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
export function credits({ dtdd = false } = {}) {
  return h("p", { class: "credits" }, "Posters and film data from TMDB ", tmdbLogo(), dtdd ? dtddCredit() : null);
}
