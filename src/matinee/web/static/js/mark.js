// A profile's mark: its avatar, or its initials, in a rounded square. The same mark stands on the front
// door's tile (`door`) and in the top bar (`bar`); only its size differs.

import { h } from "./dom.js";

// The image width for each size: twice the size it is shown at, for high-density screens.
const PIXELS = { door: 256, bar: 80 };

// The first letter of each word of a name, at most three, as a capital.
export function initials(name) {
  return String(name)
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 3)
    .map((word) => [...word][0].toLocaleUpperCase())
    .join("");
}

// `avatar` is one of the names the server offers, or null for initials.
export function avatarSrc(avatar, size = "door") {
  return `/static/avatars/${avatar}-${PIXELS[size]}.webp`;
}

export function mark({ name, avatar }, size = "door") {
  const inner = avatar
    ? h("img", { src: avatarSrc(avatar, size), alt: "", width: PIXELS[size] / 2, height: PIXELS[size] / 2, decoding: "async" })
    : h("span", { class: "mark-initials" }, initials(name));
  return h("span", { class: `mark ${size}`, "aria-hidden": "true" }, inner);
}
