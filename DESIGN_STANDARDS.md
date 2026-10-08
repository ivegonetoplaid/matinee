---
title: Matinee — Design Standards
purpose: The visual and copy laws every Matinee surface holds to — colour, type, the two control families, the scrim and the bands, where Matinee speaks, and the copy.
status: Binding for every surface under `src/matinee/web/static/`. Section 1 says what to do when the code disagrees with a rule here.
updated: 2026-10-08
---

# Matinee — Design Standards

Binding whenever you build or change a surface of Matinee, on the same footing
as `CODING_STANDARDS.md`. A violation is a defect to fix, not a difference of
taste.

`CODING_STANDARDS.md` states the usability and accessibility floor: visible
focus, keyboard reach, WCAG 2.1 AA contrast. This document does not repeat it.
It states what is specific to Matinee.

This file owns shared design requirements and the meaning of its tokens.
[The page specification](docs/spec/matinee.md#12-the-page) owns screen wording,
action assignments, placement and behaviour. The `:root` block and component
rules in `src/matinee/web/static/css/matinee.css` define reusable token values.
Do not maintain a second palette in Markdown. A value change must preserve the
requirements here, or include an explicitly reviewed change to the contract.

---

## 1. Authority and exceptions

Follow the design contract; do not silently override it or contort a screen to
hide a conflict. When a requirement and implementation disagree, identify the
rule, show the evidence and propose a correction or a scoped exception in the
issue or PR. Implementation is evidence, not authority to waive a rule.
An amendment or exception needs maintainer approval and a recorded reason
before it becomes part of the accepted design. A prototype may demonstrate an
alternative for review, but must identify the requirement it departs from.

---

## 2. What Matinee looks like, and what it must not look like

- **A theatre, not an app.** A marquee, a poster wall, letter-board placards,
  and a voice that speaks in large condensed type. Nothing looks like a
  software dashboard: no filled coloured pills, no cards with drop shadows, no
  toggle switches.
- **Dark only.** One theme on the page base `--base`. There is no light theme.
- **One bright thing at a time.** The eye goes to Matinee's line, then to the
  choices under it. Nothing else competes.
- **The poster wall is the stage.** It is never blurred and never dimmed
  between answers. What stands on it follows section 6.
- **Two screens.** A phone is a viewport 600 px wide or less. Everything else
  is a desktop, and the page spec names the few screens with an extra step.
  There is no TV layout.

---

## 3. Colour

### 3.1 The tokens

The stylesheet is the source for token values; this table states their roles.
Component-local aliases such as `--words` and `--thread` resolve to these palette
tokens. Use the token appropriate to the role, not a hard-coded colour.

| Token | Role |
|---|---|
| `--base` | Page base and the source colour for scrims and bands |
| `--text` | Cream body text and the second part of Matinee's line |
| `--dim` | Quiet text inside bands and muted chrome; never an active control's label |
| `--gold` | Matinee's first sentence, theatre accents and general focus rings |
| `--velvet` | Base rose colour, including destructive menu text and warning strips |
| `--petrol` | Base petrol palette colour; action text uses `--petrol-vivid` |
| `--strip`, `--strip-hi`, `--strip-lo` | Letterbox glass and the marquee's letter board |
| `--strip-ink` | Letterbox words |
| `--strip-edge`, `--edge-hi`, `--edge-lo` | Letterbox bezel |
| `--enamel`, `--enamel-rim` | Action body gradient and neutral rim |
| `--gold-vivid`, `--rose-vivid`, `--petrol-vivid`, `--cream-vivid` | Action text and accent threads |
| `--cream-thread` | Cream action's thread |
| `--action` | Supporting form-field backgrounds; not the enamel action body |
| `--gold-words` | Link hover and supporting highlights; not gold action text |
| `--shade` | Scrims and bands, mixed from `--base` |
| `--black`, `--white` | Shadows, ruled lines, highlights and field edges |
| `--glow` | Letterbox glow |
| `--warm` | Resting poster ring |
| `--mark`, `--menu`, `--panel`, `--about-panel` | Profile mark, menu and panel backgrounds |

A shade is its token mixed toward transparent
(`color-mix(in srgb, var(--gold) 45%, transparent)`), never a repeated literal.
Add a new palette colour through `:root` and document its role here in the same
change. The marquee, door and poster artwork keep their own colours. The
marquee is the drawing in `static/marquee/`, Matinee's mark, with no glow behind it.

### 3.2 One job per colour

On a control or a line of text, gold means two things only: the first part
Matinee speaks, and carry on. Gold is also the theatre's dressing: the
corner mark, the marquee, About's headings, a profile's initials, a field's
caret, bare links and the keyboard focus ring. Rose means turn something down or take it
away. Petrol means leave Matinee. Cream is the rest of what Matinee speaks, and
a neutral utility. Dim is for quiet text inside a band and for disabled
controls, never for a control a viewer is meant to use.

### 3.3 Contrast

Action text must reach at least 4.5 : 1 contrast against the lightest rendered
part of the enamel body. Letterbox words must reach the same floor against the
darkest part of the glass. Measure
again when either foreground or background changes; a historical ratio does
not validate new colours. Text on the poster wall needs a scrim that maintains
contrast over bright posters, not just a dark example.

---

## 4. Type

### 4.1 Two faces

| Face | Weight | Used for |
|---|---|---|
| Big Shoulders Display | 800 | Matinee's lines, the marquee, letterbox words, profile names on the tiles and in the top bar |
| DM Sans | 400 to 600 | Everything else: body text, notes, counts, action words, fields, About |

Both faces are self-hosted with their OFL licences. A third face is a defect.

### 4.2 Sizes

| What | Desktop | Phone |
|---|---|---|
| A letterbox's words | 24 px | 19 px |
| An action's words | 18 px | 16 px |
| Body text on the poster wall | 16 px at least | 16 px at least |
| Quiet text inside a band | 13 px | 11 px |

A letterbox has one size. No screen shrinks letterboxes to fit more of them;
a long list scrolls instead. Matinee's lines keep the sizes the page spec
gives each screen.

### 4.3 Matinee's lines

A line Matinee speaks has two parts. Gold carries what Matinee says first: its
reply to the last answer on a question screen, or the first sentence of any
other line. Cream carries what follows: a question when Matinee asks, a second
statement when it tells. A line types out; the choices appear once it finishes, except where the
page spec says otherwise (the locked door's slot takes the word at once).

A line Matinee speaks shows no caret, while it types or after. A caret marks a
field a viewer types into, and is gold.

### 4.4 Case

All displayed text is in sentence case. Letterbox words show in capitals
through the stylesheet (`text-transform`), never typed in capitals in the
script.

---

## 5. Controls

Matinee has two families of control. **A letterbox chooses something. An action
does something.** They differ in shape as well as colour.

An action carries the class `action` and one of `gold`, `rose`, `petrol` or
`cream`; a letterbox carries the class `letterbox`. The tests in section 9 find
them by these classes.

### 5.1 Letterboxes

A backlit milk-glass panel in a dark bezel, as on the marquee's letter board:
glass shading from `--strip-lo` at its edges to `--strip-hi` through its middle,
a 3 px bezel (2 px on a phone) shading from `--edge-hi` through `--strip-edge` to
`--edge-lo`, 4 px corners, and a channel rail above and below every row of
words, so a wrapped answer stands between rails at any width. Words in Big
Shoulders Display capitals on a 32 px line (26 px on a phone). A soft cream glow
at rest brightens on hover, as the glass brightens toward `--strip`; pressed, it
sinks 1 px. Keyboard focus shows a 2 px gold outline 2 px outside the bezel.

Letterboxes carry the text choices in Matinee's questions, doors and kinds,
profile-making steps, trigger topics and "Delete <name>?". Picture choices and
report-form fields use the exceptions under Everything else. "Yes, delete it"
keeps its rose words. Inside the profile menu's panels ("Delete <name>?" and
"Change avatar") a letterbox has no glow at
rest and glows on hover.

A letterbox that toggles, as a trigger topic does, shows a check mark before
its words when chosen. Its face, glow and size do not change.

The page specification owns the trigger picker's column layout and scrolling.
A long topic wraps without shrinking the standard letterbox type.

### 5.2 Actions

A black-enamel face, always an HTML control and never a picture: 8 px corners,
the `--enamel` gradient under a very light grain (`static/grain.svg`), a 1 px
black border inside a 1 px neutral rim (`--enamel-rim`), a highlight along the
top edge and a slight inset shadow at the foot. Words and icons use the accent's
vivid colour. The body is never filled with the accent. A single-line face is
40 px tall and grows when its label wraps; the tap target is at least 44 px tall.

| Accent | Meaning | Words | Thread |
|---|---|---|---|
| Gold | Carry on through Matinee | `--gold-vivid` | `--gold-vivid` |
| Rose | Turn something down or take it away | `--rose-vivid` | `--rose-vivid` |
| Petrol | Leave Matinee | `--petrol-vivid` | `--petrol-vivid` |
| Cream | Neutral utility | `--cream-vivid` | `--cream-thread` |

Hovered (where a pointer can hover), keyboard-focused or pressed, a 2 px thread
in the accent's thread colour draws across the face's foot from the left in
0.32 s, inside its corners; under reduced motion it stands at once. The face is
never filled or lit. Pressed, it sinks 1.5 px. Keyboard focus shows a 2 px outline
in the words' colour, 2 px outside the edge. A disabled action stands at 45 per
cent opacity. A petrol action's words always end with ↗.

[The page specification](docs/spec/matinee.md#shared-action-assignments) lists each action's
accent. New actions follow the meanings above; if none fits, propose a contract
change under Authority and exceptions instead of inventing a fifth accent.

### 5.3 Links

Everything a viewer uses over the poster wall is a letterbox or an action. A bare
text link stands only in the foot band: the credit line, its "About",
DoesTheDogDie's credit and the trail's crumbs. About's own prose keeps its
links, and the corner mark is the brand's link.

The page specification owns phone navigation, action order and credit placement.

"Powered by DoesTheDogDie.com" stands in the foot band of every screen that
shows DoesTheDogDie's data.

An action that goes to another address is an `<a>` styled as an action, never a
`<button>`. Every link that leaves Matinee opens in a new tab with
`rel="noopener noreferrer"`.

### 5.4 Everything else

The profile menu's rows ("Edit my list", "Change avatar", "Switch profiles",
"Delete profile") are plain menu rows; "Delete profile" is set in rose. Pictures
that answer a question, the pails and the avatars, stay pictures. The locked
door's eye is part of the door. The wordmark is the corner mark
(`static/marquee/mark-corner.svg`), the marquee's crown over a small lit sign
carrying the name, 40 px tall: a picture inside a link, never text styled as a
mark. About shows the same mark as a picture, not a link. The film-reporting
form uses labelled native radio buttons and checkboxes as the spec describes;
these are form fields, not letterbox choices.

---

## 6. Text on the poster wall

### 6.1 The scrim

Every piece of text set on the poster wall stands on a scrim: a feathered dark
patch with no visible edge, the page base at no less than 72 per cent behind the
text, fading to nothing at least 32 px beyond the text's block. These are
minimum requirements; the page specification describes the current treatment.
That covers Matinee's lines, notes, counts, status lines and footnotes. Text inside a band, on a letterbox,
on an action or in a panel needs none. The darkness holds across the text's
whole block, corners included. The locked door's greeting, on subway tile rather
than the wall, shows the look.

### 6.2 Size and colour

Text on the wall is at least 16 px and set in cream or gold. Dim text, and text
from 11 to 15 px, stands only inside a band.

### 6.3 The bands

Every screen over the poster wall has a dark band at the top and at the foot.
Each is the page base at 92 per cent behind its bar, the top bar with the
corner mark and the viewer, the foot with the credit line (on a phone, its way back
and DoesTheDogDie's credit), and feathers to nothing
into the wall over 96 px on a desktop and 48 px on a phone, with no visible
edge. On the door's screens, the dark fade behind the marquee is the top band,
at its own depth. The locked door stands on subway tile and has no bands. About
keeps its own panel, with the bands beneath it.

---

## 7. Where Matinee speaks

Matinee speaks from one place on each screen, and its choices stand in one place
beneath it. Nothing re-centres while a line types or the choices appear.
[The page specification](docs/spec/matinee.md#screen-composition) owns the desktop and
phone composition for each screen. Distinguish the reporting action beneath the
pick's controls from an unchecked-content warning beneath the film's synopsis.

---

## 8. Copy

- **Short big lines.** Matinee's lines stay short; detail goes in a body-type
  line beneath, on the wall's rules (section 6).
- **Safety copy is gentle.** Copy about a viewer's trigger list names mild
  examples, spiders and needles, never an upsetting one. Its question asks what
  a viewer would rather not see happen on screen.
- **The credits are fixed wording.** TMDB's notice and logo, "Powered by
  DoesTheDogDie.com" wherever its data shows, and the MovieLens credit on About
  are set by the README and the page spec; do not reword them.

---

## 9. Enforcement

**Source checks:** `tests/test_design_standards.py`, run by `./check.sh`, reads
CSS and JavaScript as text. It checks token references, component corners and
bodies, action accents and petrol arrows, permitted bare links, external-link
attributes, and control font sizes. It also checks the control-building helper
and wordmark. It does not compare this Markdown with the stylesheet.

**Browser review:** inspect changed surfaces at 390 px and 1440 px wide, over a
bright stretch of wall. Check readable wall text and scrims, both bands without
visible edges, stable screen composition and one bright thing at a time. Also
check keyboard operation and focus, rendered contrast, wrapped-label tap targets
and reduced motion. Source checks do not verify those browser outcomes.

Keep intended design requirements, token values and spec behaviour consistent.
If browser review cannot run, report `UNVERIFIED` and what remains unchecked.
