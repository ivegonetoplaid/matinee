---
purpose: The contract Matinee's first build holds to — the conversation model, the pools and scales, the offline film table, profiles, exclusions, the DoesTheDogDie check, corrections, the web surface, the page, deployment and third-party terms — with a map of where each part lives.
updated: 2026-09-26
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
   and corrections live in Matinee's store. None of it reaches a media server.
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
"Right this way, <name>.". The answers, their order and the tree or mode each
leads to are data in `data/first_question.json`:

| Answer | Leads to | Label |
|---|---|---|
| I want to be scared. | `horror` | Horror |
| I need a laugh. | `comedy` | Comedy |
| Get my heart pumping. | `action` | Action |
| Keep me on the edge of my seat. | `thriller` | Thriller |
| Give me a story that sticks with me. | `drama` | Drama |
| Take me somewhere else. | `fantasy` | Fantasy and adventure |
| I'm in a cowboy mood. | `western` | Western |
| Tell me something true. | `nonfiction` | Non-fiction |
| Just someone funny with a mic. | `standup` | Standup |
| Something for the kids. | `kids` | Kids |
| Something I can fall asleep to. | `fall-asleep` (a mode) | Something to fall asleep to |

- An answer is shown only when its tree or mode holds at least one film for this
  viewer, after the viewer's corrections and exclusions.
- Every answer must carry a `label`. The engine refuses to load a first question
  whose answer lacks one. The label names the tree where a short name is needed,
  such as the correction panel.
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
| `trees/comedy.json` | comedy | room (certificate ceilings); kind (labels; animated by genre; section 2.3) |
| `trees/action.json` | action | payoff; thrill |
| `trees/thriller.json` | thriller | payoff |
| `trees/drama.json` | drama | payoff |
| `trees/fantasy.json` | fantasy | payoff |
| `trees/western.json` | western | payoff |
| `trees/kids.json` | kids | age; kind |
| `trees/nonfiction.json` | nonfiction | none; it rolls from the whole pool |
| `trees/standup.json` | standup | none; it rolls from the whole pool |
| `modes/fall-asleep.json` | sleep | none; it rolls from the whole pool |

Loading is strict:

- Question, answer, filter, flavour and payoff-rule keys are checked against
  the set the engine reads. A misspelt key fails at load. It never reads as
  absent and silently widens a pool.
- Two tree or mode files with the same name are refused.
- A tree file must name its `pool` and its `opening` line.
- A tree naming a pool no pool rule builds is refused.
- `sequel` may only be `false`. `sort` may only be `rating`. `kids_band` must be
  `little`, `family` or `older`. `treat_as` must name an answer the question has.

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
| `flavour` | Films in a named flavour the tree defines: matched by keyword, genome or genre, or read from the labels |
| `flavour_none` | Films outside a named flavour, plus films also in another flavour of the tree (house pins included) |
| `payoff` | Films placed on a named payoff (see below) |
| `bands` | Films in any of the listed bands of a named scale (see section 4) |
| `score_at_most`, `score_above` | Films whose named score is at or below, or above, a value |
| `kids_band` | Films the kids tree offers to that age band |
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

**Flavours.** A flavour matches a film when any of its keywords, genome tags
(at the tree's genome threshold) or genres match. A flavour may also set
`score_at_least`: a film then matches only when each named score reaches its
floor, and a film with no score passes the floor. A flavour marked `labelled`
takes no signals: its films are those the labels file names with it (section
2.6). An answer leaving a flavour out keeps every film that also sits in another
flavour of the tree.

Horror's flavours are all labelled: supernatural, killers, monsters, slowburn,
comedy and found_footage. A film may sit in two. A film played mainly for laughs
is labelled comedy alone unless its horror is played straight, so it reaches
only the comedy answer. "anything scary" leaves comedy out, so it keeps every
horror film except those labelled comedy and nothing else. A horror film
labelled with no kind, or not yet labelled, is reached through "anything scary"
and `Just pick one!`.

Comedy's flavours are labelled except animated, which is every film carrying
TMDB's Animation genre; its labels give an animated film no other kind, so an
animated comedy sits only under animated. The labelled kinds are slapstick,
feelgood, dark, action, horror, teen and romcom. Its horror kind holds the
horror tree's comedy films, so both trees offer the same horror comedies, and
each is labelled into both. "anything" has no filter.

**Payoffs.** A payoff score is the mean genome relevance of its tags,
standardised with the reference mean and standard deviation for that tree
(section 3). A film belongs to its strongest payoff. Where the tree sets an
overlap, it also belongs to every other payoff whose standardised score reaches
that overlap. The overlap is 0.75 in the drama, fantasy, kids, thriller and
western trees. The action tree sets none, so an action film has one payoff.
A payoff may instead be a raw threshold that never counts as strongest: the
kids tree's spooky answer needs a spooky score of at least 0.30. A film with no
genome entry is placed by its genre where the tree lists genres (the western and
kids trees). A film with no genome entry that matches none of those genres goes
to the tree's default. In the western tree that is the big-sky answer.
Everywhere else it is every standardised payoff. A house payoff pin moves a
film onto the pinned payoff and off every other.

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
- An answer marked `not_after` is hidden when the viewer gave a named earlier
  answer.
- An answer that does not fit the question being asked is refused. The page is
  told to start over.
- Pool counts never include DoesTheDogDie exclusions. Those are checked only at
  the pick (section 9).
- **`Just pick one!`** is on screen from the first question onward, as the last
  choice beneath each question's answers. It ends the questions and picks from
  the pool as it stands. Pressed at the first question,
  it picks from every film some first answer offers this viewer.
- **The trail.** On each question after the first, and on the pick screen, the
  page lists the viewer's answers so far, first to last, in gold at the bottom
  centre. Choosing one asks its question again
  and forgets every answer after it; choosing the first returns to the first
  question.

### 2.5 Every film stays reachable

Every film in the library must be reachable through at least one complete path
of answers in some tree or mode, and through a tree its own genres point at.
`tools/check_trees.py` holds the trees to this. It reads the film table the
nightly rebuild writes, builds every tree through the engine, and fails, with a
non-zero exit, on any of these:

1. **Data.** A library film has no usable TMDB facts. The franchise and standup
   rules cannot see such a film.
2. **First question.** An answer leads to no tree or mode file.
3. **Answer coverage.** A film in a tree's pool is reached by no complete path
   of that tree's answers, or a path ends on no film. It also reports how many
   questions each tree asks.
4. **House pins.** A pin has no answer-key fixture asserting the pinned
   placement.
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
7. **Lists.** A film carrying a famous-list genome tag is not reachable through
   its own genres. The tags are `afi 100`, `afi 100 (laughs)`, `imdb top 250`,
   `oscar (best picture)`, `criterion`, `golden palm` and `cult classic`, read at
   relevance 0.8 or above, except `afi 100 (laughs)` at 0.5. No copy of any
   published list is kept. Lists never filter, rank or gate what Matinee offers.
8. **Expected homes and reachability.** A film is reachable through no tree its
   own genres point at, or through no tree at all.
9. **Smaller libraries.** The same trees are rebuilt against a random third of
   the library (seed 3) and a random tenth (seed 10). Each must keep every film
   reachable. A film both libraries hold in a tree's pool must reach the same
   answers of that tree in both. Fixtures are checked on the full library only.

Separately, the engine refuses to prepare when the shipped reference statistics
do not cover the tree files (section 3). The checker reports that as a failure.
The checker reads the labels file beside the film table unless `--labels` names
another, and reports each film labelled out of a tree but kept there for having
no other home.

### 2.6 Labels

A tree may take its kinds from a labels file instead of from signals. The file
is `labels.json` in the state directory. It is written outside Matinee and never
committed, because it lists the films one library holds. Its shape:

```json
{"format": 1,
 "trees": {"horror": {"kinds": {"238": ["supernatural", "slowburn"], "431": []},
                      "out": [617505]}}}
```

- `kinds` maps a TMDB id to the kinds the film clearly fits. An empty list means
  the film was labelled and fits no kind. Every film in `kinds` joins the tree's
  pool, whatever the pool rules said: a horror comedy the rules sent to comedy
  alone is in horror too once labelled.
- A film absent from `kinds` is unlabelled and sits under no kind.
- `out` lists films carrying the tree's genre that belong elsewhere. Such a film
  leaves the tree's pool only when another tree's pool holds it; otherwise it
  stays, so no film loses its way in.
- An absent file means no film is labelled, and the server logs a warning. A
  malformed file, a tree no file defines, or a kind the tree does not label
  stops the server at start-up.
- The server reads the file once at start-up. Replacing it takes a restart.

The horror labels were written by a language model against one rule per kind,
with the operator's calls laid over them. The kinds' rules are the `note` of
each flavour in `data/trees/horror.json`.

## 3. Pools and reference statistics

### 3.1 Which films a tree holds

Pools are built once per film table, before any question is asked. The rule is
inclusive. A tree takes every film carrying its genre. A film leaves a tree
only when its score for the tree's own effect is under the tree's floor **and**
it has another home.

| Tree | Starts from | Leaves when |
|---|---|---|
| horror | Horror | fear under 0.20 and tagged Comedy; or a young kids film |
| comedy | Comedy | a standup special; or kids-only |
| action | Action; any of Adventure, Thriller, Crime, Mystery, Science Fiction or War with excitement at 0.60 or above; Adventure with no genome entry | excitement under 0.30 and tagged Comedy; or kids-only |
| thriller | Thriller or Mystery with tension at 0.20 or above, or no genome entry | a young kids film; or kids-only |
| drama | Drama, plus every unclaimed stray | weight under 0.13 and tagged Comedy; or kids-only |
| fantasy | Fantasy or Adventure with wonder or explore at 0.45 or above; Fantasy with no genome entry | kids-only |
| western | Western | kids-only |
| nonfiction | Documentary | a standup special; or kids-only |
| standup | standup specials, plus films pinned to standup | — |
| kids | the gated kids pool (below) | — |
| sleep | enchantment at 0.55 or above and edge under 0.40; a film with no genome entry is never in it | — |

- **A missing score never removes a film.** A film with no genome entry is never
  under a floor.
- **Scores** are mean genome relevance of fixed tag lists. Fear: scary,
  frightening, creepy, horror. Excitement: action, action packed, good action.
  Tension: tense, suspense, suspenseful, intense. Weight: drama, dramatic,
  emotional, moving, touching, harsh. Wonder: fantasy world, magic, fantasy,
  mythology, fairy tale, imagination, dragons, wizards. Explore: treasure,
  treasure hunt, pirates, archaeology, jungle, island. Enchantment: fairy tale,
  childhood, fantasy, whimsical, magic, fantasy world, fairy tales. Edge:
  violent, gore, disturbing, tense, brutal.
- **Standup specials.** A title is a standup special when it carries the TMDB
  keyword `stand-up comedy`, or when it is tagged Comedy and either is a TV Movie
  carrying `comedian`, `concert` or `concert film`, or carries `comedian` and a
  concert keyword together. A concert keyword alone never marks a special.
  Unknown TMDB keywords never mark a special.
- **Strays.** A stray is a film tagged Crime, Mystery, Thriller, Romance, War,
  History, Music, Science Fiction, Fantasy or Adventure that no horror, comedy,
  action, fantasy or thriller pool holds, that no house tree pin places, and
  that is not kids-only. A stray joins each of those five trees that holds
  another film of its TMDB collection. Membership is read before any stray is
  added, so it never chains. A stray still unclaimed joins drama.
- **House tree pins** add single films to a tree after every rule above.

### 3.2 The kids pool

The kids pool is gated and fails closed. A film enters when one of these holds:

- tagged Animation or Family, with a certificate of G, PG, TV-Y, TV-Y7, TV-G,
  TV-PG or E;
- tagged Animation or Family, certificate PG-13 or TV-14, either tagged Family
  or animation without a Comedy tag, and adult signal under 0.40;
- not tagged Animation or Family, a certificate from the first list, and a young
  score of 0.50 or above;
- in the same TMDB collection as a film that entered by the rules above, with a
  certificate from the first list or PG-13 or TV-14, and adult signal under
  0.40 (a film that joins this way does not pass it on);
- pinned to a kids band in the house list.

Any other certificate, including an absent one, enters only by a pin. The pool
splits into three bands, each allowing rather than requiring:

| Band | Holds |
|---|---|
| little | G, TV-Y, TV-Y7, TV-G or E; fright under 0.30; adult signal under 0.25; not pinned to older |
| family | the pool, less rough films |
| older | the whole pool |

A film is rough when its fright is 0.45 or above, its certificate is PG-13 or
TV-14, or it is pinned to the older band. Young: kids, children, cute, cute!,
talking animals. Fright: scary, creepy, dark fantasy. Adult signal is the
highest of foul language; sex, sexual, sex comedy and the nudity tags; crude
humor and gross-out; and drugs. An unknown fright or adult signal never counts
against a film.

A **young kids film** is tagged Animation or Family and offered to the little or
family band. A **kids-only** film is a young kids film with no genome entry.

### 3.3 Reference statistics

Every score means the same in every library. Matinee scores films against a
fixed reference drawn from films in general, never against the library it
reads.

- A tree file's `reference` names its MovieLens genres and a score floor. Its
  reference films are every film in the MovieLens ml-latest genome carrying one
  of those genres and reaching any one floor, inclusive. A tree with no floor
  writes `"floor_any": {}`.
- `tools/build_reference.py` measures, over each tree's reference films, the mean
  and population standard deviation of every payoff, and the cut points of every
  scale by linear interpolation. It rounds to six places and writes
  `data/reference.json`, named by the dataset's own generation date. The same
  release and tree files always produce the same file.
- Matinee reads that file at runtime and never recomputes it from a library.
- The engine refuses to prepare, and the server refuses to start, when the file
  is absent or does not cover a tree file: a missing tree, different genres or
  floor, or a payoff or scale that is missing or has other tags or percentiles.
  A test in `./check.sh` fails in the same case, so a changed tree file cannot
  ship with stale statistics.

| Tree | Reference genres | Floor | Reference films |
|---|---|---|---|
| action | Action | excitement ≥ 0.30 | 1,958 |
| drama | Drama | weight ≥ 0.13 | 6,901 |
| fantasy | Fantasy or Adventure | wonder or explore ≥ 0.45 | 381 |
| horror | Horror | fear ≥ 0.20 | 1,572 |
| kids | Children or Animation | none | 1,505 |
| thriller | Thriller or Mystery | tension ≥ 0.20 | 2,871 |
| western | Western | none | 302 |

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
| `kids` | in the kids pool, in the named band |
| `trees` | in a tree's pool (a film pinned to standup also leaves comedy and non-fiction) |
| `payoffs` | on one payoff of one tree, and off its others |
| `scales` | in one band of one scale, and out of its others |
| `flavours` | in one flavour of one tree (`member` true) or out of it (`member` false) |

A film pinned into a flavour stays in every answer that leaves another flavour
out. A funny horror film pinned into monsters is therefore offered under the
comedy answer and under the scary ones.

Every pin must also be an answer-key fixture asserting the pinned placement. The
checker fails otherwise, so a later rule change cannot silently undo a pin.
Personal corrections (section 10) apply on top of house pins.

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
- the labels file is malformed, or names a tree no file defines or a kind its
  tree does not label.

## 6. What one viewer's pool is

For each tree, the viewer's starting pool is built in this order:

1. The tree's pool, with house pins already applied.
2. The viewer's corrections for that tree, oldest first, so a later one wins.
3. Matinee's own exclusions the viewer holds remove every film they match. A
   correction can never bring back an excluded film.
4. Every question the viewer's DoesTheDogDie topics skip applies its `treat_as`
   answer.

Answers narrow that pool from there (section 2.4).

## 7. Viewers, profiles and devices

Matinee has no accounts and no login. A viewer is either a **profile** this
device holds a token for, or a **visitor** whose choices travel with each
request and end with the visit.

| Rule | Value |
|---|---|
| A profile holds | a display name, an optional four-digit PIN, DoesTheDogDie topics, Matinee's own exclusions, and corrections |
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
- A token for a deleted profile is ignored. The box office clears it from the
  cookie.
- There is no PIN reset and no administrative surface. Whoever runs the
  installation clears a forgotten PIN in Matinee's store.
- A request naming a profile (the first question, a walk, a pick, saving
  exclusions or saving a correction) is refused with 403 unless this device
  holds a token for it.

## 8. Exclusions

A viewer may exclude two kinds of thing. A profile saves them. A visitor's apply
to this visit only.

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
- When the topic list cannot be fetched, the picker says so and offers "Nope,
  show me all the movies." (or, when editing, "Never mind, keep my list") and
  "Try again".

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

## 10. Corrections

A correction says a film is not really the kind of film the tree offered it as.

- It belongs to one profile and changes only that profile's results.
- It removes the film from the tree that offered it and adds it to each tree the
  viewer names. Both halves are written together as one override.
- Each override is stored as structured rows sharing an override id. Each row
  carries the profile, the film's TMDB id, the tree, the direction (`remove` or
  `add`) and a UTC timestamp, so it can later be exported or pooled.
- A visitor is asked for a name, which creates a profile, before a correction is
  saved.
- A correction naming a film not in the library, or a tree that does not exist,
  is refused.
- A correction adding a film to a tree whose answers re-apply a kids age band is
  refused. A film joins the kids tree only through a house pin. Such trees are not offered as "belongs to", and the panel says why: "Kids'
  films are picked for the whole house, so I can't add one just for you. Ask
  whoever runs Matinee to add it." Removing a film from the kids tree is allowed.
- The correction link is offered only on a pick that came through a tree. It is
  a small "Something wrong with this pick?" link that opens a panel and never
  dominates the result.
- The panel opens with "How you got here:" and the viewer's answers in order,
  ending with "Just pick one!" when that ended the questions.
- The panel asks what is wrong, with three choices, and offers an optional "Why?"
  box of at most 500 characters:
  - "Not <genre> at all" asks where the film belongs and saves a correction.
  - "<Genre>, but not the kind I asked for" changes nothing the viewer is shown.
  - "The right kind, just not a good pick" changes nothing the viewer is shown.
- Every choice is also kept as a note for whoever tunes Matinee: the profile,
  the film, the tree, the choice, the answers that led to the pick in words,
  whether "Just pick one!" ended the questions, the comment and a UTC timestamp.
  A note needs a held profile. Its answers are resolved against the tree when it
  is saved, and an answer the tree does not have is refused.

## 11. The web surface

### 11.1 Routes

The routes serve Matinee's own page. They are not a public API. The interactive
documentation, ReDoc and the OpenAPI schema are all disabled.

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
| POST | `/api/first` | the first question for this viewer, and the pool behind it |
| POST | `/api/walk` | the next question and the pool, given a tree and answers |
| POST | `/api/pick` | one checked film from the pool the answers leave |
| POST | `/api/corrections` | save one correction for a held profile |
| POST | `/api/notes` | keep one note on a pick for a held profile |

### 11.2 What the browser may name

- **A film** only by a TMDB id in the current live film list. Any other id
  answers 404 before any request leaves for the media server.
- **An image** only as `poster` at `s` (160 px), `m` (320 px) or `l` (640 px),
  or `backdrop` at `m` (960 px) or `l` (1600 px). The media-server item id is
  never taken from the browser. It must be 32 hexadecimal characters before it
  is joined into a request. An image answer must be `image/*` and at most
  8 MiB. Images are served with `Cache-Control: public, max-age=3600`.
- **An answer** as a question id and an option index, never as a filter.
- **Request sizes** are capped: a typed name 80 characters; a profile name 80
  and a PIN 8; topics 400; exclusions 20; answers 12; tree names 40; option
  indexes 0 to 50; films already seen 200; trees a correction adds 12. A pick
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

The page builds all text as text nodes, never as markup, so a name or title from
the server can never become part of the page's HTML.

## 12. The page

One dark theme: base `#07080d`, marquee gold `#f2b33d`, velvet red `#e0566b`
for `Not that one` only. Matinee's lines and the wordmark are set in Big
Shoulders Display, other text in DM Sans. Both fonts are self-hosted with their
OFL licences. All displayed text is in sentence case. A phone is a viewport
600 px wide or less.

- **The box office.** An art deco booth: a stepped crown with a sunburst, a lit
  sign reading "Matinee" over "Now showing N films", velvet columns, a back
  wall, and a counter carrying the full credits. Bulbs run round the sign (132
  on desktop, 60 on a phone). They twinkle while one dark bulb travels
  clockwise. They are steady under reduced motion. Every question at the door
  is asked on the back wall. The booth stays on screen until the viewer goes in.
  - A device with no token opens on "Hi! A few questions before I show you to
    your seats. Anything you never want to see?", with "Nope, show me all the
    movies.", "Yes, there are a few things." and "I've been here before".
  - A device holding one token opens on "Welcome back, <name>. Your seats are
    waiting.", with "Take me in" and "Not <name>?". A device holding several
    asks "Who's watching?".
  - The trigger picker has a "Remember me" box, ticked by default. Ticked, it
    asks for a name and an optional PIN and saves a profile. Unticked, the
    choices apply to this visit only. "Never mind, show me everything" enters
    with no exclusions.
- **The iris.** Leaving the booth, the screen closes into a shrinking circle to
  black (0.6 s) and the poster wall opens from a growing one (0.75 s). The first
  line starts typing 0.52 s into the opening. It is the only transition through
  black. Under reduced motion it is instant.
- **The poster wall.** The posters of the films still in the pool, laid on a
  floor in perspective, blurred on the poster layer itself (never a backdrop
  blur) under a dark frost. Poster size follows the pool: from 22 across on
  desktop, or 14 on a phone, at 1,200 films or more, down to 9, or 6, at 40 or
  fewer. Each answer shuffles the floor with a short motion blur. The answer
  that ends the questions brings the posters to 9 across, or 6, the size they
  keep through the pick; "Just pick one!" keeps the size the wall has. From the
  glide's start to the resting page the floor keeps the same posters in the
  same places: the glide waits until the wall's posters have loaded, and a
  shuffle while a check runs moves the floor without re-dealing it. The wall
  never dims to black between answers.
- **Questions.** Matinee's line types out (an acknowledgement, then the
  question), and the answers appear once it finishes. The line and the answers
  keep apart, and nothing re-centres as the line types or the answers appear:
  the line hangs from the top of the screen with three lines reserved, so on
  desktop the answers start at the same height on every question whose line
  fits in three; on a phone the answers sit at the foot of the screen. On
  desktop the answers are letter-board strips, on a phone dark pills. The first action on a screen
  disables every button on it. The profile's name tag, with "Edit my list" and
  "Not <name>?", sits at the top of the wall and the pick screen.
- **The pails.** The gore question shows four pail pictures, spotless to
  overflowing, each with its answer's words beneath it as text.
- **The pick, in two beats.**
  1. *Land.* The wall glides far across its floor in a random direction (1.4
     s; up to 760 px across and 620 px deep on desktop, 190 and 480 on a phone,
     inside the floor's spare edge so no edge shows), as if going to fetch one
     poster. Then that poster tears loose from the floor of the wall (in the right
     two-thirds on desktop, the upper half on a phone): it lies at the floor's
     angle, blurred and dim, for about a second while it brightens, catches at
     a corner, pulls free toward the viewer with a twist, and settles in a
     spotlight (2.3 s in all), leaving a dark gap in the floor. "Here. Watch
     this one." types meanwhile.
  2. *Reveal.* After 2.7 seconds the wall fades nearly away and the lit poster
     slides to where it rests (1.3 s). It is the same picture, and the move
     starts from exactly where it hung, without a jump. On a desktop that is the foot of the left
     column, as large as the height left there allows at 2:3 (never under 160
     px), while the film's backdrop rises on the right, fading into the title,
     year and synopsis, shown without a tap. On a phone the poster fills the
     width at the top, the details follow without a backdrop, and after 2.2
     seconds the page scrolls gently to them. The left column hangs from the
     top of the screen: the line, then `Not that one`, a "More on Seerr" link to
     the film's page on the configured Seerr and `Start over` in one row, then
     the correction link. The line's words never change, so `Not that one`
     stays in one place from film to film. With reduced motion the poster and
     the scroll move without animation.

  The pick fetches the lit poster's picture, and on a desktop the backdrop, as
  soon as it knows the film. The lit poster shows only once its picture can be
  drawn, and the backdrop rises only once it has loaded, so neither shows as an
  empty box. A late picture appears late: the wait ends when Matinee's server
  gives up on it (10 s). With no poster picture the pick goes from the glide
  straight to the film, with no lit poster and no poster at rest; a backdrop
  that fails is left out. A phone's resting page shows no backdrop, so a phone
  fetches none.

  While a DoesTheDogDie check runs, the page types "One moment. Let me check
  this one against your list." and shuffles the wall.
- **Credits.** The bottom bar of the wall and pick screens carries "Posters and
  film data from TMDB [logo] · Tag genome by MovieLens · Powered by
  DoesTheDogDie.com", each linked. The box office counter carries the same line
  and adds TMDB's notice and the MovieLens citations.
  The TMDB logo is smaller than Matinee's own mark.
- **Failures.** A failed request shows its message and "Try again". No stale
  film list is ever shown.
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
  box office counter. The TMDB logo appears there and in the credit line of the
  wall and pick screens, less prominent than Matinee's own mark. TMDB data is
  non-commercial under the default licence.
- **MovieLens tag genome.** Credited to F. Maxwell Harper and Joseph A. Konstan
  (2015), *The MovieLens Datasets: History and Context*, and Jesse Vig, Shilad
  Sen and John Riedl (2012), *The Tag Genome: Encoding Community Knowledge to
  Support Novel Interaction*. The raw dataset is never committed. A derived
  table Matinee ships carries the dataset's own conditions:
  `data/reference.json` states them in its `licence` field (research and
  non-commercial use, no implied endorsement, redistribution only under the
  same conditions).
- **DoesTheDogDie.** Queried one film at a time, at the moment of a pick. Never
  fetched ahead, never used to build a score. Votes are never kept. The search's
  answer for a film, and the topic list, are remembered for at most 30 days, the
  refresh period the terms set for a performance cache (sections 8 and 9). "Powered by
  DoesTheDogDie.com", linked to `https://www.doesthedogdie.com`, appears
  wherever its data does: the trigger picker, the swap reason, the unchecked
  note and the exhausted pool. The free tier is non-commercial.

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
- corrections shared or pooled between installations;
- any administrative surface, including PIN reset;
- offline use of the installed page.

---

# Known gaps

Behaviour that is deliberately absent, still open, or short of the contract,
as the code stood on 2026-09-27.

**Short of the contract:**

1. **The profile API does not require anything to save.** `POST /api/profiles`
   accepts empty topics and exclusions from any caller. The page's own "Save
   and continue" refuses to send that request and asks the viewer to choose
   something or untick Remember me, so only a caller bypassing the page can
   create an empty profile. Any caller may still do this until the cap of 50
   fills. (`src/matinee/web/app.py:170`, `src/matinee/store.py:207`)
2. **A film with no genres fails reachability.** It is not set apart as a
   metadata fault. (`tools/check_trees.py:119`)

**Deliberately absent or open:**

3. **No cap on corrections or notes per profile.** Identical corrections are not
   deduplicated. One held profile can grow its correction rows without bound,
   which slows that profile's walks, and its note rows likewise.
   (`src/matinee/store.py:281`, `src/matinee/store.py:296`)
4. **The per-device allowance is per cookie.** A client that discards
   `matinee_device` is issued a new one with a fresh allowance. The
   installation's hourly ceiling still bounds it. (`src/matinee/web/viewing.py:226`)
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
   `{"error", "message"}` shape. (`src/matinee/web/app.py:86`)

---

# Part 2 — Map

A pointer to where each part lives, never proof of what it does. Every entry was
verified against the source on **2026-09-26**. Line numbers drift; search by the
symbol when one does not match.

### Boundaries and the library

| Handle | Where | Verified |
|---|---|---|
| `src/matinee/library/__init__.py::Library` | `src/matinee/library/__init__.py:44` | 2026-09-26 |
| `src/matinee/library/__init__.py::LibraryFilm` | `src/matinee/library/__init__.py:20` | 2026-09-26 |
| `src/matinee/library/jellyfin.py::JellyfinReader` | `src/matinee/library/jellyfin.py:60` | 2026-09-26 |
| `src/matinee/library/jellyfin.py::JellyfinReader.films` | `src/matinee/library/jellyfin.py:111` | 2026-09-26 |
| `src/matinee/library/jellyfin.py::JellyfinReader.image` (no key, size and type caps) | `src/matinee/library/jellyfin.py:95` | 2026-09-26 |
| `src/matinee/library/jellyfin.py::ITEM_ID` | `src/matinee/library/jellyfin.py:24` | 2026-09-26 |
| `src/matinee/library/jellyfin.py::parse_film` (`{tmdb-N}` folder tag) | `src/matinee/library/jellyfin.py:40` | 2026-09-26 |

### Conversation model

| Handle | Where | Verified |
|---|---|---|
| `data/first_question.json` (lines, answers, labels) | `data/first_question.json:3` | 2026-09-26 |
| `src/matinee/trees.py::parse_tree` | `src/matinee/trees.py:263` | 2026-09-26 |
| `src/matinee/trees.py::load_trees` (duplicate names refused) | `src/matinee/trees.py:281` | 2026-09-26 |
| `src/matinee/trees.py::FILTER_KEYS` / `OPTION_KEYS` / `QUESTION_KEYS` | `src/matinee/trees.py:107` | 2026-09-26 |
| `src/matinee/trees.py::parse_filter` | `src/matinee/trees.py:159` | 2026-09-26 |
| `src/matinee/trees.py::Payoffs` | `src/matinee/trees.py:76` | 2026-09-26 |
| `src/matinee/engine.py::STOP_UNDER` | `src/matinee/engine.py:50` | 2026-09-26 |
| `src/matinee/engine.py::load_catalog` | `src/matinee/engine.py:385` | 2026-09-26 |
| `src/matinee/engine.py::_first_option` (label required) | `src/matinee/engine.py:350` | 2026-09-26 |
| `src/matinee/engine.py::first_question` | `src/matinee/engine.py:530` | 2026-09-26 |
| `src/matinee/engine.py::base_pool` (order of corrections, exclusions, topic skip) | `src/matinee/engine.py:420` | 2026-09-26 |
| `src/matinee/engine.py::walk` | `src/matinee/engine.py:479` | 2026-09-26 |
| `src/matinee/engine.py::_gate` (`only_if_pool_over`, `skip_if_topics`) | `src/matinee/engine.py:462` | 2026-09-26 |
| `src/matinee/engine.py::_shown` (empty answers hidden, `not_after`) | `src/matinee/engine.py:450` | 2026-09-26 |
| `src/matinee/engine.py::_plain_mask` / `_range_mask` (unknown values pass) | `src/matinee/engine.py:293` | 2026-09-26 |
| `src/matinee/engine.py::payoff_members` | `src/matinee/engine.py:198` | 2026-09-26 |
| `src/matinee/engine.py::walk_ends` / `reachable` | `src/matinee/engine.py:504` | 2026-09-26 |
| `data/trees/comedy.json` room question (ceilings) | `data/trees/comedy.json:7` | 2026-09-27 |
| `data/modes/fall-asleep.json` | `data/modes/fall-asleep.json:3` | 2026-09-26 |

### The checker

| Handle | Where | Verified |
|---|---|---|
| `tools/check_trees.py::main` | `tools/check_trees.py:376` | 2026-09-26 |
| `tools/check_trees.py::SAMPLES` | `tools/check_trees.py:48` | 2026-09-26 |
| `tools/check_trees.py::check_answer_coverage` | `tools/check_trees.py:295` | 2026-09-26 |
| `tools/check_trees.py::check_same_answers` | `tools/check_trees.py:324` | 2026-09-26 |
| `tools/check_trees.py::check_sample` | `tools/check_trees.py:342` | 2026-09-26 |
| `tools/check_trees.py::check_pins_in_key` | `tools/check_trees.py:246` | 2026-09-26 |
| `tools/check_trees.py::check_gore` | `tools/check_trees.py:284` | 2026-09-26 |
| `tools/check_trees.py::check_lists` | `tools/check_trees.py:136` | 2026-09-26 |
| `tools/check_trees.py::check_data` | `tools/check_trees.py:366` | 2026-09-26 |
| `data/answer_key.json` list tags | `data/answer_key.json:3` | 2026-09-26 |

### Pools and reference statistics

| Handle | Where | Verified |
|---|---|---|
| `src/matinee/pools.py::build_pools` | `src/matinee/pools.py:227` | 2026-09-26 |
| `src/matinee/pools.py::EFFECT_FLOOR` and the other thresholds | `src/matinee/pools.py:39` | 2026-09-26 |
| `src/matinee/pools.py::SCORES` | `src/matinee/pools.py:68` | 2026-09-26 |
| `src/matinee/pools.py::kids_bands` | `src/matinee/pools.py:172` | 2026-09-26 |
| `src/matinee/pools.py::standup_specials` | `src/matinee/pools.py:210` | 2026-09-26 |
| `src/matinee/pools.py::_strays_follow_franchise` | `src/matinee/pools.py:198` | 2026-09-26 |
| `src/matinee/reference.py::reference_films` | `src/matinee/reference.py:157` | 2026-09-26 |
| `src/matinee/reference.py::compute_tree` | `src/matinee/reference.py:176` | 2026-09-26 |
| `src/matinee/reference.py::problems` | `src/matinee/reference.py:252` | 2026-09-26 |
| `src/matinee/reference.py::LICENCE` | `src/matinee/reference.py:29` | 2026-09-26 |
| `tools/build_reference.py::main` | `tools/build_reference.py:25` | 2026-09-26 |
| `data/reference.json` (horror gore cuts) | `data/reference.json:335` | 2026-09-26 |
| `tests/test_reference.py::test_shipped_reference_covers_every_tree` | `tests/test_reference.py:132` | 2026-09-26 |

### Scales and pins

| Handle | Where | Verified |
|---|---|---|
| `src/matinee/scales.py::scale_of` | `src/matinee/scales.py:44` | 2026-09-26 |
| `src/matinee/scales.py::film_scores` (bonus only with a genome entry) | `src/matinee/scales.py:65` | 2026-09-26 |
| `src/matinee/scales.py::band_index` | `src/matinee/scales.py:75` | 2026-09-26 |
| `src/matinee/scales.py::membership` (unscored bands, pins) | `src/matinee/scales.py:81` | 2026-09-26 |
| `src/matinee/engine.py::scale_members` | `src/matinee/engine.py:233` | 2026-09-26 |
| `data/trees/horror.json` gore scale | `data/trees/horror.json:38` | 2026-09-26 |
| `data/trees/horror.json` gore question, `skip_if_topics`, `treat_as` | `data/trees/horror.json:134` | 2026-09-27 |
| `data/trees/horror.json` labelled flavours (the kinds' rules) | `data/trees/horror.json:241` | 2026-09-27 |
| `src/matinee/labels.py::load_labels` | `src/matinee/labels.py:64` | 2026-09-27 |
| `src/matinee/engine.py::_apply_labels` (out films leave only with another home) | `src/matinee/engine.py:365` | 2026-09-27 |
| `src/matinee/pools.py::load_house` / `House` | `src/matinee/pools.py:110` | 2026-09-26 |
| `src/matinee/engine.py::house_flavour` | `src/matinee/engine.py:177` | 2026-09-26 |
| `data/house_overrides.json` scale pins | `data/house_overrides.json:94` | 2026-09-26 |

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

### Profiles, devices and corrections

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
| `src/matinee/store.py::Store.correct` / `corrections` | `src/matinee/store.py:281` | 2026-09-26 |
| `src/matinee/web/common.py::set_tokens` / `TOKENS_COOKIE` / `MAX_TOKENS` | `src/matinee/web/common.py:81` | 2026-09-26 |
| `src/matinee/web/common.py::Suggestion` | `src/matinee/web/common.py:38` | 2026-09-26 |
| `src/matinee/web/viewing.py::held_profile` | `src/matinee/web/viewing.py:178` | 2026-09-26 |
| `src/matinee/web/viewing.py::resolve` | `src/matinee/web/viewing.py:192` | 2026-09-26 |
| `src/matinee/web/viewing.py::add_note_routes` / `answer_says` | `src/matinee/web/viewing.py:352` | 2026-09-26 |
| `src/matinee/web/viewing.py::add_correction_routes` | `src/matinee/web/viewing.py:322` | 2026-09-26 |
| `src/matinee/web/viewing.py::banded` | `src/matinee/web/viewing.py:317` | 2026-09-26 |

### Exclusions and the DoesTheDogDie check

| Handle | Where | Verified |
|---|---|---|
| `data/exclusions.json` | `data/exclusions.json:4` | 2026-09-26 |
| `src/matinee/engine.py::_exclusion` | `src/matinee/engine.py:338` | 2026-09-26 |
| `src/matinee/web/viewing.py::check_exclusions` | `src/matinee/web/viewing.py:186` | 2026-09-26 |
| `src/matinee/dtdd.py::Dtdd.get` / `_pace` (`BURST`, `RATE_PER_S`) | `src/matinee/dtdd.py:106` | 2026-09-26 |
| `src/matinee/dtdd.py::Dtdd._check_holds` / `_refused` / `_note_remaining` (`REQUESTS_PER_HOUR`, `MONTH_RESERVE`, `RESERVE_HOLD_S`, `BACKOFF_S`) | `src/matinee/dtdd.py:123` | 2026-09-26 |
| `src/matinee/dtdd.py::Dtdd.topics` (`TOPICS_REFRESH_S`, `TOPICS_KEEP_S`) | `src/matinee/dtdd.py:178` | 2026-09-26 |
| `src/matinee/pick.py::failing` (`MIN_VOTES`) | `src/matinee/pick.py:73` | 2026-09-26 |
| `src/matinee/pick.py::ItemIds` (`ID_KEEP_S`) | `src/matinee/pick.py:113` | 2026-09-26 |
| `src/matinee/pick.py::look_up` (`LOOKUP_S`) | `src/matinee/pick.py:142` | 2026-09-26 |
| `src/matinee/pick.py::DeviceCap` (`LOOKUPS_PER_HOUR`) | `src/matinee/pick.py:178` | 2026-09-26 |
| `src/matinee/pick.py::candidates` | `src/matinee/pick.py:211` | 2026-09-26 |
| `src/matinee/engine.py::gentlest` | `src/matinee/engine.py:252` | 2026-09-26 |
| `src/matinee/pick.py::Picker.pick` (`PICK_TRIES`) | `src/matinee/pick.py:234` | 2026-09-26 |
| `src/matinee/web/viewing.py::device_id` / `DEVICE_COOKIE` | `src/matinee/web/viewing.py:226` | 2026-09-26 |
| `src/matinee/web/viewing.py::SWAP_LINE` / `UNCHECKED_LINES` / `EXHAUSTED` / `TIRED` | `src/matinee/web/viewing.py:202` | 2026-09-26 |
| `src/matinee/web/viewing.py::pick_pool` | `src/matinee/web/viewing.py:366` | 2026-09-26 |
| `src/matinee/web/viewing.py::add_pick_routes` | `src/matinee/web/viewing.py:376` | 2026-09-26 |

### Web surface

| Handle | Where | Verified |
|---|---|---|
| `src/matinee/web/main.py::build` | `src/matinee/web/main.py:25` | 2026-09-26 |
| `src/matinee/web/config.py::from_env` | `src/matinee/web/config.py:47` | 2026-09-26 |
| `src/matinee/web/app.py::create_app` (docs disabled) | `src/matinee/web/app.py:224` | 2026-09-26 |
| `src/matinee/web/app.py::SECURITY_HEADERS` | `src/matinee/web/app.py:190` | 2026-09-26 |
| `src/matinee/web/app.py::add_page` | `src/matinee/web/app.py:202` | 2026-09-26 |
| `src/matinee/web/app.py::add_film_routes` / `IMAGE_WIDTHS` | `src/matinee/web/app.py:123` | 2026-09-26 |
| `src/matinee/web/app.py::held` | `src/matinee/web/app.py:83` | 2026-09-26 |
| `src/matinee/web/app.py::add_door_routes` | `src/matinee/web/app.py:155` | 2026-09-26 |
| `src/matinee/web/app.py::add_error_handlers` | `src/matinee/web/app.py:92` | 2026-09-26 |
| `src/matinee/web/common.py::Problem` | `src/matinee/web/common.py:102` | 2026-09-26 |
| `src/matinee/web/viewing.py::add_viewing_routes` | `src/matinee/web/viewing.py:257` | 2026-09-26 |
| `src/matinee/web/viewing.py::WalkIn` / `PickIn` (request caps) | `src/matinee/web/viewing.py:48` | 2026-09-26 |

### The page

| Handle | Where | Verified |
|---|---|---|
| `src/matinee/web/static/js/door.js::Door` | `src/matinee/web/static/js/door.js:91` | 2026-09-26 |
| `src/matinee/web/static/js/door.js::Door.picker` | `src/matinee/web/static/js/door.js:251` | 2026-09-26 |
| `src/matinee/web/static/js/door.js::Door.fillTopics` / `topicsTrouble` | `src/matinee/web/static/js/door.js:345` | 2026-09-26 |
| `src/matinee/web/static/js/door.js::bulbs` | `src/matinee/web/static/js/door.js:31` | 2026-09-26 |
| `src/matinee/web/static/js/door.js::BULBS` | `src/matinee/web/static/js/door.js:12` | 2026-09-26 |
| `src/matinee/web/static/js/iris.js::closeIris` / `openIris` | `src/matinee/web/static/js/iris.js:14` | 2026-09-26 |
| `src/matinee/web/static/js/wall.js::Wall` / `across` | `src/matinee/web/static/js/wall.js:34` | 2026-09-26 |
| `src/matinee/web/static/js/main.js::start` | `src/matinee/web/static/js/main.js:186` | 2026-09-26 |
| `src/matinee/web/static/js/main.js::step` | `src/matinee/web/static/js/main.js:225` | 2026-09-26 |
| `src/matinee/web/static/js/main.js::pickNow` / `checking` | `src/matinee/web/static/js/main.js:272` | 2026-09-26 |
| `src/matinee/web/static/js/main.js::trail` / `backTo` | `src/matinee/web/static/js/main.js:71` | 2026-09-26 |
| `src/matinee/web/static/js/main.js::lockStage` / `nameTag` | `src/matinee/web/static/js/main.js:42` | 2026-09-26 |
| `src/matinee/web/static/js/pick.js::showNoFilm` | `src/matinee/web/static/js/pick.js:93` | 2026-09-26 |
| `src/matinee/web/static/js/pick.js::showPick` | `src/matinee/web/static/js/pick.js:113` | 2026-09-26 |
| `src/matinee/web/static/js/pick.js::firstPickReveal` | `src/matinee/web/static/js/pick.js:70` | 2026-09-26 |
| `src/matinee/web/static/js/correct.js::GATED_NOTE` | `src/matinee/web/static/js/correct.js:10` | 2026-09-26 |
| `src/matinee/web/static/js/correct.js::correctionLink` / `ensureProfile` | `src/matinee/web/static/js/correct.js:91` | 2026-09-26 |
| `src/matinee/web/static/js/credits.js::credits` | `src/matinee/web/static/js/credits.js:23` | 2026-09-26 |
| `src/matinee/web/static/js/dom.js::h` (text nodes only) | `src/matinee/web/static/js/dom.js:12` | 2026-09-26 |
| `src/matinee/web/static/js/type.js::typeLine` | `src/matinee/web/static/js/type.js:10` | 2026-09-26 |
| `src/matinee/web/static/manifest.webmanifest` | `src/matinee/web/static/manifest.webmanifest:1` | 2026-09-26 |
| `src/matinee/web/static/css/matinee.css` reduced-motion rules | `src/matinee/web/static/css/matinee.css:848` | 2026-09-26 |

### Deployment

| Handle | Where | Verified |
|---|---|---|
| `Dockerfile` (one worker, uid 1000, `/state`) | `Dockerfile:1` | 2026-09-26 |
| `.dockerignore` | `.dockerignore:1` | 2026-09-26 |
