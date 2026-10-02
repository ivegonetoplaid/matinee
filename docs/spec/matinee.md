---
purpose: The contract Matinee's first build holds to — the conversation model, the pools and scales, the offline film table, profiles, exclusions, the DoesTheDogDie check, corrections, the web surface, the page, deployment and third-party terms — with a map of where each part lives.
updated: 2026-09-30
governs:
  - src/matinee/
  - tools/
  - data/
  - Dockerfile
  - .dockerignore
---

# Matinee

Matinee is a film picker for a home media library. A viewer answers two or three
questions and is handed one film from the library, presented as tonight's
showing, with `Not that one` to draw again.

This spec was written from the code on 2026-09-26. It has two halves. The
**contract** says what Matinee must do and must refuse. It is authoritative. The
**map** says where each part lives. It is a pointer, never proof. The
[index](README.md) explains how to read the two when they disagree with the
code. Behaviour that is deliberately absent, still open, or short of the
contract is listed under [Known gaps](#known-gaps).

---

# Part 1 — Contract

## 1. Boundaries

1. **Read-only against every media server.** Matinee reads a Jellyfin library
   and never writes to it. Every request the Jellyfin reader makes is an HTTP
   GET. No module other than the library reader calls a media server.
2. **One door to the library.** All media-server access passes through one
   library interface with three reads: the film list, one film's synopsis, and
   one film's poster or backdrop. A second reader, such as Plex, would sit behind
   the same interface. Only the Jellyfin reader exists.
3. **Library mode only.** Matinee offers only films the library holds at the
   moment of the request. A film gone from the library is never offered.
4. **Matinee's own state is its own.** Profiles, device tokens, saved exclusions
   and viewers' notes live in Matinee's store. None of it reaches a media server.
5. **No public API and no viewer CLI.** The HTTP routes serve Matinee's own page
   only. The command-line tools are for whoever runs the installation: the
   nightly rebuild, the tree checker and the reference builder.
6. **The engine is a plain module.** The tree walk imports no web framework and
   reads no request state. The web page and the tree checker call the same
   engine, so they cannot disagree about a pool.

## 2. The conversation

### 2.1 The first question

The poster wall opens by typing "Right this way." and "So, what are we in the
mood for?". When the viewer has a profile, the first line carries the name:
"Right this way, <name>.". Each answer is a door, offered by its plain name.
The answers, their order and the tree or mode each leads to are data in
`data/first_question.json`:

| Answer | Leads to |
|---|---|
| Comedy | `comedy` |
| Action and adventure | `action` |
| Drama | `drama` |
| Thriller | `thriller` |
| Crime | `crime` |
| Horror | `horror` |
| Sci-fi | `scifi` |
| Fantasy | `fantasy` |
| Romance | `romance` |
| Animation | `animation` |
| Westerns | `western` |
| War | `war` |
| For the kids | `kids` |
| Documentaries | `nonfiction` |
| Something to fall asleep to | `fall-asleep` (a mode) |

- An answer is shown only when its tree or mode holds at least one film for this
  viewer, after the viewer's exclusions.
- Every answer must carry a `label`. The engine refuses to load a first question
  whose answer lacks one. The label names the door where a short name is needed,
  such as the note panel. Each door's label is its name.
- Matinee's reply to a door is the opening line of the tree or mode it leads to.
- Stand-up specials are not a door. They are an answer under Comedy (section
  2.3).
- A mode is what the viewer is doing rather than a genre. The viewer is never
  asked to know whether they chose a genre or a mode.

### 2.2 Trees and modes are data

Each genre's questions live in their own file under `data/trees/`. Each mode
lives under `data/modes/`. A file carries the content: its opening line, its
questions, each answer's wording and reply, and the rule each answer filters
on. The engine carries the behaviour. Adding a genre means adding a file.

| File | Pool | Questions, in order |
|---|---|---|
| `trees/horror.json` | horror | flavour (kinds read from the labels; section 2.3); gore (pictures); era (only above 40 films) |
| `trees/comedy.json` | comedy | room (certificate ceilings); kind (labels; the standup specials held apart; section 2.3) |
| `trees/action.json` | action | kind (labels; section 2.3) |
| `trees/thriller.json` | thriller | kind (labels; section 2.3) |
| `trees/crime.json` | crime | kind (labels; section 2.3) |
| `trees/drama.json` | drama | kind (labels; section 2.3) |
| `trees/scifi.json` | scifi | kind (labels; section 2.3) |
| `trees/fantasy.json` | fantasy | kind (labels; section 2.3) |
| `trees/romance.json` | romance | kind (labels; section 2.3) |
| `trees/animation.json` | animation | kind (labels; section 2.3) |
| `trees/western.json` | western | none; it rolls from the whole pool |
| `trees/war.json` | war | kind (labels; section 2.3) |
| `trees/kids.json` | kids | age (labelled bands under certificate ceilings; section 3.2); kind (labels) |
| `trees/nonfiction.json` | nonfiction | none; it rolls from the whole pool |
| `modes/fall-asleep.json` | sleep | none; it rolls from the whole pool |

Loading is strict:

- Question, answer, filter and flavour keys are checked against
  the set the engine reads. A misspelt key fails at load. It never reads as
  absent and silently widens a pool.
- Two tree or mode files with the same name are refused.
- A tree file must name its `pool` and its `opening` line.
- A tree naming a pool no pool rule builds is refused.
- `sequel` may only be `false`. `sort` may only be `rating`. `kids_band` must be
  `little`, `family` or `older`. `treat_as` must name an answer the question has.
- A tree may name one flavour it defines as `apart`; naming a flavour it does not
  define is refused. Every flavour is marked either `labelled` or `specials`,
  and takes nothing else. Only a labelled flavour may be marked
  `always_shown`, and only as `true`.
- An answer may carry `self_destruct`, a whole number of seconds from 1 to 9. Any
  other value is refused. Every answer carrying it, across the trees and modes,
  must speak the same reply, or the trees refuse to load: the self-destructing
  reply is one joke, told by the spies answer behind Thriller and behind Action
  and nowhere else.

### 2.3 Answers are filters

Each answer narrows the pool with the filter its file gives. A filter may use
these signals, and no others:

| Filter key | Keeps |
|---|---|
| `runtime_min`, `runtime_max` | Films at or above, or at or below, a runtime in minutes |
| `rating_min` | Films rated at or above the value (the media server's community rating) |
| `year_min`, `year_max` | Films released in or after, or in or before, a year |
| `spoken_english` | Films whose original language is English |
| `sequel: false` | Films in no TMDB collection |
| `certificate_in` | Films whose certificate is listed; an absent certificate is the empty string |
| `genres_any`, `genre_also` | Films carrying any listed media-server genre |
| `genres_none` | Films carrying none of the listed genres |
| `flavour` | Films in a named flavour the tree defines: a kind read from the labels, or the standup specials |
| `flavour_none` | Films outside a named flavour, plus films also in another flavour of the tree (house pins included) |
| `bands` | Films in any of the listed bands of a named scale (see section 4) |
| `score_at_most`, `score_above` | Films whose named score is at or below, or above, a value |
| `kids_band` | Films the kids tree offers to that age band (section 3.2) |
| `sort: rating` | Nothing is removed; the pick draws from the better-rated half |

**Unknown values are inclusive.** A film whose runtime, rating, year, language,
collection or score is unknown passes a filter on it. A `sequel: false` filter
keeps films with no known collection, so a film whose TMDB facts are unknown
passes it too. A wrongly included film costs one `Not that one`; a wrongly
excluded one is invisible. One signal is the exception:

- A certificate filter keeps only the certificates it lists. Comedy's room
  answers are ceilings: "children present" lists G, TV-G, PG, TV-PG, TV-Y and
  TV-Y7; "grown-ups, technically" adds PG-13 and TV-14; "no witnesses" has no
  certificate filter, so it alone offers films with no usable certificate.

**Flavours.** A flavour is a tree's kind. A flavour marked `labelled` holds the
films the labels file names with it at that tree (section 2.6). A flavour marked
`specials` holds the standup specials (section 3.1). No flavour is matched by
keyword, genome tag or genre. An answer leaving a flavour out keeps every film
that also sits in another flavour of the tree.

**A flavour held apart.** A tree may hold one flavour `apart`. Its films always
sit in the tree's pool, whatever the labels say. No pool the
walk offers holds them until the answer naming the flavour is given, so every
other answer, and `Just pick one!` anywhere in that tree, leaves them out. No
other door's pool holds them either (the checker fails otherwise).

**A small kind is not offered.** An answer offering a labelled kind shows only
when that kind holds at least 30 films of the tree's pool in the library the
server loaded, counted before any answer narrows it. A kind is exempt when it
is marked `always_shown` (horror's found footage and every kids kind), or when another answer of the
same question leaves it out (horror's "anything scary" leaves horror_comedy out, so
hiding horror_comedy would leave its films no answer). The bar changes whether an
answer shows, never which films it holds, so a hidden kind's films stay
reachable through the door's "anything" answer and `Just pick one!`. An answer
that filters on anything but a labelled kind is never held to the bar. The kids
kinds are always shown because the kids kind question has no "anything" answer:
a hidden kind would leave its films no way in.

Horror's flavours are all labelled: supernatural, killers, monsters, slowburn,
horror_comedy and found_footage. A film may sit in two. A film played mainly for
laughs is labelled horror_comedy alone unless its horror is played straight, so
it reaches only the comedy answer. "anything scary" leaves horror_comedy out, so
it keeps every horror film except those labelled horror_comedy and nothing else.
Found footage is a format marker: it may come on top of a film's kinds, or
alone. A horror film
labelled with no kind, or not yet labelled, is reached through "anything scary"
and `Just pick one!`.

Comedy's flavours are labelled, except standup. The labelled kinds are
slapstick, feelgood, cartoon_comedy, dark_comedy, action_comedy, horror_comedy,
teen_comedy and romcom; the answers' words are unchanged from before the labels
named them so. Its horror_comedy kind is the horror tree's, so both trees offer
the same horror comedies. Comedy holds its standup flavour apart: the answer
"just someone funny with a mic." offers only the standup specials, and sits just
above "anything. surprise me.*", which offers every other film. That question's
footnote reads "*stand-up specials have their own answer." The room answers'
certificate ceilings apply to the specials as to any film. A special whose
certificate a ceiling does not list is offered only after "no witnesses.
anything goes.". Where the standup answer
is not shown, the footnote and the asterisk on "anything" are not shown either.
A pick on a special came through Comedy, so it speaks comedy's lines (section
2.7).

Every other genre door asks one question: its kinds, in the order its file
lists them, then "anything", which has no filter. The kinds, all labelled, are:

| Door | Kinds, in order |
|---|---|
| Action and adventure | superheroes, martial_arts, revenge, spies, scifi_action, quests, disaster_survival, war_battle, action_comedy |
| Drama | true_stories, family_coming_of_age, lives_apart, history_period, crime_drama, war_cost, sports, courtroom_politics, showbiz |
| Thriller | keep_guessing, trapped, mind_games, spies, serial_killers, erotic |
| Crime | cops, gangsters, heists, crime_drama, serial_killers, prison |
| Sci-fi | space_aliens, time_robots_ai, dystopia, lab_monsters, superheroes |
| Fantasy | sword_sorcery, fairy_tales, magic_our_world, superheroes |
| Romance | romcom, love_hurts, period_romance, teen_love |
| Animation | family_adventure, cartoon_comedy, anime, superheroes, adult_animation |
| War | war_battle, war_cost, behind_lines |

Westerns asks no question, like Documentaries: the door is the choice, and it
rolls from its whole pool after its opening line. Thriller's spies answer
carries `self_destruct` of 5 seconds (section 12), the one answer that does. A
film may sit in two kinds of a door. A kind several doors offer (superheroes,
spies, war_battle, war_cost, crime_drama, romcom, cartoon_comedy,
action_comedy, serial_killers, horror_comedy) is one label per film, written to
hold the same films at every door that offers it; Matinee does not enforce it.
A film behind a door that is not yet labelled, or placed there by a house pin,
is reached through "anything" and `Just pick one!`. In the operator's library
the 30-film bar hides Thriller's erotic, Crime's prison, Romance's
period_romance, Sci-fi's lab_monsters and War's behind_lines answers, as the
answer key's `hidden` list records.

For the kids asks its age question, then its kind question: something super
silly, a big adventure, something with magic in it, animals, superheroes and
robots, songs, one that makes you feel all warm inside, and a little bit
spooky. Each kind answer holds the films the labels give that kids kind
(silly, adventure, magic, animals, heroes, songs, warm, spooky). Spooky is not
offered after "the little ones. nothing scary.".

### 2.4 Walking a tree

- The walk starts from the viewer's pool for the tree (section 6) and applies
  each answer in turn. The reply line of the last answer acknowledges it before
  the next question is asked.
- **Fewer than 12 films left:** no further question is asked, and the walk ends.
- A question marked `only_if_pool_over` is asked only while the pool holds more
  films than that number. Horror's era question uses 40.
- A question marked `skip_if_topics` is never asked of a viewer who excludes any
  of those DoesTheDogDie topics. Its `treat_as` answer is applied to the whole
  starting pool instead, so every count and every shown answer already reflects
  it.
- **An answer that would leave the pool empty is not shown.** A question with no
  answer to show is skipped.
- A question may carry a `footnote`, a line the viewer sees in small type beneath
  its answers and above `Just pick one!` (`footnote` in `/api/walk`). A question's
  `note` is maintainer documentation and is never shown.
- An answer marked `not_after` is hidden when the viewer gave a named earlier
  answer.
- A walk that ends on an answer carrying `self_destruct` reports its seconds
  with the reply (`self_destruct` in `/api/walk`); every other walk reports none.
- An answer that does not fit the question being asked is refused. The page is
  told to start over.
- Pool counts never include DoesTheDogDie exclusions. Those are checked only at
  the pick (section 9).
- **`Just pick one!`** is on screen from the first question onward, as the last
  choice beneath each question's answers. It ends the questions and picks from
  the pool as it stands. Pressed at the first question, it picks from each
  door's pool for this viewer before any answer, less the flavour that door's
  tree holds apart.
- **The trail.** On each question after the first, and on the pick screen, the
  page shows the way here in gold at the bottom centre: `Start`, the door, then
  each answer so far. Choosing a crumb goes to the screen it led to and forgets
  every answer after it: `Start` returns to the first question, the door asks
  the door's first question, and an answer asks the question that followed it.
  The crumb for the screen showing now is plain text, not a link; on a pick
  that `Just pick one!` ended early, every crumb is a link.

### 2.5 Every film stays reachable

Every film in the library must be reachable through at least one complete path
of answers in some tree or mode a first-question answer leads to. A tree no
door leads to is no film's home.
`tools/check_trees.py` holds the trees to this. It reads the film table the
nightly rebuild writes, builds every tree through the engine, and fails, with a
non-zero exit, on any of these:

1. **Data.** A library film has no usable TMDB facts. The standup rule cannot
   see such a film.
2. **First question.** An answer leads to no tree or mode file.
3. **Answer coverage.** A film in a tree's pool is reached by no complete path
   of that tree's answers, or a path ends on no film. It also reports how many
   questions each tree asks.
4. **House pins.** A pin has no answer-key fixture asserting the pinned
   placement. A `specials` pin's fixture asserts comedy's standup flavour.
5. **Fixtures.** A fixture film in `data/answer_key.json`,
   `data/fixtures/horror.json` or `data/fixtures/comedy.json` misses a tree it
   must reach, reaches one it must not, or lands in the wrong kids band or gore
   pail. A fixture's `flavour_in` and `flavour_out` kinds, and a horror fixture
   file's `expect` and `must_not` kinds, must hold after labels and house pins.
   A fixture names its film by TMDB id, and fails when that id holds a
   different title in the library. A fixture-file entry without an id must match
   exactly one library title.
6. **The gore promise.** A horror film with no genome entry and no pin lands in
   the spotless or rip pail.
7. **Lists.** A film carrying a famous-list genome tag has no home. The tags are `afi 100`, `afi 100 (laughs)`, `imdb top 250`,
   `oscar (best picture)`, `criterion`, `golden palm` and `cult classic`, read at
   relevance 0.8 or above, except `afi 100 (laughs)` at 0.5. No copy of any
   published list is kept. Lists never filter, rank or gate what Matinee offers.
8. **Reachability.** A film is reachable through no tree at all. A film a tree
   holds apart (section 2.3) sits in another door's pool.
9. **Smaller libraries.** The same trees are rebuilt against a random third of
   the library (seed 3) and a random tenth (seed 10). Each must keep every film
   reachable. A film both libraries hold in a tree's pool must reach the same
   answers of that tree in both. Fixtures are checked on the full library only.
10. **Quips.** The pick's lines break a rule of section 2.7, or the file cannot
    be loaded.
11. **Shared kinds.** A kind two or more doors offer (a tree file's flavour name,
    such as `action_comedy` at Action and Comedy) must hold the same films at
    every one of those doors. A film the labels list under two sharing doors,
    holding the kind at one and not the other, fails.

Separately, the engine refuses to prepare when the shipped reference statistics
do not cover the tree files (section 3). The checker reports that as a failure.
The checker reads the labels file beside the film table unless `--labels` names
another. It lists by title the films in the waiting room (section 3.1) with the
doors their genres place them behind, the films each door holds under no kind
(by a house pin, the waiting room or the standup rule), the labelled films no
kind of their door fits (reached through "anything" and `Just pick one!` only;
the labels give no kind where none is a real fit), and each answer a small
kind hides. On the full library it fails
when the kinds the bar hides differ from the answer key's `hidden` list of
`[tree, kind]` pairs, so a kind that starts hiding, or stops, is never silent.

### 2.6 Labels

The labels alone decide which genre doors and kinds a film belongs to (section
3.1). The file is `labels.json` in the state directory. It is written outside
Matinee, by a labelling pass, and never committed, because it lists the films
one library holds. Its shape (format 2):

```json
{"format": 2,
 "trees": {"action": {"kinds": {"1891": ["scifi_action", "quests"]}},
           "western": {"kinds": {"11969": []}},
           "kids": {"kinds": {"9340": ["adventure", "silly"]}, "bands": {"9340": "family"}}}}
```

- A tree's `kinds` maps a TMDB id to the kinds the film holds at that door, one
  or two (horror's found_footage marker may come on top, or alone; a kind shared
  with another door may come on top too), or none where no kind of the door is a
  real fit. Every film listed under a door is behind it. Westerns asks no question, so its films hold
  no kind.
- `bands`, under `kids` only, gives each kids film the youngest age band it
  suits: `little`, `family` or `older` (section 3.2).
- A film the file lists under no door at all is unlabelled and waits behind the
  doors its genres name (section 3.1).
- An absent file stops the server at start-up with the path named; the labelling
  pass must write one first. A file in any format but 2 is refused at start-up
  with its format named. A malformed file, a band outside the three, a tree no
  file defines, or a kind the tree does not label stops the server at start-up
  too.
- The server reads the file once at start-up. Replacing it takes a restart.

Each labelled flavour's `note` in its tree file states the rule its kind
follows. The labels were written by a language model against those rules, with
the operator's calls laid over them. A kids-first film, made mainly for
children and the families watching with them, is labelled behind For the kids,
behind Animation when it is animated, and behind no other door; the engine does
not read that call, which the file already holds.

### 2.7 The pick's lines

What Matinee says as it hands over a film is data in `data/quips.json`. The
page reads it through `GET /api/quips`, which returns the file as loaded
(`src/matinee/quips.py::Quips`, served by
`src/matinee/web/app.py::add_quip_routes`):

```json
{"note": "…",
 "caps": {"line": 64, "pair": 76},
 "categories": {"universal": {"reveal": ["How about this one?", "…"], "nope": ["…"]},
                "horror": {"reveal": ["…"], "nope": ["…"]},
                "comedy": {"reveal": ["…"], "nope": ["…"]}}}
```

- A category is `universal`, or a tree or mode by its file name. It may hold
  `reveal` lines, said as a film arrives, and `nope` lines, said after
  `Not that one`. The shipped file holds universal (16 reveal, 22 nope),
  horror (18, 19), comedy (22, 29) and action (16, 19). A tree or mode with no category of its
  own, such as thriller or crime, draws universal's lines. No category draws
  another tree's lines.
- `caps.line` is the most characters one line may hold. `caps.pair` is the
  most a nope line and a reveal line shown together may hold. Both were set by
  rendering every line as the pick line, on a 360 px phone and on the widest
  desktop: `line` is the longest line that fits in three lines at both, and
  `pair` is one less than the shortest same-category pair that overflows four
  lines at either. A test pins them at 64 and 76, so a cap cannot be raised to
  admit a long line without that test failing.
- Loading is strict. An unknown key is refused. A file whose universal
  category lacks reveal lines or nope lines is refused, because every set
  falls back on universal's. The server reads the file once at start-up;
  replacing it takes a restart.
- The checker (section 2.5), and a test in `./check.sh`, refuse by name a line
  over `caps.line`, a line wrapped in quotation marks, and a line in title
  case. A line is in title case when it has at least two words after its
  first, not counting words in capitals for emphasis or "I" and its
  contractions, and every one of them is capitalised. They also refuse a
  category that is neither universal nor a tree or mode.
- The pair cap is held when the page deals lines (section 12), not by the
  checker.

## 3. Pools and reference statistics

### 3.1 Which films a tree holds

Pools are built once per film table, before any question is asked. No genre
tag, genome score, franchise or catch-all rule places a film behind a genre
door.

| Tree | Holds |
|---|---|
| comedy, action, drama, thriller, crime, horror, scifi, fantasy, romance, animation, western, war | the films the labels list under it, plus the waiting films its genres name, plus house tree pins; comedy also holds every standup special |
| kids | the films the labels list under For the kids whose certificate passes (section 3.2), plus house kids pins |
| nonfiction | every film tagged Documentary, less the standup specials, plus house tree pins |
| sleep | enchantment at 0.55 or above and edge under 0.40; a film with no genome entry is never in it |

- **The waiting room.** A library film the labels file lists under no door
  waits behind the doors its TMDB genres name: Action or Adventure behind
  action; Comedy; Drama; Horror; Thriller or Mystery behind thriller; Crime;
  Science Fiction behind scifi; Fantasy; Romance; Animation; War; Western. It
  holds no kind there, so only "anything" and `Just pick one!` reach it, until a
  labelling pass places it. A documentary or a standup special does not wait,
  since its own rule gives it a home. This is the only place genres place a
  film behind a genre door.
- **Scores** for the fall-asleep mode are mean genome relevance of fixed tag
  lists. Enchantment: fairy tale, childhood, fantasy, whimsical, magic, fantasy
  world, fairy tales. Edge: violent, gore, disturbing, tense, brutal.
- **Standup specials.** A title is a standup special when it carries the TMDB
  keyword `stand-up comedy`, or when it is tagged Comedy and either is a TV Movie
  carrying `comedian`, `concert` or `concert film`, or carries `comedian` and a
  concert keyword together, or when the house counts it as one (a `specials`
  pin, section 4.2). A concert keyword alone never marks a special. Unknown TMDB
  keywords never mark a special. Every special joins the comedy pool, where only
  its standup answer offers it (section 2.3), and stays out of non-fiction.
- **House tree pins** add single films to a tree after every rule above.
  Comedy's standup specials then return to its pool, whatever the labels said
  (section 2.3).

### 3.2 The kids pool

The kids pool is gated and fails closed. A film enters when the labels list it
under For the kids and its certificate passes. Its band is the older of its
labelled band and its certificate's band:

| Certificate | Youngest band it allows |
|---|---|
| G, TV-Y, TV-Y7, TV-G, E | little |
| PG, TV-PG | family |
| PG-13, TV-14 | older |

One exception: a film labelled for the whole family with a G-class certificate
is in the little band, unless one of its kids kinds is spooky.

Any other certificate, R, NC-17, TV-MA, an absent or unusable one, never
passes. A house kids pin puts a film in the pool in the named band, whatever
its certificate and labels. The bands allow rather than require:

| Answer | Offers |
|---|---|
| the little ones | films whose band is little |
| the whole gang | films whose band is little or family |
| the big kids | the whole pool |

### 3.3 Reference statistics

Every score means the same in every library. Matinee scores films against a
fixed reference drawn from films in general, never against the library it
reads.

- A tree file's `reference` names its MovieLens genres and a score floor. Its
  reference films are every film in the MovieLens ml-latest genome carrying one
  of those genres and reaching any one floor, inclusive. A tree with no floor
  writes `"floor_any": {}`.
- `tools/build_reference.py` measures, over each tree's reference films, the cut
  points of every scale by linear interpolation. It rounds to six places and writes
  `data/reference.json`, named by the dataset's own generation date. The same
  release and tree files always produce the same file.
- Matinee reads that file at runtime and never recomputes it from a library.
- The engine refuses to prepare, and the server refuses to start, when the file
  is absent or does not cover a tree file: a missing tree, different genres or
  floor, or a scale that is missing or has other tags or percentiles.
  A test in `./check.sh` fails in the same case, so a changed tree file cannot
  ship with stale statistics.

| Tree | Reference genres | Floor | Reference films |
|---|---|---|---|
| horror | Horror | fear ≥ 0.20 | 1,572 |

Horror alone names a reference, for its gore scale. No other tree's answer is a
scale.

The shipped release is "MovieLens ml-latest, generated July 20, 2023".

## 4. Scales and pins

### 4.1 The gore scale

Horror's gore question is a scale cut into four pails, asked in pictures.

- **Score.** The mean genome relevance of gore, goretastic, gory, bloody,
  splatter, gruesome, gratuitous violence and torture. A film with a genome
  entry gains 0.08 for each of its TMDB keywords in this list, counting at most
  three: gore, splatter, extreme violence, torture, body horror, dismemberment,
  decapitation, cannibalism, brutality, graphic violence, blood, bloody. A film
  with no genome entry has no score, whatever its keywords.
- **Cuts.** Fixed scores at the 40th, 70th and 90th percentiles of the horror
  reference: **0.220412, 0.380262 and 0.581994.** A film is in band *i* when its
  score is at or above cut *i−1* and below cut *i*.
- **Unscored films** belong to the some and messy pails.
- **Pins.** A house scale pin puts a film in one pail whatever its score, and
  in no other. The Terrifier films are pinned to rip.

| Answer | Offers |
|---|---|
| None. I'm squeamish. | spotless |
| Some. I'll look away when I need to. | spotless, some |
| Properly messy. I'm fine. | some, messy |
| RIP AND TEAR. | every pail: the worst and everything under it |

A viewer excluding any of these DoesTheDogDie topics is never asked the gore
question and is treated as "None. I'm squeamish.": 188, 296, 331, 203, 250,
200, 361, 171, 258, 223, 254 and 255.

### 4.2 House pins

`data/house_overrides.json` holds this installation's hand-set placements,
applied for everyone. A pin is keyed by TMDB id with its title and a note. It
takes one of five forms:

| Form | Places a film |
|---|---|
| `kids` | in the kids pool, in the named band, whatever its certificate |
| `trees` | in a tree's pool |
| `specials` | among the standup specials: in comedy's standup answer and out of non-fiction |
| `scales` | in one band of one scale, and out of its others |
| `flavours` | in one flavour of one tree (`member` true) or out of it (`member` false) |

A film pinned into a flavour stays in every answer that leaves another flavour
out. A funny horror film pinned into monsters is therefore offered under the
comedy answer and under the scary ones.

Every pin must also be an answer-key fixture asserting the pinned placement. The
checker fails otherwise, so a later rule change cannot silently undo a pin.

## 5. The offline film table

The trees filter on an offline film table: one SQLite file in Matinee's state
directory, never in the repository. The server reads it. It never queries the
genome or TMDB.

### 5.1 The nightly rebuild

`tools/rebuild_table.py` writes the table. With `--daily HH:MM` it rebuilds at
once and then every day at that local time. The time is validated before the
first rebuild. A failed nightly rebuild leaves the previous table in place.

1. It reads the media server's film list, by GET only.
2. It refreshes TMDB facts (collection, keywords, original language) for every
   library film with a TMDB id. That is one GET per film, 0.15 seconds apart.
   It honours `Retry-After` on a 429 and stops after 5 network failures in a
   row.
3. It loads the local MovieLens genome.
4. It builds and writes the table, replacing the previous one only once the new
   one is complete.
5. It logs a report. The report counts films with and without genome scores and
   items with no TMDB id. It names every file whose `{tmdb-N}` folder tag differs
   from the TMDB id the media server gives, and every film missing a usable TMDB
   record. It uses the media server's id and changes nothing on the server.

### 5.2 TMDB facts and the six-month limit

- The TMDB cache holds the newest record per film. A record is refetched once
  it is **150 days** old, or when it predates the original-language field.
- After each refresh the cache is rewritten to hold only records younger than
  **183 days**. A film TMDB does not know (404) is never cached. A damaged cache
  line is skipped, logged, and its film fetched again.
- A film whose TMDB record is missing or 183 days old or more carries no TMDB
  facts. Its keywords are unknown, never empty.
- **The table is refused once its oldest TMDB fact is 183 days old.** The server
  will not start on such a table. A running server checks the age on every
  request and answers 503 `not_ready` once it passes.

### 5.3 The genome join

- The genome is read from a local copy of the MovieLens ml-latest release. The
  raw dataset is never committed or shipped.
- Films join the genome on TMDB id through the release's own `links.csv`, never
  by title. Where two MovieLens films share a TMDB id, the first one wins.
- **A film the genome does not cover carries no genome scores (NaN), never
  zeros.**
- The table stores one row per distinct TMDB id. Library items with no TMDB id
  are left out and reported.
- The parsed genome matrix may be cached beside the dataset. The cache is
  reused only when made from a genome file of the same size and modification
  time.

### 5.4 The live library

- The server reads the media server's film list at most every **300 seconds**
  and narrows the table to the films the library holds now.
- A library film the table does not yet hold is offered by its media-server
  facts alone, with no genome scores and no TMDB facts, and is logged.
- When the media server cannot be read, nothing is served from an older list.
  Every request that needs the film list answers 503 `library_unreachable` until
  a read succeeds. For
  **15 seconds** after a failed read no new read is attempted.
- The table file is reloaded when the nightly rebuild replaces it.
- The sign's "Now showing N films" counts the distinct TMDB ids in the live
  film list.

### 5.5 Refusing to start

The server refuses to start, and logs why, when any of these holds:

- a required setting is missing;
- the state directory does not exist (Matinee does not start empty and lose
  every profile silently);
- the film table is absent, in another format, or too old;
- the reference statistics are absent or stale;
- a tree or mode file is malformed;
- the labels file is absent, malformed, or names a tree no file defines or a
  kind its tree does not label;
- the pick's lines (`data/quips.json`) are missing or malformed, or universal
  lacks reveal lines or nope lines (section 2.7);
- the store file is newer than the code, is not a SQLite database, or cannot be
  upgraded to the current shape (section 7.1). The file is left unchanged.

## 6. What one viewer's pool is

For each tree, the viewer's starting pool is built in this order:

1. The tree's pool, with house pins already applied.
2. Matinee's own exclusions the viewer holds remove every film they match.
3. Every question the viewer's DoesTheDogDie topics skip applies its `treat_as`
   answer.

A viewer's notes (section 10) never change a pool.

Answers narrow that pool from there (section 2.4).

## 7. Viewers, profiles and devices

Matinee has no accounts and no login. Every viewing runs under a **profile**
this device holds a token for. A device without one is shown the first
question's pool behind the front door, with no exclusion applied, and walks or
picks nothing until it opens or makes a profile.

| Rule | Value |
|---|---|
| A profile holds | a display name, an optional four-digit PIN, DoesTheDogDie topics and Matinee's own exclusions |
| Most profiles | **50**; creating a fifty-first is refused |
| Name | 1 to 40 characters after NFKC normalisation, trimming and collapsing spaces; no character of Unicode category C (control, format, private-use, unassigned); unique ignoring case (NFKC, case-folded) |
| PIN | exactly four ASCII digits, or none |
| PIN storage | salted scrypt digest (N 2^14, r 8, p 1, 32 bytes, 16-byte salt); never stored as typed |
| Lockout | **5** wrong PINs lock that profile against PIN entry for **15 minutes**; keyed on the profile, never on a client address |
| Device token | 32 random bytes, URL-safe; stored only as a SHA-256 digest, so a copy of the store cannot be replayed as a cookie |
| Token cookie | `matinee_tokens`: `HttpOnly`, `Secure`, `SameSite=Lax`, path `/`, 400 days; holds at most **8** tokens and never a name or PIN |
| Token pruning | tokens older than 400 days are deleted whenever a new token is issued |
| Name suggestions | none until **3** characters are typed; at most **3**; a match is one name, ignoring case, starting with the other, or the two within **2** single-character edits; prefix matches first, then fewer edits, then the name |

- **A device holding a valid token for a profile is never asked its PIN** and
  keeps its token when it opens the profile again.
- A profile with a PIN opens on another device only after its PIN.
- "Who's watching?" lists only profiles this device holds a token for. Any other
  profile appears only as a name suggestion.
- A name suggestion carries the profile's id, name and whether it has a PIN.
  It never carries the profile's exclusions.
- A token for a deleted profile is ignored. The door's reply clears it from the
  cookie.
- There is no PIN reset and no administrative surface. Whoever runs the
  installation clears a forgotten PIN in Matinee's store.
- A request naming a profile (the first question, a walk, a pick, saving
  exclusions or saving a note) is refused with 403 unless this device
  holds a token for it. A walk or a pick naming no profile is refused with 403.

### 7.1 The store file

The store is one SQLite file, `matinee.sqlite`, in the state directory. It
records its shape in SQLite's `user_version`; the current shape is **1**. A file
from before shapes were recorded reads 0 and holds profiles, tokens, notes (in a
table named `feedback`) and personal corrections.

- A missing or empty file is made at the current shape.
- A shape-0 file is upgraded in place when Matinee starts, in one transaction.
  The upgrade keeps every profile, token and note, each note under its own id,
  and removes the corrections. It is kept only when the counts of profiles,
  tokens and notes are the same after it as before and no row points at nothing.
- Before its first change to a shape-0 file, the upgrade copies the file as it
  stood to a new file beside it, named
  `matinee.sqlite.before-shape-1-<UTC time>`. Nothing ever overwrites that copy,
  and a later start on the upgraded file makes none.
- A file newer than the code, a file that is not a SQLite database, a shape no
  upgrade starts from, and an upgrade that fails all stop the start. The store
  file is left unchanged.

## 8. Exclusions

A viewer may exclude two kinds of thing. A profile saves them.

**Matinee's own exclusions** (`data/exclusions.json`) remove every film they
match from every tree and mode, through the engine. A genome test matches when
the mean relevance of its tags reaches its minimum. Unknown data never matches.

| Exclusion | Matches when |
|---|---|
| Superheroes | superhero, superheroes, super hero at 0.80 or above; or the TMDB keyword `superhero` |
| Sci-fi and magic | any one group at 0.50 or above: sci-fi, science fiction; mythology, magic; mindfuck, surreal, dreamlike, alternate reality |

An exclusion name Matinee does not define is refused before it is saved or
walked with.

**DoesTheDogDie topics** are checked only at the pick (section 9). Before the
pick, they only decide whether a question marked `skip_if_topics` is asked. A
film fails a topic when the topic has **at least 5 votes and more yes votes
than no.**

- The topic list is fetched from DoesTheDogDie when a page that offers topics
  opens and no list is kept. It is then kept in memory and fetched again once it
  is **29 days** old. While a refresh fails, the kept list serves until it is
  **30 days** old.
- The trigger picker, which is also the preferences page, offers Matinee's own
  exclusions and the DoesTheDogDie topics. It says the check is best effort from
  crowd votes and carries "Powered by DoesTheDogDie.com", linked.
- When the topic list cannot be fetched, the picker says so and offers "Try
  again" (and, when editing, "Never mind, keep my list").

## 9. The DoesTheDogDie check at the pick

A film is looked up on DoesTheDogDie only when Matinee has drawn it for a pick
and the viewer holds DoesTheDogDie topics. Nothing is looked up ahead. Votes are
never kept. No tree, scale or score is built from DoesTheDogDie data.

- **The lookup.** By TMDB id: `/api/v3/items?tmdb={id}`, then
  `/api/v3/items/{itemId}`. Where the search returns several items for the film,
  the one Movie among them is used. Where that does not leave exactly one item,
  the film counts as having no record.
- **The item id is remembered.** The search's answer (the film's item id, or
  that it has none) is kept in memory for **30 days**, so a later lookup of the
  same film skips the search. A search answer that cannot be read is not kept.
  A held id is forgotten when DoesTheDogDie answers 404 for its votes.
- **The draw.** The pick draws a film at random from the candidates. The
  candidates are the pool less the films already shown or turned away since the
  viewer last answered the first question.
- **Used up.** When every film in the pool has been shown or turned away, no
  film is drawn again. The page says "That's every film I've got for those
  answers. Step back along the trail, or start over." and offers `Start over`.
  With `sort: rating`, they are the better-rated half, and an unknown rating
  ranks last.
- **Least gory first.** When a viewer's topics skip a question whose answers
  cut a scale (horror's gore question, skipped for its blood and gore topics),
  the pick draws first from the third of the candidates scoring lowest on that
  scale, rounded up. It draws from the rest only once that third is spent. The
  scale scores every film, whichever tree the pick came through; a film it
  cannot score is never in that third.
- **A failing film** is replaced by another draw from the same pool. A film that
  failed in this pick is never looked up again in it. The page says why in
  Matinee's voice: "Oh, I almost recommended a film where <topic>. Let's find you
  an alternative." It offers "What were you going to show me?", which reveals
  the first film turned away and the topics it failed.
- **Every film fails.** The page says "Every film left here trips something on
  your list. Want to start over?" and offers `Start over`.
- **Three in a row.** A pick looks up at most **3** films that fail. When three
  have failed and others remain, it stops and the page says "Three in a row
  trip your list, starting with one where <topic>. Roll again, or I can just
  pick one without turning any away. It might have some of what you'd rather
  skip." It offers `Roll again`, `Just pick one` and `Start over`. `Just pick
  one` draws a film (least gory first, where that applies) and shows it without
  looking it up, marked unchecked.
- **Turned-away films.** Every film a pick turns away is reported to the page
  and joins the visit's seen list. The page sends the 200 most recent.
- **Unchecked.** The film is shown with a note, and the DoesTheDogDie credit
  beside it, when any of these holds:
  - DoesTheDogDie is slow (no turn, or no answer, within **3 seconds** per
    request) or refuses;
  - DoesTheDogDie holds no record, or a vote row cannot be read;
  - the device has spent its allowance for the hour;
  - the installation has reached its own hourly ceiling;
  - the client is holding its requests after a refusal, or because
    DoesTheDogDie reports the month's allowance nearly spent;
  - the viewer chose `Just pick one` after three films failed.

  An unreadable vote row never counts as a pass. The note reads "I couldn't
  check this one against your list, so have a look before you press play." A
  spent device allowance, the installation's ceiling and `Just pick one` each
  have their own line saying so (`UNCHECKED_LINES`). The note does not name the topics: an
  unchecked film was checked against none of them.
- **Pacing.** All DoesTheDogDie traffic, from every viewer, passes through one
  client that serialises requests. It allows a burst of **2** and refills at
  **0.45 a second**, so no 60-second window carries more than 29 requests. That
  keeps the whole installation under the free tier's 30 a minute. A caller waits
  for its turn at most its own budget and is then told DoesTheDogDie is busy.
  The topic list waits about 2.7 seconds and allows 10 seconds for an answer.
- **Hourly ceiling.** The installation sends at most **120 requests** to
  DoesTheDogDie in any hour, whoever asks, topic lists included. Past it, a
  request is refused without being sent.
- **Refusals.** A 429 or 503 holds every request for its `Retry-After` seconds.
  Without one it holds **60 seconds**, doubling with each refusal in a row up to
  an hour; a successful answer resets the doubling.
- **The month's reserve.** When DoesTheDogDie's `X-RateLimit-Remaining-Month`
  header reports fewer than **250** requests left, every request is held for
  **6 hours**, after which requests flow again and the next answer's header is
  read afresh.
- **Per-device allowance.** A device may spend at most **60 film lookups** in
  any hour. A film lookup is one film, which is up to two requests. The device
  is known by an anonymous cookie, `matinee_device` (`HttpOnly`, `Secure`,
  `SameSite=Lax`, 400 days), issued only to a viewer with topics. Devices idle
  for an hour are forgotten.
- Every request names Matinee in its user agent, because DoesTheDogDie refuses
  the default one.

## 10. Notes

A note is a viewer's complaint about a pick, kept for whoever runs Matinee. It
changes nothing any viewer is shown.

- The note link is offered only on a pick that came through a tree. It is a
  small "Something wrong with this pick?" link that opens a panel and never
  dominates the result. The pick always belongs to a profile this device holds,
  so the panel never asks for a name.
- The panel opens with "How you got here:" and the viewer's answers in order,
  ending with "Just pick one!" when that ended the questions.
- The panel asks what is wrong, with three choices, and offers an optional "Why?"
  box of at most 500 characters:
  - "Not <genre> at all", which asks where the film belongs;
  - "<Genre>, but not the kind I asked for";
  - "The right kind, just not a good pick".
- A tree whose answers re-apply a kids age band is not offered as where a film
  belongs, and the panel says why: "Kids' films are picked for the whole house,
  so I can't add one just for you. Ask whoever runs Matinee to add it."
- Every choice saves a note and nothing else: the profile, the film, the tree,
  the choice, the answers that led to the pick in words, whether "Just pick
  one!" ended the questions, the comment and a UTC timestamp. A note needs a
  held profile. Its answers are resolved against the tree when it is saved, and
  an answer the tree does not have, a tree that does not exist or a film not in
  the library is refused.
- Once the note is saved the panel says "Thanks. That's gone to whoever runs
  Matinee." in gold and "If they agree, it moves for everyone." in cream.

## 11. The web surface

### 11.1 Routes

The routes serve Matinee's own page. They are not a public API. The interactive
documentation, ReDoc and the OpenAPI schema are all disabled.

Every `/api/` reply carries `Cache-Control: no-store`. The door's reply lists the
profiles the asking device holds, so a copy kept by a browser or an edge cache
would hand one device's profiles to another.

| Method | Path | Does |
|---|---|---|
| GET | `/` | the page (`Cache-Control: no-cache`) |
| GET | `/static/…` | scripts, styles, self-hosted fonts, icons, pails, manifest (`Cache-Control: no-cache`, so a deploy is never seen half-applied) |
| GET | `/img/{kind}/{tmdb}/{size}` | a poster or backdrop, read from the media server |
| GET | `/api/film/{tmdb}` | title, year, runtime, synopsis and the Seerr link for one film |
| GET | `/api/door` | the film count and the profiles this device holds |
| POST | `/api/names` | name suggestions |
| POST | `/api/profiles` | create a profile and issue this device a token |
| POST | `/api/profiles/{id}/open` | open a profile by PIN, or at once when held or PIN-less |
| PUT | `/api/profiles/{id}/exclusions` | replace a held profile's exclusions |
| GET | `/api/topics` | DoesTheDogDie's topic list, with its credit |
| GET | `/api/exclusions` | Matinee's own exclusions |
| GET | `/api/quips` | the pick's lines and their caps (section 2.7) |
| POST | `/api/first` | the first question for this viewer, and the pool behind it |
| POST | `/api/walk` | the next question and the pool, given a tree and answers |
| POST | `/api/pick` | one checked film from the pool the answers leave |
| POST | `/api/notes` | keep one note on a pick for a held profile |

### 11.2 What the browser may name

- **A film** only by a TMDB id in the current live film list. Any other id
  answers 404 before any request leaves for the media server.
- **An image** only as `poster` at `xs` (100 px), `s` (160 px), `m` (320 px)
  or `l` (640 px), or `backdrop` at `m` (960 px) or `l` (1600 px). The media-server item id is
  never taken from the browser. It must be 32 hexadecimal characters before it
  is joined into a request. An image answer must be `image/*` and at most
  8 MiB. An image 160 px wide or narrower, a wall tile shown dimmed, is asked
  of the media server at quality 60; any other at quality 80. Images are served
  with `Cache-Control: public, max-age=2592000` (30 days), so a return visit
  draws the wall from the browser's cache.
- **An answer** as a question id and an option index, never as a filter.
- **Request sizes** are capped: a typed name 80 characters; a profile name 80
  and a PIN 8; topics 400; exclusions 20; answers 12; tree names 40; option
  indexes 0 to 50; films already seen 200. A pick
  with no tree may carry no answers.

### 11.3 What no response carries

No response carries the media server's address or key, a file path, a disk
location or an exception's text. The media server's key travels only in the
header of Matinee's own requests to it and is never logged. Posters, backdrops
and synopses reach the browser through Matinee's server. The media server is
never exposed to the browser.

Every error leaves as `{"error": <code>, "message": <sentence>}`:

| Code | Status | When |
|---|---|---|
| `library_unreachable` | 503 | the media server cannot be read |
| `not_ready` | 503 | the film table is too old to serve |
| `topics_unavailable` | 503 | the topic list cannot be fetched |
| `not_found` | 404 | an unknown film, image or path |
| `refused` | 400, 403 or other | answers that no longer fit, an unknown exclusion or tree, a profile this device does not hold, a malformed request |
| `profile` | 400, 401, 404, 409 or 423 | a profile rule refused the request; the body adds `code` (`bad_name`, `bad_pin`, `name_taken`, `full`, `no_profile`, `wrong_pin`, `locked`) |

One error falls outside that shape. A request body that fails validation, such
as a field over its size cap, answers 422 with the web framework's own
`{"detail": [...]}` body. That body echoes the offending input back. It carries
nothing from the server.

### 11.4 Headers

Every response, including static files and errors, carries:

- `Content-Security-Policy: default-src 'self'; img-src 'self'; style-src 'self'; font-src 'self'; script-src 'self'; connect-src 'self'; manifest-src 'self'; worker-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'`
- `X-Content-Type-Options: nosniff`
- `Referrer-Policy: same-origin`
- `Permissions-Policy: camera=(), microphone=(), geolocation=()`
- `X-Robots-Tag: noindex`, whether or not a door word is set. Matinee serves no
  robots.txt, because one that blocked crawling would stop search engines from
  reading this header.

The page builds all text as text nodes, never as markup, so a name or title from
the server can never become part of the page's HTML.

## 12. The page

One dark theme: base `#07080d`, marquee gold `#f2b33d`, velvet red `#e0566b`
for `Not that one` only. Matinee's lines and the wordmark are set in Big
Shoulders Display, other text in DM Sans. Both fonts are self-hosted with their
OFL licences. All displayed text is in sentence case. A phone is a viewport
600 px wide or less.

- **The door.** The marquee stands at the top centre of the screen over the
  poster wall, and nothing else frames it: no booth and no curtains. The
  marquee is an art deco stepped crown with a sunburst over a free-standing lit
  sign, with a warm glow behind them and a dark fade across the top of the
  screen (420 px deep, 260 px on a phone) that lets the sign read against the
  posters. On a desktop the sign is 900 by 216 px under a crown 620 by 114 px;
  on a phone it is 350 by 140 px under a crown 230 by 54 px. The sign never
  runs wider than the screen less 32 px (10 px on a phone). "Matinee" is the
  largest thing on it, at 104 px (58 px on a phone), over a small letter board
  reading "Now showing N films" with the live count. A thin gold frame sits
  inside the ring of bulbs, and on a desktop striped rules flank the name.
  Bulbs run round the sign: 156 of 10 px on a desktop, 64 of 7 px on a phone.
  They twinkle while two dark bulbs travel clockwise, half a lap apart, one lap
  every 12 s; a lap starts with the two at the middles of the top and bottom
  edges. Under reduced motion no bulb darkens or twinkles. A window too short
  for the full marquee scales it down: to 0.8 under 820 px tall and 0.45 under
  700 px tall on a desktop, and to 0.75 under 640 px tall on a phone.

  Every question at the door is typed onto the wall below the marquee, with
  nothing behind Matinee's words. On a desktop the words are a centred column
  680 px wide, 44 px under the sign, with the line at 52 px and its answers as
  22 px letter-board strips. On a phone the line hangs 26 px under the marquee
  at 34 px, and the answers, 18 px strips, sit at the foot of the screen. A
  short window closes the words up: under 820 px tall on a desktop they start
  28 px under the sign, and under 640 px tall on a phone the line is 26 px. The
  trigger picker sits on the wall too: on a desktop 1000 px wide, the question
  and saving in a 360 px left column and the topics beside it. Its topic pills
  and fields keep their own dark fill. On a phone, while the picker is open,
  the crown fades and the sign shrinks to a lit strip of bulbs round the letter
  board, with no name; it returns to full size when the picker closes. The
  marquee stays on screen until the viewer goes in or opens
  About.
  - Every viewing runs under a profile. The door offers no way in without one.
  - A device with no token opens on the trigger picker, which asks for a name
    and an optional PIN and saves a profile with whatever is chosen.
  - A device holding one token opens on "Welcome back, <name>. Your seats are
    waiting.", with "Take me in" and "Not <name>?", which makes a new profile. A
    device holding several asks "Who's watching?", with "Someone new".
- **Going in.** Every answer at the door that leads into the theatre asks for
  the first question at the tap, and a door is entered once: a second tap or
  Enter changes nothing. The door's words and the corner credit line fade out
  (0.3 s), and the rest of the marquee fades over 0.55 s while it lifts 110 px
  and shrinks to 0.93 of its size over 0.8 s. Meanwhile "Matinee" flies from
  the sign's letters to the wordmark's place at the top left, shrinking to the
  wordmark's 30 px and losing its glow, over 0.9 s. It lands letter for letter
  on the theatre's wordmark, placed beside the name tag when the viewer has a
  profile, and gives way to that wordmark when the theatre's screen is built.
  The poster wall stays on screen throughout. No transition on the page passes
  through black. The first question types once the name has landed and the
  question has arrived; a landing that never reports counts as landed 0.95 s
  after the flight began. When the viewer's pool differs from the door's, the
  wall re-sorts in place as after any answer. From a phone's lit strip, which
  draws no name, the name stands at the wordmark's place at once while the
  strip lifts, and the question still waits the flight's time. Under reduced
  motion the change is instant. "Edit my list" and "Not <name>?" return to the
  door with the marquee already in place and lit; the name does not fly back.
- **The poster wall.** A flat grid of the posters of the films still in the
  pool, each its own image element, sharp and upright, held at 35 per cent
  strength, with no backing behind Matinee's words. The wall holds that one
  strength across the site's navigation and pages: the door, the questions,
  going in and About never dim it. The pick's reveal is the one special case:
  the rest of the wall dims to 12 per cent as the picked poster lands and stays
  there while the pick rests (below). Along a row the films run in the page's
  order, which is drawn at random once per page load; each row starts a fixed
  number of films on from the row above, chosen so a film's repeats sit as far apart as the
  pool's size allows, and the wall repeats in both directions so no edge ever
  shows. Poster size follows the pool: from 22 across on desktop, or 14 on a
  phone, at 1,200 films or more, down to 10, or 5.2, at 40 or fewer, with a
  14 px gap, or 8 px. The answer that ends the questions brings the posters to
  10 across, or 5.2, the size they keep through the pick; "Just pick one!"
  keeps the size the wall has. Each answer re-sorts the wall in place: the
  page waits up to 0.6 s for the pictures of the posters the new layout puts
  on screen, then, over 1.4 s on an even S-curve (easing out of place, gliding,
  and settling gently), each of them slides from the nearest place its
  film stood on screen, or in from the screen's edge toward its film's old
  place, or grows in place when its film is new to the wall; the posters of
  dropped films shrink to half size and fade where they stand, and a film
  still in the running whose new place is off screen slides away toward it.
  The new layout centres the new place of the surviving film that stood
  nearest the screen's centre. The wall never dims between answers, and under
  reduced motion it changes without sliding. The wall drifts upward at 10 px a second,
  timed by the clock, and stands still under reduced motion. Each poster uses
  the smallest picture (100, 160, 320 or 640 px wide) that covers its cell at
  the screen's pixel density; while it loads, a picture of the same film
  already loaded at another size stands in, and with none the cell is dark,
  never a broken-image mark. A wall laid fresh, on the page's first pool or after an empty one,
  stays unseen until every tile's picture has loaded or failed, or for 2.5 s,
  then fades in whole over 0.4 s, so it never fills in a cell at a time; under
  reduced motion it does not fade. A picture that fails is not asked for again on
  that page load. The posters ignore taps and clicks.
- **Questions.** Matinee's line types out (an acknowledgement, then the
  question), and the answers appear once it finishes. The line and the answers
  keep apart, and nothing re-centres as the line types or the answers appear:
  the line hangs from the top of the screen with three lines reserved, so on
  desktop the answers start at the same height on every question whose line
  fits in three; on a phone the answers sit at the foot of the screen. On
  desktop and on a phone the answers are letter-board strips, smaller on a phone.
  A question's footnote appears with the answers, in small dim type beneath
  them and above "Just pick one!". The first action on a screen
  disables every button on it. The profile's name tag, with "Edit my list" and
  "Not <name>?", sits at the top of the wall and the pick screen.
- **The pails.** The gore question shows four pail pictures, spotless to
  overflowing, each with its answer's words beneath it as text.
- **The pick, as a hunt.** From a question screen the question's words fade
  over 0.35 s (at once under reduced motion) while the pick is already being
  fetched. Where the last answer has a reply, it types in gold on the pick
  screen and stays whole for at least 1 s. Then, once any re-sort has ended,
  the drift stops, Matinee's words fade out (a gold nope line, or a line
  saying why a film was turned away, stays), and the wall eases forward to
  the next whole row (0.4 s). The wall then hunts in one, two or three hops,
  drawn at random with weights 1, 2 and 3 in 6: 6 to 9 posters in 1.5 s; 5
  to 7 then 1 in 1.05 and 0.55 s; 5 to 8, 2 to 3, then 1 in 0.95, 0.7 and
  0.5 s, pausing 0.3; 0.18 and 0.34; 0.14, 0.22 and 0.34 s after each. The
  first hop runs across the wall three times in five and down it otherwise;
  a second hop turns onto the other axis, and a third takes either. The
  first hop always runs at least one poster further than the screen shows
  along its axis, so the landing poster starts off screen. A vertical hop
  longer than one poster runs 0.7 of its count, rounded, and goes down the
  wall, the drift's way; no hop moves back along an axis already travelled.
  Each hop moves on one axis, passes its stop by at most 12 px (6 per cent
  of a short hop) and settles back, and never moves the wall more than half
  the poster spacing along its axis in 1/60 s; a hop that would takes longer,
  its length unchanged. Before the hunt the whole plan is made and the picked
  film is placed in the landing cell, which is never beside a copy of the
  picked film: a plan whose landing has that film in any of the eight cells
  around it, in the wall's order or placed by an earlier hunt, is drawn again,
  up to 20 times, and a pool too small to allow it takes the last plan. The
  landing cell is off screen until the hunt
  brings it to the centre (on a phone, the middle of the space above the
  foot, below). Under reduced motion there is no ease and no
  hunt: the wall moves to the landing cell at once, and the pick waits up to
  1 s for that cell to draw the picked film. Over the last hop's pause the
  landed poster brightens to full strength while the rest of the wall dims
  halfway to 12 per cent; then, over 0.75 s, it grows about its centre to
  2.4 times a resting-size poster (whatever the wall's poster size) while the
  wall dims to 12 per cent and the pick's reveal line types in the text
  colour. As it grows it glows in its strongest colour: its picture (the
  sharp one once decoded, else the wall's) is read at 32 by 48 pixels,
  near-black (brightest channel under 0.22), grey and near-white (saturation
  under 0.3) pixels are dropped, the rest are grouped into 24 hue bands
  weighted by saturation times brightness, and the heaviest band's average
  is raised to full brightness; a poster with too little vivid colour, or
  whose pixels cannot be read (logged as a warning), glows marquee gold. The
  glow grows in with the poster, and its blur and spread follow the grown
  poster's width. The poster grows by its laid-out size, so its picture stays
  sharp. The sharp 640 px picture is shown over the wall's picture, in the
  same box, only once it has decoded. A landed poster with no picture of its
  own at the wall's size (a smaller picture standing in does not count) waits
  for the sharp one; with neither, nothing grows, the wall dims to 12 per
  cent over 0.35 s and the pick goes to the resting page without a poster.
  Under reduced motion the wall is not dimmed before it moves; once there, the
  poster appears grown and the wall dimmed at once. After a 0.5 s beat (2 s under reduced
  motion), once the line has typed and the film's details (and on a desktop
  its backdrop) have arrived, the poster moves from exactly where it hangs to
  its resting place (1.3 s) as the details rise, leaving its cell empty while
  it rests. It keeps its glow at rest, at full strength, sized from its resting width. The wall stays at 12 per cent behind the resting page. On a
  desktop the resting place is the foot of the left column, as large as the height left there allows at 2:3 (never under
  160 px), while the backdrop rises on the right, fading into the title, year
  and synopsis, shown without a tap. The left column hangs from the top of the
  screen: the line, then `Not that one`, a "More on Seerr" link to the film's
  page on the configured Seerr and `Start over` in one row, then the
  note link.

  On a phone Matinee's words keep the foot of the pick screen, which is about a
  third of the screen (36 per cent of its height, never under 270 px) and holds,
  from its top, the line, `Not that one` and "More on Seerr", the note
  link, then the trail on one line, each crumb cut to 16 characters, and the
  credits. The foot has no backing of its own; the wall shows through it.
  `Start over` is not shown there: the trail's `Start` beneath does the same.
  Anything taller than the foot, such as the open note panel, scrolls
  inside it. The foot's top never moves from the first word of a pick to the
  last, through `Not that one` and the next pick. The space above it scrolls on
  its own, runs to the screen's sides and fades at its top and foot, so nothing
  passes behind the words and the poster's glow is never cut square. The hunt
  lands, and the poster grows, at the middle of that space, not at the screen's
  centre, the camera rising there over the same ease that stops the drift. At
  rest the poster fills that space at 2:3, the title, year and synopsis follow
  beneath it without a backdrop, and after 2.2 seconds the space scrolls gently
  to them. The poster at rest is the sharp 640 px picture when it has
  loaded, else a decoded copy of the wall's own picture of the film, replaced
  by the sharp picture when it arrives; with neither, no poster rests. A backdrop that fails is left out, and a phone fetches none.

  The pick's line is a quip from `data/quips.json` (section 2.7), served by
  `GET /api/quips` and read once per page load. When the lines cannot be
  read, the page logs a warning and its picks show no line. A pick draws from
  the category the first answer led to: its own lines, each set (reveal, nope)
  falling back separately to universal's; "Just pick one!" before a category draws universal. The
  film's own genres play no part. Each set deals like a shuffled deck, one
  deck per page load, and is reshuffled only when every line has been dealt.
  The line is set in Big Shoulders Display, scaling with the screen between
  28 px and 40 px, with four lines reserved, so the buttons beneath it stay in
  place from pick to pick. On a first pick Matinee's reply to the last answer
  types in gold, is read for 1 s before the hunt starts, and stays through the
  hunt; the reveal line, dealt to fit beneath it within the combined cap, types
  beneath it in the text colour as the poster grows. While the check runs, its
  line types beneath the reply, and goes once the check is done. A reply that
  self-destructs is the exception: its fuse owns the line. A pick with no reply
  before it (`Just pick one!`, "Roll again") shows no line during the hunt. On `Not that one` a nope line
  and a reveal line are dealt together within the combined cap: when a pair
  is over it, the longer line goes back unshown and its set deals the next
  that fits beside the other, then, if the pair is still over, the other is
  redealt the same way, and a set with no line left that fits gives its
  shortest line. The nope line types in gold at the tap and stays through the
  wait and the hunt, and the reveal line types beneath it in the text colour
  as the new poster grows. Where the check turned a film away, its reason
  types in gold in the nope line's place and stays, and only the reveal line
  is redealt to fit beneath it within the cap. DoesTheDogDie's credit is placed
  beneath the reason before it starts to type and stays through the hunt; on
  the resting page it moves beneath the buttons, joined by the "What were you
  going to show me?" link. The three-in-a-row and exhausted-pool lines likewise
  have their credit on screen before they type. A pick with no film speaks no quip.

  `Not that one` asks for the next film at the tap and carries the resting
  poster back from where it rests to its cell on the wall, at the wall's size
  and strength, over 0.45 s while the wall's dimming lifts (at once under
  reduced motion; with no poster at rest the dimming alone lifts over 0.45 s).
  The wall then drifts, and the returned poster rests in its cell, until the
  next film is known; the check's line does not type, and the nope line holds
  the screen. The next hunt starts
  from where the wall stands, by every rule above. "Roll again", after three
  films in a row were turned away, is a new pick: its check line types.
  `Just pick one` there is a new pick that checks nothing, so no check line
  types.

  A trail answer, the name tag or `Start over` ends the pick at the tap: the
  hunt stops where it is, the wall drifts again, and the pick changes nothing
  further. A film the hunt placed keeps its cell until the next pool's
  posters take over.

  While a DoesTheDogDie check runs, the page types "One moment. Let me check
  this one against your list." and the wall keeps drifting.

  The wall's geometry and re-sort plan, the hop plan and its speed limit, the
  glow colour and the quip deal are modules that touch no page. Their tests
  under `tests/js/` run with `node --test` from `./check.sh`.
- **The self-destructing reply.** When the last answer carries `self_destruct`
  (the spies answer, behind Thriller and behind Action),
  its reply types in gold as usual, then counts down on its own one-second
  clock, whatever the hunt is doing: a large gold number beneath the reply
  shows each second in turn, fading in and out in the same place. One second
  after the last number the reply burns away from the left, glowing orange,
  over 1.4 s, and leaves a dark scorch where it stood. The line holds no other
  text for that pick: the check's line does not type over it and no reveal line
  follows, so the film rests beneath the scorch. When the check turns a film
  away, the fuse is put out and the explanation types as usual. Under reduced
  motion the numbers change without fading and the reply goes at once, leaving
  the scorch. "Not that one" and every later pick speak as usual.
- **Credits.** The corner credit line reads "Posters and film data from TMDB
  [logo] · About", the logo linked to TMDB and "About" a button that opens the
  About page. It sits at the bottom right of the door, the question screens and
  the pick screen on a desktop (13 px), and centred at the foot on a phone
  (11 px). The TMDB logo is smaller than Matinee's own mark. MovieLens and
  DoesTheDogDie are not on the line: MovieLens is credited on the About page,
  and "Powered by DoesTheDogDie.com", linked, stands beside DoesTheDogDie's
  data wherever it shows (section 14).
- **About.** A screen inside the page, with no address of its own and no
  server route. It opens over whatever screen is showing, as a centred dark
  panel 65 per cent opaque over the poster wall, 1040 px wide on a desktop and
  the screen's width less a 16 px gutter each side on a phone, with no sideways
  scroll. The screen underneath, its credit line included, is hidden, never
  rebuilt or paused, so only the posters show through; it shows again exactly
  as it stood when About closes. Matinee's wordmark stands at the theatre
  wordmark's place: fixed from 1400 px wide up, and scrolling away with the page
  below that so it never sits over the text. About scrolls as a page when the panel
  is taller than the screen. "Back" at its top, the browser's Back, a phone's back gesture
  and Escape each close it and return the focus to the About link: opening it
  adds one history entry at the same address, and a second Back leaves the page
  rather than reopening About. The title is 68 px, the lead 23 px and the
  paragraphs 19 px (on a phone the title is at most 13 per cent of the screen's
  width, the lead 20 px and the paragraphs 17 px); section headings are gold,
  in the display face. The copy, in order: a lead; "Why it exists"; "How it
  knows what a film feels like", with links to MovieLens and the tag genome
  dataset and the two MovieLens citations; "How it steers around things", with
  "Powered by DoesTheDogDie.com", linked; and "Posters and film data", with the
  TMDB logo (14 px tall), linked, and TMDB's notice. It states no count that
  changes over time. Opened from inside, About moves nothing. Opened from the
  door, the name flies to the wordmark's place and the rest of the marquee lifts
  and fades, as on going in; the screen underneath is hidden once the name has
  landed, and the panel fades in 0.8 s after opening (at once under reduced
  motion). Closing it flies the name back to the sign, from wherever it is, and
  the marquee and the door's words return. From a phone's lit strip the name
  stands at the wordmark's place at once, and closing removes it.
- **Failures.** A failed request shows its message and "Try again". No stale
  film list is shown, with one exception: when the first question fails after
  the viewer goes in, the problem screen keeps the door's posters on the wall
  behind its message, the wordmark and "Try again", and a "Try again" that fails
  keeps them too. A "Try again" that succeeds shows the viewer's own pool. Every
  other problem screen empties the wall.
- **Installable.** A web app manifest (display fullscreen, falling back to
  standalone; start URL `/`; icons at 192 and 512 px, the 512 also maskable)
  lets the page install to a home screen. There is **no service worker.**
  Nothing is cached for offline use.

## 13. Deployment

- **One server process, one worker.** Every DoesTheDogDie limit, hold and
  remembered item id lives in the process (known gap 7). A second worker would
  double every limit.
- **The image** (`Dockerfile`) runs on `python:3.13-slim`. It installs the
  package editable, so it finds `data/` beside `src/` as a checkout does. It
  runs as an unprivileged user (uid 1000), with `uvicorn --factory
  matinee.web.main:build --workers 1` on port 8000 and no server header. It
  trusts forwarded headers from any address, so it must sit behind a reverse
  proxy. The image carries `tools/`, so the same image can run the nightly
  rebuild with `--daily`.
- **State** is one directory mounted at `/state` (`MATINEE_STATE`). It holds
  the film table (`films.sqlite`), Matinee's store (`matinee.sqlite`), the
  labels (`labels.json`, section 2.6), the TMDB cache (`tmdb/films.jsonl`) and
  the MovieLens genome (`ml-latest/`, or `MATINEE_ML`). None of it is in the
  image.
- **Settings and keys arrive as environment**, never committed, logged or sent
  to a browser. `.dockerignore` keeps `.env` files out of the image.

| Variable | Used by | Holds |
|---|---|---|
| `MATINEE_STATE` | server, rebuild | the state directory |
| `MATINEE_JELLYFIN_URL` | server, rebuild | the media server's address |
| `JELLYFIN_API_KEY` | server, rebuild | the media server's key |
| `MATINEE_SEERR_URL` | server | the base of the "More on Seerr" link |
| `DTDD_API_KEY` | server | the DoesTheDogDie key |
| `TMDB_READ_TOKEN` | rebuild | the TMDB read token |
| `MATINEE_ML` | rebuild | the genome directory, if not under the state directory |

## 14. Third-party terms

The terms of each source are part of the design.

- **TMDB.** Cached at most six months (section 5.2). The notice "This product
  uses the TMDB API but is not endorsed or certified by TMDB." appears on the
  About page. The TMDB logo appears there and in the corner credit line of the
  door, the question screens and the pick screen, less prominent than
  Matinee's own mark. TMDB data is non-commercial under the default licence.
- **MovieLens tag genome.** Credited on the About page to F. Maxwell Harper and
  Joseph A. Konstan (2015), *The MovieLens Datasets: History and Context*, and
  Jesse Vig, Shilad Sen and John Riedl (2012), *The Tag Genome: Encoding
  Community Knowledge to Support Novel Interaction*. The raw dataset is never
  committed. A derived table Matinee ships carries the dataset's own conditions:
  `data/reference.json` states them in its `licence` field (research and
  non-commercial use, no implied endorsement, redistribution only under the
  same conditions).
- **DoesTheDogDie.** Queried one film at a time, at the moment of a pick. Never
  fetched ahead, never used to build a score. Votes are never kept. The search's
  answer for a film, and the topic list, are remembered for at most 30 days, the
  refresh period the terms set for a performance cache (sections 8 and 9). "Powered by
  DoesTheDogDie.com", linked to `https://www.doesthedogdie.com`, appears
  wherever its data does: the trigger picker, the swap reason, the unchecked
  note and the exhausted pool. It also appears beside the three-in-a-row line
  and on the About page. The page gives the used-up line (section 9) the same
  credit, whether or not the viewer holds topics, because that line reaches the
  page in the same field as the exhausted pool's. Beside a line typed from its
  data, it is on screen before the line starts to type and stays while the line
  does. The corner credit line does not carry it. The free tier is
  non-commercial.

## 15. Out of scope

Not part of this build, and not to be added until asked:

- offering films the library does not hold (TMDB mode);
- a checker run over every film in the genome;
- a CLI or HTTP API for anyone but Matinee's own page;
- `Watch this`, or any hand-off to a player;
- thumbs up and thumbs down;
- personal modes learned from examples;
- a Plex reader;
- a TV layout;
- notes shared or pooled between installations;
- any administrative surface, including PIN reset;
- offline use of the installed page.

---

# Known gaps

Behaviour that is deliberately absent, still open, or short of the contract,
as the code stood on 2026-09-30.

**Short of the contract:**

1. **A profile needs nothing chosen to save.** `POST /api/profiles` accepts
   empty topics and exclusions, as the page's own picker does. Any caller may
   create profiles until the cap of 50 fills. (`src/matinee/web/app.py::add_door_routes`,
   `src/matinee/store.py::Store.create`)
2. **A film with no genres fails reachability.** It is not set apart as a
   metadata fault. (`tools/check_trees.py::check_reachability`)

**Deliberately absent or open:**

3. **No cap on notes per profile.** One held profile can file notes without
   bound. (`src/matinee/store.py::Store.note`)
4. **The per-device allowance is per cookie.** A client that discards
   `matinee_device` is issued a new one with a fresh allowance. The
   installation's hourly ceiling still bounds it. (`src/matinee/web/viewing.py:232`)
5. **"Slow" is timed per request, not per film.** A film lookup is two
   requests. Each may wait up to 3 seconds for its turn, then pause for the
   pacing allowance, then allow 3 seconds for an answer. One check can therefore
   take longer than 3 seconds before it counts as slow.
   (`src/matinee/dtdd.py:106`, `src/matinee/pick.py:142`)
6. **Names are compared after NFKC normalisation and case folding only.**
   Look-alike letters from other scripts count as different names. The refusal
   message says names are "letters, numbers or spaces". The rule accepts any
   printable character. (`src/matinee/store.py:127`,
   `src/matinee/web/common.py:18`)
7. **The allowances, holds, pacing, item ids and topic list live in memory.** A
   restart forgets every device's spent lookups, the hour's ceiling, any hold,
   every remembered item id and the kept topic list, and a second worker would
   double every limit.
   (`Dockerfile:1`)
8. **Validation failures use the framework's error shape.** A request body
   that fails validation answers 422 with `{"detail": [...]}`, not Matinee's
   `{"error", "message"}` shape. (`src/matinee/web/app.py:87`)
9. **The engine does not check that a shared kind holds the same films at every
   door.** The labelling pass writes it so; a labels file that breaks it still
   loads and serves. Only the offline checker catches it, as a failure.
   (`src/matinee/engine.py::_check_labels`, `tools/check_trees.py::check_shared_kinds`)
10. **A house pin may put a film behind a door under no kind.** Such a film is
    reached through "anything" only; the checker lists it but does not fail it.
    (`tools/check_trees.py::check_kinds`)
11. **An apart flavour no answer offers loads.** The loader checks only that
    the tree defines the flavour it holds apart. The server starts with such a
    tree, whose held-apart films no answer offers; only the checker's
    answer-coverage rule fails it.
    (`src/matinee/trees.py:301`)
12. **Nothing ties a kind to its answer's words.** An answer may filter on any
    labelled flavour of its tree, so an answer worded for heists that names the
    cops flavour loads and passes the checker. (`tools/check_trees.py::check_answer_coverage`)

**Short of the contract, in the page:**

13. **The door can be entered while About is open over it.** A late answer to
   the name lookup or a profile opening, or the keyboard reaching the door's
   controls during the name's flight, can take the viewer in behind the panel.
   Closing About then flies the full-size name back over the theatre.
   (`src/matinee/web/static/js/door.js::Door.bringBack`)
14. **The name's home on the sign is measured once.** A resize or a phone
    rotation while About is open over the door lands the returning name where
    the sign's letters stood before, not where they stand now.
    (`src/matinee/web/static/js/door.js::Door.leave`)

---

# Part 2 — Map

A pointer to where each part lives, never proof of what it does. Every entry was
verified against the source on the date in its row. Line numbers drift; search by the
symbol when one does not match.

### Boundaries and the library

| Handle | Where | Verified |
|---|---|---|
| `src/matinee/library/__init__.py::Library` | `src/matinee/library/__init__.py:44` | 2026-09-26 |
| `src/matinee/library/__init__.py::LibraryFilm` | `src/matinee/library/__init__.py:20` | 2026-09-26 |
| `src/matinee/library/jellyfin.py::JellyfinReader` | `src/matinee/library/jellyfin.py:63` | 2026-09-26 |
| `src/matinee/library/jellyfin.py::JellyfinReader.films` | `src/matinee/library/jellyfin.py:117` | 2026-09-26 |
| `src/matinee/library/jellyfin.py::JellyfinReader.image` (no key, size and type caps) | `src/matinee/library/jellyfin.py:98` | 2026-10-01 |
| `src/matinee/library/jellyfin.py::ITEM_ID` | `src/matinee/library/jellyfin.py:24` | 2026-09-26 |
| `src/matinee/library/jellyfin.py::parse_film` (`{tmdb-N}` folder tag) | `src/matinee/library/jellyfin.py:43` | 2026-09-26 |

### Conversation model

| Handle | Where | Verified |
|---|---|---|
| `data/first_question.json` (lines, answers, labels) | `data/first_question.json:3` | 2026-09-30 |
| `src/matinee/trees.py::parse_tree` | `src/matinee/trees.py:233` | 2026-09-30 |
| `src/matinee/trees.py::Tree.apart` (a flavour the tree does not define is refused) | `src/matinee/trees.py:85` | 2026-09-30 |
| `src/matinee/trees.py::Question.footnote` | `src/matinee/trees.py:73` | 2026-09-30 |
| `src/matinee/trees.py::SOLE_SIGNALS` / `_check_flavours` (`labelled`, `specials`, `always_shown`) | `src/matinee/trees.py:218` | 2026-09-30 |
| `src/matinee/trees.py::load_trees` (duplicate names refused) | `src/matinee/trees.py:253` | 2026-09-30 |
| `src/matinee/trees.py::FILTER_KEYS` / `OPTION_KEYS` / `QUESTION_KEYS` | `src/matinee/trees.py:88` | 2026-09-30 |
| `src/matinee/trees.py::parse_filter` | `src/matinee/trees.py:148` | 2026-09-30 |
| `src/matinee/engine.py::STOP_UNDER` | `src/matinee/engine.py:58` | 2026-09-30 |
| `src/matinee/engine.py::load_catalog` | `src/matinee/engine.py:363` | 2026-09-30 |
| `src/matinee/engine.py::_first_option` (label required) | `src/matinee/engine.py:307` | 2026-09-30 |
| `src/matinee/engine.py::first_question` | `src/matinee/engine.py:535` | 2026-09-30 |
| `src/matinee/engine.py::base_pool` (order of exclusions, topic skip) | `src/matinee/engine.py:398` | 2026-09-30 |
| `src/matinee/engine.py::walk` | `src/matinee/engine.py:483` | 2026-09-30 |
| `src/matinee/engine.py::_gate` (`only_if_pool_over`, `skip_if_topics`) | `src/matinee/engine.py:466` | 2026-09-30 |
| `src/matinee/engine.py::_shown` (empty answers hidden, `not_after`, small kinds hidden) | `src/matinee/engine.py:443` | 2026-09-30 |
| `src/matinee/engine.py::KIND_MIN_FILMS` | `src/matinee/engine.py:59` | 2026-09-30 |
| `src/matinee/engine.py::_too_small` (`always_shown`, a kind another answer leaves out) | `src/matinee/engine.py:338` | 2026-09-30 |
| `src/matinee/engine.py::_answer_masks` / `Catalog.small` | `src/matinee/engine.py:354` | 2026-09-30 |
| `src/matinee/engine.py::_hold_apart` / `Catalog.apart` | `src/matinee/engine.py:325` | 2026-09-30 |
| `src/matinee/engine.py::opening_pool` | `src/matinee/engine.py:424` | 2026-09-30 |
| `src/matinee/engine.py::_served` (apart films stay out until their answer) | `src/matinee/engine.py:432` | 2026-09-30 |
| `src/matinee/engine.py::_asked` / `Asked.footnote` (footnote and asterisks dropped with the apart answer) | `src/matinee/engine.py:453` | 2026-09-30 |
| `src/matinee/web/viewing.py::everything` (the first question's pool) | `src/matinee/web/viewing.py:172` | 2026-09-30 |
| `src/matinee/web/viewing.py::QuestionOut.footnote` | `src/matinee/web/viewing.py:82` | 2026-09-30 |
| `src/matinee/engine.py::_plain_mask` / `_range_mask` (unknown values pass) | `src/matinee/engine.py:255` | 2026-09-30 |
| `src/matinee/engine.py::walk_ends` / `reachable` | `src/matinee/engine.py:509` | 2026-09-30 |
| `data/trees/comedy.json` room question (ceilings) | `data/trees/comedy.json:7` | 2026-09-27 |
| `data/trees/comedy.json` kind question (standup answer, footnote), `standup` flavour, `apart` | `data/trees/comedy.json:49` | 2026-09-30 |
| `data/trees/thriller.json` kind question (spies `self_destruct`) | `data/trees/thriller.json:6` | 2026-09-30 |
| `data/trees/action.json`, `drama.json`, `scifi.json`, `fantasy.json`, `romance.json`, `animation.json`, `war.json` kind questions; `western.json` (no question) | `data/trees/action.json:6` | 2026-09-30 |
| `data/trees/kids.json` age and kind questions (labelled, always shown) | `data/trees/kids.json:6` | 2026-09-30 |
| `data/trees/crime.json` kind question | `data/trees/crime.json:6` | 2026-09-30 |
| `data/modes/fall-asleep.json` | `data/modes/fall-asleep.json:3` | 2026-09-26 |

### The checker

| Handle | Where | Verified |
|---|---|---|
| `tools/check_trees.py::main` | `tools/check_trees.py:498` | 2026-09-30 |
| `tools/check_trees.py::SAMPLES` | `tools/check_trees.py:67` | 2026-09-30 |
| `tools/check_trees.py::check_answer_coverage` | `tools/check_trees.py:295` | 2026-09-30 |
| `tools/check_trees.py::check_same_answers` | `tools/check_trees.py:324` | 2026-09-30 |
| `tools/check_trees.py::check_sample` | `tools/check_trees.py:353` | 2026-09-30 |
| `tools/check_trees.py::check_homes` | `tools/check_trees.py:341` | 2026-09-30 |
| `tools/check_trees.py::door_pools` (only doors are homes) | `tools/check_trees.py:116` | 2026-09-30 |
| `tools/check_trees.py::check_apart` | `tools/check_trees.py:122` | 2026-09-30 |
| `tools/check_trees.py::check_kinds` / `report_waiting` | `tools/check_trees.py:382` | 2026-09-30 |
| `tools/check_trees.py::check_hidden` | `tools/check_trees.py:452` | 2026-09-30 |
| `tools/check_trees.py::check_pins_in_key` | `tools/check_trees.py:241` | 2026-09-30 |
| `tools/check_trees.py::SPECIALS_KIND` (a `specials` pin's fixture) | `tools/check_trees.py:71` | 2026-09-30 |
| `tools/check_trees.py::check_gore` | `tools/check_trees.py:284` | 2026-09-30 |
| `tools/check_trees.py::check_lists` | `tools/check_trees.py:135` | 2026-09-30 |
| `tools/check_trees.py::check_data` | `tools/check_trees.py:488` | 2026-09-30 |
| `tools/check_trees.py::check_quips` | `tools/check_trees.py:478` | 2026-09-30 |
| `data/answer_key.json` list tags | `data/answer_key.json:3` | 2026-09-30 |
| `data/answer_key.json` `hidden` | `data/answer_key.json:18` | 2026-09-30 |

### The pick's lines

| Handle | Where | Verified |
|---|---|---|
| `data/quips.json` (caps, categories) | `data/quips.json:3` | 2026-09-30 |
| `src/matinee/quips.py::Quips` / `QuipSet` / `Caps` (universal must hold both sets) | `src/matinee/quips.py:43` | 2026-09-30 |
| `src/matinee/quips.py::load_quips` / `QuipsError` | `src/matinee/quips.py:61` | 2026-09-30 |
| `src/matinee/quips.py::quip_problems` / `line_problems` / `in_title_case` | `src/matinee/quips.py:90` | 2026-09-30 |
| `tests/test_quips.py::test_the_caps_are_the_measured_ones` | `tests/test_quips.py:24` | 2026-09-28 |

### Pools and reference statistics

| Handle | Where | Verified |
|---|---|---|
| `src/matinee/pools.py::build_pools` (labelled films, the waiting room and pins; comedy holds the specials) | `src/matinee/pools.py:187` | 2026-09-30 |
| `src/matinee/pools.py::SCORES` (the fall-asleep mode) | `src/matinee/pools.py:46` | 2026-09-30 |
| `src/matinee/pools.py::kids_bands` / `kids_band` / `CERTIFICATE_BANDS` | `src/matinee/pools.py:141` | 2026-09-30 |
| `src/matinee/pools.py::waiting` / `WAITING_ROOM` / `GENRE_DOORS` | `src/matinee/pools.py:180` | 2026-09-30 |
| `src/matinee/pools.py::standup_specials` | `src/matinee/pools.py:158` | 2026-09-30 |
| `src/matinee/pools.py::specials` (the rule plus `specials` pins) | `src/matinee/pools.py:175` | 2026-09-30 |
| `src/matinee/reference.py::reference_films` | `src/matinee/reference.py:140` | 2026-09-30 |
| `src/matinee/reference.py::compute_tree` | `src/matinee/reference.py:155` | 2026-09-30 |
| `src/matinee/reference.py::problems` | `src/matinee/reference.py:225` | 2026-09-30 |
| `src/matinee/reference.py::LICENCE` | `src/matinee/reference.py:28` | 2026-09-30 |
| `tools/build_reference.py::main` | `tools/build_reference.py:24` | 2026-09-30 |
| `data/reference.json` (horror gore cuts) | `data/reference.json:38` | 2026-09-30 |
| `tests/test_reference.py::test_shipped_reference_covers_every_tree` | `tests/test_reference.py:126` | 2026-09-30 |

### Scales and pins

| Handle | Where | Verified |
|---|---|---|
| `src/matinee/scales.py::scale_of` | `src/matinee/scales.py:44` | 2026-09-26 |
| `src/matinee/scales.py::film_scores` (bonus only with a genome entry) | `src/matinee/scales.py:65` | 2026-09-26 |
| `src/matinee/scales.py::band_index` | `src/matinee/scales.py:75` | 2026-09-26 |
| `src/matinee/scales.py::membership` (unscored bands, pins) | `src/matinee/scales.py:81` | 2026-09-26 |
| `src/matinee/engine.py::scale_members` | `src/matinee/engine.py:195` | 2026-09-30 |
| `data/trees/horror.json` gore scale | `data/trees/horror.json:38` | 2026-09-26 |
| `data/trees/horror.json` gore question, `skip_if_topics`, `treat_as` | `data/trees/horror.json:134` | 2026-09-27 |
| `data/trees/horror.json` labelled flavours (the kinds' rules) | `data/trees/horror.json:244` | 2026-09-30 |
| `src/matinee/labels.py::load_labels` (format 2; format 1 refused) / `Labels` / `TreeLabels` | `src/matinee/labels.py:75` | 2026-09-30 |
| `src/matinee/pools.py::load_house` / `House` (`House.specials`) | `src/matinee/pools.py:93` | 2026-09-30 |
| `src/matinee/engine.py::_check_labels` (unknown tree or kind refused) | `src/matinee/engine.py:313` | 2026-09-30 |
| `src/matinee/engine.py::house_flavour` (a `specials` flavour holds the standup specials) | `src/matinee/engine.py:171` | 2026-09-30 |
| `data/house_overrides.json` scale pins | `data/house_overrides.json:101` | 2026-09-30 |
| `data/house_overrides.json` `specials` pins | `data/house_overrides.json:79` | 2026-09-30 |

### Film table and nightly rebuild

| Handle | Where | Verified |
|---|---|---|
| `tools/rebuild_table.py::main` | `tools/rebuild_table.py:68` | 2026-09-26 |
| `tools/rebuild_table.py::rebuild` | `tools/rebuild_table.py:35` | 2026-09-26 |
| `src/matinee/tmdb.py::refresh` | `src/matinee/tmdb.py:134` | 2026-09-26 |
| `src/matinee/tmdb.py::REFETCH_AFTER` / `MAX_AGE` | `src/matinee/tmdb.py:28` | 2026-09-26 |
| `src/matinee/tmdb.py::compact` | `src/matinee/tmdb.py:82` | 2026-09-26 |
| `src/matinee/tmdb.py::load_cache` | `src/matinee/tmdb.py:64` | 2026-09-26 |
| `src/matinee/genome.py::load_genome` (links.csv join, stamped cache) | `src/matinee/genome.py:98` | 2026-09-26 |
| `src/matinee/table.py::build_table` / `BuildReport` | `src/matinee/table.py:164` | 2026-09-26 |
| `src/matinee/table.py::_genome_rows` (first MovieLens film wins) | `src/matinee/table.py:111` | 2026-09-26 |
| `src/matinee/table.py::write_table` | `src/matinee/table.py:253` | 2026-09-26 |
| `src/matinee/table.py::load_table` | `src/matinee/table.py:305` | 2026-09-26 |
| `src/matinee/table.py::check_age` | `src/matinee/table.py:292` | 2026-09-26 |
| `src/matinee/table.py::with_live` | `src/matinee/table.py:198` | 2026-09-26 |
| `src/matinee/web/theatre.py::Theatre.showing` (`LIVE_TTL`, `RETRY_AFTER`) | `src/matinee/web/theatre.py:69` | 2026-09-26 |

### Profiles, devices and notes

| Handle | Where | Verified |
|---|---|---|
| `src/matinee/store.py::MAX_PROFILES` and the other limits | `src/matinee/store.py:32` | 2026-09-26 |
| `src/matinee/store.py::Store.create` | `src/matinee/store.py:207` | 2026-09-26 |
| `src/matinee/store.py::Store.holding` | `src/matinee/store.py:238` | 2026-09-26 |
| `src/matinee/store.py::Store.suggest` | `src/matinee/store.py:251` | 2026-09-26 |
| `src/matinee/store.py::names_match` / `edits` | `src/matinee/store.py:157` | 2026-09-26 |
| `src/matinee/store.py::clean_name` / `clean_pin` | `src/matinee/store.py:131` | 2026-09-26 |
| `src/matinee/store.py::Store.open` / `_check_pin` (lockout) | `src/matinee/store.py:321` | 2026-09-26 |
| `src/matinee/store.py::Store._issue` (token pruning) | `src/matinee/store.py:199` | 2026-09-26 |
| `src/matinee/store.py::Store.note` / `Note` | `src/matinee/store.py:296` | 2026-09-26 |
| `src/matinee/web/common.py::set_tokens` / `TOKENS_COOKIE` / `MAX_TOKENS` | `src/matinee/web/common.py:81` | 2026-09-26 |
| `src/matinee/web/common.py::Suggestion` | `src/matinee/web/common.py:38` | 2026-09-26 |
| `src/matinee/web/viewing.py::held_profile` | `src/matinee/web/viewing.py:183` | 2026-09-30 |
| `src/matinee/web/viewing.py::resolve` | `src/matinee/web/viewing.py:197` | 2026-09-30 |
| `src/matinee/web/viewing.py::add_note_routes` / `answer_says` | `src/matinee/web/viewing.py:373` | 2026-09-30 |
| `src/matinee/web/viewing.py::banded` | `src/matinee/web/viewing.py:338` | 2026-09-30 |

### Exclusions and the DoesTheDogDie check

| Handle | Where | Verified |
|---|---|---|
| `data/exclusions.json` | `data/exclusions.json:4` | 2026-09-26 |
| `src/matinee/engine.py::_exclusion` | `src/matinee/engine.py:295` | 2026-09-30 |
| `src/matinee/web/viewing.py::check_exclusions` | `src/matinee/web/viewing.py:191` | 2026-09-30 |
| `src/matinee/dtdd.py::Dtdd.get` / `_pace` (`BURST`, `RATE_PER_S`) | `src/matinee/dtdd.py:106` | 2026-09-26 |
| `src/matinee/dtdd.py::Dtdd._check_holds` / `_refused` / `_note_remaining` (`REQUESTS_PER_HOUR`, `MONTH_RESERVE`, `RESERVE_HOLD_S`, `BACKOFF_S`) | `src/matinee/dtdd.py:123` | 2026-09-26 |
| `src/matinee/dtdd.py::Dtdd.topics` (`TOPICS_REFRESH_S`, `TOPICS_KEEP_S`) | `src/matinee/dtdd.py:178` | 2026-09-26 |
| `src/matinee/pick.py::failing` (`MIN_VOTES`) | `src/matinee/pick.py:74` | 2026-09-26 |
| `src/matinee/pick.py::ItemIds` (`ID_KEEP_S`) | `src/matinee/pick.py:114` | 2026-09-26 |
| `src/matinee/pick.py::look_up` (`LOOKUP_S`) | `src/matinee/pick.py:143` | 2026-09-26 |
| `src/matinee/pick.py::DeviceCap` (`LOOKUPS_PER_HOUR`) | `src/matinee/pick.py:179` | 2026-09-26 |
| `src/matinee/pick.py::candidates` | `src/matinee/pick.py:212` | 2026-09-26 |
| `src/matinee/engine.py::gentlest` | `src/matinee/engine.py:214` | 2026-09-30 |
| `src/matinee/pick.py::Picker.pick` (`PICK_TRIES`) | `src/matinee/pick.py:238` | 2026-09-30 |
| `src/matinee/web/viewing.py::device_id` / `DEVICE_COOKIE` | `src/matinee/web/viewing.py:232` | 2026-09-30 |
| `src/matinee/web/viewing.py::SWAP_LINE` / `UNCHECKED_LINES` / `EXHAUSTED` / `TIRED` | `src/matinee/web/viewing.py:207` | 2026-09-30 |
| `src/matinee/web/viewing.py::pick_pool` | `src/matinee/web/viewing.py:387` | 2026-09-30 |
| `src/matinee/web/viewing.py::add_pick_routes` | `src/matinee/web/viewing.py:397` | 2026-09-30 |

### Web surface

| Handle | Where | Verified |
|---|---|---|
| `src/matinee/web/main.py::build` (reads the quips) | `src/matinee/web/main.py:27` | 2026-09-28 |
| `src/matinee/web/config.py::from_env` | `src/matinee/web/config.py:47` | 2026-09-26 |
| `src/matinee/web/app.py::create_app` (docs disabled) | `src/matinee/web/app.py:238` | 2026-09-28 |
| `src/matinee/web/app.py::SECURITY_HEADERS` | `src/matinee/web/app.py:194` | 2026-09-28 |
| `src/matinee/web/app.py::add_page` | `src/matinee/web/app.py:206` | 2026-09-28 |
| `src/matinee/web/app.py::add_quip_routes` (`GET /api/quips`) | `src/matinee/web/app.py:231` | 2026-09-28 |
| `src/matinee/web/app.py::add_film_routes` / `IMAGE_WIDTHS` | `src/matinee/web/app.py:126` | 2026-10-01 |
| `src/matinee/web/app.py::held` | `src/matinee/web/app.py:86` | 2026-09-28 |
| `src/matinee/web/app.py::add_door_routes` | `src/matinee/web/app.py:159` | 2026-09-28 |
| `src/matinee/web/app.py::add_error_handlers` | `src/matinee/web/app.py:95` | 2026-09-28 |
| `src/matinee/web/common.py::Problem` | `src/matinee/web/common.py:102` | 2026-09-26 |
| `src/matinee/web/viewing.py::add_viewing_routes` | `src/matinee/web/viewing.py:269` | 2026-09-30 |
| `src/matinee/web/viewing.py::WalkIn` / `PickIn` (request caps) | `src/matinee/web/viewing.py:48` | 2026-09-30 |

### The page

| Handle | Where | Verified |
|---|---|---|
| `src/matinee/web/static/js/door.js::Door` | `src/matinee/web/static/js/door.js:107` | 2026-09-30 |
| `src/matinee/web/static/js/door.js::Door.open` (the marquee, the door's wall, the corner line) | `src/matinee/web/static/js/door.js:118` | 2026-09-30 |
| `src/matinee/web/static/js/door.js::Door.talk` (a question typed onto the wall) | `src/matinee/web/static/js/door.js:141` | 2026-09-30 |
| `src/matinee/web/static/js/door.js::Door.enter` (entered once) | `src/matinee/web/static/js/door.js:260` | 2026-09-30 |
| `src/matinee/web/static/js/door.js::Door.leave` / `settle` / `bringBack` (the marquee leaves and returns) | `src/matinee/web/static/js/door.js:271` | 2026-09-30 |
| `src/matinee/web/static/js/door.js::Door.picker` (sets the phone's lit strip) | `src/matinee/web/static/js/door.js:314` | 2026-09-30 |
| `src/matinee/web/static/js/door.js::Door.fillTopics` / `topicsTrouble` | `src/matinee/web/static/js/door.js:408` | 2026-09-30 |
| `src/matinee/web/static/js/door.js::sign` (frame, rules, name, live count) | `src/matinee/web/static/js/door.js:78` | 2026-09-30 |
| `src/matinee/web/static/js/door.js::bulbs` / `ringAt` | `src/matinee/web/static/js/door.js:48` | 2026-09-30 |
| `src/matinee/web/static/js/door.js::time` (the two-bulb chase's start) | `src/matinee/web/static/js/door.js:36` | 2026-09-30 |
| `src/matinee/web/static/js/door.js::BULBS` / `CHASE_S` | `src/matinee/web/static/js/door.js:14` | 2026-09-30 |
| `src/matinee/web/static/js/flight.js::fly` (`FLIGHT_MS`, the fail-open) | `src/matinee/web/static/js/flight.js:63` | 2026-09-30 |
| `src/matinee/web/static/js/flight.js::nameAt` / `wordmarkAt` / `riseOf` / `copyAt` | `src/matinee/web/static/js/flight.js:14` | 2026-09-30 |
| `src/matinee/web/static/js/about.js::openAbout` | `src/matinee/web/static/js/about.js:111` | 2026-09-30 |
| `src/matinee/web/static/js/about.js::close` (popstate; Escape steps back) | `src/matinee/web/static/js/about.js:94` | 2026-09-30 |
| `src/matinee/web/static/js/about.js::copy` (the About page's words and links) | `src/matinee/web/static/js/about.js:21` | 2026-09-30 |
| `src/matinee/web/static/js/wall-grid.js::posterAcross` / `ACROSS` / `GAP` | `src/matinee/web/static/js/wall-grid.js:27` | 2026-09-28 |
| `src/matinee/web/static/js/wall-grid.js::wallLayout` | `src/matinee/web/static/js/wall-grid.js:37` | 2026-09-28 |
| `src/matinee/web/static/js/wall-grid.js::bestStride` / `repeatDistance` | `src/matinee/web/static/js/wall-grid.js:61` | 2026-09-28 |
| `src/matinee/web/static/js/wall-grid.js::filmIndex` / `nearestCell` / `filmAt` | `src/matinee/web/static/js/wall-grid.js:71` | 2026-09-28 |
| `src/matinee/web/static/js/wall-grid.js::pictureSize` | `src/matinee/web/static/js/wall-grid.js:89` | 2026-10-01 |
| `src/matinee/web/static/js/wall-grid.js::rankPool` (the page's order) | `src/matinee/web/static/js/wall-grid.js:98` | 2026-09-28 |
| `src/matinee/web/static/js/wall-grid.js::resortAnchor` | `src/matinee/web/static/js/wall-grid.js:141` | 2026-09-28 |
| `src/matinee/web/static/js/wall-grid.js::resortPlan` | `src/matinee/web/static/js/wall-grid.js:168` | 2026-09-28 |
| `src/matinee/web/static/js/hunt-plan.js::HOP_TABLE` / `hopCount` | `src/matinee/web/static/js/hunt-plan.js:7` | 2026-09-28 |
| `src/matinee/web/static/js/hunt-plan.js::hopOffset` (the tick) / `TICK_PX` | `src/matinee/web/static/js/hunt-plan.js:58` | 2026-09-28 |
| `src/matinee/web/static/js/hunt-plan.js::peakStep` / `limitedTime` (the speed limit) | `src/matinee/web/static/js/hunt-plan.js:65` | 2026-09-28 |
| `src/matinee/web/static/js/hunt-plan.js::settledCamera` | `src/matinee/web/static/js/hunt-plan.js:96` | 2026-09-28 |
| `src/matinee/web/static/js/hunt-plan.js::planHunt` (first hop, no reversal) | `src/matinee/web/static/js/hunt-plan.js:118` | 2026-09-28 |
| `src/matinee/web/static/js/hunt-plan.js::hopCell` / `placeLanding` | `src/matinee/web/static/js/hunt-plan.js:138` | 2026-09-28 |
| `src/matinee/web/static/js/glow.js::posterGlow` / `GOLD` | `src/matinee/web/static/js/glow.js:19` | 2026-09-28 |
| `src/matinee/web/static/js/quips.js::setFor` | `src/matinee/web/static/js/quips.js:9` | 2026-09-30 |
| `src/matinee/web/static/js/quips.js::Deck` | `src/matinee/web/static/js/quips.js:19` | 2026-09-30 |
| `src/matinee/web/static/js/quips.js::dealPair` / `dealBeneath` | `src/matinee/web/static/js/quips.js:51` | 2026-09-30 |
| `src/matinee/web/static/js/wall.js::Wall` | `src/matinee/web/static/js/wall.js:84` | 2026-09-28 |
| `src/matinee/web/static/js/wall.js::Wall.show` / `fadeIn` / `clear` / `whenStill` | `src/matinee/web/static/js/wall.js:127` | 2026-10-01 |
| `src/matinee/web/static/js/wall.js::Wall.endPick` | `src/matinee/web/static/js/wall.js:181` | 2026-09-28 |
| `src/matinee/web/static/js/wall.js::Wall.hunt` / `jump` / `readyToHunt` / `settle` / `hop` | `src/matinee/web/static/js/wall.js:227` | 2026-10-01 |
| `src/matinee/web/static/js/wall.js::Wall.stepBack` / `grownScale` | `src/matinee/web/static/js/wall.js:326` | 2026-09-28 |
| `src/matinee/web/static/js/wall.js::Wall.useSharp` (the front element) | `src/matinee/web/static/js/wall.js:351` | 2026-09-28 |
| `src/matinee/web/static/js/wall.js::Wall.bringForward` | `src/matinee/web/static/js/wall.js:370` | 2026-09-28 |
| `src/matinee/web/static/js/wall.js::Wall.dress` / `glowShadow` / `glowAt` | `src/matinee/web/static/js/wall.js:392` | 2026-09-29 |
| `src/matinee/web/static/js/wall.js::glowOf` | `src/matinee/web/static/js/wall.js:55` | 2026-09-28 |
| `src/matinee/web/static/js/wall.js::Wall.putBack` / `returnPoster` / `liftDim` / `settleBack` | `src/matinee/web/static/js/wall.js:439` | 2026-09-28 |
| `src/matinee/web/static/js/wall.js::Wall.relayout` / `makeTiles` | `src/matinee/web/static/js/wall.js:539` | 2026-09-28 |
| `src/matinee/web/static/js/wall.js::Wall.prepare` (the re-sort's wait) | `src/matinee/web/static/js/wall.js:572` | 2026-10-01 |
| `src/matinee/web/static/js/wall.js::Wall.frame` (the drift, `DRIFT_PX_S`) | `src/matinee/web/static/js/wall.js:592` | 2026-09-28 |
| `src/matinee/web/static/js/wall.js::Wall.place` / `lay` / `picture` / `request` (`BLANK`) | `src/matinee/web/static/js/wall.js:603` | 2026-09-28 |
| `src/matinee/web/static/js/wall.js::Wall.resort` / `slide` / `depart` | `src/matinee/web/static/js/wall.js:683` | 2026-09-28 |
| `src/matinee/web/static/js/main.js::lockStage` / `leaveTo` / `nameTag` | `src/matinee/web/static/js/main.js:56` | 2026-09-30 |
| `src/matinee/web/static/js/main.js::trail` / `lastCrumb` | `src/matinee/web/static/js/main.js:101` | 2026-10-01 |
| `src/matinee/web/static/js/main.js::frame` / `ask` (the footnote) | `src/matinee/web/static/js/main.js:121` | 2026-09-30 |
| `src/matinee/web/static/js/main.js::start` | `src/matinee/web/static/js/main.js:213` | 2026-09-30 |
| `src/matinee/web/static/js/main.js::goTo` / `step` | `src/matinee/web/static/js/main.js:242` | 2026-10-01 |
| `src/matinee/web/static/js/main.js::checking` / `fadeTalk` (`READ_MS`) | `src/matinee/web/static/js/main.js:293` | 2026-09-30 |
| `src/matinee/web/static/js/main.js::pickLines` | `src/matinee/web/static/js/main.js:325` | 2026-09-30 |
| `src/matinee/web/static/js/main.js::clearForPick` / `requestPick` / `openPick` | `src/matinee/web/static/js/main.js:340` | 2026-09-30 |
| `src/matinee/web/static/js/main.js::pickNow` (`notThatOne`, `rollAgain`, `justPick`) | `src/matinee/web/static/js/main.js:384` | 2026-09-30 |
| `src/matinee/web/static/js/main.js::enter` (the start asked at the tap, the question after the landing) | `src/matinee/web/static/js/main.js:203` | 2026-09-30 |
| `src/matinee/web/static/js/main.js::topbar` (settles a landed name) | `src/matinee/web/static/js/main.js:70` | 2026-09-30 |
| `src/matinee/web/static/js/main.js::problem` (`keep`: the failed start's posters) | `src/matinee/web/static/js/main.js:176` | 2026-09-30 |
| `src/matinee/web/static/js/pick.js::showPick` / `huntLift` | `src/matinee/web/static/js/pick.js:249` | 2026-10-01 |
| `src/matinee/web/static/js/pick.js::goldLine` | `src/matinee/web/static/js/pick.js:194` | 2026-09-30 |
| `src/matinee/web/static/js/pick.js::bringOut` | `src/matinee/web/static/js/pick.js:227` | 2026-09-30 |
| `src/matinee/web/static/js/pick.js::toRest` (`BEAT_MS`, `STILL_HOLD_MS`) | `src/matinee/web/static/js/pick.js:272` | 2026-09-30 |
| `src/matinee/web/static/js/pick.js::fetchFilm` / `picture` | `src/matinee/web/static/js/pick.js:285` | 2026-09-30 |
| `src/matinee/web/static/js/pick.js::restingPoster` | `src/matinee/web/static/js/pick.js:177` | 2026-09-30 |
| `src/matinee/web/static/js/pick.js::rest` | `src/matinee/web/static/js/pick.js:155` | 2026-10-01 |
| `src/matinee/web/static/js/pick.js::settle` / `fit` | `src/matinee/web/static/js/pick.js:43` | 2026-09-30 |
| `src/matinee/web/static/js/fuse.js::lightFuse` / `fuseTimeline` | `src/matinee/web/static/js/fuse.js:37` | 2026-09-30 |
| `src/matinee/trees.py::_self_destruct` / `_one_self_destruct` | `src/matinee/trees.py:178` | 2026-09-30 |
| `src/matinee/web/static/js/pick.js::feature` | `src/matinee/web/static/js/pick.js:66` | 2026-09-30 |
| `src/matinee/web/static/js/pick.js::choices` | `src/matinee/web/static/js/pick.js:142` | 2026-09-30 |
| `src/matinee/web/static/js/pick.js::showNoFilm` | `src/matinee/web/static/js/pick.js:117` | 2026-09-30 |
| `src/matinee/web/static/js/pick.js::firstPickReveal` | `src/matinee/web/static/js/pick.js:92` | 2026-09-30 |
| `src/matinee/web/static/js/pick.js::creditBeneath` (DoesTheDogDie's credit before its line types) | `src/matinee/web/static/js/pick.js:84` | 2026-09-30 |
| `src/matinee/web/static/js/note.js::GATED_NOTE` | `src/matinee/web/static/js/note.js:9` | 2026-10-02 |
| `src/matinee/web/static/js/note.js::noteLink` | `src/matinee/web/static/js/note.js:62` | 2026-10-02 |
| `src/matinee/web/static/js/credits.js::credits` | `src/matinee/web/static/js/credits.js:23` | 2026-09-30 |
| `src/matinee/web/static/js/credits.js::aboutLink` | `src/matinee/web/static/js/credits.js:18` | 2026-09-30 |
| `src/matinee/web/static/js/dom.js::h` (text nodes only) | `src/matinee/web/static/js/dom.js:12` | 2026-09-26 |
| `src/matinee/web/static/js/type.js::typeLine` (`shown`: a gold line kept while the rest types beneath) | `src/matinee/web/static/js/type.js:11` | 2026-09-28 |
| `src/matinee/web/static/manifest.webmanifest` | `src/matinee/web/static/manifest.webmanifest:1` | 2026-09-26 |
| `src/matinee/web/static/css/matinee.css` reduced-motion rules (the marquee and the door's words change at once) | `src/matinee/web/static/css/matinee.css:931` | 2026-09-30 |
| `src/matinee/web/static/css/matinee.css` `.wall`, `.wall-tiles`, `.tile` (`--tile`, the one strength; the dark cell) | `src/matinee/web/static/css/matinee.css:97` | 2026-09-30 |
| `src/matinee/web/static/css/matinee.css` `.marquee` (its measures as properties, the top fade, the short windows' scaling) | `src/matinee/web/static/css/matinee.css:963` | 2026-09-30 |
| `src/matinee/web/static/css/matinee.css` `.marquee.lifted`, `.stage.leaving`, `.flying-name` (going in) | `src/matinee/web/static/css/matinee.css:993` | 2026-09-30 |
| `src/matinee/web/static/css/matinee.css` `.sign`, `.bulb`, `@keyframes chase` | `src/matinee/web/static/css/matinee.css:1167` | 2026-09-30 |
| `src/matinee/web/static/css/matinee.css` `.door-wall`, `.door-talk`, `.door-foot` | `src/matinee/web/static/css/matinee.css:1504` | 2026-09-30 |
| `src/matinee/web/static/css/matinee.css` `.picker` | `src/matinee/web/static/css/matinee.css:1627` | 2026-09-30 |
| `src/matinee/web/static/css/matinee.css` phone door: `.marquee` sizes, `.marquee.compact` (the lit strip) | `src/matinee/web/static/css/matinee.css:1810` | 2026-09-30 |
| `src/matinee/web/static/css/matinee.css` `.credits`, `.tmdb-logo`, `.bottombar .credits`, `.inline-link` | `src/matinee/web/static/css/matinee.css:1317` | 2026-09-30 |
| `src/matinee/web/static/css/matinee.css` `.stage.behind-about`, `.about`, `.about-wordmark`, `.about-panel` | `src/matinee/web/static/css/matinee.css:1358` | 2026-09-30 |
| `src/matinee/web/static/css/matinee.css` `.pick-line` (size, four lines reserved), `.hushed` | `src/matinee/web/static/css/matinee.css:490` | 2026-09-30 |
| `src/matinee/web/static/css/matinee.css` `.talk > .footnote` | `src/matinee/web/static/css/matinee.css:358` | 2026-09-30 |
| `src/matinee/web/static/blank.svg` (a tile with no picture) | `src/matinee/web/static/blank.svg:1` | 2026-09-28 |

### Deployment

| Handle | Where | Verified |
|---|---|---|
| `Dockerfile` (one worker, uid 1000, `/state`) | `Dockerfile:1` | 2026-09-26 |
| `.dockerignore` | `.dockerignore:1` | 2026-09-26 |
