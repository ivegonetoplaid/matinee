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

// What each avatar shows, for a screen reader.
const AVATAR_NAMES = {
  "3d-glasses": "3D glasses",
  camera: "Film camera",
  candy: "Box of candy",
  chair: "Director's chair",
  clapperboard: "Clapperboard",
  "comedy-tragedy": "Comedy and tragedy masks",
  "director-megaphone": "Megaphone",
  "film-reel": "Film reel",
  hotdog: "Hot dog",
  nachos: "Nachos",
  popcorn: "Popcorn",
  soda: "Soda cup",
  "theater-seat": "Theatre seat",
  ticket: "Ticket",
  vhs: "VHS tape",
};

// The avatars to choose from, as buttons; `onPick` is handed the avatar chosen. `current` is pressed.
export function avatarChoices(avatars, onPick, current = null) {
  return h(
    "div",
    { class: "avatar-choices", role: "group", "aria-label": "Avatars" },
    avatars.map((avatar) =>
      h(
        "button",
        {
          class: "avatar-choice",
          type: "button",
          "aria-label": AVATAR_NAMES[avatar] ?? avatar,
          "aria-pressed": String(avatar === current),
          onclick: () => onPick(avatar),
        },
        mark({ name: "", avatar }, "door"),
      ),
    ),
  );
}
