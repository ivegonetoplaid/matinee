// The unobtrusive correction link on a result: "not really this kind of film".
// It removes the film from the tree that offered it and adds it to the trees the
// viewer names, for their profile only. A visitor is asked for a name first.
// A tree gated by age (kids) is never offered; the panel says why.

import { post } from "./api.js";
import { h } from "./dom.js";

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

export function correctionLink({ visit, film, trees }) {
  if (!visit.tree) return null;
  const here = trees.find((t) => t.tree === visit.tree);
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
    "Wrong kind of film?",
  );
  const choices = treeChoices(trees, visit.tree);
  const nameInput = visit.viewer.profile_id
    ? null
    : h("input", { type: "text", maxlength: 40, placeholder: "Your name", "aria-label": "Your name", autocomplete: "nickname" });
  const save = h(
    "button",
    {
      class: "pill gold",
      type: "button",
      onclick: async () => {
        save.disabled = true;
        const addTo = choices.map((c) => c.querySelector("input")).filter((i) => i.checked).map((i) => i.value);
        if (await ensureProfile(visit, nameInput, say)) {
          nameInput?.remove(); // the profile exists now; a changed name would be ignored
          const res = await post("/api/corrections", {
            profile_id: visit.viewer.profile_id,
            tmdb: film.tmdb,
            remove_from: visit.tree,
            add_to: addTo,
          });
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
  const gated = trees.some((t) => !t.correctable && t.tree !== visit.tree);
  const parts = [
    h("p", { class: "note" }, `Not really ${here ? here.label.toLowerCase() : "this kind of film"}? Where does it belong?`),
    h("div", { class: "tree-choices" }, choices),
    gated ? h("p", { class: "note small" }, GATED_NOTE) : null,
    nameInput ? h("p", { class: "note" }, "What should I call you? I keep corrections by name.") : null,
    nameInput,
    save,
    status,
  ];
  panel.append(...parts.filter(Boolean)); // append() would print a null as "null"
  return h("div", { class: "correct" }, open, panel);
}
