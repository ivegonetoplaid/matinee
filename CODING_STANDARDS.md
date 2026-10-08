# Matinee — Coding Standards

These rules apply to all Matinee code. This file is self-contained: contributors
do not need private standards, notes or agent configuration.

[DESIGN_STANDARDS.md](DESIGN_STANDARDS.md) governs visual design and copy;
[docs/spec/matinee.md](docs/spec/matinee.md) defines behaviour;
[AGENTS.md](AGENTS.md) covers repository workflow and data-source restrictions.
Follow all three alongside this file. Cite rules by section name, not number.

Resolve conflicts explicitly. A departure must be documented in the relevant
standard with its reason and scope; never silently waive a rule or bypass its
gate. Experiments may relax style and architecture, but never input validation,
secrets protection or DOM safety.

## Boundaries and Types

- **Declare boundary contracts.** Functions returning records across modules
  declare and return typed records: dataclasses, Pydantic models, `TypedDict`
  or equivalent object types. Scalars and collections also have explicit types.
  An untyped mapping such as `dict[str, Any]` crosses a boundary only during
  serialisation or as an explicitly opaque payload that core logic does not inspect.
  An API decorator does not replace the function's own return annotation.
- **Validate at entry.** Parse external input at the boundary before core logic
  uses it. Reject unknown fields in closed schemas; deliberately open schemas
  document which extra data they accept. Static types alone do not validate input.
- **Pass dependencies explicitly.** Read configuration and environment variables
  at entry points and pass them down. No hidden collaborators, singletons or
  mutable global state.
- **Keep transport in adapters.** Core logic does not parse HTTP requests, open
  sockets or inspect platform-specific wire payloads.
- **Make side effects explicit.** Names and signatures reveal external changes;
  functions do not mutate their arguments. Writes have an explicit outcome.
- **Keep async responsive.** Blocking I/O uses an async implementation or a worker
  thread, never the event-loop thread.
- **Remove obsolete fields completely.** Find and remove every obsolete read and
  write site in the same change, including tests and serialisation paths.

## Errors and Diagnostics

- **Handle specific exceptions.** Add context, recover meaningfully or re-raise.
  Never swallow a failure.
- **Broad catches exist only to continue safely.** Log a warning with exception
  details before continuing. `except Exception: pass`, unlogged broad catches
  and `# noqa: BLE001` are forbidden. Suppression names a specific exception,
  never `Exception`.
- **Use explicit runtime checks.** Do not use `assert` for input validation,
  type narrowing or production guarantees; Python can remove it under `-O`.
  Restructure the code or raise explicitly. Test assertions are appropriate.
- **Describe observations, not invented causes.** A timeout, a 401 response and
  a malformed response are different failures. A successful response with no
  usable content also needs an honest explanation.
- **Show useful, safe evidence.** Give users the relevant status or missing-field
  description and a recovery action where available. Detailed diagnostics belong
  on an operator surface. Redact secrets everywhere, including operator logs;
  public messages also omit personal data and private installation details.
- **Keep explanations grounded.** Label uncertain causes as possibilities.
  Friendly wording supplements evidence; "Unknown error" is a last resort when
  no useful signal exists. These rules cover the page, setup notes, CLI and logs.

## Readable Code

- **Respect both complexity limits:** cognitive complexity at most 15 and
  cyclomatic complexity at most 10 per function. Extract cohesive operations or
  use guard clauses; do not game the metrics by inlining. Extra branches do not
  justify an exception.
- **Keep classes cohesive.** A Python class under `src/` has at most 30 directly
  defined methods. Python files over 700 lines receive a warning, not a failure;
  size alone does not require splitting a cohesive file.
- **No nested ternaries.** Python single-line ternaries may return only literals
  or variable lookups, not calls or complex expressions. JavaScript permits
  single, non-nested ternaries.
- **Use modern JavaScript.** Use `const` where possible and `let` when reassignment
  is needed, never `var`; use strict equality.
- **Write comments about contracts.** State what code does and guarantees,
  impersonally. No first person, temporal work narration or links to private
  notes and chats. Rationale belongs in public specs or decision records.
- **Keep file headers short.** State the file's job, promises and relevant traps;
  reference an existing contract instead of restating it. `TODO` and `FIXME` may
  identify unfinished work. A deliberate simplification may use `NOTE:` to name
  its limitation and upgrade path.

## External Text and Comparisons

- **Decode according to format.** Parse JSON escapes as JSON and HTML entities
  as HTML. Do not decode escapes that the input's format does not define, or
  decode already-parsed text again.
- **Normalise for the comparison's purpose.** For semantic matching, apply the
  same defined whitespace and Unicode rules to both sides. Remove format
  characters only when the format or matching contract treats them as ignorable;
  do not indiscriminately strip invisible characters.
- **Keep identity checks protocol-defined.** Tokens, paths and allowlist entries
  use their defined canonical form, never fuzzy semantic matching.
- **Document failure policy beside the check or in its contract.** Choose open
  or closed according to the risk and the spec, not a universal default. Preserve
  Matinee's specified handling of unchecked content warnings; an unchecked film
  must never be described as verified clear.
- **Explain consequential mismatches.** When a comparison changes what a person
  sees, report what was compared and what did not match, using safe diagnostics.

## Interfaces and DOM Safety

- **Insert untrusted content as text.** Use `textContent`, `createTextNode` or
  helpers that build nodes that way. Treat user input and every API response
  field as untrusted. Never assign `innerHTML` or `outerHTML`, or call
  `insertAdjacentHTML`; escaping is not an exception to Matinee's ban.
- **Make controls and status obvious.** Controls look interactive, sit near what
  they affect and show immediate feedback. Display busy, ready and connection
  states; do not imply completion while work is pending.
- **Keep navigation predictable.** Use consistent controls and plain language.
  Show state instead of requiring memory. Make back, cancel, leave and undo
  obvious where applicable; prevent mistakes and offer recovery.
- **Use clear hierarchy and concise copy.** Every element earns its place.
  Matinee's theatrical styling follows `DESIGN_STANDARDS.md` without obscuring
  what a control does.
- **Meet the accessibility floor.** Keyboard operation, visible focus,
  appropriate image alternatives and WCAG 2.1 AA contrast are required.
- **Render and inspect changed surfaces.** Check phone and desktop widths,
  including bright posters behind text, as `DESIGN_STANDARDS.md` specifies.
  Matinee is dark-only. If rendering is unavailable, report `UNVERIFIED` and
  name the surfaces and interactions not checked.

## Shared Values

- **Give shared behaviour one source in code.** On its second use, move a repeated
  timeout, threshold, spacing value or motion setting into a named constant,
  token or settings default. Both consumers use it; a one-off needs no registry.
- **Document the contract and its source.** Standards state important constraints
  and identify their implementation source instead of duplicating implementation
  values. Rationale belongs with the public decision or spec.
- **Update consumers together.** Change all affected consumers and contracts in
  the same repository change. Track coordinated changes across repositories
  separately until complete.

## External Services

- **Use one client per service.** Centralise connections, limits, retries and
  caching. Jellyfin and Plex access remains read-only; data-source restrictions
  and required notices in `AGENTS.md` also bind.
- **Respect provider limits with margin.** Read quota information when available.
  Add an installation-wide cap on request volume or concurrency appropriate to
  the service, using a named setting or constant. Per-user limits alone do not
  prevent a runaway client.
- **Back off together.** A 429 or 503 pauses requests to that service until its
  valid `Retry-After` expires, or uses bounded exponential backoff when absent.
  Coordinate the hold across callers; never retry in a tight loop.
- **Bound every request.** Use timeouts and bounded retries. A slow or unavailable
  service degrades the feature according to the spec and explains the limitation.
- **Cache within the terms.** Reuse permitted stable results, including misses,
  only for the permitted duration. Never prefetch or retain data the source forbids.
- **Identify Matinee where supported.** Send an application-identifying User-Agent
  when the platform permits it; browsers need not override theirs.

## Verification

Run `./bootstrap.sh` once to install development tools, then `./check.sh` before
calling a repository change complete. Do not bypass pre-commit hooks. Update
`docs/spec/` in the same change as any behaviour change.

| Rule | Automated enforcement |
|---|---|
| Python formatting, lint and cyclomatic complexity ≤ 10 | Ruff, configured in `pyproject.toml` |
| Python cognitive complexity ≤ 15 | complexipy on `src/`, `tools/`, `scripts/` |
| Python nested ternaries | `scripts/check_nested_ternaries.py` |
| Python class methods ≤ 30 in `src/`; file-size warnings > 700 lines | `scripts/check_file_size.py` |
| No `# noqa: BLE001` | `check.sh` scans `src/`, `tools/`, `scripts/`, `tests/` |
| Page JavaScript cyclomatic complexity ≤ 10, nested ternaries, equality, declarations, `innerHTML`/`outerHTML` | `eslint.config.js` |
| Python static typing | Strict mypy, configured in `pyproject.toml` |
| Behaviour and regression coverage | Python and JavaScript tests run by `check.sh` |

Review covers rules beyond these gates, including JavaScript cognitive complexity,
Python ternary result restrictions, `insertAdjacentHTML`, diagnostic privacy and
visual accessibility. A passing gate does not prove every rule was checked.
Report checks that failed or did not run; never present them as passing.
