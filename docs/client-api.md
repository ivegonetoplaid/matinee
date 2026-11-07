# Client API

Matinee exposes two stateless, authenticated HTTP operations. They call the same
engine and picker as the website. They do not wait for browser animations and do
not play films, change profiles, or manage another application's conversation.
The website keeps its existing routes and behavior.

## Authorization and setup

Create or choose a dedicated profile in Matinee and configure its rating floor,
languages and content exclusions there. Use an existing device token for that
profile in the `Authorization: Bearer <profile-token>` header. The token selects
the profile; callers cannot name a different profile in the request.

When Matinee has a door word, requests also need the existing `matinee_admit`
admission cookie. A profile token never admits a device. Missing or expired door
admission produces `401 not_admitted`; a missing or invalid profile token produces
`401 unauthorized`. Turning off the door word does not remove profile-token
authorization from the client API.

An operator can obtain the existing credentials from a browser already admitted
and holding the profile, using its storage inspector. `matinee_tokens` holds
profile device tokens; `matinee_admit` holds door admission. Transfer only the
chosen profile's token and the admission cookie into the client's secret store.
Do not paste them into chats, URLs, source files or logs. This API adds no token
issuance, login, credential storage or permission-management endpoint. A profile
token also authorizes existing profile operations when used as a browser token;
entrust it only to a client allowed to hold that profile. Deleting the profile
revokes its tokens. Door admission retains the website's expiration policy.

Keep the API on the installation's private network. No public endpoint is
required. Use HTTPS or a trusted encrypted transport when credentials cross a
network. Disable client redirects so credentials cannot reach another host.

## Requests

Send JSON to `POST /api/client/choices` or `POST /api/client/pick`:

```json
{
  "source": "held",
  "tree": "horror",
  "answers": [{"question": "flavour", "option": "supernatural"}],
  "year_min": null,
  "year_max": null,
  "seen": []
}
```

The example choice is usable only when Matinee offers it for the current profile
and library. Start with `{}` to inspect doors or pick from the whole permitted
pool. Omit `tree` or use `null` before choosing a door. Send the entire constraint
set on each call. Matinee retains no client conversation state.

- `source` defaults to `held`. `new` means films not in the library, not newer
  releases. `all` explicitly requests both pools.
- `tree` is a door identifier returned by Matinee.
- `answers` contains up to twelve ordered choices. Each names the current
  question and a returned option identifier. A uniquely named flavour uses its
  canonical identifier, such as `supernatural`. Other choices use the tree's
  question-local `option_0`, `option_1`, etc. Clients must inspect current choices
  instead of maintaining their own mapping.
- `year_min` and `year_max` are inclusive release-year bounds. An explicit bound
  excludes unknown years. Bounds refine the engine's resulting pool, so adding a
  release bound does not invalidate earlier choices merely by making the pool
  small. No result ever silently drops a bound.
- `seen` contains up to 200 positive TMDB identifiers to avoid on a subsequent
  pick. A fully exhausted pool returns no film, rather than resetting this list.

The profile supplies the rating floor, languages, hidden films, previous ratings
and content exclusions. The client cannot override these settings. An early pick
needs no answers to remaining questions. To change direction, send the replacement
door and choices. To request another, retain constraints and add offered films to
`seen`. To request a newer film, retain constraints and increase `year_min` using
the selected film's known year.

Unknown fields, malformed bounds and invalid sources fail with `422`. An unknown,
stale, unavailable or out-of-order choice fails with `400`. The API never repairs
an invalid choice by widening the pool. A library that is absent or cannot be
read produces `503 library_unavailable` for `held` and `new`, even if the website
can continue with films outside the library.

## Responses

Both operations return the supplied constraints plus:

- `profile`: its `id`, `name` and configured `floor`.
- `pool_count`: films matching the constraints before `seen` or content checks.
- `available_count`: those films less the supplied `seen` identifiers.
- `doors`: currently available `{id, label, count}` entries.
- `question`: the next `{id, options}` or `null`. Each option has `id`, `label`
  and `count`. Counts include release bounds. Labels use canonical filter terms
  where available instead of the website's theatrical prose.

A pick also returns `film` as `{tmdb, title, year}`, or `null` when nothing can be
selected. It returns `warnings` and `excluded`, the identifiers rejected by the
profile's content checks during this pick. Preserve the title and year for any
separately authorized playback handoff. Counts are not promises that content
checks will allow a film: those checks run only at selection time.

Picks also return `credits` as `{text, url}` entries when content checks run.
Clients must retain the DoesTheDogDie attribution wherever those results appear,
including a link where the medium permits. Its checks are best effort, never a
guarantee. The installation and its clients remain subject to [data terms](data-terms.md).

Clients must surface warnings, including unchecked content or an exhausted pool.
A null film is not permission to invent a Matinee result. The Matinee website's
error envelope uses `error` and `message`; the API uses it for service and
authorization failures too. Responses are `Cache-Control: no-store` and contain
no credentials, media-server item identifiers or private service addresses.
