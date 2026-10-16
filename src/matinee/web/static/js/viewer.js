// The viewer at the right of the theatre's top bar: their mark and name, which open the profile menu.
// The menu holds "My profile", "Switch profiles" and "About Matinee", in that order; the picture, the name, the
// topics and deleting the profile are all on My profile. About gives the focus back to the viewer's button when it
// closes. It opens on click, tap or keyboard, and closes on Escape, on a tap elsewhere, or when an item is chosen.

import { openAbout } from "./about.js";
import { h } from "./dom.js";
import { initials, mark } from "./mark.js";

// On a phone a name longer than this shows as initials beside the avatar.
export const SHORT_NAME = 10;

function item(text, onclick) {
  return h("button", { class: "viewer-item", type: "button", role: "menuitem", onclick }, text);
}

// `viewer` is { name, avatar }. `actions` holds myProfile(opener) and switchProfiles().
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
    item("My profile", choose(() => actions.myProfile(button))),
    item("Switch profiles", choose(actions.switchProfiles)),
    item("About Matinee", choose(() => openAbout(button))),
  );
  tag.append(menu);
  const items = () => [...menu.querySelectorAll("[role=menuitem]")];
  const elsewhere = (e) => {
    if (!tag.contains(e.target)) close();
  };
  // Escape closes from anywhere while the menu is open; focus leaving the viewer closes it too.
  const escape = (e) => {
    if (e.key === "Escape") close({ refocus: tag.contains(document.activeElement) });
  };
  tag.addEventListener("focusout", (e) => {
    if (e.relatedTarget && !tag.contains(e.relatedTarget)) close();
  });
  const listen = () => {
    document.addEventListener("pointerdown", elsewhere, true);
    document.addEventListener("keydown", escape);
  };
  function close({ refocus = false } = {}) {
    if (menu.hidden) return;
    menu.hidden = true;
    button.setAttribute("aria-expanded", "false");
    document.removeEventListener("pointerdown", elsewhere, true);
    document.removeEventListener("keydown", escape);
    if (refocus) button.focus();
  }

  function open() {
    menu.hidden = false;
    button.setAttribute("aria-expanded", "true");
    listen();
    items()[0].focus();
  }
  button.addEventListener("click", () => (menu.hidden ? open() : close()));
  // The arrow keys walk the items, round from the last to the first.
  tag.addEventListener("keydown", (e) => {
    if (menu.hidden || (e.key !== "ArrowDown" && e.key !== "ArrowUp")) return undefined;
    e.preventDefault();
    const all = items();
    const at = all.indexOf(document.activeElement);
    const next = (at + (e.key === "ArrowDown" ? 1 : -1) + all.length) % all.length;
    return all[next].focus();
  });
  return tag;
}
