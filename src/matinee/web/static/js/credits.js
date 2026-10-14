// The acknowledgements live on the About page alone: TMDB's notice and logo, the MovieLens citations and
// DoesTheDogDie's credit. "About Matinee" opens it: at the foot's middle on a screen with no profile menu, and as the
// profile menu's last item inside the theatre. DoesTheDogDie's terms also want its credit wherever its data shows,
// so it stands in the door's credit line while the topic picker shows its topics (`credits`), in the pick's foot
// band when Matinee's line names one of its topics (`dtddFoot`), beside an unchecked film's note (`dtddBeside`), and
// under My profile's "Scenes you don't want to see" (`dtddSetting`).

import { openAbout } from "./about.js";
import { h } from "./dom.js";

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

// DoesTheDogDie's credit beside a resting pick's unchecked note, which stands on the scrim.
export function dtddBeside() {
  return h(
    "p",
    { class: "beside-credit" },
    h("a", { href: "https://www.doesthedogdie.com", target: "_blank", rel: "noopener noreferrer" }, "Powered by DoesTheDogDie.com"),
  );
}

// DoesTheDogDie's credit in the pick's foot band, built hidden: a pick whose line names one of its topics shows it
// before the line starts to type, and it stays for as long as the pick does.
export function dtddFoot() {
  return h(
    "p",
    { class: "credits", hidden: true },
    h("a", { href: "https://www.doesthedogdie.com", target: "_blank", rel: "noopener noreferrer" }, "Powered by DoesTheDogDie.com"),
  );
}

// DoesTheDogDie's credit under My profile's "Scenes you don't want to see", which offers its topics.
export function dtddSetting() {
  return h("a", { class: "set-credit", href: "https://www.doesthedogdie.com", target: "_blank", rel: "noopener noreferrer" }, "Powered by DoesTheDogDie.com ↗");
}

// The door's credit line: DoesTheDogDie's credit, built hidden, for the topic picker to show.
export function credits() {
  return h("p", { class: "credits" }, dtddCredit());
}
