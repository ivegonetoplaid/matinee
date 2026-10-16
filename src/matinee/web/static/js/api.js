// The only way the page talks to its server. Every answer comes back as
// { ok, status, data }, so a failure is always a value the page can show. The one exception: a device whose
// admission has ended (the door word changed, or its cookie is gone) is sent back to the door, which the page
// shows on load, and the call never answers, so nothing half-done is drawn in the meantime.

async function call(method, path, body) {
  const init = { method, headers: { Accept: "application/json" }, credentials: "same-origin" };
  if (body !== undefined) {
    init.headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(body);
  }
  let response;
  try {
    response = await fetch(path, init);
  } catch {
    return { ok: false, status: 0, data: { error: "offline", message: "I can't reach Matinee right now." } };
  }
  let data;
  try {
    data = await response.json();
  } catch {
    return { ok: false, status: response.status, data: { error: "refused", message: "Matinee answered with something I can't read." } };
  }
  if (response.status === 401 && data?.error === "not_admitted") {
    location.reload();
    return new Promise(() => {});
  }
  return { ok: response.ok, status: response.status, data };
}

export const get = (path) => call("GET", path);
export const post = (path, body) => call("POST", path, body);
export const put = (path, body) => call("PUT", path, body);
export const del = (path) => call("DELETE", path);
