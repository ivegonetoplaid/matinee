// The unobtrusive correction link on a result: what was wrong with the pick, and why.
// "Not this genre at all" removes the film from the tree that offered it and adds it to
// the trees the viewer names, for their profile only. Every answer is also kept as a
// note with the path that led to the pick, for whoever tunes Matinee. A visitor is
// asked for a name first. A tree gated by age (kids) is never offered; the panel says why.

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

async function ensureProfile(visit, nameInput, say) {
  if (visit.viewer.profile_id) return true;
  const name = nameInput ? nameInput.value.trim() : "";
  if (!name) {
    say("I'll need a name to keep that for you.");
    return false;
  }
  const res = await post("/api/profiles", {
    name,
    topics: visit.viewer.topics || [],
    exclusions: visit.viewer.exclusions || [],
  });
  if (!res.ok) {
    say(res.data.message);
    return false;
  }
  visit.profileTopics = res.data.topics.length > 0;
  visit.viewer = { profile_id: res.data.id };
  visit.name = res.data.name;
  return true;
}

// What was wrong with the pick. Only "genre" changes what the viewer is shown; every choice is kept as a note.
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

async function send(visit, film, kind, addTo, comment) {
  if (kind === "genre") {
    const res = await post("/api/corrections", {
      profile_id: visit.viewer.profile_id,
      tmdb: film.tmdb,
      remove_from: visit.tree,
      add_to: addTo,
    });
    if (!res.ok) return res;
  }
  const note = await post("/api/notes", {
    profile_id: visit.viewer.profile_id,
    tmdb: film.tmdb,
    tree: visit.tree,
    kind,
    answers: visit.answers,
    rushed: visit.rushed,
    comment,
  });
  if (note.ok && kind === "genre") note.data.line = "Got it. I'll remember that for you.";
  return note;
}

export function correctionLink({ visit, film, trees }) {
  if (!visit.tree) return null;
  const here = trees.find((t) => t.tree === visit.tree);
  const label = here ? here.label.toLowerCase() : "this kind of film";
  const status = h("p", { class: "note", role: "status" });
  const say = (text) => {
    status.textContent = text;
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
  const nameInput = visit.viewer.profile_id
    ? null
    : h("input", { type: "text", maxlength: 40, placeholder: "Your name", "aria-label": "Your name", autocomplete: "nickname" });
  const save = h(
    "button",
    {
      class: "pill gold",
      type: "button",
      onclick: async () => {
        const kind = picked();
        if (!kind) return say("Tell me what's wrong with it first.");
        save.disabled = true;
        const addTo = choices.map((c) => c.querySelector("input")).filter((i) => i.checked).map((i) => i.value);
        if (await ensureProfile(visit, nameInput, say)) {
          nameInput?.remove(); // the profile exists now; a changed name would be ignored
          const res = await send(visit, film, kind, addTo, why.value);
          say(res.data.line || res.data.message);
          if (res.ok) {
            open.remove();
            for (const node of [...panel.children]) if (node !== status) node.remove();
            return;
          }
        }
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
    nameInput ? h("p", { class: "note" }, "What should I call you? I keep notes by name.") : null,
    nameInput,
    save,
    status,
  ];
  panel.append(...parts.filter(Boolean)); // append() would print a null as "null"
  return h("div", { class: "correct" }, open, panel);
}
