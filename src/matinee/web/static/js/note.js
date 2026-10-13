// "Wrong pick?" on a result: what was wrong with the pick, and why, in the pick's panel. Every
// answer is kept as a note, with the path that led to the pick, for whoever runs
// Matinee; it changes nothing any viewer is shown. The pick always belongs to a profile
// this device holds. "Not this genre at all" asks where the film belongs, offering every
// other tree, the kids tree included, and the note keeps every tree ticked.

import { post } from "./api.js";
import { h, sentenceCase } from "./dom.js";
import { panelAction } from "./panel.js";

function treeChoices(trees, current) {
  return trees
    .filter((t) => t.tree !== current)
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

function send(walk, film, kind, belongs, comment) {
  return post("/api/notes", {
    profile_id: walk.profileId,
    tmdb: film.tmdb,
    tree: walk.tree,
    kind,
    answers: walk.answers,
    rushed: walk.rushed,
    comment,
    belongs: kind === "genre" ? belongs : [],
    run: walk.run ?? null,
  });
}

// The saved note's two lines, the first in gold.
function noted([gold, cream]) {
  return [h("span", { class: "ack" }, gold), " ", h("span", { class: "ask" }, cream)];
}

// The walk a pick was drawn under, as the note records it: the profile, the run, the door, the answers and their
// words, and whether "Just pick one!" ended the questions. Taken when the film is shown, so a film brought back later
// is noted under the walk it first came from.
export function walkOf(visit) {
  const { tree, answers, says, rushed, firstSay, runKey } = visit;
  return { profileId: visit.viewer.profile_id, run: runKey, tree, answers: [...answers], says: [...says], rushed, firstSay };
}

// "Wrong pick?": opens the pick's panel with the note's form. Null on a pick that came through no door. The form is
// built once per pick, so closing and opening the panel keeps what the viewer chose and wrote.
export function noteLink({ walk, film, trees, panel }) {
  if (!walk.tree) return null;
  const here = trees.find((t) => t.tree === walk.tree);
  const label = here ? here.label.toLowerCase() : "this kind of film";
  const status = h("p", { class: "note", role: "status" });
  const say = (...text) => {
    status.replaceChildren(...text);
  };
  const choices = treeChoices(trees, walk.tree);
  const belongs = h(
    "div",
    { class: "belongs", hidden: true },
    h("p", { class: "note" }, "Where does it belong?"),
    h("div", { class: "tree-choices" }, choices),
  );
  const what = h(
    "fieldset",
    { class: "what-wrong" },
    h("legend", { class: "panel-section" }, "What's wrong with it?"),
    kindChoices(label, () => {
      belongs.hidden = picked() !== "genre";
    }),
  );
  const picked = () => what.querySelector("input[name=what-wrong]:checked")?.value;
  const why = h("textarea", { maxlength: 500, rows: 3, placeholder: "Why? (optional)", "aria-label": "Why? (optional)" });
  const said = [walk.firstSay, ...walk.says, walk.rushed ? "Just pick one!" : null].filter(Boolean);
  const form = [
    h("p", { class: "panel-lede" }, "This goes to whoever runs Matinee as a note. It changes nothing you are shown."),
    h("p", { class: "panel-section" }, "How you got here"),
    h("ol", { class: "path" }, said.map((step) => h("li", {}, sentenceCase(step)))),
    what,
    belongs,
    why,
  ];
  const save = h("button", { class: "action gold", type: "button" }, "Save");
  const foot = h("div", { class: "panel-foot" }, save);
  save.addEventListener("click", async () => {
    const kind = picked();
    if (!kind) return say("Tell me what's wrong with it first.");
    save.disabled = true;
    const belongsTo = choices.map((c) => c.querySelector("input")).filter((i) => i.checked).map((i) => i.value);
    const res = await send(walk, film, kind, belongsTo, why.value);
    if (res.ok) {
      say(...noted(res.data.lines));
      for (const node of [...form, foot]) node.remove();
      return undefined;
    }
    say(res.data.message);
    save.disabled = false;
    return undefined;
  });
  const body = h("div", { class: "note-form" }, form, status, foot);
  const open = panelAction("Wrong pick?", () => panel.open(open, "Wrong pick?", body));
  return open;
}
