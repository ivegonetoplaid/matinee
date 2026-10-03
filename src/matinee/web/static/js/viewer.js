// The viewer at the right of the theatre's top bar: their mark and name, which open the profile menu.
// The menu holds "Edit my list", "Change avatar", "Switch profiles" and "Delete profile", in that order.
// It opens on click, tap or keyboard, and closes on Escape, on a tap elsewhere, or when an item is chosen.
// "Change avatar" opens a panel beneath it; a tap saves the choice and the bar shows it at once. "Delete
// profile" asks in a panel, never a browser dialog; "No, keep it" changes nothing.

import { h } from "./dom.js";
import { avatarChoices, initials, mark } from "./mark.js";
import { typeLine } from "./type.js";

// On a phone a name longer than this shows as initials beside the avatar.
export const SHORT_NAME = 10;

function item(text, onclick, danger = false) {
  return h("button", { class: danger ? "viewer-item danger" : "viewer-item", type: "button", role: "menuitem", onclick }, text);
}

// A panel beneath the viewer, closed by Escape or a tap elsewhere, as the menu is.
function panel(label, ...children) {
  return h("div", { class: "viewer-panel", role: "dialog", "aria-label": label }, children);
}

// `viewer` is { name, avatar }; `avatars` are the ones offered. `actions` holds editList and switchProfiles,
// and saveAvatar(avatar) and deleteProfile(), which resolve to the page's { ok, data } answer; a profile
// deleted, deleteProfile leaves the theatre itself.
export function viewerTag(viewer, avatars, actions) {
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
    item("Change avatar", choose(() => openPanel(changeAvatar()))),
    item("Switch profiles", choose(actions.switchProfiles)),
    item("Delete profile", choose(() => openPanel(confirmDelete())), true),
  );
  tag.append(menu);
  const items = () => [...menu.querySelectorAll("[role=menuitem]")];
  const elsewhere = (e) => {
    if (!tag.contains(e.target)) close();
  };
  // Escape closes from anywhere while the menu or a panel is open; focus leaving the viewer closes it too.
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
  let shown = null; // the open panel, if any
  function close({ refocus = false } = {}) {
    if (menu.hidden && !shown) return;
    menu.hidden = true;
    shown?.remove();
    shown = null;
    button.setAttribute("aria-expanded", "false");
    document.removeEventListener("pointerdown", elsewhere, true);
    document.removeEventListener("keydown", escape);
    if (refocus) button.focus();
  }
  function openPanel(built) {
    shown = built;
    tag.append(built);
    listen();
    (built.querySelector("[data-focus]") ?? built.querySelector("button"))?.focus({ preventScroll: true });
  }
  // The bar shows a new avatar, or the initials, at once.
  function show(avatar) {
    viewer.avatar = avatar;
    button.querySelector(".mark").replaceWith(mark(viewer, "bar"));
    tag.classList.toggle("has-avatar", Boolean(avatar));
  }
  function changeAvatar() {
    const line = h("p", { class: "line viewer-line", "aria-live": "polite" });
    const status = h("p", { class: "note", role: "status" });
    const save = async (avatar) => {
      for (const b of built.querySelectorAll("button")) b.disabled = true;
      const res = await actions.saveAvatar(avatar);
      if (res.ok) {
        show(res.data.avatar);
        return close({ refocus: true });
      }
      status.textContent = res.data.message;
      for (const b of built.querySelectorAll("button")) b.disabled = false;
      return undefined;
    };
    const initialsOnly = h("button", { class: "letterbox", type: "button", onclick: () => save(null) }, "Just my initials");
    const built = panel("Change avatar", line, avatarChoices(avatars, save, viewer.avatar), initialsOnly, status);
    typeLine(line, "Which one's yours?", "");
    return built;
  }
  function confirmDelete() {
    const line = h("p", { class: "line viewer-line", "aria-live": "polite" });
    const status = h("p", { class: "note", role: "status" });
    const yes = async () => {
      for (const b of built.querySelectorAll("button")) b.disabled = true;
      const res = await actions.deleteProfile();
      if (res.ok) return undefined;
      status.textContent = res.data.message;
      for (const b of built.querySelectorAll("button")) b.disabled = false;
      return undefined;
    };
    const choices = h(
      "div",
      { class: "viewer-choices" },
      h("button", { class: "letterbox danger", type: "button", onclick: yes }, "Yes, delete it"),
      h("button", { class: "letterbox", type: "button", "data-focus": true, onclick: () => close({ refocus: true }) }, "No, keep it"),
    );
    const built = panel(`Delete ${viewer.name}?`, line, choices, status);
    typeLine(line, `Delete ${viewer.name}?`, "Your list goes with it. Any notes you sent stay with whoever runs Matinee.");
    return built;
  }

  function open() {
    shown?.remove();
    shown = null;
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
