// The About page: a screen inside the page, with no address of its own. It opens over whatever screen
// is showing, as a centred see-through panel over the poster wall with the wordmark at the top left.
// The screen underneath is hidden, never rebuilt or paused, and shows again exactly as it stands when
// About closes. "Back", the browser's Back, a phone's back gesture and Escape all close it: opening it
// adds one history entry at the same address, and closing it by "Back" or Escape steps back over that entry.

import { h } from "./dom.js";

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
        "It won't always get it right. Where a film belongs is a judgment call, and yours may differ from mine. If you disagree with where I've put something, move it. Matinee keeps your moves with your profile and sorts around them, so over time its picks lean toward your idea of a thriller, not mine.",
      ),
    ),
    section(
      "How it knows what a film feels like",
      h(
        "p",
        {},
        "Genre labels are blunt. The tag genome is the opposite. It comes from MovieLens, a research project at the University of Minnesota, and it scores thousands of films against more than a thousand tags like atmospheric, dark humor, slow paced and twist ending, learned from the tags and ratings of MovieLens users. It's how Matinee can tell a slow-burn thriller from a popcorn one.",
      ),
      h("p", {}, "It's a genuinely fascinating piece of work, and worth a look."),
      h("p", {}, link("https://movielens.org", "Visit MovieLens"), " · ", link("https://grouplens.org/datasets/movielens/", "The tag genome dataset")),
      h(
        "p",
        { class: "about-cite" },
        "Harper and Konstan (2015), The MovieLens Datasets: History and Context. Vig, Sen and Riedl (2012), The Tag Genome: Encoding Community Knowledge to Support Novel Interaction.",
      ),
    ),
    section(
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
  ];
}

let shown = null; // { layer, opener } while About is open

// Closes About and shows the screen underneath as it stands. Runs on the browser's Back, which the
// page's own "Back" also goes through.
function close() {
  if (!shown) return;
  const { layer, opener } = shown;
  shown = null;
  layer.remove();
  stage.classList.remove("behind-about");
  if (opener?.isConnected) opener.focus({ preventScroll: true });
}

window.addEventListener("popstate", close);
window.addEventListener("keydown", (e) => {
  if (shown && e.key === "Escape") history.back();
});

// Opens About over the current screen. `opener` gets the focus back when About closes.
export function openAbout(opener = null) {
  if (shown) return;
  const back = h("button", { class: "link-button about-back", type: "button", onclick: () => history.back() }, "Back");
  const layer = h(
    "div",
    { class: "about", role: "dialog", "aria-modal": "true", "aria-labelledby": "about-title" },
    h("div", { class: "wordmark about-wordmark", "aria-hidden": "true" }, "Matinee"),
    h("main", { class: "about-panel" }, copy(back)),
  );
  shown = { layer, opener };
  history.pushState({ about: true }, "");
  stage.classList.add("behind-about");
  document.body.append(layer);
  back.focus({ preventScroll: true });
}
