// The only way the page talks to its server. Every answer comes back as
// { ok, status, data }, so a failure is always a value the page can show.

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
  try {
    return { ok: response.ok, status: response.status, data: await response.json() };
  } catch {
    const data = { error: "refused", message: "Matinee answered with something I can't read." };
    return { ok: false, status: response.status, data };
  }
}

export const get = (path) => call("GET", path);
export const post = (path, body) => call("POST", path, body);
export const put = (path, body) => call("PUT", path, body);
