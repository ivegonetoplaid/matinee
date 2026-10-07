---
title: Matinee — Design Standards
purpose: The visual and copy laws every Matinee surface holds to — colour, type, the two control families, the scrim and the bands, where Matinee speaks, and the copy.
status: Binding for every surface under `src/matinee/web/static/`. Section 1 says what to do when the code disagrees with a rule here.
updated: 2026-10-07
---

# Matinee — Design Standards

Binding whenever you build or change a surface of Matinee, on the same footing
as `CODING_STANDARDS.md`. A violation is a defect to fix, not a difference of
taste.

`CODING_STANDARDS.md` states the usability and accessibility floor: visible
focus, keyboard reach, WCAG 2.1 AA contrast. This document does not repeat it.
It states what is specific to Matinee.

This file holds the rules that hold on every screen; a decision about one
screen's wording or placement goes to the page spec. The `:root` block of
`src/matinee/web/static/css/matinee.css` is this file's one transcription for
the browser. Where this file and the stylesheet disagree, this file wins.

---

## 1. These rules are law, and how to disagree with one

When the code strongly disagrees with a rule here, that is information about
the rule. Do not break it silently, do not contort a screen to satisfy it, and
do not edit the rule to match what got built. Build the thing the way it wants
to be built, then raise the conflict as an issue on the code host, naming the
rule, what the code wanted, and why. If the code was right, amend this file. If
the rule was right, fix the code.

---

## 2. What Matinee looks like, and what it must not look like

- **A theatre, not an app.** A marquee, a poster wall, letter-board placards,
  and a voice that speaks in large condensed type. Nothing looks like a
  software dashboard: no filled coloured pills, no cards with drop shadows, no
  toggle switches.
- **Dark only.** One theme on the page base `#07080d`. There is no light theme.
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

| Token | Value | Job |
|---|---|---|
| `--base` | `#07080d` | The page, the bands, the scrims |
| `--text` | `#efe9dc` | Cream: Matinee's second sentence, body text, cream actions' words |
| `--dim` | cream at 66 % | Quiet text inside a band only; disabled controls |
| `--gold` | `#f2b33d` | Matinee's first sentence, the wordmark, gold actions' edge |
| `--velvet` | `#e0566b` | Rose: rose actions' edge, "Delete profile" |
| `--petrol` | `#3B7C8C` | Petrol actions' edge |
| `--strip` | `#f4efe2` | A letterbox's glass toward the bezel, on hover; the lit strip's letter board |
| `--strip-ink` | `#121212` | A letterbox's words |
| `--strip-edge` | `#2a2622` | A letterbox's bezel, at its middle |
| `--strip-hi` | `#fffdf6` | A letterbox's glass where the backlight is brightest |
| `--strip-lo` | `#e4d9c2` | A letterbox's glass toward the bezel |
| `--edge-hi` | `#5a5046` | A letterbox's bezel, its lit top |
| `--edge-lo` | `#120f0c` | A letterbox's bezel, its shaded foot |
| `--action` | `#161926` | An action's body, opaque |
| `--gold-words` | `#f6ca77` | A gold action's words; replaces `--gold-hover` |
| `--rose-words` | `#e98997` | A rose action's words |
| `--petrol-words` | `#5FA3B3` | A petrol action's words |
| `--cream-edge` | `#a39e93` | A cream action's edge |
| `--shade` | `--base` at 92 % | Scrims and bands |
| `--black` | `#000` | Drop shadows and a letterbox's ruled lines |
| `--white` | `#fff` | A letterbox's inner light; a field's edge |
| `--glow` | `#ffecbe` | A letterbox's glow |
| `--warm` | `#ffd68c` | The resting poster's ring |
| `--mark` | `#151827` | A profile's mark |
| `--menu` | `#12141f` | The profile menu |
| `--panel` | `#0e101a` | The profile panels |
| `--about-panel` | `#090a10` | About's panel |

A shade of a colour is its token mixed toward transparent
(`color-mix(in srgb, var(--gold) 45%, transparent)`), never a value written again.
`--chip`, the pills' see-through body, goes with the pills. Add a colour for a
control, a scrim, a band or text only through a new token here and in the
stylesheet's `:root`; such a colour written straight into a rule is a defect.
The marquee, the door and the wall's artwork keep their own colours. The marquee is
the drawing in `static/marquee/`, Matinee's mark, and nothing glows behind it.

### 3.2 One job per colour

On a control or a line of text, gold means two things only: the first part
Matinee speaks, and carry on. Gold is also the theatre's dressing: the
wordmark, the marquee, About's headings, a profile's initials, a field's
caret, bare links and the keyboard focus ring. Rose means turn something down or take it
away. Petrol means leave Matinee. Cream is the rest of what Matinee speaks, and
a neutral utility. Dim is for quiet text inside a band and for disabled
controls, never for a control a viewer is meant to use.

### 3.3 Contrast

Measured against the action body `#161926`, every action's words clear WCAG's
4.5 : 1 for normal text (section 5.2 gives the figures). A letterbox's words
measure 13.4 : 1 on the darkest of its glass (`--strip-lo`) and 18.4 : 1 on the
brightest. Text on the poster wall reaches its contrast only
through a scrim (section 6.1); a contrast that holds only over a dark poster
does not count.

---

## 4. Type

### 4.1 Two faces

| Face | Weight | Used for |
|---|---|---|
| Big Shoulders Display | 800 | Matinee's lines, the wordmark, the marquee, letterbox words, profile names on the tiles and in the top bar |
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

Letterboxes carry every choice: the answers to Matinee's questions, the doors
and kinds, the profile-making answers, the trigger topics, and the answers to
"Delete <name>?". "Yes, delete it" keeps its rose words. Inside the profile
menu's panels ("Delete <name>?" and "Change avatar") a letterbox has no glow at
rest and glows on hover.

A letterbox that toggles, as a trigger topic does, shows a check mark before
its words when chosen. Its face, glow and size do not change.

The trigger picker's topics stand in two aligned columns on a desktop and one
column on a phone. In a row of two, both take the height of the taller. The
topic list scrolls in its own box under its search field.

### 5.2 Actions

A rounded rectangle: 10 px corners, the opaque `--action` body, a 1.5 px edge in
its accent, and its words, and any icon, in its accent's words colour. The body
is never filled with the accent. At least 44 px tall.

| Accent | Means | Edge | Words | Words on the body |
|---|---|---|---|---|
| Gold | Carry on through Matinee | `#f2b33d` | `#f6ca77` | 11.4 : 1 |
| Rose | Turn something down or take it away | `#e0566b` | `#e98997` | 7.1 : 1 |
| Petrol | Leave Matinee | `#3B7C8C` | `#5FA3B3` | 6.1 : 1 |
| Cream | A neutral utility | `#a39e93` | `#efe9dc` | 14.5 : 1 |

On hover the edge takes the words' colour. Keyboard focus shows a 2 px outline
in the words' colour, 2 px outside the edge. A disabled action stands at 45 per
cent opacity. A petrol action's words always end with ↗.

Every action and its accent:

| Action | Accent |
|---|---|
| "Find me something to watch" (centred, at the standard size) | gold |
| "Continue" (the name step) | gold |
| "Save and continue", "Save my list" | gold |
| "Just pick one!" (the questions) | gold |
| "Roll again" | gold |
| "Just show me what you picked" | gold |
| "Save" (a note) | gold |
| "Not that one" | rose |
| "More on Seerr ↗" | petrol |
| "Read about these on DoesTheDogDie ↗" | petrol |
| "Look it up on DoesTheDogDie ↗" | petrol |
| "Start over" | cream |
| "Back" (a phone's way back, in the trail's place) | cream |
| "Never mind", "Never mind, show me everything", "Never mind, keep my list", "That's not me" | cream |
| "Try again" (a problem screen and the topic list) | cream |
| "Something wrong with this pick?" | cream |
| The turned-away pick's reveal button | cream |
| "Back" (About) | cream |

A new action takes the accent its meaning names. If none fits, raise it under
section 1; do not invent a fifth.

### 5.3 Links

Everything a viewer uses over the poster wall is a letterbox or an action. A bare
text link stands only in the foot band: the credit line, its "About",
DoesTheDogDie's credit and the trail's crumbs. About's own prose keeps its
links, and the wordmark is the brand's link.

On a phone the trail and the TMDB credit line show on no screen; the About page
carries TMDB's logo and notice. A question screen past the first shows "Back"
and "Start over", actions at the standard size, centred in the foot band where a
desktop shows the trail; where "Back" would lead to the walk's first screen,
only "Start over" shows. The pick shows "Back" before "Start over" among its
actions.

"Powered by DoesTheDogDie.com" stands in the foot band of every screen that
shows DoesTheDogDie's data.

An action that goes to another address is an `<a>` styled as an action, never a
`<button>`. Every link that leaves Matinee opens in a new tab with
`rel="noopener noreferrer"`.

### 5.4 Everything else

The profile menu's rows ("Edit my list", "Change avatar", "Switch profiles",
"Delete profile") are plain menu rows; "Delete profile" is set in rose. Pictures
that answer a question, the pails and the avatars, stay pictures. The locked
door's eye is part of the door. The wordmark is a link styled as the wordmark.

---

## 6. Text on the poster wall

### 6.1 The scrim

Every piece of text set on the poster wall stands on a scrim: a feathered dark
patch with no visible edge, the page base at no less than 72 per cent behind the
text, fading to nothing at least 32 px beyond the text's block. That covers Matinee's lines,
notes, counts, status lines and footnotes. Text inside a band, on a letterbox,
on an action or in a panel needs none. The darkness holds across the text's
whole block, corners included. The locked door's greeting, on subway tile rather
than the wall, shows the look.

### 6.2 Size and colour

Text on the wall is at least 16 px and set in cream or gold. Dim text, and text
from 11 to 15 px, stands only inside a band.

### 6.3 The bands

Every screen over the poster wall has a dark band at the top and at the foot.
Each is the page base at 92 per cent behind its bar, the top bar with the
wordmark and the viewer, the foot with the credit line (on a phone, its way back
and DoesTheDogDie's credit), and feathers to nothing
into the wall over 96 px on a desktop and 48 px on a phone, with no visible
edge. On the door's screens, the dark fade behind the marquee is the top band,
at its own depth. The locked door stands on subway tile and has no bands. About
keeps its own panel, with the bands beneath it.

---

## 7. Where Matinee speaks

Matinee speaks from one place on each screen, and its choices stand in one place
beneath it. Nothing re-centres while a line types or the choices appear. The
page spec (`docs/spec/matinee.md`, section 12) gives the measurements.

| Screen | Desktop | Phone |
|---|---|---|
| The locked door | Beside the door, to its left; between the marquee and the door under 1000 px wide | Between the marquee and the door |
| The front door and making a profile | A centred column under the marquee, the line left-aligned at its top, tiles or letterboxes beneath | The line under the marquee; letterboxes at the foot of the screen |
| The trigger picker | The left column's top, its explanation and the save actions beneath; the topics in the right column, with the DoesTheDogDie action under them | Stacked under the marquee's lit strip: the line, the explanation, the topics, the actions |
| The questions | The line hangs from the top, three lines reserved, letterboxes beneath it | The line hangs from the top; letterboxes at the foot of the screen |
| The pick | The left column's top: the line, then the actions in one row, then the note | The foot of the screen, which never scrolls: the line, `Not that one` and "More on Seerr ↗", then "Back" and `Start over`, then the note, then DoesTheDogDie's credit line where it has a key |

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

**The tests check mechanically:**

- every colour on a control, a scrim, a band or text comes from a `:root`
  token;
- no control uses the pill shape (a 999 px radius) or a filled accent body;
- every action is one of the four accents, and every petrol action's words end
  with ↗;
- no `<a>` or text button outside the foot band, About's prose and the
  wordmark is styled as a bare link;
- every external `<a>` opens in a new tab with `rel="noopener noreferrer"`;
- the letterbox and action sizes match section 4.2.

**A visual review judges,** on a render at 390 px and at 1440 px wide, over a
bright stretch of wall:

- every piece of wall text stands on a scrim, reads clearly and is at least
  16 px;
- both bands frame the screen with no visible edge;
- Matinee speaks from the place section 7 names;
- one bright thing at a time.

Render it and look at it before calling a surface done.
