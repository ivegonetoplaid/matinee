# Matinee — Coding Standards

These are the non-negotiable laws for every line of code in Matinee.
`DESIGN_STANDARDS.md` stands beside them for every surface a viewer sees.
`./check.sh` enforces the mechanical parts; the rest is on the author.

## 1. Data Boundaries & Typing
- **Domain Models over Dicts:** Inter-module boundaries must use typed models (e.g., dataclasses, Pydantic). Never pass raw dictionaries across boundaries.
- **Explicit Inputs:** Validate external inputs at the absolute edge of the system.
- **Opaque Payloads:** Do not pass platform-specific raw payloads through core logic unless explicitly wrapped or marked as opaque.

## 2. Dependency Rules
- **Dependency Injection:** Pass collaborators in explicitly. Do not hide dependencies in globals or singletons.
- **Clean Core:** Core logic must never reach directly into adapters, transports, or environment state (`os.environ`).
- **Sync/Async:** Keep synchronous and asynchronous boundaries strictly separated and explicit.

## 3. Error Handling
- **No Silent Failures:** Never swallow exceptions. Catch specific exceptions, add domain context, and either handle them meaningfully or re-raise.
- **Useful Telemetry:** Error messages must be safe to log (no secrets) and contain enough context to reconstruct the failure state.

## 4. Forbidden Patterns
- Hidden side effects (mutating arguments, writing to disk without returning a result).
- Mixed transport and domain logic.
- Mutable global state.
- When removing a field from a model, find every read and write site of that field across the codebase and delete them in the same change.
- Using `assert` for type narrowing or runtime validation. Restructure the code so the type checker can prove correctness, or use `if ... raise` for checks that must survive `python -O`.

## 5. Complexity

Two metrics gate function complexity, each covering the other's blind spot.
Cyclomatic complexity counts branches but charges flat dispatch and deep
nesting alike; cognitive complexity tracks how hard code is to *read* —
discounting flat structures humans skim, penalizing nesting — but over-charges
idioms like per-line `x or default()` wiring. A function must satisfy both.

- **Cognitive complexity ≤ 15 per function** (primary gate). Enforced by
  `complexipy` (`max-complexity-allowed = 15` in `pyproject.toml`). When a
  function exceeds it, the cause is almost always nesting — extract the inner
  block or invert a guard, do not flatten by inlining.
- **Cyclomatic complexity ≤ 10 per function** (breadth backstop). Enforced by
  ruff `C901` with `max-complexity = 10`, and by ESLint `complexity` for the
  page scripts. This catches functions that are *wide* (many sequential
  branches) rather than deep.
- No exceptions for "it's just a few more branches" — decompose instead.
- **Class size.** A class under `src/` holds at most 30 methods of its own, a
  hard gate in `scripts/check_file_size.py`. A file over 700 lines draws a
  warning, never a failure: a large but cohesive file is not forced apart.

## 6. No Silent Exception Handling

- `except Exception: pass` and any broad catch with no logging are banned outright.
- `# noqa: BLE001` is prohibited — `check.sh` has a grep gate that fails the build if it appears anywhere in `src/`, `tools/`, `scripts/` or `tests/`.
- If a function must continue after an error (stream safety): `logger.warning("...", exc_info=True)`, then continue.
- If cleanup must suppress a specific error: use `contextlib.suppress(SpecificError)` — never bare `Exception`.
- Ruff `BLE001` is enabled and the `# noqa: BLE001` escape hatch is banned at the gate level.

## 7. Ternary Rules

- **No nested ternaries** anywhere (Python or JS). Enforced by `scripts/check_nested_ternaries.py` (Python) and ESLint `no-nested-ternary` as an error (JS) in `check.sh`.
- **Python only:** Simple single-line ternaries are permitted only when the result is a literal or a variable lookup — never a function call or complex expression.
- **JavaScript:** Single (non-nested) ternaries are permitted. Nested ternaries are not — use `if/else` or a block-body `return`.

## 8. JavaScript Standards

- All user-controlled strings entering the DOM are **inserted as text**: `textContent`, `createTextNode`, or a helper that builds nodes that way. Treat every API response field as untrusted.
- Never assign `innerHTML` or `outerHTML`, and never call `insertAdjacentHTML`. ESLint forbids the first two in the page scripts.
- Use `const` and `let`, never `var`.
- XSS safety is non-negotiable.

## 9. Typed Returns at Module Boundaries

- Functions returning data across module boundaries must return typed models (dataclasses or Pydantic), not raw dicts.
- The Pydantic model is the return type of the function itself, not just the FastAPI route decorator.
- Example: a library reader's `films()` declares and returns `list[LibraryFilm]`, not `list[dict]`.

## 9a. Comparing Text We Did Not Write

Any comparison, match, or extraction over text the program did not author — an
API response, a media server's title, a file a user supplied, a scraped page —
crosses a boundary where the program does not control how characters are
spelled. Two strings meaning the same thing are routinely spelled differently:
escaped non-ASCII (the six characters `°F` against the two characters
`°F`), HTML entities, smart quotes, a byte-order mark, a re-wrap. Three rules,
and any one of them alone catches the failure.

- **Canonicalize both sides before comparing.** Never compare a payload as
  stored against text that has been through another hand. Normalize whitespace,
  turn escapes into the characters they denote, and drop invisible format
  characters — on both sides, by rule rather than by a list of the cases seen so
  far.
- **State which way the comparison fails when it cannot be trusted.** Where a
  comparison of this kind gates anything, write the direction down beside the
  check, in a comment or in the contract the check implements. Default to
  failing *open*: normalization can never be proven total over an alphabet the
  payload chooses, so a check that quietly fails closed refuses correct work on
  inputs nobody anticipated. Fail closed only where a stated requirement says
  the risk runs the other way, and say which requirement.
- **Make it visible when it fires.** A comparison that changes what a person
  sees is reported to them, naming what was compared and what did not match.
  Section 10 governs the wording: state the observation, never a cause invented
  to fill the gap.

## 10. Honest Failure Messages

User-facing failure text must describe what was actually observed. Never
invent a cause-and-effect explanation to fill a gap in our knowledge.

- **Don't fabricate causes.** Saying "the server is down" when we observed a
  401, a timeout, or a response we could not parse is a lie — the server
  answered *something*, just not what we expected.
- **Truthful headlines.** A failure message states an observation
  ("TMDB refused the key"), not a guess ("TMDB is having problems").
- **Show the evidence.** When a payload is unexpected, surface the relevant
  parts of its raw shape — the status, the fields that were missing — so the
  person running Matinee can see what we saw. Diagnostic detail belongs in the
  failure surface, not buried in logs. Never surface a key or a secret.
- **Generic placeholders are a last resort.** "Unknown error" is only honest
  when the payload truly had no usable signal. If there is any signal, render
  it.
- **Fancy on top, never instead of.** A friendly one-liner that maps
  a known error pattern to a likely cause is welcome — but it layers
  on top of the raw evidence, it does not replace it.

This rule binds every surface a person sees: the page, the setup note, logs
and CLI output. It applies to error paths (HTTP failure, exception text) and to
"success-with-no-content" paths equally.

## 11. Design & Usability (binding whenever building an interface)

Whenever the work has a user-facing surface — a web page, a CLI, a setup
note — usability is a correctness property, not a coat of paint. A confusing
interface fails the user the same way a swallowed exception fails the person
running the software. Follow these three sources whenever building or
iterating any surface; they are law, not aspiration.

### Norman — the machine explains itself

*The Design of Everyday Things.* A control should tell you what it does, and
what it just did.

- **Affordance and signifier.** Every interactive thing looks interactive, and
  a visible cue says how to use it. A button reads as a button; a draggable
  control looks draggable. No mystery-meat icons.
- **Feedback.** Every action gets an immediate, visible response. The state
  flips at once; never leave the user wondering whether the action landed.
- **Mapping.** Controls map naturally to their effect. A progress bar fills as
  the thing advances; the control nearest an element acts on that element.
- **Constraints and a clear conceptual model.** Make the wrong action hard and
  the right one obvious. The user's mental model should match how the thing
  actually behaves.

### Nielsen — the usability heuristics

The ten heuristics, kept to the ones that bite most:

- **Visibility of system status.** Always show what is happening: busy or ready,
  how far along, connected or not.
- **Match the real world.** Plain language and familiar patterns, never system
  jargon.
- **User control and freedom.** Undo, cancel, back, and leave are always one
  obvious action away. No traps.
- **Consistency and standards.** One visual language; the same thing looks and
  behaves the same everywhere. Follow platform convention instead of inventing.
- **Error prevention and graceful recovery.** Design so the user cannot easily
  get lost or stuck. When something fails, say so in plain words and offer the
  way out. (Pairs with §3 and §10.)
- **Recognition over recall.** The user never has to remember state or how a
  control works; the interface shows it.
- **Aesthetic and minimal design.** Every element earns its place. Clutter is a
  usability bug, not only an aesthetic one.

### Krug — Don't Make Me Think

*Don't Make Me Think.* The operative laws:

- **Self-evident beats clever.** A user should grasp what a thing is and how to
  use it without a beat of thought. If it needs a label to explain a label,
  redesign it.
- **People scan, they don't read.** Clear visual hierarchy, obvious headings,
  scannable structure so the eye finds the path on its own.
- **Omit needless words**, then omit half of what is left. This applies to UI
  copy and chrome.
- **Obvious is a feature.** People satisfice — they take the first reasonable
  option. Make the reasonable option unmissable.

### How this gets enforced

- **`DESIGN_STANDARDS.md` owns Matinee's look and copy**; these heuristics own
  usability. Both bind.
- **Render it and look** before calling it done: phone and desktop widths.
  Rendered correctness is the author's job. If you could not actually render
  it, report `UNVERIFIED` and name what you could not check.
- **Accessibility is usability.** Keyboard operability, visible focus, meaningful
  `alt` text, and WCAG 2.1 AA contrast are part of "self-evident and usable," not
  a separate checklist.

## 12. Comments and Docstrings

- Docstrings and comments state what the code does and guarantees, impersonally.
- No first person, and no narration of time (`currently`, `for now`, `until X
  lands`). Code describes what is, not what was or will be.
- No pointers to private notes, chat threads or decision logs. Rationale lives
  in the spec or the record of the decision, not in source.
- Explicit `TODO` and `FIXME` markers are fine; work-state disguised as a
  description is not.
- A deliberate simplification may carry a `NOTE:` naming its ceiling and the
  way to lift it.

## 13. The First Use Writes the Standard

A constant that more than one place will need is settled once, in the standards
document that governs it, by whoever needs it first. Nobody discovers it a second
time.

This binds any value or behaviour that will repeat: a gesture's timing, a
motion's duration and easing, a spacing step, a retry backoff, a timeout, a
threshold. The first implementation does three things rather than one:

- **Choose the value by building with it**, because the right number is found by
  trying it, not by reasoning about it.
- **Write it into the standards** as the rule for every later use, naming the
  value and what it applies to.
- **Read it from there**, so the standard is the source and the code is a
  consumer. A value the standards name and the code repeats has already begun to
  drift.

**When a standard changes, every user of it changes in the same commit.** A
standards document that disagrees with the code it governs is worse than none: it
teaches a reader something false and it costs the next person the search that this
rule exists to prevent.

**The standard records the setting, never the argument for it.** Rationale lives
with the decision that settled it. The standards document says what to do.

A one-off with no second caller is not a standard. Wait for the second use; that
is when the shape is known.

## 14. Services We Do Not Run

A service someone else runs is not ours to disrupt. When unsure, choose what costs
them less, even where it costs us a feature.

- **One door.** Every request to an outside service goes through one client
  module. Nothing else opens a connection to it.
- **Under their published limits, with margin.** Pace below the documented rate.
  Where the service reports what remains (rate-limit headers), read it and stop
  before it runs out.
- **A global ceiling of our own.** Beyond any per-user or per-device limit, the
  client caps its own total requests per hour, so a runaway loop, a bug or a crowd
  of visitors cannot become the service's problem. The ceiling is a named constant,
  or a setting where the application has settings.
- **Back off when told.** A 429 or 503 stops every request to that service until
  its `Retry-After` has passed, or for an exponential backoff when none is given.
  Never retry in a tight loop.
- **Time out, then degrade.** Every request has a timeout. When the service is
  slow, refusing or out of allowance, the feature degrades and says so (§10); it
  never blocks the user or retries harder.
- **Ask once, not twice.** Where the service's terms allow a cache, remember what
  does not change (an id mapping, a "not found") for as long as the terms permit,
  rather than asking again. Never keep more than the terms allow.
- **Say who we are.** Every request carries a user agent naming the application.
