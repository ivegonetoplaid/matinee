// The unobtrusive note link on a result: what was wrong with the pick, and why. Every
// answer is kept as a note, with the path that led to the pick, for whoever runs
// Matinee; it changes nothing any viewer is shown. The pick always belongs to a profile
// this device holds. A tree gated by age (kids) is not offered; the panel says why.

import { post } from "./api.js";
import { h, sentenceCase } from "./dom.js";

const GATED_NOTE =
  "Kids' films are picked for the whole house, so I can't add one just for you. Ask whoever runs Matinee to add it.";

function treeChoices(trees, current) {
  return trees
    .filter((t) => t.correctable && t.tree !== current)
    .map((t) =>
      h(
        "label",
        { class: "tree-choice" },
        h("input", { type: "checkbox", value: t.tree }),
        h("span", {}, t.label),
      ),
    );
}

// What was wrong with the pick. Every choice is kept as a note and changes nothing anyone is shown.
function kinds(label) {
  return [
    { kind: "genre", say: `Not ${label} at all` },
    { kind: "kind", say: `${sentenceCase(label)}, but not the kind I asked for` },
    { kind: "quality", say: "The right kind, just not a good pick" },
  ];
}

function kindChoices(label, onchange) {
  return kinds(label).map((k) =>
    h(
      "label",
      { class: "tree-choice" },
      h("input", { type: "radio", name: "what-wrong", value: k.kind, onchange }),
      h("span", {}, k.say),
    ),
  );
}

function send(visit, film, kind, comment) {
  return post("/api/notes", {
    profile_id: visit.viewer.profile_id,
    tmdb: film.tmdb,
    tree: visit.tree,
    kind,
    answers: visit.answers,
    rushed: visit.rushed,
    comment,
  });
}

// The saved note's two lines, the first in gold.
function noted([gold, cream]) {
  return [h("span", { class: "ack" }, gold), " ", h("span", { class: "ask" }, cream)];
}

export function noteLink({ visit, film, trees }) {
  if (!visit.tree) return null;
  const here = trees.find((t) => t.tree === visit.tree);
  const label = here ? here.label.toLowerCase() : "this kind of film";
  const status = h("p", { class: "note", role: "status" });
  const say = (...text) => {
    status.replaceChildren(...text);
  };
  const panel = h("div", { class: "correct-panel", hidden: true });
  const open = h(
    "button",
    {
      class: "link-button",
      type: "button",
      "aria-expanded": "false",
      onclick: () => {
        panel.hidden = !panel.hidden;
        open.setAttribute("aria-expanded", String(!panel.hidden));
      },
    },
    "Something wrong with this pick?",
  );
  const choices = treeChoices(trees, visit.tree);
  const gated = trees.some((t) => !t.correctable && t.tree !== visit.tree);
  const belongs = h(
    "div",
    { class: "belongs", hidden: true },
    h("p", { class: "note" }, "Where does it belong?"),
    h("div", { class: "tree-choices" }, choices),
    gated ? h("p", { class: "note small" }, GATED_NOTE) : null,
  );
  const picked = () => panel.querySelector("input[name=what-wrong]:checked")?.value;
  const what = h(
    "fieldset",
    { class: "what-wrong" },
    h("legend", { class: "note" }, "What's wrong with it?"),
    kindChoices(label, () => {
      belongs.hidden = picked() !== "genre";
    }),
  );
  const why = h("textarea", { maxlength: 500, rows: 3, placeholder: "Why? (optional)", "aria-label": "Why? (optional)" });
  const save = h(
    "button",
    {
      class: "pill gold",
      type: "button",
      onclick: async () => {
        const kind = picked();
        if (!kind) return say("Tell me what's wrong with it first.");
        save.disabled = true;
        const res = await send(visit, film, kind, why.value);
        if (res.ok) {
          say(...noted(res.data.lines));
          open.remove();
          for (const node of [...panel.children]) if (node !== status) node.remove();
          return;
        }
        say(res.data.message);
        save.disabled = false;
      },
    },
    "Save",
  );
  const said = [visit.firstSay, ...visit.says, visit.rushed ? "Just pick one!" : null].filter(Boolean);
  const path = said.map((step) => h("li", {}, sentenceCase(step)));
  const parts = [
    h("p", { class: "note" }, "How you got here:"),
    h("ol", { class: "path" }, path),
    what,
    belongs,
    why,
    save,
    status,
  ];
  panel.append(...parts.filter(Boolean)); // append() would print a null as "null"
  return h("div", { class: "correct" }, open, panel);
}
