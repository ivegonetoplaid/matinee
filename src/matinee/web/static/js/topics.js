// A DoesTheDogDie topic as a letterbox that toggles: chosen, it shows a check mark before its words. The door's
// trigger picker and My profile's "Scenes you don't want to see" build their topics this way.

import { h } from "./dom.js";

// `chosen` is the set of chosen topic ids, changed in place as the viewer toggles; `find` is the topic's words a
// search matches; `onToggle(id, on)` hears each change.
export function topicButton({ label, find, chosen, id, onToggle }) {
  const b = h("button", { class: "letterbox topic", type: "button", "aria-pressed": String(chosen.has(id)) }, label);
  b.dataset.find = `${label} ${find}`.toLowerCase();
  b.addEventListener("click", () => {
    if (chosen.has(id)) chosen.delete(id);
    else chosen.add(id);
    b.setAttribute("aria-pressed", String(chosen.has(id)));
    onToggle(id, chosen.has(id));
  });
  return b;
}
