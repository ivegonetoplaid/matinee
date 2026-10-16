// "Hide film": the pick's panel with the four hide lengths, none chosen. A choice hides the film from the viewer's
// picks for that length and rolls again; while the next pick hunts, a plain "Undo" stands in the foot and fades as
// the hunt lands. "Undo" brings the film back as the pick.

import { h } from "./dom.js";
import { panelAction } from "./panel.js";

// The lengths a hide may last, as the viewer chooses them, and as the server keeps them.
export const LENGTHS = [
  { length: "3m", say: "3 months" },
  { length: "6m", say: "6 months" },
  { length: "1y", say: "1 year" },
  { length: "good", say: "For good" },
];

const UNDO_FADE_MS = 400;
const UNDO_REFUSED = "That didn't go through. The film is still hidden; bring it back from My profile.";
const UNDO_REFUSED_MS = 8000; // long enough to read the line twice

// The pick's words above the lengths: a hide there rolls again.
const ROLLS = (title) => `Matinee won't pick ${title} for you until then, and rolls again now. You can bring it back any time from My profile.`;

// "Hide film" for `film`; `hide(length)` hides it (and on the pick rolls again), resolving to the page's { ok, data }
// answer. `lede(title)` gives the words above the lengths.
export function hideLink({ film, panel, hide, lede = ROLLS }) {
  const open = panelAction("Hide film", () => {
    const status = h("p", { class: "rate-status", role: "status" });
    const choices = LENGTHS.map((l) =>
      h(
        "button",
        {
          class: "letterbox",
          type: "button",
          onclick: async () => {
            for (const b of choices) b.disabled = true;
            const res = await hide(l.length);
            if (res.ok) return undefined;
            status.textContent = res.data.message;
            for (const b of choices) b.disabled = false;
            return undefined;
          },
        },
        l.say,
      ),
    );
    panel.open(
      open,
      "Hide film",
      h("p", { class: "panel-lede" }, lede(film.title)),
      h("div", { class: "panel-mid" }, choices, status),
    );
  });
  return open;
}

// The brief "Undo" in the foot while the next pick hunts; `undo()` brings the hidden film back and resolves to whether
// it did. `fade()` takes it away, fading, as the hunt lands. A refused undo says so in `home`, a part of the foot the
// landing pick keeps, and stays a while longer, so the viewer can read where to bring the film back from.
export function undoLink(undo, home) {
  let refused = false;
  const link = h("button", { class: "undo-link", type: "button" }, "Undo");
  link.addEventListener("click", async () => {
    link.disabled = true;
    if (await undo()) return;
    refused = true;
    const said = h("p", { class: "undo-refused", role: "status" }, UNDO_REFUSED);
    link.remove();
    home.append(said);
    setTimeout(() => said.remove(), UNDO_REFUSED_MS);
  });
  return {
    node: link,
    fade() {
      if (refused || !link.isConnected) return;
      link.classList.add("leaving");
      link.disabled = true;
      setTimeout(() => link.remove(), UNDO_FADE_MS);
    },
  };
}
