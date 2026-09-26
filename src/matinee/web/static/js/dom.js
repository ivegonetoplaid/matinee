// Building page nodes. Text always goes in as text nodes, never as markup, so a
// name or a title from the server can never become part of the page's HTML.

export function h(tag, props = {}, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (value === undefined || value === null || value === false) continue;
    if (key === "class") el.className = value;
    else if (key.startsWith("on")) el.addEventListener(key.slice(2).toLowerCase(), value);
    else el.setAttribute(key, value === true ? "" : String(value));
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    el.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return el;
}

export function clear(el) {
  el.replaceChildren();
  return el;
}

// Each sentence starts with a capital; everything else is left as written ("I", "RIP AND TEAR").
export function sentenceCase(text) {
  return String(text).replace(/(^|[.!?]\s+)([a-z])/g, (_, lead, letter) => lead + letter.toUpperCase());
}

export const prefersLessMotion = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

export const isPhone = () => window.matchMedia("(max-width: 600px)").matches;

export const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
