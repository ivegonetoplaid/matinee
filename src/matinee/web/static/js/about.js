// The About page: a screen inside the page, with no address of its own. It opens over whatever screen
// is showing, as a centred see-through panel over the poster wall with the wordmark at the top left.
// The screen underneath is hidden, never rebuilt or paused, and shows again exactly as it stands when
// About closes. "Back", the browser's Back, a phone's back gesture and Escape all close it: opening it
// adds one history entry at the same address, and closing it by "Back" or Escape steps back over that entry.
// Opened from the door, the marquee's name flies to the wordmark's place first and flies back on closing.

import { h } from "./dom.js";
import { cornerMark } from "./flight.js";
import { offers } from "./offers.js";

const stage = document.getElementById("stage");

function link(href, text) {
  return h("a", { href, target: "_blank", rel: "noopener noreferrer" }, text);
}

function section(title, ...parts) {
  return h("section", { class: "about-section" }, h("h2", {}, title), ...parts);
}

// The approved copy, in order. It states no count that changes over time.
function copy(back) {
  return [
    h(
      "div",
      { class: "about-head" },
      back,
      h("h1", { class: "about-title", id: "about-title" }, "About Matinee"),
      h("p", { class: "about-lead" }, "Tell Matinee what you're in the mood for and it picks tonight's film from the library."),
    ),
    section(
      "Why it exists",
      h(
        "p",
        {},
        "It started with a problem I kept running into. I'd sit down with no idea what I was in the mood for. Eventually I'd settle on something, say a thriller, and sort the library by genre. Then I'd scroll past films I felt didn't truly belong, and the ones I actually wanted got lost in the noise.",
      ),
      h(
        "p",
        {},
        "So I built a small recommender, just for me. Along the way I found the MovieLens tag genome and DoesTheDogDie, and each one pulled the project further. It grew into what you're using now: a way to land on the film you actually feel like watching tonight.",
      ),
      h(
        "p",
        {},
        'It won\'t always get it right. Where a film belongs is a judgment call, and yours may differ from mine. If you think I\'ve put something in the wrong place, you can tell me where it fits best by choosing "Something wrong with this pick?". Every note reaches whoever runs Matinee, and when they agree, the film moves for everyone.',
      ),
    ),
    section(
      "How it knows what a film feels like",
      h(
        "p",
        {},
        "Genre labels are blunt. The tag genome is the opposite. It comes from MovieLens, a research project at the University of Minnesota, and it scores thousands of films against more than a thousand tags like atmospheric, dark humor, slow paced and twist ending, learned from the tags and ratings of MovieLens users. Matinee leans on it to judge how much gore a horror film carries.",
      ),
      h("p", {}, "It's a genuinely fascinating piece of work, and worth a look."),
      h("p", {}, link("https://movielens.org", "Visit MovieLens"), " · ", link("https://grouplens.org/datasets/movielens/", "The tag genome dataset")),
      h(
        "p",
        { class: "about-cite" },
        "Harper and Konstan (2015), The MovieLens Datasets: History and Context. Vig, Sen and Riedl (2012), The Tag Genome: Encoding Community Knowledge to Support Novel Interaction.",
      ),
    ),
    // Without a DoesTheDogDie key nothing steers around anything, so the section and its credit are left out.
    !offers.dtdd ? null : section(
      "How it steers around things",
      h(
        "p",
        {},
        "DoesTheDogDie is a site where people vote on what's in a film, so you can know before you watch. Its name is its most famous question, but it covers hundreds of topics, from spiders to needles. It's a lovely bit of community work, and worth a visit.",
      ),
      h(
        "p",
        {},
        "When you ask Matinee to steer around something, it checks each pick against those votes before showing it to you. It's best effort: a film nobody has voted on can't be checked, and Matinee tells you when that happens.",
      ),
      h("p", {}, link("https://www.doesthedogdie.com", "Powered by DoesTheDogDie.com")),
    ),
    section(
      "Posters and film data",
      h("p", {}, "Posters and film details come from TMDB, The Movie Database, which its community builds and keeps up to date."),
      h(
        "p",
        {},
        link("https://www.themoviedb.org", h("img", { class: "about-tmdb", src: "/static/credits/tmdb.svg", alt: "TMDB", width: 108, height: 14 })),
      ),
      h("p", { class: "about-cite" }, "This product uses the TMDB API but is not endorsed or certified by TMDB."),
    ),
    // Shown on every installation, whichever media server and request service it uses, or none.
    section(
      "Good company",
      h(
        "p",
        {},
        "Matinee only picks the film. Two projects I've relied on for years take care of the rest of the evening, and both are worth your time.",
      ),
      h(
        "p",
        {},
        "Jellyfin is a free, open-source media server: your own films, kept on your own computer, ready on the screens around the house.",
      ),
      h(
        "p",
        {},
        "Seerr is where a film you don't have yet becomes one you can ask for. Matinee can open any pick there, and in my house that's the very next step after a pick we don't own. It's free and open source too, from the team behind Overseerr and Jellyseerr.",
      ),
      h("p", {}, link("https://jellyfin.org", "Visit Jellyfin"), " · ", link("https://seerr.dev", "Visit Seerr")),
    ),
    keeps(),
  ];
}

// The privacy statement. It names only what this installation does: the DoesTheDogDie lines need its key,
// and the TMDB line shows only when each browser loads pictures straight from TMDB.
function keeps() {
  const profile = offers.dtdd
    ? "each profile's name, picture, PIN (stored scrambled, never as typed) and list of things to steer around"
    : "each profile's name, picture and PIN (stored scrambled, never as typed)";
  return section(
    "What Matinee keeps",
    h(
      "p",
      {},
      "Matinee runs on its owner's own computer. Nothing you do here is sent to Matinee's maker or anyone else, and there are no accounts, no ads and no tracking.",
    ),
    h(
      "p",
      {},
      "It's built to know as little about you as it can. It never asks for your email or your real name, a profile's name can be anything you like, and it doesn't log your address.",
    ),
    h(
      "p",
      {},
      `Kept on this computer: ${profile}; any note you leave about a pick, for whoever runs this Matinee; and cookies in your browser that remember which profiles this device has opened and that it gave the door word, for up to 400 days.`,
    ),
    h(
      "p",
      {},
      offers.dtdd
        ? "To check a pick, Matinee asks DoesTheDogDie about that one film. Your list never leaves this computer, because the check happens here, and the answer is forgotten within 30 days. "
        : "",
      "Film details come from TMDB, fetched overnight, with nothing about you. ",
      offers.postersFromTmdb ? "Your browser loads posters straight from TMDB, so TMDB sees you as any website you visit does. " : "",
      "Matinee only ever reads a Jellyfin or Plex library; it never changes it.",
    ),
    h(
      "p",
      {},
      offers.dtdd ? "A PIN stops other devices opening your profile or seeing your list. " : "A PIN stops other devices opening your profile. ",
      "Deleting a profile removes its name, PIN and everything it keeps; notes it left stay. Ask whoever runs this Matinee to remove anything else.",
    ),
  );
}

let shown = null; // { layer, opener, around } while About is open

// Closes About and shows the screen underneath as it stands. Runs on the browser's Back, which the
// page's own "Back" also goes through.
function close() {
  if (!shown) return;
  const { layer, opener, around } = shown;
  shown = null;
  layer.remove();
  stage.classList.remove("behind-about");
  around?.bringBack();
  if (opener?.isConnected) opener.focus({ preventScroll: true });
}

window.addEventListener("popstate", close);
window.addEventListener("keydown", (e) => {
  if (shown && e.key === "Escape") history.back();
});

// Opens About over the current screen. `opener` gets the focus back when About closes. `around` is the
// door, when About opens from it: its name flies to the wordmark's place before the screen is hidden.
export async function openAbout(opener = null, around = null) {
  if (shown) return;
  const back = h("button", { class: "action cream", type: "button", onclick: () => history.back() }, "Back");
  const layer = h(
    "div",
    { class: around ? "about from-door flying" : "about", role: "dialog", "aria-modal": "true", "aria-labelledby": "about-title" },
    h("div", { class: "wordmark about-wordmark", "aria-hidden": "true" }, cornerMark()),
    h("main", { class: "about-panel" }, copy(back)),
  );
  shown = { layer, opener, around };
  history.pushState({ about: true }, "");
  document.body.append(layer);
  back.focus({ preventScroll: true });
  if (around) {
    await around.leave();
    if (shown?.layer !== layer) return; // closed while the name was flying
    layer.querySelector(".about-wordmark").classList.add("arriving");
    layer.classList.remove("flying");
    around.settle({ handover: true });
  }
  stage.classList.add("behind-about");
}
