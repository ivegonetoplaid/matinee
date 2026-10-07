---
purpose: The contract Matinee holds to — the media servers it reads, the source question and the conversation model, the labels and the household override file, the pools and scales, the offline film table and its rebuild, the setup note and the logs, profiles and the store file, the door word, the optional DoesTheDogDie topics and check, viewers' notes, the web surface, the page, deployment and third-party terms — with a map of where each part lives.
updated: 2026-10-07
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

This spec was written from the code on 2026-09-26 and last reconciled with it on
2026-10-05. It has two halves. The
**contract** says what Matinee must do and must refuse. It is authoritative. The
**map** says where each part lives. It is a pointer, never proof. The
[index](README.md) explains how to read the two when they disagree with the
code. Behaviour that is deliberately absent, still open, or short of the
contract is listed under [Known gaps](#known-gaps).

---

# Part 1 — Contract

## 1. Boundaries

1. **Read-only against every media server.** Matinee reads a Jellyfin or a Plex
   library and never writes to it. Every request either reader makes is an HTTP
   GET. No module other than a library reader calls a media server.
2. **One door to the library.** All media-server access passes through one
   library interface with three reads: the film list, one film's synopsis, and
   one film's poster or backdrop. The Jellyfin reader and the Plex reader sit
   behind it. Section 13 says which one an installation reads.
   - The Jellyfin reader asks for every movie item with collections unfolded
     (`CollapseBoxSetItems=false`), so a film inside a collection is listed as
     itself; an item that is not a movie (a collection) is left out and
     counted in a warning.
   - The Jellyfin reader's key travels only in the `Authorization` header, as
     `MediaBrowser Token="<key>"` (the one form Jellyfin 12 accepts), never
     in a URL or a log, and never follows a redirect. An item id is 32
     hexadecimal characters before it is joined into a request.
   - The Plex reader reads every movie section. An item a section lists that
     is not a movie (a collection) is left out and counted in a warning. A film's TMDB id is its
     `tmdb://` guid, or the id in a legacy "The Movie Database" agent guid
     (`com.plexapp.agents.themoviedb://<id>`); a film with neither has no TMDB
     id. Plex writes a US age rating bare and any other country's with its
     prefix: a `us/` prefix is dropped and any other kept whole (`gb/15`), so a
     rating from another country's system never passes the kids gate. The
     runtime is Plex's duration in minutes, and the rating its audience rating,
     else its rating. Pictures come through Plex's photo transcoder at the
     asked width, the poster 2:3 and the backdrop 16:9, at quality 60 for an
     image 160 px wide or narrower and 80 otherwise. The synopsis is the film's
     `summary`. An item id is 1 to 12 digits before it is joined into a request.
     The token travels only in the `X-Plex-Token` header, never in a URL or a
     log, and never follows a redirect.
3. **The library and the films the labels name.** Matinee offers the films the
   library holds at the moment of the request, and the films the labels name
   that it does not hold. A film gone from the library that no label names is
   never offered. Which films the library holds is read from the media server's
   live film list, never from the film table.
4. **Matinee's own state is its own.** Profiles, device tokens, saved topics
   and viewers' notes live in Matinee's store. None of it reaches a media server.
5. **No public API and no viewer CLI.** The HTTP routes serve Matinee's own page
   only. The command-line tools are for whoever runs the installation: the
   nightly rebuild, the tree checker and the notes tool. The reference builder
   and the genome builder are for whoever maintains Matinee.
6. **The engine is a plain module.** The tree walk imports no web framework and
   reads no request state. The web page and the tree checker call the same
   engine, so they cannot disagree about a pool.
7. **Every request names Matinee.** Each request Matinee makes, to the media
   server, TMDB, TMDB's image server, Seerr or DoesTheDogDie, carries a user
   agent naming it: `Matinee/0.1`, with DoesTheDogDie's address added on
   requests to DoesTheDogDie (`src/matinee/__init__.py::USER_AGENT`). A proxy in
   front of a household's service may refuse a library's default agent.

## 2. The conversation

### 2.0 The source question

The source question opens every walk when three things hold. The library can be
used: a media server is set, its settings can be used, and it answers. The
library holds at least one film. At least one film the library lacks is offered.
With either pool empty, every answer would draw from the same films or from
none, so the question is not asked. Matinee types "Right this way, <name>." and
"what are we choosing from tonight?". Its answers, in this order, bound the walk:

| Answer | The walk draws from | Matinee's reply on the doors |
|---|---|---|
| only what we can watch right now. | the films the library holds now (`held`) | home turf. good, the popcorn's already made. |
| something we don't have yet. something new! | the films the labels name that the library does not hold (`new`) | ooh, something new. let's go window shopping. |
| anything at all. ours or not. | both, a film in both once (`all`) | no borders tonight. I like it. |

- The chosen source bounds every later question, count and pick of the walk,
  `Just pick one!` included: which doors are shown, which answers are shown or
  hidden (the 30-film bar for a labelled kind counts the source's films), and
  when the questions stop.
- The answer is never carried into the next walk: every start asks again. It is
  sent with each request of the walk (`source` on `/api/first`, `/api/walk` and
  `/api/pick`) and never stored.
- A phone shows no trail; its way back is "Back" and `Start over` (section 12).
- Before it is answered, the wall behind the front door and behind the source
  question shows the library's films, and `Just pick one!` there picks from
  them. The wall re-sorts to the answer's films.
- While the library cannot be used, or none is set, the source question is not
  asked and a sent `source` is ignored: the walk starts at the doors and draws
  from every film offered (the films the labels name, while the library cannot
  be used).
- When the library stops answering after a walk was given `held` or `new`, the
  walk goes on among every film offered, and never silently: `POST /api/first`,
  `POST /api/walk` and `POST /api/pick` carry `fallback`, "I can't reach your
  <server> right now, so I'm picking from every film I know, in your library or
  not, until it's back.", with `Jellyfin` or `Plex` for <server>. When the
  library answered and turned down the key (HTTP 401 or 403), it reads "Your
  <server> turned down my key, so I'm picking from every film I know, in your
  library or not, until that's sorted." instead. The page shows
  it in the warning strip (section 12). An answer of `all` loses nothing and
  carries none, and neither does a walk the source question was not asked of,
  whose setup note said so. A response without it takes it down, so the strip
  clears when the library answers again or a new walk starts.
- The wording is data in `data/first_question.json` (`source`). A file whose
  answer names no source is refused.

### 2.1 The first question

The poster wall opens by typing "Right this way." and "So, what are we in the
mood for?". Every viewing runs under a profile, so the first line carries its
name: "Right this way, <name>.". After the source question the doors type the
source answer's reply in gold, then "So, what are we in the mood for?"; a return
to the doors through the trail types the same reply. Each answer is a door, offered by its plain name.
The answers, their order and the tree each leads to are data in
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

- An answer is shown only when its tree holds at least one film for this
  viewer in the chosen source.
- Every answer must carry a `label`. The engine refuses to load a first question
  whose answer lacks one. The label names the door where a short name is needed,
  such as the note panel. Each door's label is its name.
- Matinee's reply to a door is the opening line of the tree it leads to.
- Stand-up specials are not a door. They are an answer under Comedy (section
  2.3).

### 2.2 Trees are data

Each door's questions live in their own file under `data/trees/`. A file carries the content: its opening line, its
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

Loading is strict:

- Question, answer, filter and flavour keys are checked against
  the set the engine reads. A misspelt key fails at load. It never reads as
  absent and silently widens a pool.
- Two tree files with the same name are refused.
- A tree file must name its `pool` and its `opening` line.
- A tree naming a pool no pool rule builds is refused.
- `sequel` may only be `false`. `sort` may only be `rating`. `kids_band` must be
  `little`, `family` or `older`. `treat_as` must name an answer the question has.
- A tree may name one flavour it defines as `apart`; naming a flavour it does not
  define is refused. Every flavour is marked either `labelled` or `specials`,
  and takes nothing else. Only a labelled flavour may be marked
  `always_shown`, and only as `true`.
- An answer may carry `self_destruct`, a whole number of seconds from 1 to 9. Any
  other value is refused. Every answer carrying it, across the trees,
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
when that kind holds at least 30 films of the tree's pool in the walk's source
(section 2.0), counted before any answer narrows it. A kind is exempt when it
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
rolls from its whole pool after its opening line. The spies answer, behind
Thriller and behind Action, carries `self_destruct` of 5 seconds (section 12);
no other answer carries it. A
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
- A question marked `skip_if_topics` is never asked of a viewer who holds any
  of those DoesTheDogDie topics (only with a DoesTheDogDie key, section 8). Its `treat_as` answer is applied to the whole
  starting pool instead, so every count and every shown answer already reflects
  it.
- **An answer that would leave the pool empty is not shown.** A question with no
  answer to show is skipped.
- A question may carry a `footnote`, a line the viewer sees in body type beneath
  its answers and above `Just pick one!` (`footnote` in `/api/walk`). A question's
  `note` is maintainer documentation and is never shown.
- An answer marked `not_after` is hidden when the viewer gave a named earlier
  answer.
- A walk that ends on an answer carrying `self_destruct` reports its seconds
  with the reply (`self_destruct` in `/api/walk`); every other walk reports none.
- An answer that does not fit the question being asked is refused. The page is
  told to start over.
- Pool counts never leave out a film for the viewer's DoesTheDogDie topics.
  Those are checked only at the pick (section 9).
- **`Just pick one!`** is on screen from the first question onward, as the last
  choice beneath each question's answers. It ends the questions and picks from
  the pool as it stands. Pressed at the first question, it picks from each
  door's pool for this viewer before any answer, less the flavour that door's
  tree holds apart.
- **The trail.** Once the walk holds a source answer or a door, each question
  screen and the pick screen show the way here in gold at the bottom centre:
  `Start`, the source answer when the source question was asked, the door, then
  each answer so far. The walk's first screen shows none, and neither does a
  pick that `Just pick one!` started there. Choosing a crumb goes to the screen it led to and forgets every answer
  after it: `Start` returns to the walk's first screen (the source question
  asks again), the source answer shows the doors within it, the door asks the
  door's first question, and an answer asks the question that followed it.
  The crumb for the screen showing now is plain text, not a link; on a pick
  that `Just pick one!` ended early, every crumb is a link. The trail shows on
  a desktop only. A phone shows, in its place, "Back", which goes to the screen
  before this one as its crumb would (from a pick, the question last answered;
  from a pick `Just pick one!` ended early, the question it left), and
  `Start over`. Where "Back" would lead to the walk's first screen, only
  `Start over` shows; the walk's first screen shows neither.

### 2.5 Every film stays reachable

Every film in the library must be reachable through at least one complete path
of answers in some tree a first-question answer leads to. A tree no
door leads to is no film's home.
`tools/check_trees.py` holds the trees to this. It reads the film table the
nightly rebuild writes and checks the films of the library that table was built
from; a table built with no library is checked whole. It builds every tree
through the engine, and fails, with a non-zero exit, on any of these:

1. **Data.** A library film has no usable TMDB facts. The standup rule cannot
   see such a film.
2. **First question.** An answer leads to no tree file.
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
The checker reads the shipped labels file, `data/labels.json`, unless `--labels`
names another. It lists by title the films in the waiting room (section 3.1) with the
doors their genres place them behind, the films each door holds under no kind
(by a house pin, the waiting room or the standup rule), the labelled films no
kind of their door fits (reached through "anything" and `Just pick one!` only;
the labels give no kind where none is a real fit), and each answer a small
kind hides. On the full library it fails
when the kinds the bar hides differ from the answer key's `hidden` list of
`[tree, kind]` pairs, so a kind that starts hiding, or stops, is never silent.

### 2.6 Labels

The labels alone decide which genre doors and kinds a film belongs to (section
3.1). The file is `data/labels.json`, shipped in the repository under the
repository's own licence. It is written outside Matinee, by a labelling pass,
and names films by TMDB id only: TMDB's most-voted ten thousand films and every
film of the first library it sorted. No label was derived from the MovieLens
genome. Its shape (format 2):

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
- A file that cannot be read (absent, in any format but 2, malformed, or with a
  band outside the three) starts the server with no film placed behind a door:
  every film waits behind its genres (section 3.1), and the setup note names
  the problem with its format or path (section 5.6). A file naming a tree no
  file defines, or a kind the tree does not label, leaves the engine unable to
  prepare, so no film is offered and the setup note says so.
- The server reads the file once at start-up. Replacing it takes a restart, and
  updating Matinee replaces it. A `labels.json` in the data directory is not
  read; the server logs a warning naming it at start-up.

**The household override file.** An installation may keep `overrides.json` in its
data directory, in the labels file's shape (format 2). Matinee reads it at
start-up, after the shipped labels and the house pins, and never writes it; an
update never touches it. A film the file names anywhere, under a door's kinds or
in the kids bands, takes its whole placement from the file: the shipped labels'
doors, kinds and band for it are set aside, and so are its house pins that place
it (kids, tree, flavour and specials pins). Its gore-pail pin stays, since a pail
is neither a door nor a kind. The file may label a film the shipped labels lack,
which then joins the films the rebuild fetches and Matinee offers. Removing the
file restores the shipped placements. A file Matinee cannot use (not valid JSON,
another format, a tree no file defines or a kind its tree does not label, bands
under any tree but kids, or a kids film with its kinds and no band or its band
and no kinds) is a
setup fault (section 5.6): the note names the problem, and the shipped
placements apply alone until a restart reads a mended file. A household shares its file in a "Sorting suggestion"
issue, and whoever edits the shipped labels may merge its entries in by hand.

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

- A category is `universal`, or a tree by its file name. It may hold
  `reveal` lines, said as a film arrives, `nope` lines, said after
  `Not that one` and "Roll again", and `rush` lines, said after "Just pick
  one!". The shipped file holds universal (16 reveal, 22 nope, 8 rush),
  horror (18, 19), comedy (22, 29) and action (16, 19). A tree with no category of its
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
  category lacks reveal, nope or rush lines is refused, because every set
  falls back on universal's. The server reads the file once at start-up;
  replacing it takes a restart.
- The checker (section 2.5), and a test in `./check.sh`, refuse by name a line
  over `caps.line`, a line wrapped in quotation marks, and a line in title
  case. A line is in title case when it has at least two words after its
  first, not counting words in capitals for emphasis or "I" and its
  contractions, and every one of them is capitalised. They also refuse a
  category that is neither universal nor a tree.
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

- **The waiting room.** A library film the labels file lists under no door
  waits behind the doors its TMDB genres name: Action or Adventure behind
  action; Comedy; Drama; Horror; Thriller or Mystery behind thriller; Crime;
  Science Fiction behind scifi; Fantasy; Romance; Animation; War; Western. It
  holds no kind there, so only "anything" and `Just pick one!` reach it, until a
  labelling pass places it. A documentary or a standup special does not wait,
  since its own rule gives it a home. This is the only place genres place a
  film behind a genre door.
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
passes. A house kids pin puts a library film in the pool in the named band,
whatever its certificate and labels. For a film the library does not hold, the
pin applies only when its certificate passes the gate, so a pin never carries an
unrated film into the pool. The bands allow rather than require:

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
- The engine refuses to prepare when the file is absent or does not cover a
  tree file: a missing tree, different genres or floor, or a scale that is
  missing or has other tags or percentiles. The server still starts, offers no
  film, and names the fault on the setup note (section 5.6).
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

A viewer holding any of these DoesTheDogDie topics is never asked the gore
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
directory, never in the repository. The server reads it. It never reads the
genome and never asks TMDB's API for a record; its only requests to TMDB are for
pictures (section 11.5).

The table holds every library film and every film the labels name that has a
usable TMDB record (format 2; a table in any other format is refused). A library
film's row carries its media-server item and the media server's title, year,
genres, certificate, runtime and rating, with three exceptions: its genres are
TMDB's when it has a usable record, because the rules read TMDB's genre names and
a Plex library writes its own; an empty title is TMDB's; and a rating another
country's system wrote (a prefix such as `gb/`) is TMDB's US rating. A row for a
film the library does not hold carries no item and TMDB's title, year, genres,
US age rating (empty where TMDB has none, which never passes the kids gate),
runtime and rating. Every row also keeps the film's TMDB facts, its synopsis and
its vote count in their own columns.

### 5.1 The nightly rebuild

`tools/rebuild_table.py` writes the table. With `--daily HH:MM` it rebuilds at
once and then every day at that local time; `--daily` alone takes the time from
`REBUILD_TIME`, 04:30 when unset. A time given to `--daily` is validated before
the first rebuild; a `REBUILD_TIME` that is no `HH:MM` time is logged and the
rebuild runs at 04:30. A rebuild that fails on an unexpected error puts back the table it
started with, which it keeps under a second name (`films.sqlite.kept`) while it
runs; one that stops on TMDB (no key, a refused key, TMDB not answering) keeps
what it saved.

1. Without a TMDB key (`TMDB_TOKEN`) it fetches nothing, writes no table, and
   reports the reason (below). It still drops cached records past six months
   and shelved pictures past 150 days (section 5.2).
2. It reads the media server's film list, by GET only, when a media server is
   set. With none, or with settings that name both servers or cannot be used
   (logged), it runs on the labels alone.
3. It writes the table from the library and the records already held, before
   any fetch, so the library can be picked at once on a first start.
4. It refreshes the TMDB record of every film the labels name (the shipped
   labels and the household override file) and every library film with a TMDB
   id, most-voted first. With no vote count held (a
   first start, or records kept before vote counts were) the order is TMDB's
   list of films by vote count (its 500 pages, read then and never stored);
   otherwise it is the vote counts in the records held.
   Films outside the order come last; when the order cannot be read the rebuild
   fetches by TMDB id and logs why. One GET per film, at `TMDB_RATE` requests a
   second (30 by default), with up to that many requests in flight at once (32
   at most). The pace takes any positive number and carries no ceiling (TMDB's
   own limit is about 40 a second); anything else is the default, logged. A
   record keeps the film's title, year, runtime, rating (TMDB's vote average), TMDB
   genres, synopsis, vote count and US age rating, and its collection,
   keywords, original language and poster and backdrop paths. The US age rating
   is the film's US theatrical certification, else its first other non-empty US
   certification, else none. A 429 holds every request for its `Retry-After`,
   those already waiting for a turn included. It stops after 5 network failures
   in a row, and at once when TMDB refuses the key (401). While it fetches it
   writes the table again every 500 new records, so the films it can offer grow
   as it learns.
5. It reads the shipped genome scores (section 5.3) for every write.
6. It writes the table a last time when the fetch ends. Every write replaces the
   previous table whole, so the server never reads half of one.
7. It logs a report. The report counts films with and without genome scores and
   items with no TMDB id. It names every file whose `{tmdb-N}` folder tag differs
   from the TMDB id the media server gives, and every film missing a usable TMDB
   record. It uses the media server's id and changes nothing on the server.

The rebuild reports itself in `rebuild.json` in the data directory, replaced
whole each time, and the server reads it
(`src/matinee/progress.py::RebuildStatus`):

```json
{"state": "running", "started_at": "2026-10-05T03:00:00+00:00",
 "updated_at": "2026-10-05T03:01:40+00:00", "done": 2500, "total": 10327, "reason": null}
```

`state` is `running` as it starts and at least every 5 seconds while it
fetches, with the films this run has fetched or failed out of those it needs
(`done`, `total`), `finished`, or `stopped` with the reason: "no TMDB key is
set", "TMDB refused the key", "TMDB is not answering", or "the rebuild failed;
its log says why". A `running` report that has not
changed for 120 seconds means the rebuild died, and the setup note says the
last rebuild failed. A report
that cannot be read, or whose fields are not of their kind (a known state, text
times, whole counts of zero or more, a text reason or none), counts as absent. A one-shot rebuild exits 0 only when it
finished.

### 5.2 TMDB facts and the six-month limit

- The TMDB cache holds the newest record per film. A record is refetched once
  it is **150 days** old, or when it predates the original-language field, the
  picture paths or the title and the other facts kept with it.
- A picture path is kept only when it has TMDB's shape: a slash, letters and
  digits, then `.jpg` or `.png`. Any other value is logged and kept as no
  picture, so nothing else is ever joined into a picture's address. A film TMDB
  gives no picture for is recorded as having none.
- After each refresh the cache is rewritten to hold only records younger than
  **183 days**. A film TMDB does not know (404) is never cached. A damaged cache
  line is skipped, logged, and its film fetched again.
- The server keeps every TMDB picture it fetches on a shelf in the data
  directory (`tmdb/pictures/<TMDB size>/<file>`), so each picture is fetched
  once for every viewer. A shelved picture is served for **150 days** and then
  fetched again; every rebuild, with or without a key, removes each one 150
  days old or more. A shelf that cannot be read or written is logged and the
  picture is fetched and served without it.
- A film whose TMDB record is missing or 183 days old or more carries no TMDB
  facts. Its keywords are unknown, never empty, and it has no picture paths.
- A table in another format, or missing a column its format holds, cannot be
  read. The server treats it as absent until the rebuild replaces it (section
  5.6); a table from before this format is such a table.
- **A table whose oldest TMDB fact is 183 days old or more still serves picks,
  with a loud warning.** The server checks the age on every request. While it
  has passed, `GET /api/setup` carries `warning`: "This film data is over six
  months old, and keeping it breaks TMDB's terms. Refresh it by running the
  rebuild: python tools/rebuild_table.py". The page shows it in a strip across
  the top of every screen past the door word, the screen beneath it (section
  12). The server logs it once each
  time the table turns stale. The warning goes once a rebuild refreshes the
  facts. The nightly rebuild (`--daily`) is on by default and refetches every
  record at 150 days, which keeps the data within TMDB's terms.

### 5.3 The genome join

- The rebuild reads the genome scores Matinee ships, `data/genome.json`, and no
  installation downloads MovieLens. The file holds the relevance of every tag a
  reader names (every tree's `scores` and
  the answer key's list tags; `src/matinee/genome_file.py::tags_read`) for
  every genome film with a TMDB id: 24 tags and 16,353 films from the shipped
  release. Values are kept to five decimal places, the genome's own precision,
  so each reads back as exactly the value the full genome holds. A test in
  `./check.sh` fails when a reader names a tag the file lacks.
- `tools/build_genome.py` writes the file from a local ml-latest release, for
  the maintainer. Films join the genome on TMDB id through the release's own
  `links.csv`, never by title. Where two MovieLens films share a TMDB id, the
  first one wins. The raw dataset is never committed or shipped.
- **A film the genome does not cover carries no genome scores (NaN), never
  zeros.**
- The table stores one row per distinct TMDB id. Library items with no TMDB id
  are left out and reported.
- The maintainer's tools may cache the parsed genome matrix beside the
  dataset. The cache is reused only when made from a genome file of the same
  size and modification time.

### 5.4 The live library

- The server reads the media server's film list at most every **300 seconds**.
  A film on the list is held. It shows the media server's facts as the rebuild
  read them, with the item the list names now; one the library took in since the
  rebuild shows the list's facts. A film the labels name that the list lacks is
  offered with its TMDB facts and no item. A film neither on the list nor named
  by a label is not offered.
- A library film the table does not yet hold is offered by its media-server
  facts alone, with no genome scores and no TMDB facts, and is logged.
- While the media server cannot be read, or with no media server configured,
  no film is held: Matinee offers the films the labels name alone, with their
  TMDB facts. The last list read stands until a read fails. For **15 seconds**
  after a failed read no new read is attempted. A read the server answers with
  HTTP 401 or 403 is a turned-down key, told apart from a server that gives no
  usable answer: its warning says to check the key, the other's to check that
  the server runs and its address.
- The table file is reloaded when the nightly rebuild replaces it.
- The sign's "Now showing N films" counts every film Matinee offers: the
  library's and the films the labels name.

### 5.5 What the logs say

At start, and whenever its state changes (looked at, on a request, at most every
15 seconds), the server logs one line naming its whole state: the media server it
reads and whether it answers, does not answer or turned down the key, whether Seerr and DoesTheDogDie are set and Seerr
answers, the film table's size and the age of its TMDB facts, how many films are
offered, and the rebuild's last report with its progress. The rebuild logs the
same way: a line as it starts (the library, the films the labels name, the records
held and to fetch, the pace) and its progress at every save. Every warning and
error either one logs says what failed, what Matinee does meanwhile, and a step
to recover. A warning one bad answer per picture would repeat is logged at most
once a minute, with a count of those held back. No log line carries a key, token
or door word.

### 5.6 Refusing to start, and the setup note

The server refuses to start, and logs why, in exactly these cases:

- `DATA_DIR` is unset or names no directory (Matinee does not start empty and
  lose every profile silently);
- a door word is set and is shorter than its mode allows or longer than 200
  characters, or the door mode names no mode, or the door's secret cannot be
  read or is not 32 bytes (section 7.2): a lock whose settings are wrong stays
  shut;
- the store file is newer than the code, is not a SQLite database, holds notes
  that older code filed into its old `feedback` table, or cannot be upgraded to
  the current shape (section 7.1). The file is left unchanged.

Every other fault starts Matinee, logs it, and puts it on the **setup note**, a
page the visitor sees once per visit before the front door (`GET /api/setup`,
after the door word where one is set). The note is headed "A word before the
show." and says, one paragraph each, what Matinee sees:

- a setting Matinee cannot use, named with what it takes: both Jellyfin and Plex
  set (neither is read), a media server address without its key or not starting
  with `http://` or `https://`, a `SEERR_URL` of that kind (picks link to TMDB),
  a `POSTERS_FROM` or, with no door word, a `DOOR_MATCH` it does not understand
  (the default stands);
- a configured media server it cannot reach, reported without instructions;
- a configured Seerr it cannot reach (picks link to TMDB until it answers);
- the rebuild's last stop and its reason (section 5.1): no TMDB key and a
  refused key with the step that fixes them, TMDB not answering without one;
- Matinee's own shipped files that cannot be used (the labels, the pick's lines,
  or data the engine cannot prepare: stale reference statistics, a malformed
  tree), with "update or reinstall Matinee";
- a household override file that cannot be used (section 2.6), with what is
  wrong in it;
- a rebuild whose report stood still for 120 seconds, as a failed rebuild;
- when there is no film to recommend, why: the rebuild is still fetching, or no
  film details exist and nothing is fetching them.

While the library cannot be used, because both servers are set, its settings
cannot be used or it does not answer, the note also says Matinee is picking from
TMDB's most popular films (the films the labels name) instead. A server that
does not answer reads "I can't reach your <server> right now."; one that
answered and turned down the key (HTTP 401 or 403) reads "Your <server> turned
down the key in <setting>, so I can't see your library.", naming
`JELLYFIN_API_KEY` or `PLEX_TOKEN`. The note offers
"Show me the films", which goes on to the front door, and never a way into an
empty pool: with no film to recommend it offers only "Try again". A note with a
way in is shown once per page visit; one without is shown every time. A fault
found as Matinee runs (a server that does not answer, the rebuild's report, the
films on offer) leaves the note without a restart once it clears; a setting or
a file read at start-up stays on it until a restart. With nothing to say there
is no note. Section 12 says how the page shows it.

A film table that is absent, in another format or cannot be read counts as an
empty one, so the server starts before the first rebuild has written anything.
Data Matinee ships that the engine cannot prepare offers no film: every route that
needs the film list answers 503 `not_ready`. The pick's lines that cannot be read
leave `GET /api/quips` answering 503, and picks come without a line. The labels
that cannot be read place no film behind a door; every film waits behind its
genres (section 3.1).

The note names a fault as Matinee found it, so a line about Matinee's own files
or the override file may carry the problem's own words, a file's path among
them (`src/matinee/web/app.py::setup_faults`).

## 6. What one viewer's pool is

For each tree, the viewer's starting pool is built in this order:

1. The tree's pool, with house pins already applied.
2. Only the films of the chosen source (section 2.0).
3. Every question the viewer's DoesTheDogDie topics skip applies its `treat_as`
   answer.

A viewer's notes (section 10) never change a pool.

Answers narrow that pool from there (section 2.4).

## 7. Viewers, profiles and devices

Matinee has no accounts and no login. Every viewing runs under a **profile**
this device holds a token for. A device without one is shown the first
question's pool behind the front door, with no topic applied, and walks or
picks nothing until it opens or makes a profile.

| Rule | Value |
|---|---|
| A profile holds | a display name, an optional four-digit PIN, an optional avatar and DoesTheDogDie topics |
| Avatar | one of fifteen: `3d-glasses`, `camera`, `candy`, `chair`, `clapperboard`, `comedy-tragedy`, `director-megaphone`, `film-reel`, `hotdog`, `nachos`, `popcorn`, `soda`, `theater-seat`, `ticket`, `vhs`; or none, for initials. Two profiles may share one |
| Most profiles | **50**; creating a fifty-first is refused |
| Name | 1 to 40 characters after NFKC normalisation, trimming and collapsing spaces; no character of Unicode category C (control, format, private-use, unassigned); unique ignoring case (NFKC, case-folded) |
| PIN | exactly four ASCII digits, or none |
| PIN storage | salted scrypt digest (N 2^14, r 8, p 1, 32 bytes, 16-byte salt); never stored as typed |
| Lockout | **5** wrong PINs lock that profile against PIN entry for **15 minutes**; keyed on the profile, never on a client address |
| Device token | 32 random bytes, URL-safe; stored only as a SHA-256 digest, so a copy of the store cannot be replayed as a cookie |
| Token cookie | `matinee_tokens`: `HttpOnly`, `Secure`, `SameSite=Lax`, path `/`, 400 days; holds at most **8** tokens, a ninth pushing out the oldest, and never a name or PIN |
| Token pruning | tokens older than 400 days are deleted whenever a new token is issued |

- **A device holding a valid token for a profile is never asked its PIN** and
  keeps its token when it opens the profile again.
- A profile with a PIN opens on another device only after its PIN.
- **The front door lists every profile** to an admitted device (section 7.2),
  sorted by name ignoring case: its id, name, avatar, whether it has a PIN, and
  whether this device holds it. It never carries a profile's topics, which can
  say what frightens a person; only a device holding the
  profile, or one that has given its PIN, receives them. There is no typed name
  lookup. A device that is not admitted gets no profiles.
- A token for a deleted profile is ignored. The door's reply clears it from the
  cookie.
- **Avatars.** A profile is made with an avatar or none, and a device holding
  it may set or clear it at any time. Every reply describing a profile to the
  page says which avatar it carries. An avatar Matinee does not offer is
  refused when set (`bad_avatar`) and reads as none when found in the store.
- **Avatar images.** Each avatar ships as two finished WebP files under
  `static/avatars/`: `<avatar>-256.webp` for the front door's tile and
  `<avatar>-80.webp` for the top bar, each twice its displayed size, square, with
  the art cropped to its visible edges, its longest side 84 per cent of the
  square, centred on transparency. No tile-size image is larger than the largest
  pail, and the thirty together stay under 1 MB. The source art is never in the
  repository, and the page never loads it.
- **Deleting a profile.** A device holding a profile may delete it, with no
  PIN asked, as it opens it with none. The profile, its topics and every
  device token issued for it go, on every device; its notes stay (section 10).
  The deleting device's cookie keeps its other tokens and drops this one. A
  device that does not hold the profile is refused with 403, so naming a
  profile's id is never enough to delete it: a profile with a PIN must first be
  opened with its PIN. A profile without a PIN opens on
  any admitted device, which may then delete it; Matinee adds no further guard.
- There is no PIN reset and no administrative surface on the web. Whoever runs
  the installation clears a forgotten PIN with the notes tool's
  `clear-pin "<profile name>"` (section 10), which matches the name as a
  profile name is stored (case, and runs of spaces, ignored), clears the PIN and any lockout on it, and refuses a name no profile has.
- A request naming a profile (the first question, a walk, a pick, saving
  topics, setting its avatar, saving a note or deleting the profile) is
  refused with 403 unless this device holds a token for it. Every write to a profile (its topics, its avatar, a
  note, its deletion) checks the device's token in the same store transaction as
  the write, so a profile deleted and its id given to a new profile between a
  device's check and its write never receives that write (`profile` error
  `not_held`, 403). A walk or a pick naming no profile is refused with 403.

### 7.1 The store file

The store is one SQLite file, `matinee.sqlite`, in the state directory. It
records its shape in SQLite's `user_version`; the current shape is **1**. A file
from before shapes were recorded reads 0 and holds profiles, tokens, notes (in a
table named `feedback`) and personal corrections.

- A missing or empty file is made at the current shape.
- Each profile row keeps an `exclusions` column from when Matinee had
  exclusions of its own. Matinee no longer reads or writes it; a new row takes
  its empty default.
- A shape-0 file is upgraded in place when Matinee starts, in one transaction.
  The upgrade keeps every profile, token and note, each note under its own id,
  and removes the corrections. A "Not <genre> at all" note first takes, as where
  its film belongs, the trees its own correction added the film to: the
  correction with the note's profile, film and tree saved at or before the
  note, the latest of them. Every note arrives with the status `open`, and
  every profile with no avatar. It is kept only when the counts of profiles,
  tokens and notes are the same after it as before and no row points at nothing.
- Before its first change to a shape-0 file, the upgrade copies the file as it
  stood to a new file beside it, named
  `matinee.sqlite.before-shape-1-<UTC time>`. Nothing ever overwrites that copy,
  and a later start on the upgraded file makes none. A start that finds such a
  copy already there makes no other, because a refused upgrade leaves the store
  unchanged.
- Code from before shapes were recorded can still open a current file: it
  recreates its old tables and files new notes into `feedback`, where no queue
  reads them. A start that finds any row in a `feedback` table is refused and
  names the count; empty old tables do not stop it.
- A file newer than the code, a file that is not a SQLite database, a shape no
  upgrade starts from, and an upgrade that fails all stop the start. The store
  file is left unchanged.

### 7.2 The door word

The door word is optional. With none set (`DOOR_WORD` unset, empty or
only spaces), every device is admitted. With one set, a device that is not admitted reaches
only the page, its static files (the locked door's art among them) and the word
check, `/api/admission`. Every other route answers `401 not_admitted`, with the
usual headers. The protection is sized for a household film picker.

- **Admission.** The right word sets the cookie `matinee_admit` (`HttpOnly`,
  `Secure`, `SameSite=Lax`, path `/`, 400 days). Its value is the time it was
  issued and an HMAC-SHA256 over that time, the match mode and the door word,
  keyed by the installation's secret. Only the server can make or check one: a
  value set by hand admits nothing, and holding one gives no way of testing
  guesses away from the server. The server also refuses a cookie issued more
  than 400 days ago, or stamped more than five minutes ahead of its own clock.
- **The secret** is 32 random bytes in `door.key` in the state directory, made
  at the first start with a door word, owner-only. An admission survives a
  restart and a redeploy. A secret that cannot be read, or is not 32 bytes,
  stops the start.
- **Changing the word or the mode** ends every admission.
- **A profile token never admits a device.** A device that held a profile
  before the word was set gives the word once, like any other.
- **Matching.** In relaxed mode (the default) both words are NFKC-normalised,
  case-folded and stripped of everything but letters and digits, and they may
  differ by at most one insertion, deletion or substitution. In strict mode the
  typed word must equal the door word exactly. A typed word over 200 characters
  is wrong without being compared. With a word set, the start is refused when a
  relaxed word is under 8 letters and digits, a strict word under 12
  characters, any word over 200 characters (more than the door compares), or
  `DOOR_MATCH` names no mode; the message names the setting, never the word.
  With no word set, a `DOOR_MATCH` that names no mode is a setup fault (section
  5.6) and relaxed stands.
- **A wrong word** is answered after 2 seconds, and words are checked one at a
  time across the installation. The wait is an asynchronous sleep: waiting
  guesses hold no worker, and every other route answers at its usual speed. The
  wait is not keyed on the client's address.
- **The greeting** (`DOOR_GREETING`): `show` (the default) is "State
  your business. Make it quick, the show's about to start."; `gin` is "State
  your business. And it better be sweeter than bathtub gin, or I'll feed you to
  the copper pipes."; any other text is the operator's own greeting.
  `GET /api/admission` carries it while the site is locked.
- The door word is never written to a log, a reply, an error or either
  repository.

## 8. DoesTheDogDie topics

A viewer may choose DoesTheDogDie topics: things they would rather not see
happen on screen. A profile saves them. The list a profile edits holds
DoesTheDogDie's topics alone; Matinee has no exclusions of its own.

**DoesTheDogDie is optional.** It needs the installation's `DTDD_API_KEY`.
Without one, Matinee offers nothing that needs DoesTheDogDie: no profile is
asked for topics, "Edit my list" is not offered, `GET /api/topics` and
`PUT /api/profiles/{id}/topics` do not exist (404), no pick is looked up, and
no DoesTheDogDie credit shows anywhere, the About page's section on steering
included. A profile's stored topics stay in the store unchanged and have no
effect on any walk or pick: no question is skipped for them. While any profile
holds topics and no key is set, the server logs a warning at start and, at most
once every 12 hours, when it loads a rebuilt film table. It says a DoesTheDogDie key was set before
and is now missing, how many profiles still hold topics, and that the household
either sets `DTDD_API_KEY` again or clears the topics with the notes tool's
`clear-topics`, which ends the warning. `GET /api/door` says whether the key is
set (`dtdd`). With a key, everything below holds.

**DoesTheDogDie topics** are checked only at the pick (section 9). Before the
pick, they only decide whether a question marked `skip_if_topics` is asked. A
film fails a topic when the topic has **at least 5 votes and more yes votes
than no.**

- The topic list is fetched from DoesTheDogDie when a page that offers topics
  opens and no list is kept. It is then kept in memory and fetched again once it
  is **29 days** old. While a refresh fails, the kept list serves until it is
  **30 days** old.
- The trigger picker, which is also the preferences page, offers the
  DoesTheDogDie topics. It says the check is best effort from
  crowd votes beside the count of chosen topics, and its credit line carries
  "Powered by DoesTheDogDie.com", linked, in the foot band.
- When the topic list cannot be fetched, the picker says so and offers "Try
  again". Its way out stays beside
  saving: "Never mind, keep my list" when editing a list, or "Never mind, show
  me everything" for a profile just made.

## 9. The DoesTheDogDie check at the pick

A film is looked up on DoesTheDogDie only when Matinee has drawn it for a pick
and the viewer holds DoesTheDogDie topics. Nothing is looked up ahead. Votes are
never kept. No tree, scale or score is built from DoesTheDogDie data.

- **The lookup.** By TMDB id: `/api/v3/items?tmdb={id}`, then
  `/api/v3/items/{itemId}`. Only a Movie item whose TMDB id is the film's is
  taken: TMDB numbers films and TV shows apart, and a TV show sharing the
  number is another title. Where that does not leave exactly one item, the film
  counts as having no record. A Movie whose item id is not a positive whole
  number is unreadable: the film goes unchecked and the search's answer is not
  kept. A vote row that is not an object, or whose topic id is negative or not
  a whole number (a JSON true included), is unreadable. So is a vote count of
  that kind on a row for one of the viewer's topics; a row for another topic is
  skipped unread. An unreadable row leaves the film unchecked, and its item id
  stays held.
- **The item id is remembered.** The search's answer (the film's item id, or
  that it has none) is kept in memory for **30 days**, so a later lookup of the
  same film skips the search, and is dropped from memory once 30 days old. A
  search answer that cannot be read is not kept.
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
  have failed and others remain, it stops and the page says, in gold, "Three in
  a row trip your list, starting with one where <topic>." and, in cream, "Roll
  again, or I can show you what I picked." `<topic>` there is the first topic
  the first film that tripped trips. It offers `Roll again`, the action "Just
  show me what you picked" and `Start over`, in that order; a phone sets
  `Start over` beside `Roll again` and "Just show me what you picked" in a row
  of its own, so the three fit its foot. The reply carries the
  third film that tripped in `last`: the film, the topics it trips and the two
  lines that show it. "Just show me what
  you picked" shows that film as a pick from the reply already held, asking
  no new pick and nothing of DoesTheDogDie (the film's details and pictures
  load as on any pick): "Here's what I picked." in gold
  at the tap, and "Heads up: it's one where <topic>." in cream as its poster
  grows, `<topic>` the first of the viewer's topics it trips, in the order
  DoesTheDogDie lists its votes. It then
  behaves as any pick: `Not that one`, the note and `Start over` work.
- **Every pick is checked.** No request can ask to skip the check: a pick for a
  viewer with topics looks its film up whatever the request carries.
- **Turned-away films.** Every film a pick turns away is reported to the page
  and joins the visit's seen list. The page sends the 200 most recent.
- **Unchecked.** The film is shown with a note, and DoesTheDogDie's credit in
  the foot band, when any of these holds:
  - DoesTheDogDie is slow (no turn, or no answer, within **3 seconds** per
    request) or refuses;
  - DoesTheDogDie holds no record, its search answer or item id cannot be
    read, or a vote row cannot be read;
  - the device has spent its allowance for the hour;
  - the installation has reached its own hourly ceiling;
  - the client is holding its requests after a refusal, or because
    DoesTheDogDie reports the month's allowance nearly spent.

  An unreadable vote row never counts as a pass. The note reads "I couldn't
  check this one against your list, so have a look before you press play." A
  spent device allowance and the installation's ceiling each have their own
  line saying so (`UNCHECKED_LINES`). The note does not name the topics: an
  unchecked film was checked against none of them.
- **Look it up.** Every unchecked film offers an action, "Look it up on
  DoesTheDogDie ↗", beneath its note, opening a new tab. The reply
  carries `dtdd_item`, the film's DoesTheDogDie item as held at that moment,
  read after any lookup has run: never one DoesTheDogDie has just answered 404
  for, and never one older than 30 days. With an item the action opens
  `https://www.doesthedogdie.com/media/<item>`, the film's own page (the API's
  item id is the website's media id: Jaws, TMDB 578, is item 10154 and
  `/media/10154`, confirmed 2026-10-03); with none it opens
  `https://www.doesthedogdie.com`, where the viewer can search. The address
  depends on the item alone. A checked film's reply carries no item.
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

- The note action is offered only on a pick that came through a tree. It is an
  action, "Something wrong with this pick?", beneath the pick's actions. It
  opens a panel. The pick always belongs to a profile this device holds,
  so the panel never asks for a name.
- The panel opens with "How you got here:" and the viewer's answers in order,
  ending with "Just pick one!" when that ended the questions.
- The panel asks "What's wrong with it?" with three choices, offers an optional
  "Why?" box of at most 500 characters, and a "Save" button:
  - "Not <genre> at all", which asks "Where does it belong?". It offers every
    tree except the one that offered the film, the kids tree included, and the
    note keeps every tree ticked;
  - "<Genre>, but not the kind I asked for";
  - "The right kind, just not a good pick".

  "Save" with no choice made says "Tell me what's wrong with it first." and
  saves nothing.
- Every choice, once saved, saves a note and nothing else: the profile, the film, the tree,
  the choice, the answers that led to the pick in words, whether "Just pick
  one!" ended the questions, the comment and a UTC timestamp. A note needs a
  held profile. Its answers are resolved against the tree when it is saved, and
  an answer the tree does not have, a tree that does not exist or a film
  Matinee does not offer now is refused. Where the film belongs is kept only on a "Not <genre>
  at all" note, and only as trees the catalogue holds other than the one that
  offered the film; anything else is refused. Naming a tree changes nothing any
  viewer is shown.
- Once the note is saved the panel says "Thanks. That's gone to whoever runs
  Matinee." in gold and "If they agree, it moves for everyone." in cream. The
  About page's paragraph on films in the wrong place says the same: a viewer
  can say where a film fits best through "Something wrong with this pick?",
  every note reaches whoever runs Matinee, and when they agree the film moves
  for everyone.
- A note outlives the profile that filed it. Deleting a profile leaves every
  note it filed in the store, naming no profile, and anything that lists the
  note shows it as from a deleted profile.
- Every note has a review status. A new note is `open`. A ruling sets it to
  `accepted`, with a one-line reason and the label ruling that fixed it, or to
  `rejected`, with a one-line reason; the store refuses any other combination. A
  reason or a label ruling is one line of 1 to 300 characters. A later ruling on
  the same note replaces the earlier one. A ruling changes no film's placement:
  an accepted note is fixed for every viewer through the operator's label
  rulings and the settle step. Matinee offers no note review on the web.
- **The notes tool**, `tools/notes.py`, is run on the server inside the server's
  image against the state directory (`--state`, or `DATA_DIR`). It never
  creates a store, and it writes only Matinee's own store, never a film's
  placement, labels or pins.
  - `list` prints every open note, oldest first: its id, the film's title and
    year (from the film table, made printable as a comment is), the door's label, the time, the profile's name
    or "a deleted profile", the answers in order (ending "Just pick one!" when
    that ended the questions), what was wrong in the panel's own words with
    where the film belongs (by door label), and the comment, then the count of
    open notes. A film no longer in the film table is named by its TMDB id. A
    viewer's comment is printed on one line, with every control or format
    character shown as U+FFFD, so it can neither forge a note nor reach the
    terminal.
  - `accept <note> "<reason>" --ruling "<the label ruling that fixed it>"` and
    `reject <note> "<reason>"` print the whole note as `list` does, then record
    the ruling.
    Where the note was already ruled, the tool prints the ruling it replaced.
  - `clear-pin "<profile name>"` clears one profile's PIN (section 7).
  - `clear-topics` clears every profile's DoesTheDogDie topics and says how
    many profiles held any (section 8).
  - A note that does not exist, an empty or multi-line reason, or an accept
    without its label ruling is refused, and nothing is written. A store the
    code cannot bring to its shape is refused in words, as at the server's
    start. A state directory with no store exits with status 2; a refusal
    exits with status 1.

## 11. The web surface

### 11.1 Routes

The routes serve Matinee's own page. They are not a public API. The interactive
documentation, ReDoc and the OpenAPI schema are all disabled.

Every `/api/` reply carries `Cache-Control: no-store`. The door's reply marks the
profiles the asking device holds, so a copy kept by a browser or an edge cache
would hand one device's profiles to another.

| Method | Path | Does |
|---|---|---|
| GET | `/` | the page (`Cache-Control: no-cache`) |
| GET | `/api/admission` | whether the site is locked, whether this device is admitted, and the locked door's greeting |
| GET | `/api/setup` | the setup note: its heading, its lines (none when all is well), the films Matinee can offer, whether it offers a way in (section 5.6), and the stale-data warning while the film data is past six months (section 5.2) |
| POST | `/api/admission` | give the door word; the right one sets the admission cookie |
| GET | `/static/…` | scripts, styles, self-hosted fonts, icons, pails, avatars, the locked door's art, manifest (`Cache-Control: no-cache`, so a deploy is never seen half-applied) |
| GET | `/img/{kind}/{tmdb}/{size}` | a poster or backdrop: from the media server for a film the library holds, else from TMDB's image server through Matinee |
| GET | `/api/pictures` | the image source, and under `tmdb` the TMDB poster path of every live film that has one (section 11.5) |
| GET | `/api/film/{tmdb}` | title, year, runtime, synopsis and the pick's link for one film (`link`, and `link_to`: `seerr` or `tmdb`), and under `tmdb` its TMDB backdrop path |
| GET | `/api/door` | the film count, every profile (marking those this device holds), the avatars offered, whether a DoesTheDogDie key is set, and `posters_from` (`server` or `tmdb`) |
| POST | `/api/profiles` | create a profile and issue this device a token |
| POST | `/api/profiles/{id}/open` | open a profile by PIN, or at once when held or PIN-less |
| PUT | `/api/profiles/{id}/topics` | replace a held profile's DoesTheDogDie topics; only with a DoesTheDogDie key |
| PUT | `/api/profiles/{id}/avatar` | set or clear a held profile's avatar |
| DELETE | `/api/profiles/{id}` | delete a held profile, its topics and its tokens; answers its name |
| GET | `/api/topics` | DoesTheDogDie's topic list, with its credit; only with a DoesTheDogDie key |
| GET | `/api/quips` | the pick's lines and their caps (section 2.7) |
| POST | `/api/first` | the source question while it is asked and no `source` is sent (`source`), the first question for this viewer within the source, the pool behind it, and whether this viewer's picks are checked against DoesTheDogDie (`checked`); `fallback` while a `held` or `new` answer cannot be kept (section 2.0) |
| POST | `/api/walk` | the next question and the pool, given a tree and answers; `fallback` as for `/api/first` |
| POST | `/api/pick` | one checked film from the pool the answers leave; `fallback` as for `/api/first` |
| POST | `/api/notes` | keep one note on a pick for a held profile |

### 11.2 What the browser may name

- **A film** only by a TMDB id in the current live film list. Any other id
  answers 404 before any request leaves for the media server.
- **An image** only as `poster` at `xs` (100 px), `s` (160 px), `m` (320 px)
  or `l` (640 px), or `backdrop` at `m` (960 px) or `l` (1600 px). The media-server item id is
  never taken from the browser. Each reader checks its shape before it is
  joined into a request (section 1). An image answer must be `image/*` and at most
  8 MiB. An image 160 px wide or narrower, a wall tile shown dimmed, is asked
  of the media server at quality 60; any other at quality 80. The media
  server's images are served
  with `Cache-Control: private, max-age=2592000` (30 days, as is a TMDB picture
  of a film the library does not hold; a TMDB picture standing in for the
  library's own is kept one day, section 11.5), so a return visit
  draws the wall from the browser's cache. `private` keeps every shared cache,
  such as a CDN in front of the site, from keeping a copy and handing it to a
  device the door word has not admitted.
- **An answer** as a question id and an option index, never as a filter; the
  source answer as `held`, `new` or `all`.
- **Request sizes** are capped: a profile name 80
  and a PIN 8; an avatar 40; topics 400; answers 12; tree names
  40; option indexes 0 to 50; films already seen 200; a note's comment 500;
  trees a note says a film belongs in 32. A pick with no tree may carry no
  answers. A word given at the door over 200 characters is wrong
  without being compared; the request itself sets no length cap on it (known
  gap 15).

### 11.3 What no response carries

No response carries the media server's address or key, a key or token of any
kind, or the door word. No response but the setup note carries a file path, a
disk location or an exception's text; the setup note may, where it names a
fault in Matinee's own files or the household override file (section 5.6). The
media server's key travels only in the header of Matinee's own requests to it,
never follows a redirect, and is never logged. A film card's synopsis is the media server's for a film the library holds, and
TMDB's, from the film table, for any other film, while the library cannot be
used, and when the media server gives none or fails to answer: the card never
answers 503 for that. Synopses always
reach the browser through Matinee's server, and so do posters and backdrops
under the default image source. Under `tmdb`, a picture with a TMDB path is
loaded by the browser from TMDB's image server (section 11.5). The media server
is never exposed to the browser.

Every error leaves as `{"error": <code>, "message": <sentence>}`:

| Code | Status | When |
|---|---|---|
| `not_ready` | 503 | Matinee's own data cannot make a catalog, the film table cannot be used, or (on `GET /api/quips`) the pick's lines cannot be read |
| `topics_unavailable` | 503 | the topic list cannot be fetched |
| `not_found` | 404 | an unknown film, image or path |
| `not_admitted` | 401 | a door word is set and this device has not given it (section 7.2) |
| `wrong_word` | 401 | the word given at the door is not the door word; answered after 2 seconds |
| `refused` | 400, 403 or other | answers that no longer fit, an unknown tree, a profile this device does not hold, a malformed request |
| `profile` | 400, 401, 403, 404, 409 or 423 | a profile rule refused the request; the body adds `code` (`bad_name`, `bad_pin`, `bad_avatar`, `not_held`, `name_taken`, `full`, `no_profile`, `wrong_pin`, `locked`) |

One error falls outside that shape. A request body that fails validation, such
as a field over its size cap, answers 422 with the web framework's own
`{"detail": [...]}` body. That body echoes the offending input back. It carries
nothing from the server.

### 11.4 Headers

Every response, including static files and errors, carries:

- `Content-Security-Policy: default-src 'self'; img-src 'self'; style-src 'self'; font-src 'self'; script-src 'self'; connect-src 'self'; manifest-src 'self'; worker-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'`.
  Under the `tmdb` image source, `img-src` reads `'self' https://image.tmdb.org`
  and every other directive is the same.
- `X-Content-Type-Options: nosniff`
- `Referrer-Policy: same-origin`
- `Permissions-Policy: camera=(), microphone=(), geolocation=()`
- `X-Robots-Tag: noindex`, whether or not a door word is set. Matinee serves no
  robots.txt, because one that blocked crawling would stop search engines from
  reading this header.

The page builds all text as text nodes, never as markup, so a name or title from
the server can never become part of the page's HTML.

### 11.5 The image source

`POSTERS_FROM` says where the page's pictures come from: the wall's posters,
the picked poster and the pick's backdrop.

- **`server`**, the default, or unset or empty. Every picture comes from the
  image route: read from the media server for a film the library holds, and
  fetched by the server from TMDB's image server through one gate (at most 50
  requests a second and 20,000 an hour; a 429 or 503 holds every picture
  request for its `Retry-After`, else 10 s doubling to at most 10 minutes, and
  a request the gate will not admit gets no picture at once), at the TMDB size the table
  below gives, for a film it does not hold, while the library cannot be used,
  and when the media server gives none, so a viewer's browser talks only to
  Matinee. The server keeps each one on its shelf (section 5.2) and asks TMDB
  only for a picture the shelf lacks. A TMDB picture of a film the library does
  not hold is kept by the browser 30 days, as the library's own are; one
  standing in for a film the library holds is kept one day
  (`Cache-Control: private, max-age=86400`), so the library's own art returns
  soon after the library does. A film with no TMDB picture path
  has no picture (404). The server checks a path's shape before joining it into
  an address, and takes an answer only when it is `image/*` and at most 8 MiB. The page asks for exactly the
  addresses it asked for before the setting existed.
- **`tmdb`.** The browser loads a picture with a TMDB path from
  `https://image.tmdb.org/t/p/<width><path>`. A picture with no TMDB path (TMDB
  has none, the film's record is missing or too old, or the film joined the
  library after the last rebuild) comes from the image route. Matinee's sizes
  map to TMDB widths as follows.

  | Picture | `xs` | `s` | `m` | `l` |
  |---|---|---|---|---|
  | poster | `w92` | `w154` | `w342` | `w780` |
  | backdrop | | | `w780` | `w1280` |

- Any other value is a setup fault (section 5.6), and `server` stands.
- An admitted page asks for `/api/pictures` once per visit, beside `/api/door`
  and `/api/first`, before it lays the first wall. A failed reply leaves every
  picture on the image route, logs a warning, and is asked again at the next
  boot. Under `tmdb` the pick reads the backdrop path from the film's card
  before it fetches the backdrop; under `server` it fetches the backdrop at
  once.
- The pick gives up on its sharp poster or its backdrop after **10 seconds**,
  the same limit the server sets on the media server's images. A picture given
  up on is stopped, logged as a warning and never shown; the pick goes on
  without it.
- Every picture the page shows is asked for with CORS (`crossOrigin =
  "anonymous"`). TMDB's image server allows it, so the glow reads a TMDB
  poster's colour as it reads one from the image route.
- A TMDB picture that fails to load leaves its cell dark, as a failed image
  route picture does, and the page logs a warning naming it. Nothing falls back
  to the image route after a failure.

## 12. The page

The colour tokens, the two families of
control (a letterbox chooses something, an action does something) and each
action's accent are those of `DESIGN_STANDARDS.md`. Matinee's lines and the wordmark are set in Big
Shoulders Display, other text in DM Sans. Both fonts are self-hosted with their
OFL licences. All displayed text is in sentence case, except that a cream
part carrying on its gold part's sentence after a comma keeps its first letter
as written. A phone is a viewport 600 px wide or less. The page declares
itself dark only (`color-scheme: only dark`, in its head and its stylesheet),
so a browser's forced dark mode, such as Samsung Internet's, leaves its
colours as they are.

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

  Every question at the door is typed onto the wall below the marquee. On a
  desktop the words are a centred column
  680 px wide, 44 px under the sign, with the line at 52 px and its answers as
  letterboxes. On a phone the line hangs 26 px under the marquee
  at 34 px, and the answers sit at the foot of the screen. A
  short window closes the words up: under 820 px tall on a desktop they start
  28 px under the sign, and under 640 px tall on a phone the line is 26 px. The
  trigger picker sits on the wall too: on a desktop 1000 px wide, the question
  and saving in a 360 px left column and the topics beside it; under 760 px
  wide it stacks as on a phone. Its topics are letterboxes in two aligned
  columns on a desktop, never narrower than 200 px: one column where two would
  each be narrower, and one on a phone; in a row of two both take the taller one's height,
  and a long topic wraps. A chosen topic shows a check mark in a gutter every
  topic keeps before its words, so choosing one never moves or resizes it.
  Under the topics, never beside saving, the action "Read about these on
  DoesTheDogDie ↗" opens DoesTheDogDie's site in a new tab. On a
  desktop it stands beside the line counting the chosen ones; under 760 px
  wide it drops beneath that line when the two do not fit side by side. The
  list scrolls in its own box under the search field, which filters it, and
  the field keeps its own dark fill. On a phone, while the picker is open,
  the crown fades and the sign shrinks to a lit strip of bulbs round the letter
  board, with no name; it returns to full size when the picker closes. The
  marquee stays on screen until the viewer goes in or opens
  About.
  - **The locked door.** The page asks `GET /api/admission` before anything
    else. When a door word is set and the device has not given it (section
    7.2), it asks nothing more: no film list, poster, count, profile or line is
    requested until the word is right. The marquee's letter board reads "Now showing" over "Private
    screening", and beneath it, in place of the poster wall, stands a wall of
    black glazed subway tile (a static SVG pattern, warm glow above, vignette at
    the edges), a wooden frame and step drawn by the page, and the painted door
    (`static/door/door.webp`, an 800 by 1200 web image derived from a painted
    source the repository does not carry). The door hangs 28 px under the marquee's foot, two thirds as wide
    as it is tall; on a desktop its height is what the window leaves beneath,
    between 240 and 600 px. Matinee types
    the greeting as it types the pick's line, first sentence gold, the rest
    cream: left of the door on a desktop, over a feathered dark scrim; between
    the marquee and the door under 1000 px wide, where the door hangs below the
    taller of the greeting and the wrong-word reply as they will stand typed,
    so it never moves while a line types and never covers its end. On a phone
    the tile is not shown, the door takes the screen's width inside the side
    margins and keeps the art's 2:3 shape, so the slot stays on the painted
    opening, running past the screen's foot on a short phone rather than
    squashing. A phone held sideways (under 500 px tall) puts the greeting
    beside the door, as a desktop does. The
    door's painted slot holds the password field, covered by a sliding metal
    cover, with no text or placeholder. The field takes input from the moment
    the door shows, while the greeting types, and holds the focus unless the
    screen is a touch screen. While the field is empty, a gold caret blinks at
    the cover's left end: when the field holds the focus,
    or on a touch screen whenever it can take input. Each character pushes the cover open in proportion, fully at ten,
    and deleting one moves it back; the dots show from the slot's left edge. A small dim eye
    button at the slot's right end, over the cover, shows or hides what is
    typed; the typed text never runs under it, and pressing it leaves the
    focus, and the caret and the view at the end, in the slot. Enter gives the
    word (a blank one does nothing), and the cover shuts (0.4 s) at once while
    the server weighs it. A wrong word clears the field and types "That ain't
    it, pal." in gold and "Try again, or take a walk." in cream in the
    greeting's place, and the field takes input again at once. Any other failure, such
    as the server out of reach, clears the field and types its message the same
    way, first sentence gold. Under reduced motion the greeting appears whole
    and the cover moves at once.
  - **The opening.** The right word asks for the film count, every profile,
    the first question's pool and the pick's lines at once, and lays the
    poster wall behind the locked door. Matinee's line fades (0.35 s) and the door swings inward
    on its left hinge onto a warm glow (0.9 s, to 80 degrees). Once the swing
    has had 0.75 s and the wall behind is drawn and faded in, the door's whole
    layer, tile included, is wiped away in ten vertical bands, each narrowing to
    nothing about its own centre over 0.38 s, the centre two first and the
    outermost two 0.42 s later, the rest evenly between, repainted on every
    frame. 0.25 s into the wipe the letter board turns from "Private screening"
    to the film count. The marquee never moves; the front door adopts it and
    ends with its tiles standing over the poster wall. Nothing passes through
    black. Under reduced motion the change is instant.
  - Every viewing runs under a profile. The door offers no way in without one.
  - **The front door** types its line, then shows every profile as a tile,
    sorted by name, with a "+ New" tile last. A tile is the profile's mark (its
    avatar, or its initials in gold: the first letter of each word of its name,
    at most three) in a rounded square, 128 px on a desktop and 96 px on a phone,
    with the name in large display type beneath, wrapping to at most two lines
    and breaking inside a long word. No tile is marked as held or last used.
    The tiles stand in a column 788 px wide on a desktop and reflow to the
    screen's width, and the wall scrolls when they do not fit; the credit line is the door's last row, below the wall, so tiles
    never pass under it. A desktop window under 760 px tall shows 100 px marks
    and a 40 px line. The "+ New" tile's square is dashed and holds a "+",
    with "New" beneath it.
  - A device holding a profile token sees "Welcome back." in gold and "Who's
    watching?" in cream. A device holding none sees "Welcome." and "Pick your
    seat, or introduce yourself and I'll find you something to watch." When no
    profile exists the line is "Welcome." and "Nobody has a seat yet. Introduce
    yourself. One profile the whole house shares works fine too.", over the
    "+ New" tile alone.
  - A tile opens its profile at once, and goes straight to the first question,
    when this device holds it or it has no PIN. Otherwise the door asks "Hi,
    <name>. What's your PIN?", with "That's not me" back to the tiles; four
    digits are sent as soon as they are typed, and a wrong PIN or a locked
    profile is said beneath the field, which clears for another try. Going in
    keeps the name's flight to the wordmark. A tile whose profile can no longer
    be opened (deleted on another device, or the server out of reach) returns to
    the tiles, refreshed from the server when it can be read, with the reason as
    the door's line.
  - **Making a profile.** "+ New" runs these steps on the wall, each typed as
    gold then cream: "Pull up a chair. What should I call you?", a name field
    and "Continue" (with "Never mind" back to the tiles). A name that is already
    a profile's, ignoring case and runs of spaces, asks "I already have a
    <name>. Is that you?": "Yes, that's me" opens that profile as its tile would,
    asking its PIN when it has one; "No, someone else" asks "Then I'll need
    another name, so I can tell you two apart." Then "Nice to meet you, <name>.
    Would you like to set an avatar?" with the fifteen avatars at 88 px (68 px
    in a desktop window under 760 px tall; on a phone, five across) and "Just my
    initials". Then "Want a PIN? Four digits
    keeps your list private." with "Set a PIN", which opens a four-digit field
    in place beside "No PIN", and "No PIN". The profile is made once the name,
    the avatar or initials and the PIN choice are known, whether or not
    anything is chosen to steer around. A name taken on another device
    meanwhile asks "Is that you?" of that profile; a full theatre returns to the
    tiles with why; an unacceptable name returns to the name step; any other
    failure stays on the PIN step with why, keeping the name and avatar. Enter
    in the name field never also presses the next screen's first button. Then
    "One more question." in gold and "Is there anything you'd rather not see
    happen on screen?" in cream, with a body-type line beneath it, "Things like
    spiders or needles. Pick them and I'll skip any film that has them.", over
    "Yes, let me pick from a list", which opens the trigger picker for the new
    profile ("No problem. What should I steer around?", "Save and continue",
    "Never mind, show me everything", each leading on to the last step), and
    "No, show me everything", which goes to the last step with no list. Last, "You're all set, <name>." over a centred
    "Find me something to watch" action, which goes in
    to the first question. Without a DoesTheDogDie key (section 8) the "One more
    question." step is skipped: the PIN choice goes straight to the last step.
- **Going in.** Every answer at the door that leads into the theatre asks for
  the walk's first screen at the tap, and a door is entered once: a second tap or
  Enter changes nothing. The door's words and the corner credit line fade out
  (0.3 s), and the rest of the marquee fades over 0.55 s while it lifts 110 px
  and shrinks to 0.93 of its size over 0.8 s. Meanwhile "Matinee" flies from
  the sign's letters to the wordmark's place at the top left, shrinking to the
  wordmark's 30 px and losing its glow, over 0.9 s. It lands letter for letter
  on the theatre's wordmark, placed as the top bar will place it with the
  viewer beside it, and gives way to that wordmark when the theatre's screen is
  built.
  The poster wall stays on screen throughout. No transition on the page passes
  through black. The walk's first screen (the source question, or the doors
  when it is not asked) types once the name has landed and the screen has
  arrived; a landing that never reports counts as landed 0.95 s after the
  flight began. When the viewer's pool differs from the door's, the
  wall re-sorts in place as after any answer. From a phone's lit strip, which
  draws no name, the name stands at the wordmark's place at once while the
  strip lifts, and the question still waits the flight's time. Under reduced
  motion the change is instant. "Edit my list", "Switch profiles" and a deleted
  profile return to the door with the marquee already in place and lit; the
  name does not fly back.
- **The wordmark.** Inside the theatre the top bar's wordmark "Matinee" is a
  link: activating it, by click, tap or keyboard, does what `Start over` does,
  back to the walk's first screen as the same viewer. On the setup note, and on
  a problem screen reached before going in, where there is no viewer yet, it
  goes back to the door, by way of the setup note when that has more to say. On
  the front door the marquee stands in its place, so there it does nothing.
- **Scrims.** Every piece of text standing on the poster wall stands on a
  scrim: a feathered dark patch, the page base at 92 per cent across the text's
  whole block, corners included, fading to nothing about 40 px beyond it with
  no edge. That covers Matinee's lines (each of its two parts), the countdown,
  notes, status lines, counts, footnotes, the tile names, the film's title,
  year and synopsis, and the open "Something wrong with this pick?" panel.
  Every scrim paints behind all of a screen's text and controls. No scroll box
  cuts a scrim: the door's column (the words and tiles that scroll under
  the marquee) keeps 40 px of room above its first line, and
  the phone pick's foot fades its top and its foot over 20 px, so a scrim at
  either end fades with its text. The locked door's greeting keeps its own scrim
  on subway tile.
- **Bands.** Every screen over the poster wall has a dark band at the top and
  at the foot, as `DESIGN_STANDARDS.md` 6.3 sets them: behind the top bar with the
  wordmark and the viewer, and behind the foot with the trail and the credit
  line. The top band lies behind everything on the screen and scrolls away
  with the top bar. The pinned foot bar carries its fade inside its own
  height, so nothing rests under the fade and what scrolls beneath fades under the band. On the
  door's screens the marquee's fade is the top band, and the foot band lies
  behind the door's last row, and what scrolls in the door's column fades out
  over its foot padding; going in, the credit line fades and the band stays.
  A problem screen carries the credit line at its foot. The locked door has
  no bands. About's panel stands over the bands, which stay showing beneath
  it; opened from the door, whose marquee leaves with its fade, About has the
  theatre's top band.
- **The poster wall.** A flat grid of the posters of the films still in the
  pool, each its own image element, sharp and upright, held at 35 per cent
  strength. The wall holds that one
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
  question), and the answers appear once it finishes. No line Matinee types
  shows a caret, while it types or after. The line and the answers
  keep apart, and nothing re-centres as the line types or the answers appear:
  the line hangs from the top of the screen with three lines reserved, so on
  desktop the answers start at the same height on every question whose line
  fits in three; on a phone the answers sit at the foot of the screen. On
  desktop and on a phone the answers are letterboxes.
  A question's footnote appears with the answers, in 16 px cream body type beneath
  them and above "Just pick one!". The first action on a screen
  disables every button on it. The count of films still in the running stands
  beside "Just pick one!" on every question screen, reading "<N> films to
  choose from" or "1 film to choose from", the exact number with thousands
  separators; on a narrow phone it wraps its own words rather than drop below
  the button. The top bar shows no count, the pick screen shows none, and the
  marquee's letter board keeps the total Matinee offers.

  The walk's first screens are question screens too. The source question
  (section 2.0) types "Right this way, <name>." in gold and its question in
  cream, over its three answers as letterboxes, one beneath another; its count
  and `Just pick one!` cover the library's films. The doors then type the
  source answer's reply in gold and "So, what are we in the mood for?" in
  cream, over the door answers as letterboxes running across the screen and
  wrapping; their count and `Just pick one!` cover the source's films. With the
  source question not asked, the doors open the walk with the greeting in its
  place. The wall shows the films the screen's count covers.
- **The setup note** (section 5.6). The page asks for it, once the device is
  admitted, each time it heads for the front door: on loading, after the locked
  door opens, and on every return to the door. It shows a note with a way in
  once per page load, and one without every time. The note empties the poster
  wall and stands under the
  theatre's top bar, its wordmark at the left and no viewer. Its heading, "A
  word before the show.", types in gold; then its lines appear together, one
  paragraph each, in 19 px cream body type on the wall's scrims, and beneath
  them one action, which takes the focus: the gold "Show me the films", or the
  cream "Try again" when there is no film to offer. Either asks for the door
  afresh, so "Try again" shows the note again while it still has no way in.
  Its foot band carries "About Matinee" and the credit line.
  (`src/matinee/web/static/js/main.js::setupNote`, `saidSetup`)
- **The stale-data warning** (section 5.2) stands in a strip across the top of
  the screen, above everything, from the first screen after admission: the
  server's sentence in 14 px bold dark type, centred, on a rose ground. The
  screen starts beneath the strip, however many lines it wraps to. The page
  reads the warning with the setup note, so the strip comes and goes when the
  page loads or returns to the door. Before the door word is given, the page
  asks for neither.
  (`src/matinee/web/static/js/main.js::showWarning`)
- **The fallback notice** (section 2.0) stands in the same strip, after the
  stale-data warning when both stand. Each walk response sets it: one carrying
  `fallback` shows it, one without takes it down and leaves the stale-data
  warning as it was.
  (`src/matinee/web/static/js/main.js::showFallback`)
- **The viewer.** Inside the theatre the top bar holds the wordmark at the left
  and the viewer at the right: the profile's mark in a 40 px rounded square and
  its name in the wordmark's face, smaller, in cream, on a dark backing so it
  reads over any poster. Activating either, by click, tap or keyboard, opens a
  menu of "Edit my list" (the trigger picker on the door, headed "Your list.
  What should I steer around?", whose "Save my list" and "Never mind, keep my
  list" both go back in), "Change avatar", "Switch profiles" (back to the front
  door's tiles, the marquee already in place and lit), "Delete profile" in
  red and "About Matinee" (the About page, which gives the focus back to the
  viewer when it closes), in that order; without a DoesTheDogDie key "Edit my
  list" is not in it.
  Escape (wherever the focus is), a tap elsewhere, focus
  leaving the viewer, or choosing an item closes it; the arrow keys walk its
  items, round from the last to the first. The same closes either panel
  below. On a phone the bar is one row: a name of 10
  characters or fewer shows in full, and a longer one shows as initials (the
  first letter of each word, at most three) beside the avatar, or as the
  avatar's own initials when it has none.
- **Change avatar** opens a panel beneath the viewer (across the screen's width
  on a phone, at most 560 px wide on a desktop): "Which one's yours?" typed in
  gold, the fifteen avatars six across (five on a phone), filling the panel's
  width, with the current one marked, and "Just my initials". A tap saves the choice,
  closes the panel, and the bar shows the new mark at once; a refusal stays on
  the panel and says why. Escape or a tap elsewhere closes it unsaved.
- **Delete profile** asks in a panel beneath the viewer, never in a browser
  dialog: "Delete <name>?" in gold, "Your list goes with it. Any notes you sent
  stay with whoever runs Matinee." in cream, then "Yes, delete it" (in red) and
  "No, keep it", which holds the keyboard's focus. "No, keep it", Escape or a
  tap elsewhere changes nothing. "Yes, delete it" deletes the profile (section
  7) and returns to the front door, whose line reads "Done." and "<name>'s seat
  is empty." over the tiles; a refusal stays on the panel and says why.
- **The profile menu's panels** ("Change avatar" and "Delete profile") show
  their letterboxes with no glow at rest; each glows on hover.
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
  screen: the line, then `Not that one`, "More on Seerr ↗" (a link to the
  film's page on the configured Seerr, opening a new tab; without a Seerr, or
  while it does not answer, it reads "More on TMDB ↗" and opens
  `https://www.themoviedb.org/movie/<tmdb>`, for every pick) and `Start over`,
  actions in one row where the column is wide enough (from about 1,320 px of
  window), wrapping beneath one another below that, then the
  note action. The left column takes a third of the row, widened toward
  470 px but never past 38 per cent of it. An unchecked film's note and its
  "Look it up on DoesTheDogDie ↗" action (section 9) follow the
  synopsis, on a phone as on a desktop. A film the library does not hold shows
  exactly as a library film does: the same layout, words and actions.

  On a phone Matinee's words keep the foot of the pick screen, 316 px tall,
  which holds without scrolling, from its top, the line (four lines reserved),
  `Not that one` and "More on Seerr ↗" (or TMDB) in one row, "Back" and
  `Start over` in the next (only `Start over` where "Back" would lead to the
  walk's first screen), and the note action, all at the standard size. Beneath
  it the foot band carries DoesTheDogDie's credit line where an installation has
  a key, and nothing else, and rises 48 px behind Matinee's words. Only
  something taller than the foot, such as the open note panel or a line longer
  than its four lines, scrolls inside it. The foot's top never moves from the first word of a pick to the
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
  the category the first answer led to: its own lines, each set (reveal, nope, rush)
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
  self-destructs is the exception: its fuse owns the line. "Just pick one!"
  deals a rush line, which stands in the reply's place by every rule above. On `Not that one` and "Roll again" a nope line
  and a reveal line are dealt together within the combined cap: when a pair
  is over it, the longer line goes back unshown and its set deals the next
  that fits beside the other, then, if the pair is still over, the other is
  redealt the same way, and a set with no line left that fits gives its
  shortest line. The nope line types in gold at the tap and stays through the
  wait and the hunt, and the reveal line types beneath it in the text colour
  as the new poster grows. Where the check turned a film away, its reason
  types in gold in the nope line's place and stays, and only the reveal line
  is redealt to fit beneath it within the cap. DoesTheDogDie's credit shows in the
  foot band before the reason starts to type and stays for the rest of the
  pick; on the resting page the "What were you going to show me?" action
  stands beneath the actions. The three-in-a-row and exhausted-pool lines, and
  the trip of a film shown after three in a row, likewise have the credit on
  screen before they type. A pick with no film speaks no quip; its line types its first sentence in
  gold and the rest in cream.

  `Not that one` asks for the next film at the tap and carries the resting
  poster back from where it rests to its cell on the wall, at the wall's size
  and strength, over 0.45 s while the wall's dimming lifts (at once under
  reduced motion; with no poster at rest the dimming alone lifts over 0.45 s).
  The wall then drifts, and the returned poster rests in its cell, until the
  next film is known; the check's line does not type, and the nope line holds
  the screen. The next hunt starts
  from where the wall stands, by every rule above. "Roll again", after three
  films in a row were turned away, is a new pick: its nope line types in gold
  at the tap, as on `Not that one`, and its check line types beneath it.
  "Just show me what you picked" asks for no new pick, so no check line types.

  A trail answer, the wordmark, a profile menu item that leaves the theatre
  ("Edit my list", "Switch profiles", a confirmed "Delete profile") or `Start
  over` ends the pick at the tap: the
  hunt stops where it is, the wall drifts again, and the pick changes nothing
  further. A film the hunt placed keeps its cell until the next pool's
  posters take over.

  While a DoesTheDogDie check runs, the page types "One moment. Let me check
  this one against your list." and the wall keeps drifting.

  The wall's geometry and re-sort plan, the hop plan and its speed limit, the
  glow colour and the quip deal are modules that touch no page. Their tests
  under `tests/js/` run with `node --test` from `./check.sh`. The page's
  mechanical design rules (`DESIGN_STANDARDS.md` section 9) are held by
  `tests/test_design_standards.py`, which reads the stylesheet and the page
  scripts as text.
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
  [logo]", the logo linked to TMDB. It sits at the bottom right of the door,
  the setup note, the question screens, the pick screen and a problem screen on
  a desktop (13 px). A phone shows no TMDB credit line on any screen: the About
  page carries TMDB's logo and notice (section 14). DoesTheDogDie's credit,
  where it shows, stands centred at a phone's foot (11 px). The link to the About
  page is named "About Matinee" on every screen: inside the theatre it is the
  profile menu's last item; on the door, the setup note and a problem screen,
  which have no profile menu, it sits at the bottom middle, apart from the
  credit (on a phone, centred above it). The TMDB logo is smaller than Matinee's own mark.
  MovieLens is credited on the About page. Where DoesTheDogDie's data shows
  (section 14) the line ends with "Powered by DoesTheDogDie.com", linked: on
  the trigger picker while it holds DoesTheDogDie's topics, and on a pick
  screen once it shows a line or note built on that data, or the used-up
  line. Every other door
  screen, a pick screen showing none, and a question or problem screen leave it
  off. Nowhere on the wall carries it. On a
  phone's pick screen, where the installation has a DoesTheDogDie key, it takes
  a line of its own, kept for it whether or not it shows, so the foot never
  changes height when it appears.
- **About.** A screen inside the page, with no address of its own and no
  server route. It opens over whatever screen is showing, as a centred dark
  panel 65 per cent opaque over the poster wall, 1040 px wide on a desktop and
  the screen's width less a 16 px gutter each side on a phone, with no sideways
  scroll. The screen underneath, its credit line included, is hidden, never
  rebuilt or paused, so only the posters and the screen's two bands show
  through (Bands, above); it shows again exactly
  as it stood when About closes. Matinee's wordmark stands at the theatre
  wordmark's place: fixed from 1400 px wide up, and scrolling away with the page
  below that so it never sits over the text. About scrolls as a page when the panel
  is taller than the screen. "Back" at its top, the browser's Back, a phone's back gesture
  and Escape each close it and return the focus to what opened it ("About
  Matinee" at the foot, or the viewer's button for the profile menu's item): opening it
  adds one history entry at the same address, and a second Back leaves the page
  rather than reopening About. The title is 68 px, the lead 23 px and the
  paragraphs 19 px (on a phone the title is at most 13 per cent of the screen's
  width, the lead 20 px and the paragraphs 17 px); section headings are gold,
  in the display face. The copy, in order: a lead; "Why it exists", whose last paragraph says a
  viewer can tell Matinee where a film fits best through "Something wrong with
  this pick?" and that a note the operator agrees with moves the film for
  everyone (section 10); "How it
  knows what a film feels like", with links to MovieLens and the tag genome
  dataset and the two MovieLens citations; "How it steers around things", with
  "Powered by DoesTheDogDie.com", linked, only with a DoesTheDogDie key
  (section 8); "Posters and film data", with the
  TMDB logo (14 px tall), linked, and TMDB's notice; "Good company", naming
  Jellyfin and Seerr with a link to each, on every installation whichever
  media server and request service it uses, or none; and "What Matinee keeps",
  the installation's privacy statement (section 14). It states no count that
  changes over time. Opened from inside, About moves nothing. Opened from the
  door, the name flies to the wordmark's place and the rest of the marquee lifts
  and fades, as on going in; the screen underneath is hidden once the name has
  landed, and the panel fades in 0.8 s after opening (at once under reduced
  motion). Closing it flies the name back to the sign, from wherever it is, and
  the marquee and the door's words return. From a phone's lit strip the name
  stands at the wordmark's place at once, and closing removes it.
- **Failures.** A failed request shows its message and "Try again". No stale
  film list is shown, with one exception: when the walk's first screen fails
  after the viewer goes in, the problem screen keeps the door's posters on the wall
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
  matinee.web.main:build --workers 1` on port 8000, no server header and no access log, so no visitor's address is logged. It
  trusts forwarded headers from any address, so it must sit behind a reverse
  proxy. The image carries `tools/`, so the same image can run the nightly
  rebuild with `--daily`.
- **`compose.yaml`** runs the image twice from the repository's folder: the
  server, built there, on port 8000, and the rebuild (`--daily`, never pulled),
  both reading `.env` and mounting `./state` at `/state`. It needs no editing;
  `./state` is ignored by git and kept out of the build context.
- **State** is one directory mounted at `/state` (`DATA_DIR`). It holds
  the film table (`films.sqlite`, and `films.sqlite.kept` while a rebuild
  runs), Matinee's store (`matinee.sqlite`), the door's secret (`door.key`,
  made at the first start with a door word), the TMDB cache
  (`tmdb/films.jsonl`) and its shelf of pictures (`tmdb/pictures/`), the
  rebuild's report (`rebuild.json`) and, where the
  household keeps one, its override file (`overrides.json`). None of it is in
  the image. The labels ship in the image with the code (`data/labels.json`).
- **Settings and keys arrive as environment**, never committed, logged or sent
  to a browser. `.dockerignore` keeps `.env` files out of the image.

| Variable | Used by | Holds |
|---|---|---|
| `DATA_DIR` | server, rebuild, notes tool | the data directory |
| `JELLYFIN_URL`, `JELLYFIN_API_KEY` | server, rebuild | a Jellyfin library's address and key |
| `PLEX_URL`, `PLEX_TOKEN` | server, rebuild | a Plex library's address and token |
| `SEERR_URL` | server, optional | the base of the "More on Seerr ↗" action's address; unset or empty means "More on TMDB ↗" |
| `DTDD_API_KEY` | server, optional | the DoesTheDogDie key; unset or empty means no list of topics and no check (section 8) |
| `TMDB_TOKEN` | rebuild | the TMDB read token |
| `TMDB_RATE` | rebuild, optional | TMDB requests a second, 30 by default; any positive number (section 5.1) |
| `DOOR_WORD` | server, optional | the door word (section 7.2); unset or empty means no lock |
| `DOOR_MATCH` | server, optional | `relaxed` (the default) or `strict` |
| `DOOR_GREETING` | server, optional | `show` (the default), `gin`, or the operator's own greeting |
| `POSTERS_FROM` | server, optional | `server` (the default) or `tmdb`: where the page's pictures come from (section 11.5) |
| `REBUILD_TIME` | rebuild, optional | the nightly rebuild's time for `--daily` alone, `HH:MM`, 04:30 when unset or not a time (section 5.1) |
| `TZ` | server, rebuild, optional | a tz database name; the clock `--daily` and the logs follow, UTC in the image when unset |

The repository's `example.env` lists every setting above, each commented out,
grouped and explained, under a box that tells the installer to copy it to `.env`,
uncomment what they need, write each value straight after `=` with no spaces or
quotes, and fill in Jellyfin or Plex but not both. It carries no value for any key,
token or door word.

No setting carries a `MATINEE_` prefix, and the old names are not read. An
installation reads one media server: Jellyfin when `JELLYFIN_URL` and
`JELLYFIN_API_KEY` are set, Plex when `PLEX_URL` and `PLEX_TOKEN` are. No setting
names the server. An address must start with `http://` or `https://`. An
optional service is on when its setting is filled in and off when it is empty.

## 14. Third-party terms

The terms of each source are part of the design.

- **TMDB.** Every installation fetches TMDB's records under its own key
  (`TMDB_TOKEN`), and no TMDB record ships in the repository. Cached at most six
  months (section 5.2). The notice "This product
  uses the TMDB API but is not endorsed or certified by TMDB." appears on the
  About page. The TMDB logo appears there and, on a desktop, in the corner
  credit line of the door, the question screens, the pick screen and a problem
  screen, less prominent than Matinee's own mark. TMDB's terms ask for the logo
  to identify the use and for the notice shown prominently in the application,
  not on every screen, so a phone carries both on the About page alone. TMDB data is non-commercial under the default licence.
  Under the `server` image source the server fetches TMDB's pictures for the
  films the library cannot picture, through one gate (section 11.5). Under the
  `tmdb` image source, a viewer's browser loads pictures from TMDB's
  image server, so TMDB sees that browser's requests. The page sends them with
  no referrer (`Referrer-Policy: same-origin`).
- **The privacy statement.** DoesTheDogDie's API terms bind whoever holds a key
  to keep a privacy policy for the application (section 2.4(b)). The About
  page's last section, "What Matinee keeps", is that policy for every
  installation. It says, in order: Matinee runs on its owner's computer and
  sends nothing to its maker or anyone else, with no accounts, ads or tracking;
  it asks for no email or real name and does not log a visitor's address (the
  image runs uvicorn with no access log); what the store and the cookies keep
  (each profile's name, avatar, scrambled PIN, and its topics only with a
  DoesTheDogDie key; notes; the two cookies, up to 400 days); what leaves the
  computer (the DoesTheDogDie lookup of the picked film only, with a key, the
  topics never leaving and the answer kept at most 30 days; TMDB's records,
  fetched with nothing about a viewer; under `tmdb`, the browser's own picture
  requests); that the library is only read; and that a PIN guards a profile,
  deleting a profile removes it and its topics while its notes stay, and
  whoever runs the installation removes anything else. Each sentence states
  only what the code does, and a change to what Matinee keeps or sends amends
  it.
- **MovieLens tag genome.** Credited on the About page to F. Maxwell Harper and
  Joseph A. Konstan (2015), *The MovieLens Datasets: History and Context*, and
  Jesse Vig, Shilad Sen and John Riedl (2012), *The Tag Genome: Encoding
  Community Knowledge to Support Novel Interaction*. The raw dataset is never
  committed. Each derived table Matinee ships carries the dataset's own
  conditions: `data/reference.json` and `data/genome.json` state them in their
  `licence` field (research and
  non-commercial use, no implied endorsement, redistribution only under the
  same conditions).
- **DoesTheDogDie.** Queried one film at a time, at the moment of a pick. Never
  fetched ahead, never used to build a score. Votes are never kept. The search's
  answer for a film, and the topic list, are remembered for at most 30 days, the
  refresh period the terms set for a performance cache (sections 8 and 9). "Powered by
  DoesTheDogDie.com", linked to `https://www.doesthedogdie.com`, appears
  in the foot band's credit line of every screen that shows its data: the
  trigger picker, the swap reason, the unchecked note, the exhausted pool, the
  three-in-a-row line and the film shown after it. It also appears on the About
  page. The page gives the used-up line (section 9) the same credit, whether or
  not the viewer holds topics, because that line reaches the page in the same
  field as the exhausted pool's. Where a line is typed from its data, the
  credit is on screen before the line starts to type and stays while the line
  does. The free tier is non-commercial.

## 15. Out of scope

Not part of this build, and not to be added until asked:

- a checker run over every film in the genome;
- a CLI or HTTP API for anyone but Matinee's own page;
- `Watch this`, or any hand-off to a player;
- thumbs up and thumbs down;
- personal modes learned from examples;
- a TV layout;
- notes shared or pooled between installations;
- any administrative surface, including PIN reset;
- offline use of the installed page;
- reading two media servers at once;
- a marker on the pick screen for a film the library does not hold.

---

# Known gaps

Behaviour that is deliberately absent, still open, or short of the contract,
as the code stood on 2026-10-05.

**Short of the contract:**

1. **A profile needs nothing chosen to save.** `POST /api/profiles` accepts
   empty topics, as the page's own picker does. Any admitted
   device (every device, with no door word set) may create profiles until the
   cap of 50 fills. (`src/matinee/web/app.py::add_door_routes`,
   `src/matinee/store.py::Store.create`)
2. **A film with no genres fails reachability.** It is not set apart as a
   metadata fault. (`tools/check_trees.py::check_reachability`)

**Deliberately absent or open:**

3. **No cap on notes per profile.** One held profile can file notes without
   bound. (`src/matinee/store.py::Store.note`)
4. **The per-device allowance is per cookie.** A client that discards
   `matinee_device` is issued a new one with a fresh allowance. The
   installation's hourly ceiling still bounds it. (`src/matinee/web/viewing.py::device_id`)
5. **"Slow" is timed per request, not per film.** A film lookup is two
   requests. Each may wait up to 3 seconds for its turn, then pause for the
   pacing allowance, then allow 3 seconds for an answer. One check can therefore
   take longer than 3 seconds before it counts as slow.
   (`src/matinee/dtdd.py::Dtdd.get`, `src/matinee/pick.py::look_up`)
6. **Names are compared after NFKC normalisation and case folding only.**
   Look-alike letters from other scripts count as different names. The refusal
   message says names are "letters, numbers or spaces". The rule accepts any
   printable character. (`src/matinee/store.py::clean_name`,
   `src/matinee/web/common.py::PROFILE_LINES`)
7. **The allowances, holds, pacing, item ids and topic list live in memory.** A
   restart forgets every device's spent lookups, the hour's ceiling, any hold,
   every remembered item id and the kept topic list, and a second worker would
   double every limit.
   (`Dockerfile:1`)
8. **Validation failures use the framework's error shape.** A request body
   that fails validation answers 422 with `{"detail": [...]}`, not Matinee's
   `{"error", "message"}` shape. (`src/matinee/web/app.py::add_error_handlers`)
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
    (`src/matinee/trees.py::parse_tree`)
12. **Nothing ties a kind to its answer's words.** An answer may filter on any
    labelled flavour of its tree, so an answer worded for heists that names the
    cops flavour loads and passes the checker. (`tools/check_trees.py::check_answer_coverage`)

**Short of the contract, in the page:**

13. **The door can be entered while About is open over it.** A late answer to
   a profile opening, or the keyboard reaching the door's controls during the
   name's flight, can take the viewer in behind the panel.
   Closing About then flies the full-size name back over the theatre.
   (`src/matinee/web/static/js/door.js::Door.bringBack`)
14. **The name's home on the sign is measured once.** A resize or a phone
    rotation while About is open over the door lands the returning name where
    the sign's letters stood before, not where they stand now.
    (`src/matinee/web/static/js/door.js::Door.leave`)

**Short of the contract, at the door word:**

15. **The door's request sets no length cap on the word.** Every other request field
    is capped (section 11.2), but `POST /api/admission` takes a word of any
    length, from a device not yet admitted, and refuses one over 200
    characters without comparing it, after the usual 2-second wait.
    (`src/matinee/web/app.py::WordIn`, `src/matinee/web/admission.py::MAX_TYPED`)

**Short of the contract, in the page (continued):**

16. **DoesTheDogDie's credit wording lives in two places.** The page writes
    "Powered by DoesTheDogDie.com" itself, and the pick and topic replies carry `credit`
    and `link` as well, which the page reads only for the link's address.
    (`src/matinee/web/static/js/credits.js::dtddCredit`,
    `src/matinee/web/viewing.py::PickOut`, `TopicsOut`)
---

# Part 2 — Map

A pointer to where each part lives, never proof of what it does. Every entry was
verified against the source on the date in its row. Line numbers drift; search by the
symbol when one does not match.

### Boundaries and the library

| Handle | Where | Verified |
|---|---|---|
| `src/matinee/library/__init__.py::Library` | `src/matinee/library/__init__.py:51` | 2026-10-05 |
| `src/matinee/library/__init__.py::LibraryFilm` | `src/matinee/library/__init__.py:27` | 2026-10-05 |
| `src/matinee/library/jellyfin.py::JellyfinReader` | `src/matinee/library/jellyfin.py:69` | 2026-10-05 |
| `src/matinee/library/jellyfin.py::JellyfinReader.films` | `src/matinee/library/jellyfin.py:126` | 2026-10-05 |
| `src/matinee/library/jellyfin.py::JellyfinReader._get_json` (the key in an unredirected header) | `src/matinee/library/jellyfin.py:78` | 2026-10-05 |
| `src/matinee/library/jellyfin.py::JellyfinReader.image` (no key, size and type caps) | `src/matinee/library/jellyfin.py:107` | 2026-10-05 |
| `src/matinee/library/jellyfin.py::ITEM_ID` | `src/matinee/library/jellyfin.py:28` | 2026-10-05 |
| `src/matinee/library/jellyfin.py::parse_film` (`{tmdb-N}` folder tag) | `src/matinee/library/jellyfin.py:49` | 2026-10-05 |
| `src/matinee/library/plex.py::PlexReader` (every movie section) | `src/matinee/library/plex.py:105` | 2026-10-05 |
| `src/matinee/library/plex.py::PlexReader._get` (GET only; the token in an unredirected header) | `src/matinee/library/plex.py:116` | 2026-10-05 |
| `src/matinee/library/plex.py::parse_film` / `_tmdb` / `certificate` (runtime, rating, folder tag) | `src/matinee/library/plex.py:84` | 2026-10-05 |
| `src/matinee/library/plex.py::ITEM_ID` / `TMDB_GUID` / `LEGACY_TMDB_GUID` / `US_PREFIX` | `src/matinee/library/plex.py:29` | 2026-10-05 |
| `src/matinee/library/choice.py::configured_server` (the server whose settings are filled in; none, or refused for both) | `src/matinee/library/choice.py:49` | 2026-10-05 |
| `src/matinee/library/choice.py::MediaServer` / `ServerChoiceError` / `open_reader` | `src/matinee/library/choice.py:31` | 2026-10-05 |
| `src/matinee/__init__.py::USER_AGENT` (every outbound request names Matinee) | `src/matinee/__init__.py:5` | 2026-10-05 |

### Conversation model

| Handle | Where | Verified |
|---|---|---|
| `data/first_question.json` (lines, answers, labels) | `data/first_question.json:23` | 2026-10-05 |
| `data/first_question.json` `source` (the source question's wording, answers and replies) | `data/first_question.json:3` | 2026-10-05 |
| `src/matinee/trees.py::parse_tree` | `src/matinee/trees.py:233` | 2026-10-05 |
| `src/matinee/trees.py::Tree.apart` (a flavour the tree does not define is refused) | `src/matinee/trees.py:85` | 2026-10-05 |
| `src/matinee/trees.py::Question.footnote` | `src/matinee/trees.py:73` | 2026-10-05 |
| `src/matinee/trees.py::SOLE_SIGNALS` / `_check_flavours` (`labelled`, `specials`, `always_shown`) | `src/matinee/trees.py:218` | 2026-10-05 |
| `src/matinee/trees.py::load_trees` (duplicate names refused) | `src/matinee/trees.py:253` | 2026-10-05 |
| `src/matinee/trees.py::FILTER_KEYS` / `OPTION_KEYS` / `QUESTION_KEYS` | `src/matinee/trees.py:88` | 2026-10-05 |
| `src/matinee/trees.py::parse_filter` | `src/matinee/trees.py:148` | 2026-10-05 |
| `src/matinee/engine.py::STOP_UNDER` | `src/matinee/engine.py:56` | 2026-10-05 |
| `src/matinee/engine.py::Source` / `SOURCES` (the three pools) | `src/matinee/engine.py:59` | 2026-10-05 |
| `src/matinee/engine.py::Viewer.source` (bounds every pool, count and pick of the walk) | `src/matinee/engine.py:70` | 2026-10-05 |
| `src/matinee/engine.py::SourceOption` | `src/matinee/engine.py:115` | 2026-10-05 |
| `src/matinee/engine.py::Catalog.sources` (per source, the films it holds) | `src/matinee/engine.py:137` | 2026-10-05 |
| `src/matinee/engine.py::source_masks` (`held` from the live list; none without one) | `src/matinee/engine.py:414` | 2026-10-05 |
| `src/matinee/engine.py::load_catalog` | `src/matinee/engine.py:379` | 2026-10-05 |
| `src/matinee/engine.py::_first_option` (label required) | `src/matinee/engine.py:291` | 2026-10-05 |
| `src/matinee/engine.py::first_question` | `src/matinee/engine.py:549` | 2026-10-05 |
| `src/matinee/engine.py::base_pool` (the source, then the topic skip) | `src/matinee/engine.py:422` | 2026-10-05 |
| `src/matinee/engine.py::walk` | `src/matinee/engine.py:497` | 2026-10-05 |
| `src/matinee/engine.py::_gate` (`only_if_pool_over`, `skip_if_topics`) | `src/matinee/engine.py:480` | 2026-10-05 |
| `src/matinee/engine.py::_shown` (empty answers hidden, `not_after`, small kinds hidden) | `src/matinee/engine.py:457` | 2026-10-05 |
| `src/matinee/engine.py::KIND_MIN_FILMS` | `src/matinee/engine.py:57` | 2026-10-05 |
| `src/matinee/engine.py::_too_small` (`always_shown`, a kind another answer leaves out; counted in the source) | `src/matinee/engine.py:352` | 2026-10-05 |
| `src/matinee/engine.py::_answer_masks` / `Catalog.small` (`small` per source) | `src/matinee/engine.py:369` | 2026-10-05 |
| `src/matinee/engine.py::_hold_apart` / `Catalog.apart` | `src/matinee/engine.py:339` | 2026-10-05 |
| `src/matinee/engine.py::opening_pool` | `src/matinee/engine.py:438` | 2026-10-05 |
| `src/matinee/engine.py::_served` (apart films stay out until their answer) | `src/matinee/engine.py:446` | 2026-10-05 |
| `src/matinee/engine.py::_asked` / `Asked.footnote` (footnote and asterisks dropped with the apart answer) | `src/matinee/engine.py:467` | 2026-10-05 |
| `src/matinee/web/viewing.py::asks_source` (asked while the library can be used and both pools hold a film) | `src/matinee/web/viewing.py:205` | 2026-10-05 |
| `src/matinee/web/viewing.py::source_for` (before an answer, the library's films; unasked, every film) | `src/matinee/web/viewing.py:212` | 2026-10-05 |
| `src/matinee/web/viewing.py::fallback_for` (`held` or `new` while the library does not answer or turned down the key) | `src/matinee/web/viewing.py:220` | 2026-10-05 |
| `src/matinee/web/setup.py::fallback_line` (the fallback notice's wording) | `src/matinee/web/setup.py:69` | 2026-10-05 |
| `src/matinee/web/viewing.py::SourceQuestionOut` / `SourceOptionOut` | `src/matinee/web/viewing.py:105` | 2026-10-05 |
| `src/matinee/web/viewing.py::everything` (the first question's pool) | `src/matinee/web/viewing.py:186` | 2026-10-05 |
| `src/matinee/web/viewing.py::QuestionOut.footnote` | `src/matinee/web/viewing.py:80` | 2026-10-05 |
| `src/matinee/engine.py::_plain_mask` / `_range_mask` (unknown values pass) | `src/matinee/engine.py:251` | 2026-10-05 |
| `src/matinee/engine.py::walk_ends` / `reachable` | `src/matinee/engine.py:523` | 2026-10-05 |
| `data/trees/comedy.json` room question (ceilings) | `data/trees/comedy.json:7` | 2026-10-05 |
| `data/trees/comedy.json` kind question (standup answer, footnote), `standup` flavour, `apart` | `data/trees/comedy.json:49` | 2026-10-05 |
| `data/trees/thriller.json` kind question (spies `self_destruct`) | `data/trees/thriller.json:8` | 2026-10-05 |
| `data/trees/action.json`, `drama.json`, `scifi.json`, `fantasy.json`, `romance.json`, `animation.json`, `war.json` kind questions; `western.json` (no question) | `data/trees/action.json:8` | 2026-10-05 |
| `data/trees/kids.json` age and kind questions (labelled, always shown) | `data/trees/kids.json:8` | 2026-10-05 |
| `data/trees/crime.json` kind question | `data/trees/crime.json:8` | 2026-10-05 |
| `tests/test_source.py::test_the_source_question_is_asked_first_in_its_order_and_bounds_every_later_answer` | `tests/test_source.py:92` | 2026-10-05 |

### The checker

| Handle | Where | Verified |
|---|---|---|
| `tools/check_trees.py::main` (the shipped labels unless `--labels`; the library's films when the table names one) | `tools/check_trees.py:498` | 2026-10-05 |
| `tools/check_trees.py::SAMPLES` | `tools/check_trees.py:67` | 2026-10-05 |
| `tools/check_trees.py::check_answer_coverage` | `tools/check_trees.py:295` | 2026-10-05 |
| `tools/check_trees.py::check_same_answers` | `tools/check_trees.py:324` | 2026-10-05 |
| `tools/check_trees.py::check_sample` | `tools/check_trees.py:353` | 2026-10-05 |
| `tools/check_trees.py::check_homes` | `tools/check_trees.py:341` | 2026-10-05 |
| `tools/check_trees.py::door_pools` (only doors are homes) | `tools/check_trees.py:116` | 2026-10-05 |
| `tools/check_trees.py::check_apart` | `tools/check_trees.py:122` | 2026-10-05 |
| `tools/check_trees.py::check_kinds` / `report_waiting` | `tools/check_trees.py:382` | 2026-10-05 |
| `tools/check_trees.py::check_hidden` (the whole source's small kinds) | `tools/check_trees.py:452` | 2026-10-05 |
| `tools/check_trees.py::check_pins_in_key` | `tools/check_trees.py:241` | 2026-10-05 |
| `tools/check_trees.py::SPECIALS_KIND` (a `specials` pin's fixture) | `tools/check_trees.py:71` | 2026-10-05 |
| `tools/check_trees.py::check_gore` | `tools/check_trees.py:284` | 2026-10-05 |
| `tools/check_trees.py::check_lists` | `tools/check_trees.py:135` | 2026-10-05 |
| `tools/check_trees.py::check_data` | `tools/check_trees.py:488` | 2026-10-05 |
| `tools/check_trees.py::check_quips` | `tools/check_trees.py:478` | 2026-10-05 |
| `data/answer_key.json` list tags | `data/answer_key.json:3` | 2026-10-05 |
| `data/answer_key.json` `hidden` | `data/answer_key.json:18` | 2026-10-05 |

### The pick's lines

| Handle | Where | Verified |
|---|---|---|
| `data/quips.json` (caps, categories) | `data/quips.json:3` | 2026-10-05 |
| `src/matinee/quips.py::Quips` / `QuipSet` / `Caps` (universal must hold every set) | `src/matinee/quips.py:45` | 2026-10-05 |
| `src/matinee/quips.py::load_quips` / `QuipsError` | `src/matinee/quips.py:63` | 2026-10-05 |
| `src/matinee/quips.py::quip_problems` / `line_problems` / `in_title_case` | `src/matinee/quips.py:92` | 2026-10-05 |
| `tests/test_quips.py::test_the_caps_are_the_measured_ones` | `tests/test_quips.py:41` | 2026-10-05 |

### Labels and the household override file

| Handle | Where | Verified |
|---|---|---|
| `data/labels.json` (format 2, shipped) | `data/labels.json:1` | 2026-10-05 |
| `src/matinee/labels.py::LABELS` (the shipped file's path) | `src/matinee/labels.py:30` | 2026-10-05 |
| `src/matinee/labels.py::load_labels` / `Labels` / `TreeLabels` (format 2; anything else refused, naming the path) | `src/matinee/labels.py:112` | 2026-10-05 |
| `src/matinee/labels.py::_mend` (how a broken file is mended, by whose it is) | `src/matinee/labels.py:107` | 2026-10-05 |
| `src/matinee/labels.py::OVERRIDES` (`overrides.json` in the data directory) | `src/matinee/labels.py:31` | 2026-10-05 |
| `src/matinee/labels.py::load_overrides` | `src/matinee/labels.py:75` | 2026-10-05 |
| `src/matinee/labels.py::with_overrides` (a named film takes its whole placement from the household) | `src/matinee/labels.py:62` | 2026-10-05 |
| `src/matinee/labels.py::Labels.named` / `overridden` | `src/matinee/labels.py:57` | 2026-10-05 |
| `src/matinee/pools.py::House.without` (the pins of a household-placed film give way, its gore pail kept) | `src/matinee/pools.py:92` | 2026-10-05 |
| `src/matinee/engine.py::label_problems` (a tree no file defines, a kind it does not label) | `src/matinee/engine.py:303` | 2026-10-05 |
| `src/matinee/engine.py::household_problems` (bands only under kids; a kids film needs kinds and band) | `src/matinee/engine.py:318` | 2026-10-05 |
| `src/matinee/engine.py::_check_labels` (the engine refuses to prepare) | `src/matinee/engine.py:332` | 2026-10-05 |
| `src/matinee/web/main.py::household` / `OVERRIDES_BROKEN` (the file laid over, or a fault) | `src/matinee/web/main.py:54` | 2026-10-05 |
| `src/matinee/web/main.py::build` (the shipped labels, an unread `labels.json` in the data directory warned of) | `src/matinee/web/main.py:82` | 2026-10-05 |
| `tools/rebuild_table.py::household_films` (the rebuild fetches the films the household names) | `tools/rebuild_table.py:206` | 2026-10-05 |
| `tests/test_overrides.py::test_a_film_the_household_names_takes_its_whole_placement_from_the_file` | `tests/test_overrides.py:24` | 2026-10-05 |

### Pools and reference statistics

| Handle | Where | Verified |
|---|---|---|
| `src/matinee/pools.py::build_pools` (labelled films, the waiting room and pins; comedy holds the specials) | `src/matinee/pools.py:209` | 2026-10-05 |
| `src/matinee/pools.py::kids_bands` / `kids_band` / `CERTIFICATE_BANDS` (a pin applies to a film not held only on a passing certificate) | `src/matinee/pools.py:154` | 2026-10-05 |
| `src/matinee/pools.py::waiting` / `WAITING_ROOM` / `GENRE_DOORS` | `src/matinee/pools.py:202` | 2026-10-05 |
| `src/matinee/pools.py::standup_specials` | `src/matinee/pools.py:180` | 2026-10-05 |
| `src/matinee/pools.py::specials` (the rule plus `specials` pins) | `src/matinee/pools.py:197` | 2026-10-05 |
| `src/matinee/reference.py::reference_films` | `src/matinee/reference.py:140` | 2026-10-05 |
| `src/matinee/reference.py::compute_tree` | `src/matinee/reference.py:155` | 2026-10-05 |
| `src/matinee/reference.py::problems` | `src/matinee/reference.py:225` | 2026-10-05 |
| `src/matinee/reference.py::LICENCE` | `src/matinee/reference.py:28` | 2026-10-05 |
| `tools/build_reference.py::main` | `tools/build_reference.py:24` | 2026-10-05 |
| `data/reference.json` (horror gore cuts) | `data/reference.json:22` | 2026-10-05 |
| `tests/test_reference.py::test_shipped_reference_covers_every_tree` | `tests/test_reference.py:126` | 2026-10-05 |

### Scales and pins

| Handle | Where | Verified |
|---|---|---|
| `src/matinee/scales.py::scale_of` | `src/matinee/scales.py:44` | 2026-10-05 |
| `src/matinee/scales.py::film_scores` (bonus only with a genome entry) | `src/matinee/scales.py:65` | 2026-10-05 |
| `src/matinee/scales.py::band_index` | `src/matinee/scales.py:75` | 2026-10-05 |
| `src/matinee/scales.py::membership` (unscored bands, pins) | `src/matinee/scales.py:81` | 2026-10-05 |
| `src/matinee/engine.py::scale_members` | `src/matinee/engine.py:191` | 2026-10-05 |
| `data/trees/horror.json` gore scale | `data/trees/horror.json:38` | 2026-10-05 |
| `data/trees/horror.json` gore question, `skip_if_topics`, `treat_as` | `data/trees/horror.json:134` | 2026-10-05 |
| `data/trees/horror.json` labelled flavours (the kinds' rules) | `data/trees/horror.json:244` | 2026-10-05 |
| `src/matinee/pools.py::load_house` / `House` (`House.specials`) | `src/matinee/pools.py:106` | 2026-10-05 |
| `src/matinee/engine.py::house_flavour` (a `specials` flavour holds the standup specials) | `src/matinee/engine.py:167` | 2026-10-05 |
| `data/house_overrides.json` scale pins | `data/house_overrides.json:65` | 2026-10-05 |
| `data/house_overrides.json` `specials` pins | `data/house_overrides.json:43` | 2026-10-05 |

### Film table and nightly rebuild

| Handle | Where | Verified |
|---|---|---|
| `tools/rebuild_table.py::main` (`TMDB_TOKEN`, `TMDB_RATE`, the server whose settings are filled in) | `tools/rebuild_table.py:285` | 2026-10-05 |
| `tools/rebuild_table.py::daily_time` / `daily_arg` / `seconds_until` (`--daily HH:MM`, validated before the first rebuild) | `tools/rebuild_table.py:245` | 2026-10-05 |
| `tools/rebuild_table.py::rebuild_time` / `DEFAULT_DAILY` (`REBUILD_TIME` for `--daily` alone; 04:30 when unset or not a time, logged) | `tools/rebuild_table.py:261` | 2026-10-05 |
| `tools/rebuild_table.py::rebuild` (no key: compact and stop; an unexpected failure puts the kept table back) | `tools/rebuild_table.py:74` | 2026-10-05 |
| `tools/rebuild_table.py::_keep` / `_compact_without_key` (`films.sqlite.kept`) | `tools/rebuild_table.py:131` | 2026-10-05 |
| `tools/rebuild_table.py::_sweep_pictures` (every rebuild sweeps the picture shelf) | `tools/rebuild_table.py:113` | 2026-10-05 |
| `tools/rebuild_table.py::_rebuild` (the start line; save before any fetch; most-voted order) | `tools/rebuild_table.py:145` | 2026-10-05 |
| `tools/rebuild_table.py::_Run` / `save` / `tick` (a save every `SAVE_EVERY` records) | `tools/rebuild_table.py:178` | 2026-10-05 |
| `tools/rebuild_table.py::SAVE_EVERY` / `FAILED` | `tools/rebuild_table.py:65` | 2026-10-05 |
| `tools/rebuild_table.py::tmdb_rate` (any positive number; anything else the default, logged) | `tools/rebuild_table.py:226` | 2026-10-05 |
| `src/matinee/progress.py::RebuildStatus` / `STATUS_FILE` (`rebuild.json`) | `src/matinee/progress.py:24` | 2026-10-05 |
| `src/matinee/progress.py::write_status` / `read_status` / `_well_formed` | `src/matinee/progress.py:33` | 2026-10-05 |
| `src/matinee/tmdb.py::refresh` (one shared pacer; compaction in `finally`) | `src/matinee/tmdb.py:494` | 2026-10-05 |
| `src/matinee/tmdb.py::fetch_order` (held vote counts, else TMDB's list) | `src/matinee/tmdb.py:473` | 2026-10-05 |
| `src/matinee/tmdb.py::most_voted` / `VOTE_PAGES` (`VOTE_PAGES`, progress after every page) | `src/matinee/tmdb.py:441` | 2026-10-05 |
| `src/matinee/tmdb.py::Pacer` / `wait` / `hold` / `held` (a 429 holds every request) | `src/matinee/tmdb.py:151` | 2026-10-05 |
| `src/matinee/tmdb.py::DEFAULT_RATE` / `MAX_WORKERS` / `workers_for` | `src/matinee/tmdb.py:38` | 2026-10-05 |
| `src/matinee/tmdb.py::get_json` | `src/matinee/tmdb.py:191` | 2026-10-05 |
| `src/matinee/tmdb.py::_fetch_all` / `_Tally` / `Tick` / `TICK_EVERY` | `src/matinee/tmdb.py:532` | 2026-10-05 |
| `src/matinee/tmdb.py::_Tally.records` / `so_far` / `take` | `src/matinee/tmdb.py:561` | 2026-10-05 |
| `src/matinee/tmdb.py::TmdbFilm` (title, year, genres, synopsis, vote count, US rating) | `src/matinee/tmdb.py:60` | 2026-10-05 |
| `src/matinee/tmdb.py::fetch_film` / `_us_certification` | `src/matinee/tmdb.py:394` | 2026-10-05 |
| `src/matinee/tmdb.py::TmdbRefused` / `Refreshed` / `NETWORK_FAILURES` | `src/matinee/tmdb.py:55` | 2026-10-05 |
| `src/matinee/tmdb.py::NO_KEY` / `KEY_REFUSED` / `NOT_ANSWERING` | `src/matinee/tmdb.py:46` | 2026-10-05 |
| `src/matinee/tmdb.py::REFETCH_AFTER` / `MAX_AGE` | `src/matinee/tmdb.py:42` | 2026-10-05 |
| `src/matinee/tmdb.py::compact` | `src/matinee/tmdb.py:135` | 2026-10-05 |
| `src/matinee/tmdb.py::load_cache` / `_record` (a damaged line, its fetch time included, is skipped) | `src/matinee/tmdb.py:112` | 2026-10-05 |
| `src/matinee/tmdb.py::needs_fetch` / `picture_path` / `PICTURE_PATH` | `src/matinee/tmdb.py:143` | 2026-10-05 |
| `src/matinee/genome.py::load_genome` (links.csv join, stamped cache) | `src/matinee/genome.py:122` | 2026-10-05 |
| `src/matinee/genome.py::Genome.scores` (the tags read, by TMDB id; the first MovieLens film wins) | `src/matinee/genome.py:57` | 2026-10-05 |
| `src/matinee/genome.py::Scores` | `src/matinee/genome.py:75` | 2026-10-05 |
| `src/matinee/genome_file.py::GENOME_FILE` / `tags_read` / `write_scores` / `load_scores` | `src/matinee/genome_file.py:27` | 2026-10-05 |
| `tools/build_genome.py` (writes `data/genome.json`; refuses a release other than `data/reference.json`'s) | `tools/build_genome.py:1` | 2026-10-05 |
| `tests/test_genome_file.py::test_every_reader_finds_its_tags_in_a_table_built_from_the_shipped_scores` | `tests/test_genome_file.py:33` | 2026-10-05 |
| `src/matinee/table.py::build_table` / `BuildReport` (the library and every labelled film with a usable record) | `src/matinee/table.py:247` | 2026-10-05 |
| `src/matinee/table.py::_library_rows` / `_listed_rows` / `_from_library` / `_from_tmdb` | `src/matinee/table.py:200` | 2026-10-05 |
| `src/matinee/table.py::FORMAT` / `COLUMNS` / `SHOWN` / `TMDB_COLUMNS` / `INSERT_FILM` | `src/matinee/table.py:41` | 2026-10-05 |
| `src/matinee/table.py::write_table` / `_cell` | `src/matinee/table.py:396` | 2026-10-05 |
| `src/matinee/table.py::load_table` / `_read` / `_text` (format 2 with every column, else refused; a stale table is read) | `src/matinee/table.py:436` | 2026-10-05 |
| `src/matinee/table.py::empty_table` | `src/matinee/table.py:292` | 2026-10-05 |
| `src/matinee/table.py::is_stale` (the oldest TMDB fact 183 days old or more) | `src/matinee/table.py:419` | 2026-10-05 |
| `src/matinee/table.py::with_live` / `_offered` / `_aligned` (held from the live list; the films the labels name) | `src/matinee/table.py:343` | 2026-10-05 |
| `src/matinee/table.py::library_films` | `src/matinee/table.py:298` | 2026-10-05 |
| `src/matinee/web/theatre.py::Theatre.showing` / `_read_library` / `_ttl` (`LIVE_TTL`, `RETRY_AFTER`) | `src/matinee/web/theatre.py:164` | 2026-10-05 |
| `src/matinee/web/theatre.py::Theatre` (`listed`, `on_reload`; an absent or unreadable table counts as empty) | `src/matinee/web/theatre.py:73` | 2026-10-05 |

### Profiles and devices

| Handle | Where | Verified |
|---|---|---|
| `src/matinee/store.py::MAX_PROFILES` (and the other limits) | `src/matinee/store.py:42` | 2026-10-05 |
| `src/matinee/store.py::AVATARS` / `clean_avatar` / `Profile.avatar` (an unknown avatar reads as none) | `src/matinee/store.py:49` | 2026-10-05 |
| `src/matinee/store.py::name_key` / `clean_name` / `clean_pin` | `src/matinee/store.py:127` | 2026-10-05 |
| `src/matinee/store.py::Store.__init__` (brings the file to its shape) | `src/matinee/store.py:203` | 2026-10-05 |
| `src/matinee/store.py::Store._issue` (token pruning) | `src/matinee/store.py:225` | 2026-10-05 |
| `src/matinee/store.py::Store.create` | `src/matinee/store.py:233` | 2026-10-05 |
| `src/matinee/store.py::Store.holding` | `src/matinee/store.py:264` | 2026-10-05 |
| `src/matinee/store.py::Store.everyone` (every profile, sorted by name) | `src/matinee/store.py:277` | 2026-10-05 |
| `src/matinee/store.py::Store._held` (the token check inside the write's transaction) | `src/matinee/store.py:284` | 2026-10-05 |
| `src/matinee/store.py::Store.set_topics` / `set_avatar` | `src/matinee/store.py:298` | 2026-10-05 |
| `src/matinee/store.py::Store.delete` (notes stay) | `src/matinee/store.py:377` | 2026-10-05 |
| `src/matinee/store.py::Store.clear_pin` | `src/matinee/store.py:384` | 2026-10-05 |
| `src/matinee/store.py::Store.open` / `_check_pin` (lockout) | `src/matinee/store.py:397` | 2026-10-05 |
| `src/matinee/web/common.py::TOKENS_COOKIE` / `MAX_TOKENS` | `src/matinee/web/common.py:22` | 2026-10-05 |
| `src/matinee/web/common.py::PROFILE_LINES` (each refusal's words) | `src/matinee/web/common.py:25` | 2026-10-05 |
| `src/matinee/web/common.py::Seat` / `Tile` / `Deleted` / `Door` (what the page is told of a profile) | `src/matinee/web/common.py:38` | 2026-10-05 |
| `src/matinee/web/common.py::NewProfile` / `AvatarChoice` / `PinEntry` (request caps) | `src/matinee/web/common.py:72` | 2026-10-05 |
| `src/matinee/web/common.py::set_tokens` / `with_token` | `src/matinee/web/common.py:104` | 2026-10-05 |
| `src/matinee/web/app.py::add_door_routes` (`GET /api/door`, create, open) | `src/matinee/web/app.py:310` | 2026-10-05 |
| `src/matinee/web/app.py::add_avatar_route` (`PUT /api/profiles/{id}/avatar`) | `src/matinee/web/app.py:349` | 2026-10-05 |
| `src/matinee/web/app.py::add_delete_route` (`DELETE /api/profiles/{id}`) | `src/matinee/web/app.py:358` | 2026-10-05 |
| `src/matinee/web/viewing.py::ViewerIn` (a profile id only) | `src/matinee/web/viewing.py:36` | 2026-10-05 |
| `src/matinee/web/viewing.py::held_profile` | `src/matinee/web/viewing.py:197` | 2026-10-05 |
| `src/matinee/web/viewing.py::resolve` (no profile: the front door's pool; no key: stored topics ignored) | `src/matinee/web/viewing.py:229` | 2026-10-05 |
| `src/matinee/web/viewing.py::resolve_held` (walks and picks need a held profile) | `src/matinee/web/viewing.py:242` | 2026-10-05 |
| `tests/test_profiles.py::test_a_write_never_lands_on_a_new_profile_that_reuses_a_deleted_ones_id` | `tests/test_profiles.py:318` | 2026-10-05 |
| `tests/test_avatar_images.py` (two square sizes each; the size budget) | `tests/test_avatar_images.py:24` | 2026-10-05 |
| `src/matinee/web/static/avatars/` (`<avatar>-256.webp` and `<avatar>-80.webp`) | `src/matinee/web/static/avatars` | 2026-10-05 |

### The store file

| Handle | Where | Verified |
|---|---|---|
| `src/matinee/upgrade.py::SHAPE` / `TABLES` (the current shape; the unread `exclusions` column) | `src/matinee/upgrade.py:24` | 2026-10-05 |
| `src/matinee/upgrade.py::BELONGS_FROM_CORRECTIONS` (where an old genre note's film belongs) | `src/matinee/upgrade.py:70` | 2026-10-05 |
| `src/matinee/upgrade.py::FROM_SHAPE_0` | `src/matinee/upgrade.py:83` | 2026-10-05 |
| `src/matinee/upgrade.py::ShapeError` | `src/matinee/upgrade.py:95` | 2026-10-05 |
| `src/matinee/upgrade.py::_stranded` / `_refuse_stranded` (notes in an old `feedback` table) | `src/matinee/upgrade.py:131` | 2026-10-05 |
| `src/matinee/upgrade.py::_keep_copy` (one copy, never overwritten) | `src/matinee/upgrade.py:138` | 2026-10-05 |
| `src/matinee/upgrade.py::_upgrade_from_0` (one transaction; the count and foreign-key guards) | `src/matinee/upgrade.py:161` | 2026-10-05 |
| `src/matinee/upgrade.py::prepare` | `src/matinee/upgrade.py:193` | 2026-10-05 |
| `tests/test_upgrade.py` | `tests/test_upgrade.py:112` | 2026-10-05 |

### The door word

| Handle | Where | Verified |
|---|---|---|
| `src/matinee/web/admission.py::COOKIE` / `LIFE_S` / `RELAXED_MIN` / `STRICT_MIN` / `KEY_FILE` / `MAX_TYPED` / `CLOCK_SKEW_S` | `src/matinee/web/admission.py:28` | 2026-10-05 |
| `src/matinee/web/admission.py::edits` / `relaxed_key` (relaxed matching) | `src/matinee/web/admission.py:42` | 2026-10-05 |
| `src/matinee/web/admission.py::too_long` / `too_short` | `src/matinee/web/admission.py:57` | 2026-10-05 |
| `src/matinee/web/admission.py::load_secret` (made once, owner-only) | `src/matinee/web/admission.py:69` | 2026-10-05 |
| `src/matinee/web/admission.py::Admission` (`issue`, `admits`, `matches`) | `src/matinee/web/admission.py:88` | 2026-10-05 |
| `src/matinee/web/config.py::GREETINGS` | `src/matinee/web/config.py:24` | 2026-10-05 |
| `src/matinee/web/config.py::_door` (a wrong lock refuses the start; with no word, a bad mode is a fault) | `src/matinee/web/config.py:72` | 2026-10-05 |
| `src/matinee/web/app.py::AdmissionOut` / `WordIn` | `src/matinee/web/app.py:377` | 2026-10-05 |
| `src/matinee/web/app.py::open_before_admission` | `src/matinee/web/app.py:389` | 2026-10-05 |
| `src/matinee/web/app.py::add_admission` (the gate, `GET`/`POST /api/admission`, the 2-second wait) | `src/matinee/web/app.py:394` | 2026-10-05 |
| `tests/test_admission.py` | `tests/test_admission.py:83` | 2026-10-05 |

### Notes and the notes tool

| Handle | Where | Verified |
|---|---|---|
| `src/matinee/store.py::Note` (`belongs`) | `src/matinee/store.py:71` | 2026-10-05 |
| `src/matinee/store.py::NOTE_SELECT` / `FiledNote` / `one_line` / `MAX_REASON` | `src/matinee/store.py:67` | 2026-10-05 |
| `src/matinee/store.py::Store.note` | `src/matinee/store.py:320` | 2026-10-05 |
| `src/matinee/store.py::Store.notes` / `filed` / `rule` | `src/matinee/store.py:340` | 2026-10-05 |
| `src/matinee/web/viewing.py::NoteOut` / `NoteIn` (request caps) | `src/matinee/web/viewing.py:134` | 2026-10-05 |
| `src/matinee/web/viewing.py::NOTED` / `answer_says` / `check_belongs` | `src/matinee/web/viewing.py:402` | 2026-10-05 |
| `src/matinee/web/viewing.py::add_note_routes` (`POST /api/notes`; a film Matinee does not offer now is refused) | `src/matinee/web/viewing.py:425` | 2026-10-05 |
| `tools/notes.py::Names` / `load_names` (titles and door labels) | `tools/notes.py:39` | 2026-10-05 |
| `tools/notes.py::printable` | `tools/notes.py:65` | 2026-10-05 |
| `tools/notes.py::what_was_wrong` / `describe` | `tools/notes.py:71` | 2026-10-05 |
| `tools/notes.py::list_open` / `rule` / `clear_pin` / `clear_topics` | `tools/notes.py:98` | 2026-10-05 |
| `tools/notes.py::note_id` / `parser` / `main` (exit statuses) | `tools/notes.py:132` | 2026-10-05 |
| `src/matinee/store.py::Store.clear_topics` (`clear-topics`) | `src/matinee/store.py:306` | 2026-10-05 |
| `tests/test_notes.py`, `tests/test_review.py`, `tests/test_notes_tool.py` | `tests/test_notes.py:56` | 2026-10-05 |

### Topics and the DoesTheDogDie check

| Handle | Where | Verified |
|---|---|---|
| `src/matinee/web/config.py::Config.dtdd_key` (optional) | `src/matinee/web/config.py:44` | 2026-10-05 |
| `src/matinee/web/app.py::create_app` (one `topics_on`; a picker that disagrees is refused) | `src/matinee/web/app.py:527` | 2026-10-05 |
| `src/matinee/web/viewing.py::add_topic_routes` (`GET /api/topics`, `PUT /api/profiles/{id}/topics`, only with a key) | `src/matinee/web/viewing.py:324` | 2026-10-05 |
| `src/matinee/web/viewing.py::save_topics` | `src/matinee/web/viewing.py:348` | 2026-10-05 |
| `src/matinee/web/viewing.py::FirstOut.checked` (whether this viewer's picks are checked) | `src/matinee/web/viewing.py:115` | 2026-10-05 |
| `src/matinee/web/common.py::Door.dtdd` (`GET /api/door` says whether a key is set) | `src/matinee/web/common.py:68` | 2026-10-05 |
| `src/matinee/web/main.py::warn_kept_topics` / `TOPICS_KEPT` / `WARN_EVERY` (kept topics without a key) | `src/matinee/web/main.py:41` | 2026-10-05 |
| `src/matinee/pick.py::Picker.dtdd` / `_checked` (none without a key) | `src/matinee/pick.py:274` | 2026-10-05 |
| `src/matinee/dtdd.py::Dtdd.get` / `_pace` (`BURST`, `RATE_PER_S`) | `src/matinee/dtdd.py:106` | 2026-10-05 |
| `src/matinee/dtdd.py::Dtdd._check_holds` / `_refused` / `_note_remaining` (`REQUESTS_PER_HOUR`, `MONTH_RESERVE`, `RESERVE_HOLD_S`, `BACKOFF_S`) | `src/matinee/dtdd.py:123` | 2026-10-05 |
| `src/matinee/dtdd.py::Dtdd.topics` (`TOPICS_REFRESH_S`, `TOPICS_KEEP_S`) | `src/matinee/dtdd.py:178` | 2026-10-05 |
| `src/matinee/pick.py::failing` (`MIN_VOTES`) | `src/matinee/pick.py:83` | 2026-10-05 |
| `src/matinee/pick.py::_count` (a DoesTheDogDie number: a plain non-negative integer, never a boolean) | `src/matinee/pick.py:78` | 2026-10-05 |
| `src/matinee/pick.py::_the_film` (the one Movie with the film's TMDB id; a malformed item id is unreadable) | `src/matinee/pick.py:106` | 2026-10-05 |
| `src/matinee/pick.py::ItemIds` (`ID_KEEP_S`) | `src/matinee/pick.py:133` | 2026-10-05 |
| `src/matinee/pick.py::ItemIds._drop_expired` (nothing held past 30 days) | `src/matinee/pick.py:145` | 2026-10-05 |
| `src/matinee/pick.py::look_up` (`LOOKUP_S`) | `src/matinee/pick.py:170` | 2026-10-05 |
| `src/matinee/pick.py::DeviceCap` (`LOOKUPS_PER_HOUR`) | `src/matinee/pick.py:226` | 2026-10-05 |
| `src/matinee/pick.py::candidates` | `src/matinee/pick.py:259` | 2026-10-05 |
| `src/matinee/engine.py::gentlest` | `src/matinee/engine.py:210` | 2026-10-05 |
| `src/matinee/pick.py::Picker.pick` (`PICK_TRIES`) | `src/matinee/pick.py:289` | 2026-10-05 |
| `src/matinee/pick.py::Pick` (`last` / `last_hits`: the third film of three in a row; `item`: an unchecked film's item) | `src/matinee/pick.py:61` | 2026-10-05 |
| `src/matinee/pick.py::Picker._item` (the item as held after any lookup) | `src/matinee/pick.py:279` | 2026-10-05 |
| `src/matinee/web/viewing.py::device_id` / `DEVICE_COOKIE` | `src/matinee/web/viewing.py:273` | 2026-10-05 |
| `src/matinee/web/viewing.py::SWAP_LINE` / `UNCHECKED_LINES` / `EXHAUSTED` / `TIRED` / `PICKED` | `src/matinee/web/viewing.py:251` | 2026-10-05 |
| `src/matinee/web/viewing.py::LastOut` / `PickOut` (`last`, `dtdd_item`) | `src/matinee/web/viewing.py:164` | 2026-10-05 |
| `src/matinee/web/viewing.py::_swap_out` / `_last_out` / `pick_out` | `src/matinee/web/viewing.py:291` | 2026-10-05 |
| `src/matinee/web/viewing.py::pick_pool` | `src/matinee/web/viewing.py:442` | 2026-10-05 |
| `src/matinee/web/viewing.py::add_pick_routes` | `src/matinee/web/viewing.py:452` | 2026-10-05 |
| `tests/test_pick.py::test_three_in_a_row_hold_the_third_film_with_its_own_topic` / `test_a_pick_that_asks_to_skip_the_check_is_still_checked` | `tests/test_pick.py:555` | 2026-10-05 |
| `tests/test_without_dtdd.py::test_stored_topics_stay_in_the_store_and_change_no_walk_or_pick` | `tests/test_without_dtdd.py:59` | 2026-10-05 |

### Settings, the setup note and the logs

| Handle | Where | Verified |
|---|---|---|
| `src/matinee/web/config.py::from_env` (refuses only `DATA_DIR` and a wrong lock; everything else a fault) | `src/matinee/web/config.py:124` | 2026-10-05 |
| `src/matinee/web/config.py::Config` / `faults` / `server_unusable` / `server` | `src/matinee/web/config.py:40` | 2026-10-05 |
| `src/matinee/web/config.py::_server` / `_seerr` / `_images` | `src/matinee/web/config.py:107` | 2026-10-05 |
| `src/matinee/web/config.py::ImageSource` (`POSTERS_FROM`: `server` or `tmdb`) | `src/matinee/web/config.py:29` | 2026-10-05 |
| `src/matinee/web/setup.py::SetupNote` (`warning` while the data is stale) | `src/matinee/web/setup.py:49` | 2026-10-05 |
| `src/matinee/web/setup.py::note` / `library_away` / `rebuild_lines` / `stalled` | `src/matinee/web/setup.py:109` | 2026-10-05 |
| `src/matinee/web/setup.py::HEADING` / `MEANWHILE` / `STOPPED` / `STALE` / `STALLED_AFTER` (every line's words) | `src/matinee/web/setup.py:20` | 2026-10-05 |
| `src/matinee/web/app.py::setup_faults` (the configured, start-up and run-time faults) | `src/matinee/web/app.py:494` | 2026-10-05 |
| `src/matinee/web/app.py::add_setup_route` (`GET /api/setup`) | `src/matinee/web/app.py:508` | 2026-10-05 |
| `src/matinee/web/theatre.py::NothingToShow` (shipped data that cannot make a catalog) | `src/matinee/web/theatre.py:61` | 2026-10-05 |
| `src/matinee/web/theatre.py::Theatre._catalog` | `src/matinee/web/theatre.py:150` | 2026-10-05 |
| `src/matinee/web/theatre.py::Showing.library` / `UNUSABLE` / `warn_library` (`none`, `usable`, `unreachable`, `refused`) | `src/matinee/web/theatre.py:70` | 2026-10-05 |
| `src/matinee/web/theatre.py::Theatre.table_films` / `stale` / `oldest_tmdb` | `src/matinee/web/theatre.py:201` | 2026-10-05 |
| `src/matinee/web/seerr.py::SeerrCheck` (`CHECK_EVERY`; picks link to TMDB while it does not answer) | `src/matinee/web/seerr.py:25` | 2026-10-05 |
| `src/matinee/web/logbook.py::describe` / `StateLog` / `state_log` / `CHECK_EVERY` (the state line) | `src/matinee/web/logbook.py:72` | 2026-10-05 |
| `src/matinee/web/logbook.py::Quiet` / `QUIET_FOR` / `SERVER_NAMES` (a repeating warning once a minute, with a count) | `src/matinee/web/logbook.py:116` | 2026-10-05 |
| `src/matinee/web/app.py::add_state_log` / `QUIET` | `src/matinee/web/app.py:516` | 2026-10-05 |
| `tests/test_setup.py::test_only_a_wrong_lock_and_a_missing_data_directory_refuse_to_start` | `tests/test_setup.py:109` | 2026-10-05 |
| `tests/test_logbook.py::test_the_state_line_names_every_part_and_no_secret` | `tests/test_logbook.py:30` | 2026-10-05 |

### Web surface

| Handle | Where | Verified |
|---|---|---|
| `src/matinee/web/main.py::build` (reads the labels and the household file; faults go on the note) | `src/matinee/web/main.py:82` | 2026-10-05 |
| `src/matinee/web/app.py::create_app` (docs disabled) | `src/matinee/web/app.py:527` | 2026-10-05 |
| `src/matinee/web/app.py::security_headers` / `CONTENT_SECURITY_POLICY` | `src/matinee/web/app.py:450` | 2026-10-05 |
| `src/matinee/web/app.py::add_page` | `src/matinee/web/app.py:456` | 2026-10-05 |
| `src/matinee/web/app.py::add_quip_routes` (`GET /api/quips`; 503 when the lines cannot be read) | `src/matinee/web/app.py:482` | 2026-10-05 |
| `src/matinee/web/app.py::add_film_routes` / `IMAGE_WIDTHS` / `IMAGE_CACHE` (`GET /api/pictures`) | `src/matinee/web/app.py:275` | 2026-10-05 |
| `src/matinee/web/app.py::film_link` / `FilmCard` (Seerr, else TMDB) | `src/matinee/web/app.py:178` | 2026-10-05 |
| `src/matinee/web/app.py::Held` / `held` / `stored_path` | `src/matinee/web/app.py:102` | 2026-10-05 |
| `src/matinee/web/app.py::film_image` / `tmdb_image` / `TMDB_IMAGE_CACHE` (the media server's, else TMDB's; 30 days for a film the library does not hold) | `src/matinee/web/app.py:185` | 2026-10-05 |
| `src/matinee/web/app.py::Shelf` / `from_shelf` (each TMDB picture fetched once for every viewer) | `src/matinee/web/app.py:207` | 2026-10-05 |
| `src/matinee/tmdb.py::shelf_file` / `read_shelf` / `shelve` / `sweep_shelf` / `PICTURE_KEEP` (150 days) | `src/matinee/tmdb.py:324` | 2026-10-05 |
| `src/matinee/web/app.py::film_synopsis` (the media server's, else TMDB's) | `src/matinee/web/app.py:264` | 2026-10-05 |
| `src/matinee/tmdb.py::fetch_picture` / `IMAGES` / `IMAGE_SIZES` / `TmdbImageError` | `src/matinee/tmdb.py:292` | 2026-10-05 |
| `src/matinee/tmdb.py::ImageGate` / `IMAGE_GATE` / `IMAGE_RATE` (50 a second, 20,000 an hour, a hold after a 429 or 503) | `src/matinee/tmdb.py:236` | 2026-10-05 |
| `src/matinee/web/app.py::add_error_handlers` | `src/matinee/web/app.py:137` | 2026-10-05 |
| `src/matinee/web/common.py::Problem` | `src/matinee/web/common.py:125` | 2026-10-05 |
| `src/matinee/web/viewing.py::add_viewing_routes` (`POST /api/first` with the source question, `POST /api/walk`) | `src/matinee/web/viewing.py:353` | 2026-10-05 |
| `src/matinee/web/viewing.py::WalkIn` / `PickIn` / `FirstIn` (request caps; no field skips the check) | `src/matinee/web/viewing.py:45` | 2026-10-05 |
| `tests/test_user_agent.py::test_every_outbound_request_names_matinee` | `tests/test_user_agent.py:36` | 2026-10-05 |

### The page

| Handle | Where | Verified |
|---|---|---|
| `src/matinee/web/static/js/main.js::boot` / `frontDoor` / `lockedDoor` (`GET /api/admission` first, then the setup note) | `src/matinee/web/static/js/main.js:330` | 2026-10-05 |
| `src/matinee/web/static/js/main.js::saidSetup` / `setupNote` (once per page load with a way in; every time without) | `src/matinee/web/static/js/main.js:299` | 2026-10-05 |
| `src/matinee/web/static/js/main.js::showWarning` (the stale-data strip; the stage starts beneath it) | `src/matinee/web/static/js/main.js:276` | 2026-10-05 |
| `src/matinee/web/static/js/main.js::showFallback` (the fallback notice after the stale-data warning) | `src/matinee/web/static/js/main.js:293` | 2026-10-05 |
| `src/matinee/web/static/js/main.js::start` (the source question, or the doors; nothing carried from the last walk) | `src/matinee/web/static/js/main.js:390` | 2026-10-05 |
| `src/matinee/web/static/js/main.js::chooseSource` / `doors` / `showFirst` | `src/matinee/web/static/js/main.js:422` | 2026-10-05 |
| `src/matinee/web/static/js/main.js::crumbs` / `trail` / `lastCrumb` | `src/matinee/web/static/js/main.js:127` | 2026-10-05 |
| `src/matinee/web/static/js/main.js::backTo` / `wayBack` / `backAction` (a phone's "Back" and `Start over`) | `src/matinee/web/static/js/main.js:151` | 2026-10-05 |
| `src/matinee/web/static/js/main.js::goTo` / `step` (`Start` asks again; the source answer shows the doors) | `src/matinee/web/static/js/main.js:445` | 2026-10-05 |
| `src/matinee/web/static/js/main.js::lockStage` / `leaveTo` | `src/matinee/web/static/js/main.js:73` | 2026-10-05 |
| `src/matinee/web/static/js/main.js::frame` / `ask` (the footnote) | `src/matinee/web/static/js/main.js:177` | 2026-10-05 |
| `src/matinee/web/static/js/main.js::checking` / `fadeTalk` (`READ_MS`) | `src/matinee/web/static/js/main.js:500` | 2026-10-05 |
| `src/matinee/web/static/js/main.js::pickLines` | `src/matinee/web/static/js/main.js:531` | 2026-10-05 |
| `src/matinee/web/static/js/main.js::clearForPick` / `requestPick` / `openPick` | `src/matinee/web/static/js/main.js:552` | 2026-10-05 |
| `src/matinee/web/static/js/main.js::pickNow` | `src/matinee/web/static/js/main.js:597` | 2026-10-05 |
| `src/matinee/web/static/js/main.js::pickActions` (`notThatOne`, `rollAgain`, `showPicked`) | `src/matinee/web/static/js/main.js:633` | 2026-10-05 |
| `src/matinee/web/static/js/main.js::showPicked` ("Just show me what you picked", from the reply held) | `src/matinee/web/static/js/main.js:658` | 2026-10-05 |
| `src/matinee/web/static/js/main.js::enter` (the start asked at the tap, the first screen after the landing) | `src/matinee/web/static/js/main.js:379` | 2026-10-05 |
| `src/matinee/web/static/js/main.js::topbar` (settles a landed name) | `src/matinee/web/static/js/main.js:97` | 2026-10-05 |
| `src/matinee/web/static/js/main.js::problem` (`keep`: the failed start's posters; "About Matinee" at the foot) | `src/matinee/web/static/js/main.js:232` | 2026-10-05 |
| `src/matinee/web/static/js/main.js::countText` (the films left, beside "Just pick one!") | `src/matinee/web/static/js/main.js:43` | 2026-10-05 |
| `src/matinee/web/static/js/main.js::loadQuips` (asked once admitted) | `src/matinee/web/static/js/main.js:52` | 2026-10-05 |
| `src/matinee/web/static/js/main.js::wordmark` (a link doing `Start over`) | `src/matinee/web/static/js/main.js:87` | 2026-10-05 |
| `src/matinee/web/static/js/main.js::nameTag` (the viewer and its menu's actions; no "Edit my list" without a key) | `src/matinee/web/static/js/main.js:106` | 2026-10-05 |
| `src/matinee/web/static/js/main.js::askPictures` (once per visit) | `src/matinee/web/static/js/main.js:316` | 2026-10-05 |
| `src/matinee/web/static/js/offers.js::offers` / `learnOffers` (whether a DoesTheDogDie key is set, from `/api/door`) | `src/matinee/web/static/js/offers.js:4` | 2026-10-05 |
| `src/matinee/web/static/js/door.js::Door` | `src/matinee/web/static/js/door.js:141` | 2026-10-05 |
| `src/matinee/web/static/js/door.js::Door.open` (the tiles, a viewer's list, or a new profile) | `src/matinee/web/static/js/door.js:154` | 2026-10-05 |
| `src/matinee/web/static/js/door.js::Door.build` (a standing marquee adopted, never rebuilt; "About Matinee" in the foot) | `src/matinee/web/static/js/door.js:168` | 2026-10-05 |
| `src/matinee/web/static/js/door.js::Door.talk` (a question typed onto the wall; `detail`, a body-type line beneath) | `src/matinee/web/static/js/door.js:222` | 2026-10-05 |
| `src/matinee/web/static/js/door.js::Door.enter` (entered once) | `src/matinee/web/static/js/door.js:388` | 2026-10-05 |
| `src/matinee/web/static/js/door.js::Door.leave` / `settle` / `bringBack` (the marquee leaves and returns) | `src/matinee/web/static/js/door.js:399` | 2026-10-05 |
| `src/matinee/web/static/js/door.js::Door.picker` (sets the phone's lit strip) | `src/matinee/web/static/js/door.js:443` | 2026-10-05 |
| `src/matinee/web/static/js/door.js::Door.fillTopics` / `topicsTrouble` (DoesTheDogDie's topics alone, their count, "Read about these on DoesTheDogDie ↗") | `src/matinee/web/static/js/door.js:495` | 2026-10-05 |
| `src/matinee/web/static/js/door.js::Door.topic` (a letterbox that toggles, with a check mark) | `src/matinee/web/static/js/door.js:543` | 2026-10-05 |
| `src/matinee/web/static/js/door.js::Door.dtddCredit` (shown on the picker, hidden on every other door screen) | `src/matinee/web/static/js/door.js:171` | 2026-10-05 |
| `src/matinee/web/static/js/door.js::sign` (frame, rules, name, live count) | `src/matinee/web/static/js/door.js:82` | 2026-10-05 |
| `src/matinee/web/static/js/door.js::bulbs` / `ringAt` | `src/matinee/web/static/js/door.js:48` | 2026-10-05 |
| `src/matinee/web/static/js/door.js::time` (the two-bulb chase's start) | `src/matinee/web/static/js/door.js:36` | 2026-10-05 |
| `src/matinee/web/static/js/door.js::BULBS` / `CHASE_S` | `src/matinee/web/static/js/door.js:17` | 2026-10-05 |
| `src/matinee/web/static/js/door.js::buildMarquee` / `showCount` ("Private screening" until admitted) | `src/matinee/web/static/js/door.js:130` | 2026-10-05 |
| `src/matinee/web/static/js/door.js::tile` / `newTile` (`.seat-label` carries the name's scrim) | `src/matinee/web/static/js/door.js:107` | 2026-10-05 |
| `src/matinee/web/static/js/door.js::Door.greet` / `choose` | `src/matinee/web/static/js/door.js:184` | 2026-10-05 |
| `src/matinee/web/static/js/door.js::Door.lock` / `refresh` / `refused` | `src/matinee/web/static/js/door.js:202` | 2026-10-05 |
| `src/matinee/web/static/js/door.js::Door.first` / `askName` / `taken` / `askAvatar` / `askPin` / `create` / `askList` / `done` (making a profile) | `src/matinee/web/static/js/door.js:238` | 2026-10-05 |
| `src/matinee/web/static/js/door.js::Door.askList` (skipped without a key) | `src/matinee/web/static/js/door.js:323` | 2026-10-05 |
| `src/matinee/web/static/js/door.js::Door.pin` (a PIN asked at a tile) | `src/matinee/web/static/js/door.js:342` | 2026-10-05 |
| `src/matinee/web/static/js/door.js::Door.seatOf` / `enterAs` | `src/matinee/web/static/js/door.js:373` | 2026-10-05 |
| `src/matinee/web/static/js/door.js::Door.neverMind` (the picker's way out) | `src/matinee/web/static/js/door.js:469` | 2026-10-05 |
| `src/matinee/web/static/js/door.js::Door.save` (`PUT /api/profiles/{id}/topics`) | `src/matinee/web/static/js/door.js:488` | 2026-10-05 |
| `src/matinee/web/static/js/door-rules.js::doorLines` / `opensAtOnce` / `nameKey` / `findTaken` / `twoParts` | `src/matinee/web/static/js/door-rules.js:5` | 2026-10-05 |
| `src/matinee/web/static/js/mark.js::initials` / `avatarSrc` / `mark` | `src/matinee/web/static/js/mark.js:10` | 2026-10-05 |
| `src/matinee/web/static/js/mark.js::AVATAR_NAMES` / `avatarChoices` | `src/matinee/web/static/js/mark.js:32` | 2026-10-05 |
| `src/matinee/web/static/js/viewer.js::SHORT_NAME` | `src/matinee/web/static/js/viewer.js:15` | 2026-10-05 |
| `src/matinee/web/static/js/viewer.js::viewerTag` (the profile menu, ending with "About Matinee"; its Change avatar and Delete profile panels) | `src/matinee/web/static/js/viewer.js:30` | 2026-10-05 |
| `src/matinee/web/static/js/locked.js::WALL_FADE_MS` / `bandsAt` / `WIPE_MS` (the band wipe) | `src/matinee/web/static/js/locked.js:26` | 2026-10-05 |
| `src/matinee/web/static/js/locked.js::LockedDoor` (`show`, `place`, `measure`, `greet`, `slide`, `shut`) | `src/matinee/web/static/js/locked.js:53` | 2026-10-05 |
| `src/matinee/web/static/js/locked.js::LockedDoor.open` / `wipe` (the opening) | `src/matinee/web/static/js/locked.js:162` | 2026-10-05 |
| `src/matinee/web/static/js/locked.js::LockedDoor.toggle` / `give` (the eye; a word given) | `src/matinee/web/static/js/locked.js:196` | 2026-10-05 |
| `src/matinee/web/static/door/door.webp`, `subway-tile.svg`, `eye.svg` (the locked door's art) | `src/matinee/web/static/door` | 2026-10-05 |
| `tests/js/door-rules.test.mjs`, `tests/js/locked.test.mjs`, `tests/js/mark.test.mjs` | `tests/js/door-rules.test.mjs:6` | 2026-10-05 |
| `src/matinee/web/static/js/flight.js::fly` (`FLIGHT_MS`, the fail-open) | `src/matinee/web/static/js/flight.js:63` | 2026-10-05 |
| `src/matinee/web/static/js/flight.js::nameAt` / `wordmarkAt` / `riseOf` / `copyAt` | `src/matinee/web/static/js/flight.js:14` | 2026-10-05 |
| `src/matinee/web/static/js/about.js::openAbout` (the focus returns to what opened it) | `src/matinee/web/static/js/about.js:176` | 2026-10-05 |
| `src/matinee/web/static/js/about.js::close` (popstate; Escape steps back) | `src/matinee/web/static/js/about.js:159` | 2026-10-05 |
| `src/matinee/web/static/js/about.js::keeps` (the privacy statement, "What Matinee keeps") | `src/matinee/web/static/js/about.js:115` | 2026-10-05 |
| `src/matinee/web/static/js/about.js::copy` (the About page's words and links; no steering section without a key; "Good company" always) | `src/matinee/web/static/js/about.js:22` | 2026-10-05 |
| `src/matinee/web/static/js/wall-grid.js::posterAcross` / `ACROSS` / `GAP` | `src/matinee/web/static/js/wall-grid.js:27` | 2026-10-05 |
| `src/matinee/web/static/js/wall-grid.js::wallLayout` | `src/matinee/web/static/js/wall-grid.js:37` | 2026-10-05 |
| `src/matinee/web/static/js/wall-grid.js::bestStride` / `repeatDistance` | `src/matinee/web/static/js/wall-grid.js:61` | 2026-10-05 |
| `src/matinee/web/static/js/wall-grid.js::filmIndex` / `nearestCell` / `filmAt` | `src/matinee/web/static/js/wall-grid.js:71` | 2026-10-05 |
| `src/matinee/web/static/js/wall-grid.js::pictureSize` | `src/matinee/web/static/js/wall-grid.js:89` | 2026-10-05 |
| `src/matinee/web/static/js/wall-grid.js::rankPool` (the page's order) | `src/matinee/web/static/js/wall-grid.js:98` | 2026-10-05 |
| `src/matinee/web/static/js/wall-grid.js::resortAnchor` | `src/matinee/web/static/js/wall-grid.js:141` | 2026-10-05 |
| `src/matinee/web/static/js/wall-grid.js::resortPlan` | `src/matinee/web/static/js/wall-grid.js:168` | 2026-10-05 |
| `src/matinee/web/static/js/hunt-plan.js::HOP_TABLE` / `hopCount` | `src/matinee/web/static/js/hunt-plan.js:7` | 2026-10-05 |
| `src/matinee/web/static/js/hunt-plan.js::hopOffset` / `TICK_PX` (the tick) | `src/matinee/web/static/js/hunt-plan.js:58` | 2026-10-05 |
| `src/matinee/web/static/js/hunt-plan.js::peakStep` / `limitedTime` (the speed limit) | `src/matinee/web/static/js/hunt-plan.js:65` | 2026-10-05 |
| `src/matinee/web/static/js/hunt-plan.js::settledCamera` | `src/matinee/web/static/js/hunt-plan.js:96` | 2026-10-05 |
| `src/matinee/web/static/js/hunt-plan.js::planHunt` (first hop, no reversal) | `src/matinee/web/static/js/hunt-plan.js:118` | 2026-10-05 |
| `src/matinee/web/static/js/hunt-plan.js::hopCell` / `placeLanding` | `src/matinee/web/static/js/hunt-plan.js:138` | 2026-10-05 |
| `src/matinee/web/static/js/glow.js::posterGlow` / `GOLD` | `src/matinee/web/static/js/glow.js:19` | 2026-10-05 |
| `src/matinee/web/static/js/quips.js::setFor` | `src/matinee/web/static/js/quips.js:9` | 2026-10-05 |
| `src/matinee/web/static/js/quips.js::Deck` | `src/matinee/web/static/js/quips.js:19` | 2026-10-05 |
| `src/matinee/web/static/js/quips.js::dealPair` / `dealBeneath` | `src/matinee/web/static/js/quips.js:51` | 2026-10-05 |
| `src/matinee/web/static/js/wall.js::Wall` | `src/matinee/web/static/js/wall.js:85` | 2026-10-05 |
| `src/matinee/web/static/js/wall.js::Wall.show` / `fadeIn` / `clear` / `whenStill` | `src/matinee/web/static/js/wall.js:142` | 2026-10-05 |
| `src/matinee/web/static/js/wall.js::Wall.endPick` | `src/matinee/web/static/js/wall.js:196` | 2026-10-05 |
| `src/matinee/web/static/js/wall.js::Wall.hunt` / `jump` / `readyToHunt` / `settle` / `hop` | `src/matinee/web/static/js/wall.js:242` | 2026-10-05 |
| `src/matinee/web/static/js/wall.js::Wall.stepBack` / `grownScale` | `src/matinee/web/static/js/wall.js:341` | 2026-10-05 |
| `src/matinee/web/static/js/wall.js::Wall.useSharp` (the front element) | `src/matinee/web/static/js/wall.js:366` | 2026-10-05 |
| `src/matinee/web/static/js/wall.js::Wall.bringForward` | `src/matinee/web/static/js/wall.js:385` | 2026-10-05 |
| `src/matinee/web/static/js/wall.js::Wall.dress` / `glowShadow` / `glowAt` | `src/matinee/web/static/js/wall.js:407` | 2026-10-05 |
| `src/matinee/web/static/js/wall.js::glowOf` | `src/matinee/web/static/js/wall.js:56` | 2026-10-05 |
| `src/matinee/web/static/js/wall.js::Wall.usePictures` / `posterUrl` (and the `fromTmdb` flag it sets) | `src/matinee/web/static/js/wall.js:127` | 2026-10-05 |
| `src/matinee/web/static/js/pictures.js::posterUrl` / `backdropUrl` / `posterPaths` / `corsImage` (`TMDB_WIDTHS`) | `src/matinee/web/static/js/pictures.js:24` | 2026-10-05 |
| `src/matinee/web/static/js/wall.js::Wall.putBack` / `returnPoster` / `liftDim` / `settleBack` | `src/matinee/web/static/js/wall.js:454` | 2026-10-05 |
| `src/matinee/web/static/js/wall.js::Wall.relayout` / `makeTiles` | `src/matinee/web/static/js/wall.js:554` | 2026-10-05 |
| `src/matinee/web/static/js/wall.js::Wall.prepare` (the re-sort's wait) | `src/matinee/web/static/js/wall.js:587` | 2026-10-05 |
| `src/matinee/web/static/js/wall.js::Wall.frame` (the drift, `DRIFT_PX_S`) | `src/matinee/web/static/js/wall.js:607` | 2026-10-05 |
| `src/matinee/web/static/js/wall.js::Wall.place` / `lay` / `picture` / `request` (`BLANK`) | `src/matinee/web/static/js/wall.js:618` | 2026-10-05 |
| `src/matinee/web/static/js/wall.js::Wall.resort` / `slide` / `depart` | `src/matinee/web/static/js/wall.js:702` | 2026-10-05 |
| `src/matinee/web/static/js/api.js::del` | `src/matinee/web/static/js/api.js:27` | 2026-10-05 |
| `src/matinee/web/static/js/pick.js::showPick` / `huntLift` | `src/matinee/web/static/js/pick.js:280` | 2026-10-05 |
| `src/matinee/web/static/js/pick.js::goldLine` | `src/matinee/web/static/js/pick.js:221` | 2026-10-05 |
| `src/matinee/web/static/js/pick.js::bringOut` | `src/matinee/web/static/js/pick.js:258` | 2026-10-05 |
| `src/matinee/web/static/js/pick.js::toRest` (`BEAT_MS`, `STILL_HOLD_MS`) | `src/matinee/web/static/js/pick.js:303` | 2026-10-05 |
| `src/matinee/web/static/js/pick.js::fetchFilm` / `picture` (the backdrop waits for the card under `tmdb`) | `src/matinee/web/static/js/pick.js:317` | 2026-10-05 |
| `src/matinee/web/static/js/pick.js::restingPoster` | `src/matinee/web/static/js/pick.js:204` | 2026-10-05 |
| `src/matinee/web/static/js/pick.js::rest` | `src/matinee/web/static/js/pick.js:181` | 2026-10-05 |
| `src/matinee/web/static/js/pick.js::settle` / `fit` | `src/matinee/web/static/js/pick.js:54` | 2026-10-05 |
| `src/matinee/web/static/js/pick.js::moreOn` ("More on Seerr ↗" or "More on TMDB ↗", by `link_to`) | `src/matinee/web/static/js/pick.js:156` | 2026-10-05 |
| `src/matinee/web/static/js/fuse.js::lightFuse` / `fuseTimeline` | `src/matinee/web/static/js/fuse.js:37` | 2026-10-05 |
| `src/matinee/trees.py::_self_destruct` / `_one_self_destruct` | `src/matinee/trees.py:178` | 2026-10-05 |
| `src/matinee/web/static/js/pick.js::feature` | `src/matinee/web/static/js/pick.js:77` | 2026-10-05 |
| `src/matinee/web/static/js/pick.js::choices` | `src/matinee/web/static/js/pick.js:167` | 2026-10-05 |
| `src/matinee/web/static/js/pick.js::showNoFilm` | `src/matinee/web/static/js/pick.js:129` | 2026-10-05 |
| `src/matinee/web/static/js/pick.js::firstPickReveal` | `src/matinee/web/static/js/pick.js:104` | 2026-10-05 |
| `src/matinee/web/static/js/pick.js::showCredit` (DoesTheDogDie's credit before its line types; none without a key) | `src/matinee/web/static/js/pick.js:97` | 2026-10-05 |
| `src/matinee/web/static/js/pick.js::lookUp` ("Look it up on DoesTheDogDie ↗") | `src/matinee/web/static/js/pick.js:90` | 2026-10-05 |
| `src/matinee/web/static/js/note.js::noteLink` | `src/matinee/web/static/js/note.js:61` | 2026-10-05 |
| `src/matinee/web/static/js/credits.js::credits` (`dtdd`: room for DoesTheDogDie's credit) | `src/matinee/web/static/js/credits.js:36` | 2026-10-05 |
| `src/matinee/web/static/js/credits.js::dtddCredit` (built hidden) | `src/matinee/web/static/js/credits.js:27` | 2026-10-05 |
| `src/matinee/web/static/js/credits.js::aboutLink` ("About Matinee"; `around`, the door) | `src/matinee/web/static/js/credits.js:20` | 2026-10-05 |
| `src/matinee/web/static/js/dom.js::h` (text nodes only) | `src/matinee/web/static/js/dom.js:12` | 2026-10-05 |
| `src/matinee/web/static/js/type.js::typeLine` (`shown`: a gold line kept while the rest types beneath) | `src/matinee/web/static/js/type.js:11` | 2026-10-05 |
| `src/matinee/web/static/manifest.webmanifest` | `src/matinee/web/static/manifest.webmanifest:1` | 2026-10-05 |
| `src/matinee/web/static/css/matinee.css` `:root` (the standard's colour tokens, `--shade`, `--band-fade`) | `src/matinee/web/static/css/matinee.css:17` | 2026-10-05 |
| `src/matinee/web/static/css/matinee.css` `.stage` (starts beneath the warning strip, `--warning-h`) | `src/matinee/web/static/css/matinee.css:150` | 2026-10-05 |
| `src/matinee/web/static/css/matinee.css` `.warning-strip` (the stale-data warning) | `src/matinee/web/static/css/matinee.css:1582` | 2026-10-05 |
| `src/matinee/web/static/css/matinee.css` `.talk > .setup-lines`, `.talk.setup` (the setup note) | `src/matinee/web/static/css/matinee.css:488` | 2026-10-05 |
| `src/matinee/web/static/css/matinee.css` `.door-foot > .about-link`, `.bottombar > .about-link` ("About Matinee" at the foot's middle) | `src/matinee/web/static/css/matinee.css:1846` | 2026-10-05 |
| `src/matinee/web/static/css/matinee.css` `.trail` (crumbs, separators, `.keep`) | `src/matinee/web/static/css/matinee.css:274` | 2026-10-05 |
| `src/matinee/web/static/css/matinee.css` `.way-back` (a phone's way back; no trail and no TMDB credit line on a phone) | `src/matinee/web/static/css/matinee.css:242` | 2026-10-05 |
| `src/matinee/web/static/css/matinee.css` `.action`, `.action.rose`, `.action.petrol`, `.action.cream` (gold is the base rule) | `src/matinee/web/static/css/matinee.css:1119` | 2026-10-05 |
| `src/matinee/web/static/css/matinee.css` `.letterbox` (one size) | `src/matinee/web/static/css/matinee.css:430` | 2026-10-05 |
| `src/matinee/web/static/css/matinee.css` `.answers`, `.answers.many` (the doors run across and wrap) | `src/matinee/web/static/css/matinee.css:418` | 2026-10-05 |
| `src/matinee/web/static/css/matinee.css` the scrims: `.line > .ack`/`.ask`, `.countdown`, `.note`, `.footnote`, `.count`, `.seat-label`, `.feature-text`, `.correct-panel` | `src/matinee/web/static/css/matinee.css:390` | 2026-10-05 |
| `src/matinee/web/static/css/matinee.css` the bands: `.topbar::before`, `.bottombar::before`, `.door-foot::before`, `.stage.at-door.behind-about::before` | `src/matinee/web/static/css/matinee.css:173` | 2026-10-05 |
| `src/matinee/web/static/css/matinee.css` `.showing` (the pick's left column) | `src/matinee/web/static/css/matinee.css:619` | 2026-10-05 |
| `src/matinee/web/static/css/matinee.css` `.topic-list`, `.topic`, `.topic-foot` (the picker's topics) | `src/matinee/web/static/css/matinee.css:2202` | 2026-10-05 |
| `tests/test_design_standards.py::declarations` / `built` / `enclosing` / `PERMITTED` / `ARTWORK` (the standard's mechanical rules) | `tests/test_design_standards.py:232` | 2026-10-05 |
| `src/matinee/web/static/css/matinee.css` reduced-motion rules (the marquee and the door's words change at once) | `src/matinee/web/static/css/matinee.css:1170` | 2026-10-05 |
| `src/matinee/web/static/css/matinee.css` `.wall`, `.wall-tiles`, `.tile` (`--tile`, the one strength; the dark cell) | `src/matinee/web/static/css/matinee.css:102` | 2026-10-05 |
| `src/matinee/web/static/css/matinee.css` `.marquee` (its measures as properties, the top fade, the short windows' scaling) | `src/matinee/web/static/css/matinee.css:1220` | 2026-10-05 |
| `src/matinee/web/static/css/matinee.css` `.marquee.lifted`, `.stage.leaving`, `.flying-name` (going in) | `src/matinee/web/static/css/matinee.css:1250` | 2026-10-05 |
| `src/matinee/web/static/css/matinee.css` `.sign`, `.bulb`, `@keyframes chase` | `src/matinee/web/static/css/matinee.css:1435` | 2026-10-05 |
| `src/matinee/web/static/css/matinee.css` `.door-wall`, `.door-talk`, `.door-foot` | `src/matinee/web/static/css/matinee.css:1271` | 2026-10-05 |
| `src/matinee/web/static/css/matinee.css` `.picker` | `src/matinee/web/static/css/matinee.css:2150` | 2026-10-05 |
| `src/matinee/web/static/css/matinee.css` phone door: `.marquee` sizes, `.marquee.compact` (the lit strip) | `src/matinee/web/static/css/matinee.css:1326` | 2026-10-05 |
| `src/matinee/web/static/css/matinee.css` `.credits`, `.dtdd-credit`, `.tmdb-logo`, `.bottombar .credits`, `.inline-link` | `src/matinee/web/static/css/matinee.css:1597` | 2026-10-05 |
| `src/matinee/web/static/css/matinee.css` `.stage.behind-about`, `.about`, `.about-wordmark`, `.about-panel` | `src/matinee/web/static/css/matinee.css:1643` | 2026-10-05 |
| `src/matinee/web/static/css/matinee.css` `.pick-line` (size, four lines reserved), `.hushed` | `src/matinee/web/static/css/matinee.css:672` | 2026-10-05 |
| `src/matinee/web/static/css/matinee.css` `.talk > .footnote` | `src/matinee/web/static/css/matinee.css:511` | 2026-10-05 |
| `src/matinee/web/static/css/matinee.css` `a.wordmark` | `src/matinee/web/static/css/matinee.css:191` | 2026-10-05 |
| `src/matinee/web/static/css/matinee.css` `.just-pick-row` (the count beside the button) | `src/matinee/web/static/css/matinee.css:523` | 2026-10-05 |
| `src/matinee/web/static/css/matinee.css` `.mark`, `.seats`, `.seat` (the tiles; the short window's sizes) | `src/matinee/web/static/css/matinee.css:1916` | 2026-10-05 |
| `src/matinee/web/static/css/matinee.css` `.avatar-choices` | `src/matinee/web/static/css/matinee.css:2059` | 2026-10-05 |
| `src/matinee/web/static/css/matinee.css` `.viewer`, `.viewer-menu`, `.viewer-panel` (the phone's initials) | `src/matinee/web/static/css/matinee.css:2449` | 2026-10-05 |
| `src/matinee/web/static/css/matinee.css` the locked door: `.locked`, `.subway`, `.door-frame`, `.locked-door`, `.slot`, `.peek`, `.line.locked-line` | `src/matinee/web/static/css/matinee.css:2726` | 2026-10-05 |
| `src/matinee/web/static/blank.svg` (a tile with no picture) | `src/matinee/web/static/blank.svg:1` | 2026-10-05 |

### Deployment

| Handle | Where | Verified |
|---|---|---|
| `Dockerfile` (one worker, uid 1000, `/state`, `DATA_DIR`) | `Dockerfile:1` | 2026-10-05 |
| `.dockerignore` | `.dockerignore:1` | 2026-10-05 |
| `example.env` (every setting of section 13, none filled in) | `example.env:1` | 2026-10-05 |
| `tests/test_example_env.py::test_example_env_names_every_setting_the_spec_lists_and_fills_in_none` | `tests/test_example_env.py:11` | 2026-10-05 |

