// The viewer at the right of the theatre's top bar: their mark and name, which open the profile menu.
// The menu holds "Edit my list", "Change avatar", "Switch profiles" and "Delete profile", in that order.
// It opens on click, tap or keyboard, and closes on Escape, on a tap elsewhere, or when an item is chosen.

import { h } from "./dom.js";
import { initials, mark } from "./mark.js";

// On a phone a name longer than this shows as initials beside the avatar.
export const SHORT_NAME = 10;

function item(text, onclick, danger = false) {
  return h("button", { class: danger ? "viewer-item danger" : "viewer-item", type: "button", role: "menuitem", onclick }, text);
}

// `viewer` is { name, avatar }; `actions` holds editList, changeAvatar, switchProfiles and deleteProfile.
export function viewerTag(viewer, actions) {
  const long = [...viewer.name].length > SHORT_NAME;
  const classes = ["viewer", long ? "long" : "", viewer.avatar ? "has-avatar" : ""].filter(Boolean).join(" ");
  const button = h(
    "button",
    { class: "viewer-button", type: "button", "aria-haspopup": "menu", "aria-expanded": "false", "aria-label": `${viewer.name}, profile menu` },
    mark(viewer, "bar"),
    h("span", { class: "viewer-name", "aria-hidden": "true" }, viewer.name),
    h("span", { class: "viewer-initials", "aria-hidden": "true" }, initials(viewer.name)),
  );
  const tag = h("div", { class: classes }, button);
  const choose = (action) => () => {
    close();
    action();
  };
  const menu = h(
    "div",
    { class: "viewer-menu", role: "menu", "aria-label": "Profile", hidden: true },
    item("Edit my list", choose(actions.editList)),
    item("Change avatar", choose(actions.changeAvatar)),
    item("Switch profiles", choose(actions.switchProfiles)),
    item("Delete profile", choose(actions.deleteProfile), true),
  );
  tag.append(menu);
  const items = () => [...menu.querySelectorAll("[role=menuitem]")];
  const elsewhere = (e) => {
    if (!tag.contains(e.target)) close();
  };
  function close({ refocus = false } = {}) {
    if (menu.hidden) return;
    menu.hidden = true;
    button.setAttribute("aria-expanded", "false");
    document.removeEventListener("pointerdown", elsewhere, true);
    if (refocus) button.focus();
  }
  function open() {
    menu.hidden = false;
    button.setAttribute("aria-expanded", "true");
    document.addEventListener("pointerdown", elsewhere, true);
    items()[0].focus();
  }
  button.addEventListener("click", () => (menu.hidden ? open() : close()));
  // Escape closes; the arrow keys walk the items, round from the last to the first.
  tag.addEventListener("keydown", (e) => {
    if (e.key === "Escape") return close({ refocus: true });
    if (menu.hidden || (e.key !== "ArrowDown" && e.key !== "ArrowUp")) return undefined;
    e.preventDefault();
    const all = items();
    const at = all.indexOf(document.activeElement);
    const next = (at + (e.key === "ArrowDown" ? 1 : -1) + all.length) % all.length;
    return all[next].focus();
  });
  return tag;
}
