// The pick's panel: the one panel every pick action but "Not that one" opens. On a desktop it stands over the left
// column, from under the top bar down to the foot, always at that full height; on a phone it stands over everything
// under the top bar. It is headed by the action's name in gold, with a × at its top right. The ×, Escape and a tap
// or click outside it each close it; a tap outside closes it and does nothing else, so a viewer reaching for
// "Not that one" with a panel open closes the panel first. Opening one action's panel while another is open
// replaces it. Focus moves into the panel as it opens and returns to the action that opened it as it closes; that
// action shows its thread while its panel is open.

import { h, isPhone } from "./dom.js";

// The click that follows a tap outside the panel is that tap's, and does nothing. A tap that never becomes a click
// (a drag) leaves the next tap alone: the next pointerdown lifts the swallow.
function swallowNextClick() {
  const eat = (e) => {
    e.preventDefault();
    e.stopPropagation();
  };
  document.addEventListener("click", eat, { capture: true, once: true });
  document.addEventListener("pointerdown", () => document.removeEventListener("click", eat, true), { capture: true, once: true });
}

// Marks the actions that open the panel: a tap on one is theirs to handle, never a tap outside.
export const OPENER = "data-opens-panel";

// On a desktop the panel stands over the left column from under the top bar to the top of the foot's bar, whatever
// the column holds and however the page has scrolled.
function place(stage, frame, node) {
  const top = stage.querySelector(".topbar").getBoundingClientRect().bottom + parseFloat(getComputedStyle(stage).rowGap);
  const bar = stage.querySelector(".bottombar");
  const foot = bar.getBoundingClientRect().top + parseFloat(getComputedStyle(bar).paddingTop);
  const column = frame.left.getBoundingClientRect();
  Object.assign(node.style, { top: `${top}px`, left: `${column.left}px`, width: `${column.width}px`, height: `${foot - top}px` });
}

// Where the pick's panel stands: `covers()` are the parts it stands over, out of reach while it is open (the left
// column on a desktop; on a phone everything under the top bar, where the stylesheet places it); `place(node)` sets
// its box on a desktop. On a desktop the stylesheet also stops drawing the column.
function onThePick(stage, frame) {
  return {
    covers: () => (isPhone() ? [frame.showing, frame.aside, stage.querySelector(".bottombar")] : [frame.left]),
    place: (node) => {
      if (!isPhone()) place(stage, frame, node);
    },
  };
}

// `frame` is the pick screen's. The panel joins `stage`; while it is open the parts it covers are hidden, so focus
// never walks under it. `entries.opened()` runs as a panel opens where none was, on the tap that opens it, and
// `entries.closed()` as it closes by any way but the browser's back, which closes it through `closedByBack()`.
// `where` is where it stands (`onThePick` unless another surface, such as My profile's overlay, gives its own).
export function pickPanel(stage, frame, entries = { opened() {}, closed() {} }, where = onThePick(stage, frame)) {
  let shown = null; // { node, opener } while a panel is open

  const cover = (on) => {
    for (const part of where.covers()) if (part) part.inert = on;
  };

  const outside = (e) => {
    if (!shown?.node.isConnected) return forget();
    if (shown.node.contains(e.target) || e.target.closest?.(`[${OPENER}]`)) return undefined;
    swallowNextClick();
    return close();
  };
  const escape = (e) => {
    if (e.key === "Escape" && shown) close();
  };
  // A window that becomes a phone's closes the panel; any other change of size places it again. A phone's own
  // resizing, as its keyboard opens, leaves the panel as it is.
  let phone = isPhone();
  const resized = () => {
    const was = phone;
    phone = isPhone();
    if (phone && !was) close();
    else if (shown && !phone) where.place(shown.node);
  };
  function listen(on) {
    const how = on ? "addEventListener" : "removeEventListener";
    document[how]("pointerdown", outside, true);
    document[how]("keydown", escape);
    window[how]("resize", resized);
  }
  // Drops the open panel's listeners without touching the page: the screen it stood on has gone.
  function forget() {
    shown = null;
    listen(false);
  }

  function close() {
    if (!shown) return;
    entries.closed();
    closedByBack();
  }

  function closedByBack() {
    if (!shown) return;
    const { node, opener } = shown;
    forget();
    cover(false);
    node.remove();
    opener.classList.remove("open");
    opener.setAttribute("aria-expanded", "false");
    if (opener.isConnected) opener.focus({ preventScroll: true });
  }

  // Opens a panel headed `title` holding `body`, for the action `opener`; the same action again closes it.
  function open(opener, title, ...body) {
    if (shown?.opener === opener) return close();
    if (shown) {
      shown.node.remove();
      shown.opener.classList.remove("open");
      shown.opener.setAttribute("aria-expanded", "false");
    } else {
      listen(true);
      entries.opened();
    }
    const heading = h("h2", { class: "panel-title", id: "panel-title" }, title);
    const shut = h("button", { class: "panel-close", type: "button", "aria-label": "Close", onclick: () => close() }, "×");
    const node = h(
      "section",
      { class: "pick-panel", role: "dialog", "aria-labelledby": "panel-title" },
      h("div", { class: "panel-head" }, heading, shut),
      h("div", { class: "panel-body" }, body),
    );
    stage.append(node);
    cover(true);
    where.place(node);
    shown = { node, opener };
    opener.classList.add("open");
    opener.setAttribute("aria-expanded", "true");
    (node.querySelector(".panel-body :is(button, a, input, textarea)") ?? shut).focus({ preventScroll: true });
    return undefined;
  }

  return { open, close, closedByBack, isOpen: () => Boolean(shown) };
}

// An action that opens a panel: cream, marked as an opener, announcing the panel it opens.
export function panelAction(words, onclick) {
  return h("button", { class: "action cream", type: "button", [OPENER]: true, "aria-expanded": "false", onclick }, words);
}
