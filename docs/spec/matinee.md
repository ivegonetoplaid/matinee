---
purpose: The contract Matinee holds to — the media servers it reads, the source question and the conversation model, the pick's rank and tags, the labels and the household override file, the pools and scales, the offline film table and its rebuild, the setup note and the logs, profiles and the store file, each profile's settings, ratings, hidden films and history, the door word, the optional DoesTheDogDie topics and check, viewers' notes, the web surface, the page and My profile, deployment and third-party terms — with a map of where each part lives.
updated: 2026-10-14
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
showing, with `Show me another` to draw again.

This spec was written from the code on 2026-09-26 and last reconciled with it on
2026-10-05; its pick screen, the pick's rank and tags, the film card and the
wordmark's size were reconciled on 2026-10-10, and each profile's own records,
the narrowing of a viewer's pool and My profile on 2026-10-14. It has two halves. The
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
   behind it. Section 13 says which one an installation reads. The film list
   carries each copy's audio track languages only when asked for them, and only
   the nightly rebuild asks (section 5.1), so no viewer waits on that read.
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
4. **Matinee's own state is its own.** Profiles, device tokens, saved topics,
   each profile's tailoring settings and welcome mark, its ratings and short
   reviews, its hidden films and its history, and viewers' notes live in
   Matinee's store. None of it reaches a media server.
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

Every question and reply answers what the viewer just said: it picks up the
matter of the answer rather than marking that an answer arrived. Across every
line Matinee speaks (the trees' openings, questions and replies, the first
question's lines and replies, the pick's lines, and every sentence the page or
the server says to a viewer) a line opens with a stock interjection ("Very
well.", "No problem.") or a lone word set off by a comma, full stop, colon or
exclamation mark ("So, …", "Horror. …") only when it was written to land that
way on purpose: a film's line ("war. war never changes.", "life, uh, finds a
way."), a joke that needs its beat, or a list that only looks like the form.
A test in `./check.sh` names each such line with what it is doing and fails on
any other, and on a named line that is gone; a literal in the page or the
server that takes the form but is not Matinee speaking, such as an answer a
viewer taps, is named in that test too. "So what …", with no pause after "so",
is not the form.

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
| something we don't have yet. something new! | the films the labels name that the library does not hold (`new`) | coming soon, to a living room near you. |
| anything at all. ours or not. | both, a film in both once (`all`) | no borders tonight. I like it. |

- The chosen source bounds every later question, count and pick of the walk,
  `Just pick one!` included: which doors are shown, which answers are shown or
  hidden (the 30-film bar for a labelled kind counts the source's films), and
  when the questions stop.
- The answer is never carried into the next walk: every start asks again. It is
  sent with each request of the walk (`source` on `/api/first`, `/api/walk` and
  `/api/pick`) and never stored.
- No screen shows a trail. A question screen's way back is one action, "‹ Back"
  or `Start over` (section 2.4); the pick's is "‹ Back" (section 12).
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
  carries no library notice, and neither does a walk the source question was not
  asked of, whose setup note said so.
- While a configured Seerr does not answer, the same three responses carry, in
  `fallback` after any library notice, "I can't reach your Seerr right now, so
  each pick links to TMDB until it's back." (section 5.4), whatever the source
  answer. A response without `fallback` takes the notice down and leaves the
  stale-data warning (section 12), so the notice clears once neither the library
  nor Seerr is away.
- The wording is data in `data/first_question.json` (`source`). A file whose
  answer names no source is refused.

### 2.1 The first question

The poster wall opens by typing "Right this way." and "What are we in the
mood for?". Every viewing runs under a profile, so the first line carries its
name: "Right this way, <name>.". After the source question the doors type the
source answer's reply in gold, then "What are we in the mood for?"; a return
to the doors through "‹ Back" or the pick's Back panel types the same reply. Each answer is a door, offered by its plain name.
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
  such as the "Something wrong?" panel. Each door's label is its name.
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
passes it too. A wrongly included film costs one `Show me another`; a wrongly
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
- **The way back.** Once the walk holds a source answer or a door, each
  question screen shows one action at the foot's left, in the place the pick's
  "‹ Back" holds, at every width (on a phone, half the row wide). The walk's
  steps are `Start`, the source answer when the source question was asked, the
  door, then each answer so far. "‹ Back" goes to the screen before this one and
  forgets every answer after it: the source answer's step shows the doors
  within it, the door's step asks the door's first question, and an answer's
  step asks the question that followed it. Where one step back would reach the
  walk's first screen, the action is `Start over` instead, since the two are
  the same. The walk's first screen shows neither. No screen shows a trail.
- **The pick's way back** is "‹ Back", which
  opens the Back panel: every answer of the walk, each a way back to its
  question, the films shown this run, and `Start over` (section 12). The
  browser's back steps back one answer from a pick (section 12).

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

The checker walks every tree as a viewer with no profile, so no profile's
settings, ratings or hidden films (section 6) count for or against a film's
reachability.

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
  `Show me another` and "Roll again", and `rush` lines, said after "Just pick
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

### 2.8 The pick's rank and tags

The pick says how well audiences regard the film, as its rank among the films
behind its door, and shows a few tags that describe it. Both arrive on the
film card (section 11.1). Neither places a film, filters a pool or explains
why a film was picked: the labels alone place films (section 2.6).

**The rank** (`src/matinee/ranks.py`).

- It is computed from TMDB's vote average, the film table's `tmdb_rating`. The
  media server's rating is never read, and no number is ever shown.
- **The vote floor.** Only a film with at least 200 TMDB votes and a TMDB score
  is ranked or counted (`VOTE_FLOOR`, one named value with no setting). A film
  under the floor, or with no score, has no clear rank, and its line says so,
  so the pick's room for the rank never empties (`thin_rank`): "Too new for
  clear ratings" for a film released this year or last (`NEW_YEARS`), else
  "Too little-known for clear ratings", over a standing that says where its
  few votes would place it among the door's counted films, by the same place
  and bands as a ranked film: "Only 19 votes, which place it in the top 40% by
  TMDB audience rating" ("Only 1 vote, which places it…"). A film with no
  score or no votes stands over "No votes on TMDB yet".
- **The door's films.** A rank counts among every film the labels and the
  waiting room put behind the door the pick came through: the door's whole
  pool over the film table (section 3.1), whatever source the viewer chose. A
  ranked film is always counted with them, behind the door or not. A pick made before any door
  counts among every film behind any door.
- **The place.** The film's place is (the counted door films scoring higher
  than it, plus one) divided by (the counted door films other than it, plus
  one): its position from the top, as a share of the counted films and itself.
  Films with the same score share the better place, so they share a band.
- **The bands.** The place reads as one of these lines, with the door's word in
  place of "horror", and a standing that names the band's share of the door's
  films and what it is measured by (`BANDS`, `BASIS`). A place exactly on an
  edge reads as the higher band.

  | The film's place among the door's films | The rank reads | Its standing |
  |---|---|---|
  | Top 5% | A crowd favourite in horror | Top 5% by TMDB audience rating |
  | Top 10% | Very well received in horror | Top 10% by TMDB audience rating |
  | Top 25% | Well liked in horror | Top 25% by TMDB audience rating |
  | Top 40%, below the top 25% | Above the middle in horror | Top 40% by TMDB audience rating |
  | The middle 20% (40% to 60%) | Middle of the pack in horror | Middle 20% by TMDB audience rating |
  | Below 60%, above the bottom 10% | A tougher sell in horror | Bottom 40% by TMDB audience rating |
  | Bottom 10% | Bringing up the rear in horror | Bottom 10% by TMDB audience rating |

- **The door's words**, by tree: comedy "comedy", action "action and
  adventure", drama "drama", thriller "thrillers", crime "crime", horror
  "horror", scifi "sci-fi", fantasy "fantasy", romance "romance", animation
  "animation", western "westerns", war "war films", kids "kids' films",
  nonfiction "documentaries" (`DOOR_WORDS`). Before any door, "overall" stands
  in for "in horror": "Well liked overall". A tree with no word has no rank; a
  test holds every door the first question offers to having one.
- The page sets the standing beneath the rank in small quiet text
  (section 12).
- A viewer's rating floor (section 6) reads the same places and the same bands'
  edges, so a film the pick would call "Bringing up the rear" is the film the
  floor "Above the bottom 10%" keeps out.

**The tags** (`src/matinee/tags.py`).

- `data/tags.json` ships each genome film's 40 strongest MovieLens genome
  words, strongest first, keyed by TMDB id, so no installation downloads
  MovieLens (`WORDS_PER_FILM`). Where two MovieLens films share a TMDB id, the
  first one wins, as in the shipped scores (section 5.3). The file names each
  word once, in its own word list, and gives each film its words as positions
  in that list. It carries the dataset's conditions in its `licence` field and
  the release in `source` (section 14). It also lists, in `alike`, every pair
  of words that say nearly the same thing, as two positions: two forms of one
  word, the same once reduced to letters and digits (such as "sci-fi" and
  "scifi") or the same once one of the endings `ENDINGS` lists is taken off
  (such as "spies" and "spying"); or two words whose relevance correlates at
  0.78 or more across the genome's films (`ALIKE`), such as "espionage" and
  "spying". It holds 252 pairs. `tools/build_genome.py` writes it from
  the same release as `data/genome.json`, after the same release check
  (`--tags-out` names another path). It holds 16,353 films.
- `data/tag_skip.txt` lists the words the pick never shows: one word per line,
  exactly as the genome spells it, a line starting with `#` a note, blank lines
  ignored. It holds 298 words in four groups: genre names and a genre's plain
  adjective ("funny", "humorous"); generic praise and
  judgement; words about the release rather than the film (lists, awards,
  sources, sequels, ratings, formats and names); and words unfit for a family
  screen. A test in `./check.sh` fails when an entry is not a genome word, and
  when a skip-list word reaches any film's tags.
- The pick shows a film's first four words not on the skip list, strongest
  first (`SHOWN`), passing over a word that is alike to one already shown, so it
  never shows both words of a pair; fewer when fewer remain, and none for a film
  the genome does not cover. The skip list applies first, so a skipped word never
  keeps its pair off a film. Every covered film shows four with the shipped
  list, reaching no deeper than its 34th word; the 40 shipped words leave room
  for a longer list.
- The server reads both files once at start-up and applies the skip list then,
  so an edit to the list takes effect at the next start. An image built from a
  source checkout carries the edit; a pulled image carries its own copy, which
  an update replaces. A skip-list word that is not a genome word is logged as a
  warning naming it, since it skips nothing.
- Either file that cannot be read (absent, not UTF-8, malformed, or giving a
  film anything but whole-number positions in its word list, or an `alike`
  entry that is not two such positions) leaves every pick
  without tags and puts the fault on the setup note (section 5.6).

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
its vote count in their own columns. A library film's row also keeps the
languages its copies' audio tracks are tagged with (`audio`, section 5.1); a
film with no copy, or whose tracks are all untagged, keeps none.

### 5.1 The nightly rebuild

`tools/rebuild_table.py` writes the table. With `--daily HH:MM` it rebuilds at
once and then every day at that local time; `--daily` alone takes the time from
`REBUILD_TIME`, 04:30 when unset. A time given to `--daily` is validated before
the first rebuild; a `REBUILD_TIME` that is no `HH:MM` time is logged and the
rebuild runs at 04:30. A media server that does not answer or turns down the key
is never a failure: the rebuild waits for it (step 2). A rebuild that fails on an unexpected error
puts back the table it started with, which it keeps under a second name
(`films.sqlite.kept`) while it runs, and tries again at the next scheduled time;
one that stops on TMDB (no key, a refused key, TMDB not answering) keeps what it
saved.

The server runs it: while the server serves, it keeps `rebuild_table.py --daily`
running as its own process beside itself (`matinee.web.main.Rebuilds`), so a
slow or failing rebuild never holds up a page. A rebuild process that exits is
logged and started again five minutes later; stopping the server stops it. Each
rebuild holds `rebuild.lock` in the state directory while it runs, so a second
rebuild on the same directory (one started by hand, or one left running by an
older two-container setup) waits for the first and then runs its own.

1. Without a TMDB key (`TMDB_TOKEN`) it fetches nothing, writes no table, and
   reports the reason (below). It still drops cached records past six months
   and shelved pictures past 150 days (section 5.2).
2. It reads the media server's film list, by GET only, when a media server is
   set. With none, or with settings that name both servers or cannot be used
   (logged), it runs on the labels alone. A media server that gives no usable
   answer, or turns down the key, is never given up on (section 5.4): the
   rebuild reports `waiting`, reads it again 15 seconds after each failed read
   with the table in place untouched, and goes on the moment it answers. While
   it waits it still sweeps the shelved pictures and the cached records past
   their keep (section 5.2) once a day. Its failures are logged as section 5.4
   says, the 120 seconds counted from the rebuild process's own start. This
   read, and no other, asks for each copy's audio track languages (below).
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
7. It logs a report. The report counts films with and without genome scores,
   library films whose audio tracks name at least one language, and items with
   no TMDB id. It names every file whose `{tmdb-N}` folder tag differs
   from the TMDB id the media server gives, and every film missing a usable TMDB
   record. It uses the media server's id and changes nothing on the server.

**Audio languages.** Step 2's read of the film list asks for each copy's audio
tracks, by GET only, and keeps the languages they are tagged with, so the
language preference (section 6) can judge a film by the audio the household
actually has.

- Jellyfin's film list carries each item's media streams when asked for them,
  about five times the bytes, so the rebuild reads it 5,000 items to a request
  (`StartIndex`, `Limit`), a page shorter than that ending the read. Only
  streams of type `Audio` count; subtitles never do.
- Plex's film list carries no streams. The rebuild reads each film's own
  details, 100 films to a request (`/library/metadata/<keys>`), and counts the
  streams of type 2 (audio) by their `languageCode`.
- A tag is an ISO 639-2 code in either of its forms ("fre" and "fra" both), or
  a two-letter code, and is kept as the two-letter code TMDB gives a film's
  original language, from the shipped table `data/languages.json`. That table
  follows TMDB where TMDB differs from ISO 639-1: Norwegian Bokmål and Nynorsk
  are `no`, and Cantonese (`yue`) is `cn`. Chinese (`chi`, `zho`) names no one
  language TMDB uses, so it is absent.
- A track with no tag, a placeholder tag (`und`, `zxx`, `mul`, `mis`) and a code
  the table does not hold count as untagged. A copy whose tracks are all
  untagged keeps no languages, and neither does a film with no copy.
- A track whose name (Jellyfin's `Title`, Plex's `title`) says `commentary`,
  `descripti…`, `isolated` or `music only`, in any case, is a commentary, an
  audio description or the score alone, not the film in a language, and is
  passed over as an untagged track is: a Thai film with an English commentary
  has no English copy.
- A film held as several copies keeps every copy's languages together.
- A rebuild with no media server records no audio languages.

The rebuild reports itself in `rebuild.json` in the data directory, replaced
whole each time, and the server reads it
(`src/matinee/progress.py::RebuildStatus`):

```json
{"state": "running", "started_at": "2026-10-05T03:00:00+00:00",
 "updated_at": "2026-10-05T03:01:40+00:00", "done": 2500, "total": 10327, "reason": null}
```

`state` is `waiting` after each failed read of the media server, 15 seconds
apart, while it does not answer or turns down the key (step 2), `running` as it fetches, at least every 5 seconds, with the films
this run has fetched or failed out of those it needs (`done`, `total`),
`finished`, or `stopped` with the reason: "no TMDB key is set", "TMDB refused
the key", "TMDB is not answering", or, for an unexpected failure, "the rebuild
failed: " and the error, so the server's state line names it; the rebuild's log
holds the traceback. A `running` or `waiting` report that has not
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
  5.6); a table from before this format is such a table. The `audio` column is
  the one exception: a table without it is read with no audio languages, so an
  update never stops picks until the next rebuild writes them.
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
- The same tool writes `data/tags.json`, each genome film's strongest words for
  the pick's tags (section 2.8). The rebuild never reads it; the server does.
- **A film the genome does not cover carries no genome scores (NaN), never
  zeros.**
- The table stores one row per distinct TMDB id. Library items with no TMDB id
  are left out and reported.
- The maintainer's tools may cache the parsed genome matrix beside the
  dataset. The cache is reused only when made from a genome file of the same
  size and modification time.

### 5.4 The live library

- The server reads the media server's film list at most every **300 seconds**.
  A film on the list is held. It shows the media server's facts and audio
  languages as the rebuild read them, with the item the list names now; one the
  library took in since the rebuild shows the list's facts and has no audio
  languages until the next rebuild. The live read never asks for audio tracks. A film the labels name that the list lacks is
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
- The media server and Seerr run on the household's network, so neither is
  ever given up on: each is asked again at most every **15 seconds** while it
  does not answer, with no backoff (the server on its next request, the rebuild
  on its own; `src/matinee/outage.py`). A connection refused, timed out or
  dropped mid-answer counts as no answer. TMDB and DoesTheDogDie are outside
  services and keep their own limits. Each run of failures is logged at most
  once at each level: at INFO, as a service that may still be starting, while
  it falls in the first **120 seconds** after Matinee starts, and as a warning
  once it fails after that or begins later. A turned-down key is warned at once.
  An answer that ends a run is logged.
- Seerr is checked at most every 15 seconds, answering or not, on the next
  request; section 2.0 says what the walk shows while it does not answer.
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
to recover; a household service not answering just after start is said at INFO
first (section 5.4). A warning one bad answer per picture would repeat is logged at most
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
  the film tags or their skip list, or data the engine cannot prepare: stale
  reference statistics, a malformed tree), with "update or reinstall Matinee";
- a household override file that cannot be used (section 2.6), with what is
  wrong in it;
- a rebuild whose report stood still for 120 seconds, as a failed rebuild;
- when there is no film to recommend, why: the rebuild is still fetching, it is
  waiting for the media server before it fetches, or no film details exist and
  nothing is fetching them.

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
genres (section 3.1). Film tags that cannot be read leave every pick without
tags (section 2.8).

The note names a fault as Matinee found it, so a line about Matinee's own files
or the override file may carry the problem's own words, a file's path among
them (`src/matinee/web/app.py::setup_faults`).

## 6. What one viewer's pool is

For each tree, the kids tree included, the viewer's starting pool is built in
this order:

1. The tree's pool, with house pins already applied.
2. Only the films of the chosen source (section 2.0).
3. Every question the viewer's DoesTheDogDie topics skip applies its `treat_as`
   answer.
4. Only the films the viewer may be offered: none the profile has hidden whose
   hide has not ended (section 7.5), none it has rated at or below its
   rated-films setting (section 7.3), and, while it has ticked any language,
   only films in a ticked language (below).
5. The rating floor: a film whose place among its own door's films (the place
   section 2.8 counts, over the door's whole pool whatever the source) falls
   past the floor's edge stays out. A film with no place, under 200 TMDB votes
   or with no TMDB score, never does, so new and little-known films still
   reach the viewer.

| Floor | The furthest place it keeps |
|---|---|
| Anything | every film |
| Above the bottom 10% | 90% (it keeps out "Bringing up the rear") |
| Middle of the pack or better | 60% |
| Above the middle or better | 40% |
| Well liked or better | 25% |

The edges are section 2.8's band edges, and a place exactly on an edge is kept.

**The language check.** While a viewer has ticked one or more languages, a film
with a library copy whose audio tracks name a language (section 5.1) passes
when one of them is ticked; any other film passes when its TMDB original
language is ticked; a film with neither, or whose only language is TMDB's
placeholder `xx`, is in no language and stays out. No film is exempt,
animation included. With no language ticked ("Any language") the check does
not run.

Steps 4 and 5 are read afresh from the store on every request, so a hide, a
rating or a changed setting shows on the viewer's next request. Every count,
every answer shown and the poster wall follow the narrowed pool, and the usual
rules apply unchanged: an answer that would leave the pool empty is not shown,
and a question with no answer to show is skipped. They narrow one viewer's
pools and nothing else: the answer masks every viewer shares never see them. A
viewer with every setting at its default, nothing hidden and nothing rated
"Hated it" sees exactly the pools a viewer with no settings sees.

**Before any door.** The first question offers a door only when that door's
narrowed pool holds a film. The first screen's wall and its count, and "Just
pick one!" there, take the films the offered doors hold together, so a film
behind several doors stays when it passes the floor behind at least one.

**An empty first question.** When a profile's settings and hidden films leave
the first question no door, `POST /api/first` carries `unsettled`: the number of
films the first question would hold in the chosen source with none of the
profile's settings, its DoesTheDogDie topics included, and nothing hidden.
Section 12 says what the page makes of it. `unsettled` is null whenever a door
is offered, for a device naming no profile, and where that number is itself 0
(the source holds no film at all), since then it is not the settings that leave
nothing.

**A pick after a hide.** A hide or a rating made during a walk can change which
questions the narrowed pool asks, so the answers already given may no longer
fit it. A pick whose answers no longer fit is drawn from those answers walked
without the viewer's own narrowing (steps 4 and 5), keeping only the films that
narrowing allows. Answers that fit neither walk are refused as any other
answers that no longer fit (section 2.4).

A viewer's notes (section 10) never change a pool. A rating by itself keeps no
film out: only the rated-films setting does.

Answers narrow that pool from there (section 2.4).

## 7. Viewers, profiles and devices

Matinee has no accounts and no login. Every viewing runs under a **profile**
this device holds a token for. A device without one is shown the first
question's pool behind the front door, with no topic applied, and walks or
picks nothing until it opens or makes a profile.

| Rule | Value |
|---|---|
| A profile holds | a display name, an optional four-digit PIN, an optional avatar, DoesTheDogDie topics, its tailoring settings and welcome mark (section 7.3), and what it keeps of its own: its ratings and short reviews (7.4), its hidden films (7.5) and its last 50 runs (7.6) |
| Avatar | one of fifteen: `3d-glasses`, `camera`, `candy`, `chair`, `clapperboard`, `comedy-tragedy`, `director-megaphone`, `film-reel`, `hotdog`, `nachos`, `popcorn`, `soda`, `theater-seat`, `ticket`, `vhs`; or none, for initials. Two profiles may share one |
| Most profiles | **50**; creating a fifty-first is refused |
| Name | 1 to 40 characters after NFKC normalisation, trimming and collapsing spaces; no character of Unicode category C (control, format, private-use, unassigned); unique ignoring case (NFKC, case-folded) |
| PIN | exactly four ASCII digits, or none |
| PIN storage | salted scrypt digest (N 2^14, r 8, p 1, 32 bytes, 16-byte salt); never stored as typed |
| Lockout | **5** wrong PINs lock that profile against PIN entry for **15 minutes**; keyed on the profile, never on a client address |
| Device token | 32 random bytes, URL-safe; stored only as a SHA-256 digest, so a copy of the store cannot be replayed as a cookie |
| Token cookie | `matinee_tokens`: `HttpOnly`, `SameSite=Lax`, path `/`, 400 days, and `Secure` whenever the browser reached Matinee over HTTPS (directly, or through a proxy whose forwarded scheme uvicorn trusts); over plain `http://` it is not `Secure`, because a browser discards a `Secure` cookie set there and every walk under a profile would be refused; holds at most **8** tokens, a ninth pushing out the oldest, and never a name or PIN |
| Token pruning | tokens older than 400 days are deleted whenever a new token is issued |

- **A device holding a valid token for a profile is never asked its PIN** and
  keeps its token when it opens the profile again.
- A profile with a PIN opens on another device only after its PIN.
- **The front door lists every profile** to an admitted device (section 7.2),
  sorted by name ignoring case: its id, name, avatar, whether it has a PIN, and
  whether this device holds it. It never carries a profile's topics, which can
  say what frightens a person, nor its settings, ratings, hidden films or
  history; only a device holding the profile, or one that has given its PIN,
  receives them. There is no typed name lookup. A device that is not admitted
  gets no profiles.
- **Everything a profile keeps is private to it.** Only a device holding the
  profile reads or changes its settings, ratings, short reviews, hidden films
  and history. The one exception is sharing (section 7.4): while a profile's
  sharing is on, its ratings and short reviews, with its name and avatar,
  reach a device holding any other profile of the household. Nothing else of it
  does.
- A token for a deleted profile is ignored. The door's reply clears it from the
  cookie.
- **Avatars.** A profile is made with an avatar or none, and a device holding
  it may set or clear it at any time. Every reply describing a profile to the
  page says which avatar it carries. An avatar Matinee does not offer is
  refused when set (`bad_avatar`) and reads as none when found in the store.
- **Renaming a profile.** A device holding a profile may rename it, under
  exactly the rules a new profile's name follows, with the same refusals and
  words: an unusable name is `bad_name`, and another profile's name, ignoring
  case and runs of spaces, is `name_taken` (409), "Someone already goes by that
  name here. Try another?". The profile's own name in another case is allowed.
  Every later reply naming the profile, the front door's included, carries the
  new name.
- **Avatar images.** Each avatar ships as two finished WebP files under
  `static/avatars/`: `<avatar>-256.webp` for the front door's tile and
  `<avatar>-80.webp` for the top bar, each twice its displayed size, square, with
  the art cropped to its visible edges, its longest side 84 per cent of the
  square, centred on transparency. No tile-size image is larger than the largest
  pail, and the thirty together stay under 1 MB. The source art is never in the
  repository, and the page never loads it.
- **Deleting a profile.** A device holding a profile may delete it, with no
  PIN asked, as it opens it with none. The profile and everything it keeps go,
  on every device: its topics, settings and welcome mark, its ratings and short
  reviews, its hidden films, its history and every device token issued for it.
  Its shared ratings vanish from every other profile at once. Its notes stay
  (section 10).
  The deleting device's cookie keeps its other tokens and drops this one. A
  device that does not hold the profile is refused with 403, so naming a
  profile's id is never enough to delete it: a profile with a PIN must first be
  opened with its PIN. A profile without a PIN opens on
  any admitted device, which may then read everything it keeps and delete it;
  Matinee adds no further guard (known gap 18).
- There is no PIN reset and no administrative surface on the web. Whoever runs
  the installation clears a forgotten PIN with the notes tool's
  `clear-pin "<profile name>"` (section 10), which matches the name as a
  profile name is stored (case, and runs of spaces, ignored), clears the PIN and any lockout on it, and refuses a name no profile has.
- A request naming a profile is refused with 403 unless this device holds a
  token for it: every route in section 11.1 whose path begins
  `/api/profiles/{id}`, except opening and making a profile, and the first
  question, a walk, a pick and a note that name one.
- Every write to a profile (its topics, avatar, name, settings and welcome
  mark, a rating, a short review, a hide, a film its run showed, a note, its
  deletion) checks the device's token in the same store transaction as the
  write. A profile deleted and its id given to a new profile between a device's
  check and its write never receives that write (`profile` error `not_held`,
  403).
- A walk or a pick naming no profile is refused with 403.

### 7.1 The store file

The store is one SQLite file, `matinee.sqlite`, in the state directory. It
records its shape in SQLite's `user_version`; the current shape is **2**. A file
from before shapes were recorded reads 0 and holds profiles, tokens, notes (in a
table named `feedback`) and personal corrections. Shape 1 holds profiles, tokens
and notes. Shape 2 adds each profile's tailoring settings and welcome mark
(columns of its row, section 7.3) and four tables of what a profile keeps:
`ratings` (7.4), `hidden` (7.5), and `runs` with their films, `run_films` (7.6).
Each of their rows goes with its profile when the profile is deleted.

- A missing or empty file is made at the current shape.
- Each profile row keeps an `exclusions` column from when Matinee had
  exclusions of its own. Matinee no longer reads or writes it; a new row takes
  its empty default.
- An older file is upgraded in place when Matinee starts, every step from its
  shape to the current one in one transaction, so a shape-0 file goes all the
  way. It is kept only when the counts of profiles, tokens and notes are the
  same after it as before and no row points at nothing; otherwise nothing of
  it is kept.
- From shape 0 the upgrade keeps every profile, token and note, each note under
  its own id, and removes the corrections. A "Not <genre> at all" note first
  takes, as where its film belongs, the trees its own correction added the film
  to: the correction with the note's profile, film and tree saved at or before
  the note, the latest of them. Every note arrives with the status `open`, and
  every profile with no avatar.
- From shape 1 every profile arrives with each setting at its default and
  without the welcome mark, so it sees the welcome once (section 12), and with
  no ratings, hidden films or history. The notes move to a new `notes` table,
  each under its own id, where a note may name no sort choice and may say the
  film's tags are wrong (section 10); none arrives saying so.
- Before its first change to an older file, the upgrade copies the file as it
  stood to a new file beside it, named
  `matinee.sqlite.before-shape-2-<UTC time>`. The copy is written under the
  working name `matinee.sqlite.copying` and takes its kept name only once it is
  whole, so a copy cut short by a crash or a full disk never passes for one.
  Nothing ever overwrites the kept copy, and a later start on the upgraded file
  makes none. A start that finds such a copy already there makes no other,
  because a refused upgrade leaves the store unchanged.
- Code from before shapes were recorded can still open a current file: it
  recreates its old tables and files new notes into `feedback`, where no queue
  reads them. A start that finds any row in a `feedback` table is refused and
  names the count; empty old tables do not stop it.
- A file newer than the code, a file that is not a SQLite database, a shape no
  upgrade starts from (a negative one), and an upgrade that fails all stop the
  start. The store file is left unchanged.

### 7.2 The door word

The door word is optional. With none set (`DOOR_WORD` unset, empty or
only spaces), every device is admitted. With one set, a device that is not admitted reaches
only the page, its static files (the locked door's art among them) and the word
check, `/api/admission`. Every other route answers `401 not_admitted`, with the
usual headers. The protection is sized for a household film picker. A page whose
device stops being admitted while it is open (the word changed, or the cookie
is gone) is sent back to the door: the first `401 not_admitted` any of its
requests meets reloads the page, which opens on the locked door, and that
request never answers, so no half-done screen is drawn first.

- **Admission.** The right word sets the cookie `matinee_admit` (`HttpOnly`,
  `SameSite=Lax`, path `/`, 400 days, and `Secure` over HTTPS exactly as the
  token cookie is: over plain `http://` a `Secure` admission would be discarded
  and the door would never open). Its value is the time it was
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

### 7.3 Tailoring settings and the welcome mark

Each profile carries four tailoring settings beside its DoesTheDogDie topics.
Section 6 says how they narrow its pool. A device holding the profile reads
them and changes any one alone; a setting the change leaves out stays as it is.
A change takes effect on the profile's next request.

| Setting | Choices, as the store keeps them | A new profile |
|---|---|---|
| The rating floor | `anything`, `above_bottom`, `middle`, `above_middle`, `well_liked` (section 6's table) | `anything` |
| The language preference | no language ticked ("Any language"), or one or more two-letter codes | none ticked |
| The rated-films setting | 0 to 5: films the profile rated this or lower stay out of its picks; 0 keeps every rated film in, 5 keeps every rated film out | 1 ("Hated it") |
| Sharing | on or off (section 7.4) | off |

- A floor or rated-films value outside its choices is refused (`bad_setting`,
  "That isn't one of the choices."), and so is a newly ticked language the film
  table does not hold (`bad_language`, "I don't have any films in that
  language."). Nothing is changed by a refused save.
- "Any language" is an empty list, which clears every tick. A language already
  ticked stays kept when the film table no longer holds it: it matches no film,
  the page does not show it, and a save is never refused for it.
- **The languages the film table holds** (`GET /api/languages`) are each
  language some film is in: its TMDB original language, never the placeholder
  `xx`, and each language its library copy's audio tracks are tagged with
  (section 5.1). Each comes with the number of films in it, most first, then by
  code. A film counts under its original language and under each audio
  language, so a count can exceed the films a tick keeps: the check in section 6
  reads a film's audio languages alone when it has any. The page names each one
  and puts the browser's own language first.
- **The welcome mark** says whether the profile has seen this feature's
  welcome (section 12). A profile made now starts marked, since making it
  already offers the tailoring steps; a profile from before (an upgraded shape-1
  store) starts unmarked. A device holding the profile marks it, and nothing
  unmarks it.

### 7.4 Ratings and short reviews

A rating is one profile's answer about one film: one of five answers, kept as a
whole number. The viewer only ever sees the words.

| Answer | Kept as | Read as a sentence about another profile |
|---|---|---|
| Loved it! | 5 | "<Name> loved it" |
| Really liked it | 4 | "<Name> really liked it" |
| It was ok, I guess | 3 | "<Name> thought it was ok" |
| Didn't like it | 2 | "<Name> didn't like it" |
| Hated it | 1 | "<Name> hated it" |

- A rating keeps its answer, the time it was made (UTC), its source (`matinee`
  for every rating made here) and an outside value, always empty in this
  build; it is kept for a rating that comes from another service (section 15
  lists none). These five answers are Matinee's only scale.
- A device holding the profile saves or changes a rating of a film Matinee
  offers now (any other film answers 404), and clears a rating of any film it
  has rated. Any other number is refused (`bad_score`). Saving the answer the
  film already has records nothing, so the stored time stays as it was; a
  changed answer takes the new time and keeps its short review.
  Clearing a rating clears its short review with it.
- **A short review** is optional: one line of plain text, trimmed, of at most
  100 characters counted as Unicode code points, so an emoji, joined or not,
  counts as its code points. A longer one, or one holding a control character
  or a line or paragraph separator, is refused, never cut (`bad_review`, "Short
  and sweet, please. About 15 words."). Format characters stay, since every
  joined emoji carries one. An empty one clears it. A short review needs a
  rating (`not_rated`, "Rate it first, then tell me why."). Changing only the
  short review leaves the rating's time as it was. Every surface shows it as
  text, never as markup.
- The profile's ratings read back newest first, each with its film's title and
  year. A rating of a film that has left the film table stays stored, and is
  neither shown nor counted.
- A rating made on the pick names its run, where the film is marked rated
  (section 7.6). A rating by itself keeps no film out of the profile's picks
  (section 6).
- **Sharing.** While a profile's sharing is on, every rating it has made, past
  and future, with its short review, its name and its avatar (one Matinee does
  not offer reads as none), reaches a device holding any other profile that asks
  about that film. While it is off, none does. Sharing covers all of a
  profile's ratings or none, and a change takes effect on the next request. A
  viewer sees the others' shared ratings whether or not its own sharing is on,
  and never its own rating as a shared one. Shared ratings stand newest rating
  first. A device that holds no profile receives none.

### 7.5 Hidden films

A hidden film is one a profile has asked Matinee not to pick, for a length the
viewer chooses each time.

- A device holding the profile hides a film Matinee offers now (any other film
  answers 404) for 3 months (`3m`), 6 months (`6m`), 1 year (`1y`) or for good
  (`good`). There is no default: a hide without a length is refused (422), and
  one with any other length too (`bad_length`, "Pick how long: 3 months, 6
  months, 1 year or for good.").
- A hide ends that many calendar months after the moment it was made, the day
  becoming the later month's last where that month lacks it (a six-month hide
  made on 31 August ends on the last day of February). A hide for good never
  ends.
- Hiding a hidden film again replaces its length and its time. Bringing a film
  back removes its hide at once. A hide whose end has passed no longer keeps the
  film out, and the film drops off the profile's list.
- The profile's hidden films read back newest hide first, each with its film's
  title and year, the length, when it was hidden and when it comes back (null
  for good). A hide of a film that has left the film table stays stored, and is
  neither shown nor counted.
- A hide made on the pick names its run, where the film is marked hid; its
  "Undo" brings the film back naming the same run, where the film gets back the
  mark the hide replaced (section 7.6).

### 7.6 History

Each profile keeps its last 50 runs. A run is everything from the walk's first
screen to `Start over` or the wordmark (section 12); changing an answer or the
door keeps it. The history belongs to the profile: it reaches whoever runs
Matinee only through a note the viewer sends, and no log line carries it.

- The page names each run with a key of its own, 32 random hexadecimal digits,
  new at every start. The server takes a key of 8 to 64 letters, digits, `-` or
  `_`, and refuses any other (`bad_run`, "I lost track of this run. Start over
  and I'll keep up.").
- As each film comes to rest on screen, the page sends it under the run's key
  with the walk that reached it: the door, the answers, and whether "Just pick
  one!" ended them. The server keeps the walk as a note takes it, with what the
  door and each answer said, and refuses a door or an answer the catalogue does
  not hold, or answers with no door (400 `refused`). A film Matinee does not
  offer now answers 404.
- A run is kept, with the time it began, once its first film is shown; a run
  that ends before any film leaves no history. Its films stand in the order
  shown. A film shown again in the same run moves to the end with its new walk
  and keeps its mark.
- Each film carries what the viewer did with it there: rated, hid, reported,
  or nothing. A rating, a hide or a note made on the pick, a film brought back
  from the Back panel included, names the run and marks the film. "Undo" of a hide puts back the mark
  the hide replaced; a second hide of the same film keeps the first one's. A
  rating, hide or note made from My profile or its overlay names no run and
  marks nothing.
- Nothing of DoesTheDogDie is kept: never a film the check turned away, even
  one the viewer then asked to see ("What were you going to show me?", "Just
  show me what you picked") or brought back from the Back panel, and never a
  verdict or an item.
- Keeping a run past the 50th drops the profile's oldest, with its films.
- The history reads back newest run first, each with its films in the order
  shown, each film with its title, year, mark and walk; a run's walk is its
  latest film's. A film that has left the film table is not shown, and a run
  left with no film is not shown either. The page sets every day in the
  viewer's own time zone.

## 8. DoesTheDogDie topics

A viewer may choose DoesTheDogDie topics: things they would rather not see
happen on screen. A profile saves them. The list a profile edits holds
DoesTheDogDie's topics alone; Matinee has no exclusions of its own.

**DoesTheDogDie is optional.** It needs the installation's `DTDD_API_KEY`.
Without one, Matinee offers nothing that needs DoesTheDogDie: the tailoring
steps ask no topics, My profile shows no "Scenes you don't want to see",
`GET /api/topics` and
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
- A viewer chooses topics in two places: in the trigger picker, the first
  tailoring step while a profile is made, and afterwards on My profile, under
  "Scenes you don't want to see" (section 12). Each says the check is best
  effort, from DoesTheDogDie's votes, beside the count of chosen topics, and
  each carries "Powered by DoesTheDogDie.com", linked: the picker in the door's
  foot band, My profile as a small text link under the row's explanation.
- When the topic list cannot be fetched, the picker says so and offers "Try
  again", with its "Skip" still beside saving; My profile's row says so in its
  open panel.

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
- **Used up.** When every film in the pool has been shown or turned away, or the
  pool holds none (a hide or a rating since the answers were given can empty
  it, section 6), no film is drawn. The page says "That's every film I've got for those
  answers. Step back, or start over." and offers `Start over`
  beneath the line and "‹ Back" in the foot (section 12).
  With `sort: rating`, the pool is the better-rated half, and an unknown rating
  ranks last.
- **Least gory first.** When a viewer's topics skip a question whose answers
  cut a scale (horror's gore question, skipped for its blood and gore topics),
  the pick draws first from the third of the candidates scoring lowest on that
  scale, rounded up. It draws from the rest only once that third is spent. The
  scale scores every film, whichever tree the pick came through; a film it
  cannot score is never in that third.
- **A failing film** is replaced by another draw from the same pool. A film that
  failed in this pick is never looked up again in it. The page says why in
  Matinee's voice: "I almost recommended a film where <topic>. Let's find you
  an alternative." It offers "What were you going to show me?", which reveals
  the first film turned away and the topics it failed.
- **Every film fails.** The page says "Every film left here trips something on
  your list. Want to start over?" and offers `Start over` beneath the line and
  "‹ Back" in the foot.
- **Three in a row.** A pick looks up at most **3** films that fail. When three
  have failed and others remain, it stops and the page says, in gold, "Three in
  a row trip your list, starting with one where <topic>." and, in cream, "Roll
  again, or I can show you what I picked." `<topic>` there is the first topic
  the first film that tripped trips. It offers `Roll again`, the action "Just
  show me what you picked" and `Start over`, in that order, beneath the line,
  and "‹ Back" in the foot; a phone sets
  `Start over` beside `Roll again` and "Just show me what you picked" in a row
  of its own, so the three fit its foot. The reply carries the
  third film that tripped in `last`: the film, the topics it trips and the two
  lines that show it. "Just show me what
  you picked" shows that film as a pick from the reply already held, asking
  no new pick and nothing of DoesTheDogDie (the film's details and pictures
  load as on any pick): "Here's what I picked." in gold
  at the tap, and "You should know it's one where <topic>." in cream as its poster
  grows, `<topic>` the first of the viewer's topics it trips, in the order
  DoesTheDogDie lists its votes. It then
  behaves as any pick: `Show me another`, "‹ Back" and, where offered, "Something
  wrong?" work.
- **Every pick is checked.** No request can ask to skip the check: a pick for a
  viewer with topics looks its film up whatever the request carries.
- **Turned-away films.** Every film a pick turns away is reported to the page
  and joins the visit's seen list. The page sends the 200 most recent.
- **Unchecked.** The film is shown with a note, and DoesTheDogDie's credit
  beside it, when any of these holds:
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
  DoesTheDogDie ↗", beneath its note and the credit, opening a new tab. The reply
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
  is known by an anonymous cookie, `matinee_device` (`HttpOnly`,
  `SameSite=Lax`, 400 days, `Secure` over HTTPS as the token cookie is), issued only to a viewer with topics. Devices idle
  for an hour are forgotten.
- Every request names Matinee in its user agent, because DoesTheDogDie refuses
  the default one.

## 10. Notes

A note is a viewer's complaint about a pick, kept for whoever runs Matinee. It
changes nothing any viewer is shown.

- The note action is offered only on a pick that came through a tree. It is
  "Something wrong?", in the pick's foot (section 12), and in My profile's poster
  overlay for a film whose kept walk came through a door. It opens the pick's
  panel, headed "Something wrong?". The film always belongs to a profile this device
  holds, so the panel never asks for a name.
- The panel opens with "This goes to whoever runs Matinee as a note. It changes
  nothing you are shown.", then "How you got here" over the door and the
  viewer's answers in order, ending with "Just pick one!" when that ended the
  questions. These are the walk the film was drawn under, taken when the film
  was shown: a film brought back from the Back panel is noted under the walk it
  first came from. In the overlay they are the walk kept with the film in the
  newest run that showed it (section 7.6).
- The panel asks "What's wrong? Tick any, or just tell me below." over four
  ticks, offers an optional "Tell me more" box of at most 500 characters, and a
  "Save" button at the panel's foot. The first three say what was wrong with
  where the film was sorted, and only one of them stands: ticking one unticks
  the other two, and any may be unticked. The form is built once per pick, so
  closing the panel and opening it again keeps what the viewer chose and wrote:
  - "Not <genre> at all", which asks "Where does it belong?". It offers every
    tree except the one that offered the film, the kids tree included, and the
    note keeps every tree ticked;
  - "<Genre>, but not the kind I asked for";
  - "The right kind, just not a good pick";
  - "The tags don't fit it", which stands with any of the three.

  A note says at least one thing: a sort choice, the tags, or words in the
  box. "Save" with none of them says "Tick what's wrong, or tell me below." and
  saves nothing; the server refuses such a note (400 `refused`).
- Every note, once saved, saves a note and nothing else: the profile, the film, the tree,
  the sort choice (or none), whether the tags are wrong, the answers that led to the pick in words, whether "Just pick
  one!" ended the questions, the comment and a UTC timestamp. A note needs a
  held profile. A film Matinee does not offer now is refused (400 `refused`).
  Its answers are resolved against the tree when it is saved; a tree that no
  longer exists, or an answer the tree no longer has, as after an update for a
  note made from My profile, is refused in words (400 `walk_gone`, "My
  questions have changed since I showed you this film, so I can't take a note
  on how you got there."), and the panel's "Save" stays disabled, since that
  note can never be taken. Where the film belongs is kept only on a "Not <genre>
  at all" note, and only as trees the catalogue holds other than the one that
  offered the film; anything else is refused. Naming a tree changes nothing any
  viewer is shown.
- A note made on the pick names its run (section 7.6), whose key is checked
  before anything is kept (`bad_run`). The note and its film's `reported` mark
  in that run are kept in one write: a failure keeps neither, so the history
  never disagrees with the notes and a retry files no second note. A note made
  from My profile's overlay names no run and marks nothing.
- Once the note is saved the form and "Save" leave the panel, and it says "Thanks for that. It's gone to
  whoever runs Matinee." in gold and, for a note with a sort choice, "If they agree, it moves for everyone." in
  cream; a note without one moves no film, so it says the gold line alone. The
  About page's paragraph on films in the wrong place says the same: a viewer
  can say where a film fits best through "Something wrong?",
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
    that ended the questions), what was ticked in the panel's own words with
    where the film belongs (by door label) and whether the tags don't fit, or
    "(nothing ticked; see the comment)", and the comment, then the count of
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
| GET | `/static/…` | scripts, styles, self-hosted fonts, icons, pails, avatars, the locked door's art, My profile's curtains and film cases, manifest (`Cache-Control: no-cache`, so a deploy is never seen half-applied) |
| GET | `/img/{kind}/{tmdb}/{size}` | a poster or backdrop: from the media server for a film the library holds, else from TMDB's image server through Matinee |
| GET | `/api/pictures` | the image source, and under `tmdb` the TMDB poster path of every live film that has one (section 11.5) |
| GET | `/api/film/{tmdb}?door=` | one film's card (`src/matinee/web/app.py::FilmCard`): `tmdb`, `title`, `year`, `runtime_min`, `synopsis`, the pick's link (`link`, and `link_to`: `seerr` or `tmdb`), under the `tmdb` image source its TMDB backdrop path (`backdrop_path`, else null), `rank` (the film's rank line among the films behind `door`, the tree its pick came through, or overall without `door`; under the vote floor or without a TMDB score, why its rank is not clear; null for a tree with no rank word; section 2.8), `standing` (the rank's band share and basis, such as "Middle 20% by TMDB audience rating", or under the floor where its few votes place it; null whenever `rank` is) and `tags` (up to four, strongest first; empty for a film the genome does not cover). A `door` that names no tree is refused (400 `refused`) |
| GET | `/api/door` | the film count, every profile (marking those this device holds), the avatars offered, whether a DoesTheDogDie key is set, and `posters_from` (`server` or `tmdb`) |
| POST | `/api/profiles` | create a profile and issue this device a token |
| POST | `/api/profiles/{id}/open` | open a profile by PIN, or at once when held or PIN-less |
| PUT | `/api/profiles/{id}/topics` | replace a held profile's DoesTheDogDie topics; only with a DoesTheDogDie key |
| PUT | `/api/profiles/{id}/avatar` | set or clear a held profile's avatar |
| PUT | `/api/profiles/{id}/name` | rename a held profile (section 7); answers it as the page sees it |
| DELETE | `/api/profiles/{id}` | delete a held profile and everything it keeps; answers its name |
| GET | `/api/profiles/{id}/settings` | a held profile's topics, tailoring settings and welcome mark (section 7.3) |
| PUT | `/api/profiles/{id}/settings` | change any of a held profile's tailoring settings |
| POST | `/api/profiles/{id}/welcomed` | mark a held profile as having seen the welcome |
| GET | `/api/languages` | the languages the film table holds, with their film counts, most first |
| GET | `/api/profiles/{id}/ratings` | a held profile's ratings of films in the film table, newest first (section 7.4) |
| PUT | `/api/profiles/{id}/ratings/{tmdb}` | save or change a held profile's rating of a film Matinee offers now; `run` names the pick's run |
| DELETE | `/api/profiles/{id}/ratings/{tmdb}` | clear a held profile's rating of a film and its short review |
| PUT | `/api/profiles/{id}/ratings/{tmdb}/review` | save, change or clear the short review of a film the held profile has rated |
| GET | `/api/profiles/{id}/shared/{tmdb}` | the household's shared ratings of a film, newest first, for a device holding the asking profile |
| GET | `/api/profiles/{id}/hidden` | a held profile's hidden films in the film table whose hide has not ended, newest first (section 7.5) |
| PUT | `/api/profiles/{id}/hidden/{tmdb}` | hide a film Matinee offers now for a length; `run` names the pick's run |
| DELETE | `/api/profiles/{id}/hidden/{tmdb}?run=` | bring a hidden film back; "Undo" on the pick names its `run` |
| POST | `/api/profiles/{id}/runs/{run}/films` | keep a film a held profile's run showed, with the walk that reached it (section 7.6) |
| GET | `/api/profiles/{id}/runs` | a held profile's kept runs, newest first |
| GET | `/api/topics` | DoesTheDogDie's topic list, with its credit; only with a DoesTheDogDie key |
| GET | `/api/quips` | the pick's lines and their caps (section 2.7) |
| POST | `/api/first` | the source question while it is asked and no `source` is sent (`source`), the first question for this viewer within the source, the pool behind it, and whether this viewer's picks are checked against DoesTheDogDie (`checked`); `fallback` while a `held` or `new` answer cannot be kept (section 2.0); `unsettled` when a profile's settings leave no door (section 6) |
| POST | `/api/walk` | the next question and the pool, given a tree and answers; `fallback` as for `/api/first` |
| POST | `/api/pick` | one checked film from the pool the answers leave; `fallback` as for `/api/first` |
| POST | `/api/notes` | keep one note on a pick for a held profile; `run` names the pick's run, where the film is marked reported (section 10) |

The routes for what a profile keeps take and give these shapes. Each is keyed
by the class it comes from, in `src/matinee/web/mine.py` except `NameChoice`,
which is `src/matinee/web/common.py::NameChoice`; the rename route answers
`src/matinee/web/common.py::Seat`. A time is ISO 8601 in UTC, and `run` is
null or a run's key wherever it appears. Changing the settings or marking the
welcome answers `SettingsOut`:

```json
{"ScoreIn": {"score": 5, "run": null},
 "ReviewIn": {"review": "Still the best shark."},
 "RatedOut": {"tmdb": 578, "score": 5, "at": "2026-10-14T19:02:11+00:00", "review": "Still the best shark.",
              "title": "Jaws", "year": 1975},
 "Cleared": {"tmdb": 578, "cleared": true},
 "SharedOut": {"name": "Pat", "avatar": "popcorn", "score": 4, "review": null},
 "HideIn": {"length": "6m", "run": null},
 "HiddenListedOut": {"tmdb": 578, "length": "6m", "at": "2026-10-14T19:02:11+00:00",
                     "until": "2027-04-14T19:02:11+00:00", "title": "Jaws", "year": 1975},
 "ShownIn": {"tmdb": 578, "tree": "thriller", "answers": [{"question": "kind", "option": 0}], "rushed": false},
 "KeptOut": {"tmdb": 578, "run": "<run key>"},
 "RunOut": {"began": "2026-10-14T19:00:02+00:00",
            "walk": {"tree": "thriller", "answers": [{"question": "kind", "option": 0}],
                     "says": ["<the door's words>", "<the answer's words>"], "rushed": false},
            "films": [{"tmdb": 578, "title": "Jaws", "year": 1975, "mark": "rated",
                       "walk": {"tree": "thriller", "answers": [{"question": "kind", "option": 0}],
                                "says": ["<the door's words>", "<the answer's words>"], "rushed": false}}]},
 "SettingsIn": {"floor": "middle", "languages": ["en", "fr"], "rated_out": 2, "sharing": true},
 "SettingsOut": {"topics": [], "floor": "middle", "languages": ["en", "fr"], "rated_out": 2, "sharing": true,
                 "welcomed": true},
 "LanguageOut": {"code": "en", "films": 9120},
 "NameChoice": {"name": "Pat"}}
```

The outer keys only name each shape here; no request or reply carries them.
`RatedOut`, `HiddenListedOut`, `SharedOut`, `RunOut` and `LanguageOut` are one
entry of their lists; a single rating answers `RatingOut` and a single hide
`HiddenOut`, the same less the title and year. A field `SettingsIn` leaves
out, or sends as null, stays as it is, and `languages: []` is "Any language". `mark` is
`rated`, `hid`, `reported` or null. `until` is null for a hide for good. A
film's walk has a null `tree`, no answers and no words before any door. A request
whose top-level shape carries a field it does not name is refused (422); the
entries inside `answers` are not checked for extras.

### 11.2 What the browser may name

- **A film** only by a TMDB id in the current live film list. Any other id
  answers 404 before any request leaves for the media server.
- **A door**, on the film card, only as a tree's name; any other is refused.
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
  trees a note says a film belongs in 32; a run's key 64; a short review
  1,000 (the store refuses one past 100 in words, section 7.4); a hide's length
  8; a rating floor 20; ticked languages 200. A pick with no tree may carry no
  answers, and neither may a film a run showed. A word given at the door over
  200 characters is wrong
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
| `walk_gone` | 400 | a note whose door or answers the catalogue no longer holds, as after an update for a note made from My profile (section 10) |
| `profile` | 400, 401, 403, 404, 409 or 423 | a profile rule refused the request; the body adds `code` (`bad_name`, `bad_pin`, `bad_avatar`, `not_held`, `name_taken`, `full`, `no_profile`, `wrong_pin`, `locked`, and, each 400, `bad_score`, `bad_review`, `not_rated`, `bad_length`, `bad_run`, `bad_setting`, `bad_language`; section 7) |

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

[Design standards](../../DESIGN_STANDARDS.md) owns shared visual requirements,
token roles and the two control families: a letterbox chooses something; an
action does something. The stylesheet's `:root` and component rules define
reusable token values. This section owns screen composition, wording, action
assignments and behaviour. Matinee's lines are set in Big
Shoulders Display, other text in DM Sans. Both fonts are self-hosted with their
OFL licences. All displayed text is in sentence case, except that a cream
part carrying on its gold part's sentence after a comma keeps its first letter
as written. A phone is a viewport 600 px wide or less. The page declares
itself dark only (`color-scheme: only dark`, in its head and its stylesheet),
so a browser's forced dark mode, such as Samsung Internet's, leaves its
colours as they are.

### Shared action assignments

These assignments apply wherever the named action appears. The design standards
own each accent's visual treatment and meaning; this table owns its use for the
page's actions. New actions follow those meanings.

| Action | Accent |
|---|---|
| "Find me something to watch" (centred, at the standard size) | gold |
| "Show me the films" (setup note) | gold |
| "Continue" (the name step) | gold |
| "Save and continue" (the topics' tailoring step) | gold |
| "Done" (the languages' tailoring step) | gold |
| "Just pick one!" (the questions) | gold |
| "Roll again" | gold |
| "Just show me what you picked" | gold |
| "Save" (a note) | gold |
| "Show me" (the welcome), "Let's go" (what's new), "Let's find something to watch" (all set up) | gold |
| "My profile" (all set up) | cream |
| "Change my settings" (the empty pool) | gold |
| "‹ Back to picking" (My profile) | gold |
| "Change", "Done" (a setting's row on My profile) | gold |
| "Bring back" (a hidden film) | gold |
| "Show me another" (its thread always drawn, with a faint rose glow) | rose |
| "Delete this profile" (My profile) | rose |
| "More on Seerr ↗", "More on TMDB ↗" (the strip on the pick's poster) | petrol |
| "Read about these on DoesTheDogDie ↗" | petrol |
| "Look it up on DoesTheDogDie ↗" | petrol |
| "Start over" | cream |
| "‹ Back" (a question screen's way back) | cream |
| "‹ Back" (the pick) | cream |
| "Never mind", "That's not me" | cream |
| "Skip" (a tailoring step) | cream |
| "Not now" (the welcome) | cream |
| "Switch profiles" (My profile) | cream |
| "Try again" (a problem screen and the topic list) | cream |
| "Something wrong?", "Rate it", "Hide film" | cream |
| The turned-away pick's reveal button | cream |
| "Back" (About) | cream |

### Screen composition

Matinee's line and choices stay anchored while the line types and the choices
appear. This table gives their composition; the detailed screen contracts below
supply dimensions, responsive exceptions and interaction behaviour. The pick's
reporting action is "Something wrong?", not the unchecked-content warning. That
warning, DoesTheDogDie's credit and the lookup action follow the synopsis in
the film information area on both desktop and phone.

| Screen | Desktop | Phone |
|---|---|---|
| The locked door | Beside the door, to its left; between the marquee and the door under 1000 px wide | Between the marquee and the door |
| The front door and making a profile | A centred column under the marquee, the line left-aligned at its top, tiles or letterboxes beneath | The line under the marquee; letterboxes at the foot of the screen |
| The trigger picker | The left column's top, its explanation and the save actions beneath; the topics in the right column, with the DoesTheDogDie action under them | Stacked under the marquee's lit strip: the line, the explanation, the topics, the actions |
| A tailoring step (at the door, or in the theatre after the welcome) | From 960 px wide, the line, the explanation and the actions in a left column, the answers in the right, as the picker; narrower, one column: the line, the explanation, the answers, then the actions | One column under the marquee's lit strip (at the door) or the top bar (in the theatre): the line, the explanation, the answers, the actions |
| The questions | The line hangs from the top, three lines reserved, letterboxes beneath it | The line hangs from the top; letterboxes at the foot of the screen |
| The pick | The left column hangs from the top: the line, then the rank, the language line, the household's line and the tags, then the note revealing a turned-away film where there is one, then the poster as the link to the film's page, its strip on its foot. The actions sit in the foot bar: "‹ Back", "Something wrong?" and "Rate it" at its left, `Show me another` at its exact centre with "Hide film" beside it on its right, DoesTheDogDie's credit at its right end when the line names one of its topics | The showing scrolls above a fixed foot: the poster with its strip, then the title and year, the rank, the language line, the household's line, the tags and the synopsis. The foot holds the line, then, at its foot, `Show me another` and "Hide film" in one row and "‹ Back", "Something wrong?" and "Rate it" in the next, with overflow scrolling inside it |
| My profile | The pinned menu in a column at the left, the four parts beside it; from 601 to 900 px wide the menu takes its own row above the parts | The page's head (the picture, the name and the ways out), a jump bar pinned to the top of the screen, then the parts |

### Screen behaviour

- **The door.** The marquee stands at the top centre of the screen over the
  poster wall, and nothing else frames it: no booth and no curtains. The
  marquee is one drawing, `static/marquee/marquee-wide.svg` on a desktop and
  `marquee-narrow.svg` on a phone: an art deco stepped crown with a sunburst
  over a free-standing lit sign, with nothing glowing behind it and a dark fade
  across the top of the screen (420 px deep, 260 px on a phone) that lets the
  sign read against the posters. The page lays the drawing in and the drawing
  scales as one piece: 924 px wide at most on a desktop and 374 px on a phone,
  never wider than the screen less 16 px. "Matinee" is the largest thing on
  the sign, gilded and crisp with no glow, over a letter board drawn as the
  letterboxes are, reading "Now showing" and the live film count. Its name and
  its letter board are live text. The bulbs round the sign twinkle while two
  dark bulbs travel clockwise, half a lap apart, one lap every 12 s; the light
  stays inside each bulb's glass. Under reduced motion no bulb darkens or
  twinkles. A window too short for the full marquee scales it down: to 0.8
  under 820 px tall and 0.45 under 700 px tall on a desktop, and to 0.75 under
  640 px tall on a phone. When the drawing cannot be fetched or read, the
  marquee shows "Matinee" as plain gold text and a warning goes to the browser
  console.

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
  the drawing shrinks toward its top and fades while its room folds away
  (0.6 s), and a lit strip fades in in its place: a dark band 374 px wide at most with a row of 24 bulbs chasing along each long side
  and the letter board between them, with no name. The drawing returns when
  the picker closes. The
  marquee stays on screen until the viewer goes in or opens
  About.
  - **The locked door.** The page asks `GET /api/admission` before anything
    else. When a door word is set and the device has not given it (section
    7.2), it asks nothing more: no film list, poster, count, profile or line is
    requested until the word is right. The marquee's letter board reads "Now showing" and "Private
    screening", on one row on a desktop and the second under the first on a
    phone, and beneath it, in place of the poster wall, stands a wall of
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
    screen's width, and the wall scrolls when they do not fit; the foot with "About Matinee" is the door's last row, below the wall, so tiles
    never pass under it. A desktop window under 760 px tall shows 100 px marks
    and a 40 px line. The "+ New" tile's square is dashed and holds a "+",
    with "New" beneath it.
  - A device holding a profile token sees "Good to see you again." in gold and
    "Who's watching?" in cream. A device holding none sees "Come on in." and "Pick your
    seat, or introduce yourself and I'll find you something to watch." When no
    profile exists the line is "Come on in." and "Nobody has a seat yet. Introduce
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
    the tailoring offer: "Want me to tailor picks to you?" in gold and "It's a
    few quick questions." in cream, over two letterboxes. "No, just show me
    movies" goes to the last step with every setting at its default. "Yes,
    let's do it" walks the tailoring steps, one screen per setting, in My
    profile's order:
    1. With a DoesTheDogDie key (section 8), the trigger picker, headed "Scenes
       you don't want to see" over My profile's explanation for that row, with
       "Save and continue" and "Skip";
    2. "How well rated a film needs to be";
    3. "Language preferences", only when the film table holds any language;
    4. "Films you've already rated";
    5. "Sharing your ratings with your household".

    Each step after the picker types its setting's title in gold and, where the
    setting asks one, its question in cream, with its explanation in body type
    beneath and its answers as letterboxes, the current one checked and ringed
    in gold: My profile's words throughout (below). A single answer saves and
    goes on; the languages are ticked and saved with "Done". Every step offers
    "Skip", which keeps that setting as it stands, and a refused save says why
    on the step and stays. Last, "You're all set, <name>." over a centred
    "Find me something to watch" action, which goes in to the first question.
    A profile made now has seen the welcome (section 7.3) whichever answer the
    viewer gives. While a step is up the marquee stands as its lit strip on a
    phone, as for the picker, and at 0.75 of its size in a desktop window 800 px
    tall or less, so a ladder of answers has room.
- **Going in.** Every answer at the door that leads into the theatre asks for
  the walk's first screen at the tap, and a door is entered once: a second tap or
  Enter changes nothing. The door's words and its foot fade out
  (0.3 s), and the rest of the marquee fades over 0.55 s while it lifts 110 px
  and shrinks to 0.93 of its size over 0.8 s. Meanwhile "Matinee" flies from
  the sign's letters to the corner mark's place at the top left, shrinking to
  the mark's lettering, over 0.9 s; its copy lies letter for letter over the
  drawing's lettering as it leaves. It lands letter for letter on the corner
  mark's own name, placed as the top bar will place the mark with the viewer
  beside it. When the theatre's screen is built, the mark fades in around the
  landed name (0.3 s) and the name then gives way to it.
  The poster wall stays on screen throughout. No transition on the page passes
  through black. The walk's first screen (the source question, or the doors
  when it is not asked) types once the name has landed and the screen has
  arrived; a landing that never reports counts as landed 0.95 s after the
  flight began. When the viewer's pool differs from the door's, the
  wall re-sorts in place as after any answer. From a phone's lit strip, which
  draws no name, the name stands at the wordmark's place at once while the
  strip lifts, and the question still waits the flight's time. Under reduced
  motion the change is instant. "Switch profiles", from the profile menu or My
  profile, and a profile deleted on My profile return to the door with the
  marquee already in place and lit; the name does not fly back.
- **The wordmark.** Inside the theatre the top bar's wordmark is the corner
  mark, `static/marquee/mark-corner.svg`: the marquee's crown over a small lit
  sign with "Matinee" across it, 64 px tall on a desktop and 40 px on a phone,
  as a picture named "Matinee". It is a
  link: activating it, by click, tap or keyboard, does what `Start over` does,
  back to the walk's first screen as the same viewer. On the setup note, and on
  a problem screen reached before going in, where there is no viewer yet, it
  goes back to the door, by way of the setup note when that has more to say. On
  the front door the marquee stands in its place, so there it does nothing.
- **Scrims.** Every piece of text standing on the poster wall stands on a
  scrim meeting the minimums in the design standards: the current treatment is
  a feathered dark patch, the page base at 92 per cent across the text's whole
  block, corners included, fading to nothing about 40 px beyond it with
  no edge. That covers Matinee's lines (each of its two parts), the countdown,
  notes, status lines, counts, footnotes, the tile names, the film's title,
  year and synopsis, the pick's rank and the household's line under it, and the
  text of a tailoring step and the welcome's what's-new screen; the pick's tags stand on their own
  backing (below). The pick's panel is a solid surface, so its text needs none.
  Every scrim paints behind all of a screen's text and controls. No scroll box
  cuts a scrim: the door's column (the words and tiles that scroll under
  the marquee) keeps 40 px of room above its first line, and
  the phone pick's foot fades its top and its foot over 20 px, so a scrim at
  either end fades with its text. The locked door's greeting keeps its own scrim
  on subway tile.
- **Bands.** Every screen over the poster wall has a dark band at the top and
  at the foot, as `DESIGN_STANDARDS.md` 6.3 sets them: behind the top bar with the
  wordmark and the viewer, and behind the foot with its way back or "About
  Matinee", or on the pick its actions. The top band lies behind everything on the screen and scrolls away
  with the top bar. The pinned foot carries its fade inside its own
  height, so nothing rests under the fade and what scrolls beneath fades under
  the band. A desktop pick is the exception: the foot band is drawn up over the
  pick's last stretch, so the pick ends one gap above the foot bar and its last
  stretch fades under the band. On the
  door's screens the marquee's fade is the top band, and the foot band lies
  behind the door's last row, and what scrolls in the door's column fades out
  over its foot padding; going in, the foot fades and the band stays.
  A problem screen carries "About Matinee" at its foot. The locked door has
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
  source answer's reply in gold and "What are we in the mood for?" in
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
  Its foot band carries "About Matinee".
  (`src/matinee/web/static/js/main.js::setupNote`, `saidSetup`)
- **The stale-data warning** (section 5.2) stands in a strip across the top of
  the screen, above everything, from the first screen after admission: the
  server's sentence in 14 px bold dark type, centred, on a rose ground. The
  screen starts beneath the strip, however many lines it wraps to. The page
  reads the warning with the setup note, so the strip comes and goes when the
  page loads or returns to the door. Before the door word is given, the page
  asks for neither.
  (`src/matinee/web/static/js/main.js::showWarning`)
- **The fallback notice** (section 2.0), the library's and Seerr's, stands in
  the same strip, after the stale-data warning when both stand. Each walk response sets it: one carrying
  `fallback` shows it, one without takes it down and leaves the stale-data
  warning as it was.
  (`src/matinee/web/static/js/main.js::showFallback`)
- **The viewer.** Inside the theatre the top bar holds the wordmark at the left
  and the viewer at the right: the profile's mark in a 40 px rounded square and
  its name in the wordmark's face, smaller, in cream, on a dark backing so it
  reads over any poster. Activating either, by click, tap or keyboard, opens the
  profile menu, which holds three plain rows, in this order: "My profile" (the
  viewer's own page, below), "Switch profiles" (back to the front door's
  tiles, the marquee already in place and lit) and "About Matinee" (the About
  page, which gives the focus back to the viewer when it closes). The picture,
  the name, the topics and deleting the profile all live on My profile.
  Escape (wherever the focus is), a tap elsewhere, focus
  leaving the viewer, or choosing an item closes it; the arrow keys walk its
  items, round from the last to the first. On a phone the bar is one row: a name of 10
  characters or fewer shows in full, and a longer one shows as initials (the
  first letter of each word, at most three) beside the avatar, or as the
  avatar's own initials when it has none.
- **My profile** is the viewer's own page: a full page over the theatre, which
  stands beneath it as it was, covered and out of reach, never rebuilt or
  paused, so opening it ends nothing, a pick included. Opening it adds one entry
  to the browser's history: "‹ Back to picking", the browser's back, a phone's
  back gesture and Escape (outside a text field) each close it and show the
  theatre as it stood, giving the focus back to the viewer's button. The
  theatre's curtains stand behind at full brightness and never move; the parts
  scroll over them as panels, each headed by a placard in the display face,
  which is used for headings only. The corner mark stands at the top left.
  Everything on the page is the viewer's own (section 7), and nothing on it
  sets or changes a PIN.
  - **The menu.** On a desktop a pinned menu, drawn as a felt letter board,
    follows the scroll beside the parts (scrolling on its own when taller than
    the screen) and holds, from the top: "‹ Back to picking"; the viewer's
    picture; their name; one jump to each part, labelled shorter than the part's
    heading ("How I pick for you", "Your
    ratings", "Hidden films", "Past picks"), the last three with their counts
    (ratings, hidden films, runs kept); "Switch profiles"; and "Delete this
    profile", in rose, at its foot. On a phone "‹ Back to picking" stands
    beside the corner mark, the page's head holds the picture, the name,
    "Switch profiles" and "Delete this profile", and a jump bar is pinned to the
    top of the screen (the phone's labels are shorter again: "How I pick",
    "Ratings" and "Hidden" with their counts, "Past picks" without). Each jump
    scrolls to its part.
  - **The picture** opens the fifteen avatars and "Just my initials" in a row
    of their own beneath the picture and the name. A tap saves the choice, the
    page and the top bar's viewer show it at once, and the row folds; a refusal
    stays and says why.
  - **The name**, marked with a ✎, turns into a text field holding it when
    activated ("Tap your picture or name to change it" beneath it at rest,
    "Enter to save · Esc to cancel" while editing). Enter saves it under the
    rules of section 7 and Escape cancels. A taken name keeps the field open
    with "Someone already goes by that name here. Try another?" beside it; any
    other refusal says why there too. The top bar's viewer shows a new name at
    once. A name longer than 14 characters is set smaller in the menu and wraps
    between words.
  - **"Delete this profile"** asks in place, never in a browser dialog:
    "Delete <name>?" in gold, "Your ratings, hidden films, history and settings
    go with it. Any notes you sent stay with whoever runs Matinee." in cream,
    then "Yes, delete it" (in red) and "No, keep it", which takes the keyboard's
    focus. "No, keep it" puts the action back. "Yes, delete it" deletes the
    profile (section 7), leaves My profile and returns to the front door, whose
    line reads "<name>'s seat is empty." and "Who's watching?" over the tiles;
    a refusal stays and says why. The avatars and the delete question show
    their letterboxes with no glow at rest; each glows on hover.
  - **"Switch profiles"** leaves My profile for the front door's tiles.
  - **The parts**, in this order, each heading with a side line beside it:
    "How I pick films for you" ("Changes apply from your next pick"); "Films
    you've rated" ("Best first. The case around each poster shows how you
    rated it.", or "Best first" on a phone), with one line of body text
    beneath its heading, "Your ratings stay in Matinee for now. We're
    exploring syncing them with services like Trakt in the near future.",
    which no other surface carries; "Films you've hidden" ("I won't pick these
    until the date under each one"); and "Films I've picked for you" ("Your
    last 50 picks, by day. Open a day to see the films.", or "Last 50 picks" on
    a phone). A part with nothing in it says so: "Nothing rated yet. After a
    film, tap Rate it and it lands here.", "Nothing hidden. Hide a film from
    its pick and it waits here until it comes back." and "No picks yet. Once I
    pick something for you, it shows up here." A part whose records cannot be
    read shows as empty, and the page says why once above the parts.
- **How I pick films for you** holds one row for the topics and one for each
  of the four tailoring settings, in this order, the topics row only with a
  DoesTheDogDie key:

  | Row | Its explanation |
  |---|---|
  | "Scenes you don't want to see" | "Choose topics like spiders or needles. Before I show you any film, I look it up and skip it if it has one of them." |
  | "How well rated a film needs to be" | "I compare each film's audience rating with the other films behind the same door, and only pick films that rank this high or better. Films too new or too little-known to have many ratings are always included." |
  | "Language preferences" | "Choose the languages you're happy to watch a film in. I check the audio in your library too, so a film dubbed into your language counts." |
  | "Films you've already rated" | "Rating a film doesn't stop me picking it. Choose which of your ratings mean “don't pick this again”. Loved it? I can still offer it for a rewatch." |
  | "Sharing your ratings with your household" | "If you share, the other people on Matinee in your home see your ratings and short reviews when I pick that film for them. You see theirs either way." |

  A phone shows a shorter explanation for each, as its board does. Each row
  rests with its gold title, the explanation in quieter text, a framed picture
  of its open panel at about a third of its size with the chosen answers
  checked and ringed in gold (a picture holds no control), and "Change" at its
  right. "Change" or the picture opens the panel full size in the row's place,
  and "Change" reads "Done"; one row is open at a time. Every answer and tick
  saves at once, checks the answer, and says "✓ Saved" in gold beneath the
  row's head; the row stays open until "Done" closes it, which takes "✓ Saved"
  with it. There is no Save action. Saves
  reach the server one after another, in the order the viewer made them; a
  refused save says why beneath the row's head, and a refused tick is put back.
  - The rating floor's answers stack best first, each with its share beside
    it: "Well liked or better" (Top 25%), "Above the middle or better" (Top
    40%), "Middle of the pack or better" (Top 60%), "Above the bottom 10%" (Top
    90%) and "Anything" (Every film).
  - The languages ask "I'll only show you films in these languages:" over "Any
    language" and every language the film table holds (section 7.3), as
    letterboxes that toggle, named in the viewer's own language where the
    browser can say it (TMDB's `cn` as "Cantonese", which browsers do not
    name), the browser's own language first and the rest by how many films each
    holds. Only the 15 languages the most films hold show at first, with the
    browser's own and any already ticked; "+ More languages" shows the rest and
    goes. Ticking one turns "Any language" off; "Any language" clears every
    tick.
  - The rated films ask "Stop picking films I gave this rating or lower:" over
    "Loved it!" (marked "Everything I've rated"), "Really liked it", "It was
    ok, I guess", "Didn't like it", "Hated it" and "None, keep them coming",
    stacked best first.
  - Sharing offers "Keep them to myself" and "Share with my household".
  - The topics' panel holds a search ("Search, like spiders or needles"), the
    topics as letterboxes that toggle, and a tally ("3 chosen. Each tick saves
    straight away. The checks are best effort, from votes on
    DoesTheDogDie.com."). "Powered by DoesTheDogDie.com ↗" stands under the
    row's explanation as a small text link. When the topic list cannot be
    fetched, the open panel says so in the server's words. The row's picture
    shows the search and the first ten topics (four on a phone), the chosen
    ones first.
- **Films you've rated** holds one row per rating that has films, "Loved it!"
  first, each naming its rating and how many films it holds, its films newest
  rating first. Each poster stands in its rating's case (gold for "Loved it!",
  then silver, neutral, weathered and distressed for "Hated it"), with the
  film's title on the case's plate, and on a screen wider than a phone the
  viewer's short review beneath it as text. On a phone a row scrolls sideways,
  part of the next case showing at its edge. Posters never move, and every case
  is still but the gold one, whose light comes from within: it shimmers once,
  a soft diagonal band crossing it from bottom left to top right, the first
  time three quarters of it has stood on screen for 0.4 s (cases coming into
  view together start 0.35 s apart, in turns of four), and where a pointer
  can hover it glows softly under the pointer. The light only brightens what
  lies behind it and lays nothing over it, so a poster's dark areas stay dark.
  Under reduced motion it does not shimmer.
- **Films you've hidden** shows each film greyed in a bare case, newest hide
  first, with when it comes back in the viewer's own time, "Back on 14 April",
  with the year when the day and month alone would read as this year's ("Back
  on 14 October 2027" for a year's hide made today), or "Hidden for good", and
  "Bring back" at its foot. "Bring back" brings the film back at once and takes
  it off the part; the count follows and the focus moves to the next film's
  "Bring back", or to the part's heading when none is left, where the empty
  line returns. A refusal says why.
- **Films I've picked for you** stands the kept runs on one shelf per day, in
  the viewer's own time zone, newest first. The newest day is open and every
  earlier day folded. A day's head names the day ("Tuesday 14 October"), counts
  it ("You asked once, 2 films", "You asked 3 times, 9 films"), shows up to six
  of its posters and "Show" or "Hide" with a chevron, and on a desktop what
  each walk asked for; activating the head opens or folds the day. Inside an
  open day each run shows, for each stretch of its films one walk reached,
  "You asked for" and the door's and each answer's words joined by " › ",
  ending "Just pick one!" when that ended the questions (or "Just pick one!"
  alone where no door was chosen), then those films in the order
  shown, each in its case (its current rating's, else bare) and captioned with
  what the viewer did: "You hid it", "You reported it", "You rated it: <the
  answer>" with the film's current rating (a rating since cleared reads as if
  there were none), "You landed on this one" for the run's last film, or "You
  rolled past it". On a phone the day's date stands on a stub inside its head,
  a folded day's date is said to a screen reader only, and a run's films stand
  in a row to swipe.
- **The poster overlay.** Activating any poster on My profile opens one wide
  overlay over the page, a sheet over the whole screen on a phone. Its left
  side holds the film in its case (its current rating's) at the overlay's full
  height, never more than two fifths of its width, with the pick's "More on
  Seerr ↗" or "More on TMDB ↗" beneath. Its right side holds the title and
  year, the rank in plain body type (among the films behind the door of the
  film's kept walk, or overall without one, or when that door has gone), the
  household's line (below), the synopsis, "How you found it:" with the kept
  walk's words or "From what I showed you" for a film no kept run showed, and
  "What you did:" with what its part says of it. At its foot stand "Rate it",
  "Hide film" and, where the kept walk came through a door, "Something wrong?", each
  opening the pick's panel over the right side on a desktop and over the whole
  sheet on a phone. It offers neither "‹ Back" nor "Show me another", never makes
  the film the pick, and what is done there names no run (section 7.6). "Hide
  film" here reads "Matinee won't pick <film> for you until then. You can
  bring it back any time from My profile."; a hide closes the panel and the
  words say "Back on 14 April." or "Hidden for good.". A rating or a hide made
  there redraws the film parts at once. Escape closes an open panel first, then
  the overlay; the × and a click outside it close it too, and the focus returns
  to the poster (to the film's new poster when its part was redrawn, or the
  part's heading when the film left it).
- **The welcome.** The first time a profile without the welcome mark (section
  7.3) enters the theatre, once the walk's first screen stands with its answers
  and the profile's settings have arrived, the page dims but for the viewer's
  button, lit above the dimming, and a line hangs from the button: "New: you
  can now rate films, hide films, and see what I've picked for you.", with
  "Show me", which takes the focus, and "Not now". Everything else is out of
  reach while it stands. Either action marks the profile, so the welcome shows
  once, on any device. "Not now", or Escape, leaves the theatre as it was.
  "Show me" types "Welcome back." in gold over "You could already tell me what
  to steer around. Now you can rate films, hide the ones you don't want, look
  back at what I've picked, and tell me how well rated a film needs to be and
  which languages you watch in." in cream, both as Matinee's line; on a phone
  the second stands beneath the line as a quieter paragraph. Then "Let's go", which walks the tailoring
  steps in the theatre, from the profile's settings as they stand: the topics
  first with a DoesTheDogDie key, with their search, "Save and continue" and
  "Skip", and DoesTheDogDie's credit in the foot band beside "About Matinee".
  After the last step Matinee says "You're all set up." in gold and "You can
  see and change these settings on My profile." in cream, over "Let's find
  something to watch", which goes to the walk's first screen, and "My
  profile", which opens My profile at "How I pick films for you" over it. The welcome does not stand over My profile or an
  open menu, nor once the viewer has gone on from the first screen: it waits
  for the next visit. A settings read that fails shows no welcome. Nothing
  replays it.
- **An empty first question** (section 6). When `POST /api/first` carries
  `unsettled`, the doors' screen says "Your settings leave me nothing to pick.
  Without them, I'd have had N films to choose from." with N the exact count
  ("1 film" for one, thousands separated), over "Change my settings", which
  takes the focus and opens My profile at "How I pick films for you". Closing
  My profile asks for the walk's first screen afresh.
- **The pails.** The gore question shows four pail pictures, spotless to
  overflowing, each with its answer's words beneath it as text.
- **The pick, as a hunt.** From a question screen the question's words fade
  over 0.35 s (at once under reduced motion) while the pick is already being
  fetched. Where the last answer has a reply, it types in gold on the pick
  screen and stays whole for at least 1 s. Then, once any re-sort has ended,
  the drift stops, Matinee's words fade out (a gold nope line, or a line
  saying why a film was turned away, stays), and the wall eases forward to
  the next whole row (0.4 s). The wall then hunts in one, two or three hops,
  drawn at random with weights 1, 2 and 3 in 6. A hop's length is drawn as a
  share of its axis's half-span, the posters from the screen's centre to the
  first one wholly off screen, so it suits a wall of large posters and one of
  small alike: 1.1 to 2 in 1.5 s; 0.9 to 1.8 then 0.15 to 0.6 in 1.05 and
  0.55 s; 0.8 to 1.5, 0.3 to 0.7, then 0.1 to 0.29 in 0.95, 0.7 and 0.5 s,
  pausing 0.3; 0.18 and 0.34; 0.14, 0.22 and 0.34 s after each. Each share is
  rounded to whole posters, at least one, and each hop's longest share is
  shorter than the hop before it can draw. The first hop runs across the
  wall three times in five and down it otherwise; a second hop turns onto
  the other axis, and a third takes either. The landing poster always starts
  off screen: up to 20 plans are drawn for one that lands there, and failing
  that the first hop is stretched to its half-span. A vertical hop goes down the
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
  it rests. It wears its glow through the move and keeps it at rest, at full strength, sized from its resting
  width, with no gap or fade between the two; a rated film's poster, bound for its rating's case, which wears no
  glow, lets it fade over the move instead. The wall stays at 12 per cent behind the resting page.

  At rest the poster is the link to the film's page, opening a new tab: on the
  configured Seerr, or, without a Seerr or while it does not answer,
  `https://www.themoviedb.org/movie/<tmdb>`, for every pick. A strip on the
  poster's foot, 44 px tall and as wide as the poster, names the site in petrol
  words, "More on Seerr ↗" or "More on TMDB ↗", wrapping them when the poster is
  narrow; the link is named for the film, the site and the new tab. The strip
  and the poster's warm outline show once the poster has landed; hovered or
  focused, the outline strengthens to 2 px and never turns petrol. A film with
  no poster to rest shows the strip alone in the poster's place, still the
  link. There is no other link to the film's page on the pick.

  A film the viewer has rated rests in its rating's case, as on My profile
  (section 12): the poster flies into the case's window, which clips it only
  once it has landed, with the title on the case's plate and the strip beneath
  the case, which takes the poster's height. A cased poster wears no warm
  outline or glow, and takes a gold ring when focused. A rating saved from
  "Rate it" on the pick dresses the resting poster in its case at once, or
  changes the case; one cleared undresses it.

  On a desktop the pick takes the room between the top bar and the foot bar,
  ending one gap above the bar; only a window too short for a 160 px poster
  scrolls. The left column hangs from the top of
  the screen: the line, then the rank, the language line, the household's line and the tags, then the note revealing a turned-away
  film where there is one, then the poster above its strip at the column's
  foot, as large as the height left there allows at 2:3 (never under 160 px).
  At rest the line gives up the four lines it reserved, so the rank stands one
  gap beneath its words; a lit fuse keeps them, since its countdown still
  changes the line. The left column takes a third of the row, widened toward
  470 px but never past 38 per cent of it. The backdrop rises on the right,
  fading into the title, year and synopsis, shown without a tap; those details
  scroll inside their own column, fading over their last 32 px, so nothing
  runs under the foot bar. An unchecked film's note, DoesTheDogDie's credit and
  the "Look it up on DoesTheDogDie ↗" action (section 9) follow the
  synopsis, on a phone as on a desktop. A film the library does not hold shows
  exactly as a library film does: the same layout, words and actions.

  The rank stands in Matinee's display face, in cream (30 px on a desktop,
  22 px on a phone), with its standing on a line of its own beneath it in small
  quiet text (13 px, 11 px on a phone). The tags stand beneath it as outlined chips that
  wrap, 16 px, in sentence case, with small corners, each on a dark backing of
  its own (the page base at 92 per cent) in place of a scrim; never filled with
  an accent and never a pill. A film with no tags shows none, and the layout closes up; every film shows a rank line (a film under the vote floor, its own), except under a tree with no rank word.
  Nothing on the pick says the tags are why the film was picked.

  **The language line.** Beneath the rank, a pick whose own language (its
  TMDB original language) the viewer did not tick, and which reached them
  through its library copy's audio in languages they did tick (section 7.3),
  says so: "Original language: Thai" (17 px, cream), then beneath it in small
  quiet text "Your copy has English audio", naming each ticked language the
  copy's audio holds, joined as a sentence ("English, Spanish, and French").
  Languages are named as the language setting names them. The pick reply
  carries it as `heard` (`original`, `audio`); a film in a ticked language of
  its own, a viewer who ticks none, and a film whose own language is unknown
  carry none.

  **The household's line.** Between the rank and the tags stand the
  household's shared ratings of the film (section 7.4), in the household's own
  colour, `--house`, which does nothing else: the first two sharing profiles,
  newest rating first, each as a sentence, "Pat loved it", "Sam thought it was
  ok", never a number, with a ✎ after the name of one who left a short review;
  then "+ N more" when more have shared. On a desktop wider than 1080 px they
  run as one line with "·" between them; narrower, and on a phone, each takes a
  row of its own. Each is a text button, at least 44 px tall to the touch,
  opening the reading panel (below). A film no other profile has shared shows
  no line, and the layout closes up. A failure to read the shared ratings is
  logged and shows no line.

  On a phone Matinee's words keep the foot of the pick screen, 316 px tall,
  which holds without scrolling, from its top, the line (four lines reserved)
  and, at its foot, the actions at the standard size in two rows:
  `Show me another` and "Hide film" in the first, and "‹ Back", "Something wrong?" and
  "Rate it" sharing the second, each sized to its words on one line, so on the
  narrowest phones "Rate it" may take a row of its own. "‹ Back" alone keeps the
  half width it has beside "Something wrong?". The note revealing a turned-away film stands between
  the line and the actions. Beneath the foot the foot band carries only
  DoesTheDogDie's credit, centred, when the line names one of its topics, and
  rises 48 px behind Matinee's words. Only something taller than the foot, such as a turned-away
  pick's reveal or a line longer than its four lines, scrolls inside it. The
  foot's top never moves from the first word of a pick to the
  last, through `Show me another` and the next pick. The space above it scrolls on
  its own, runs to the screen's sides and fades at its top and foot, so nothing
  passes behind the words and the poster's glow is never cut square. The hunt
  lands, and the poster grows, at the middle of that space, not at the screen's
  centre, the camera rising there over the same ease that stops the drift. At
  rest the poster fills that space at 2:3 above its strip; the title and year,
  the rank, the tags and the synopsis follow
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
  28 px and 40 px, with four lines reserved while the pick arrives, so on a
  phone the actions beneath it stay in place from pick to pick (on a desktop
  the resting line gives the reserve up, above). On a first pick Matinee's reply to the last answer
  types in gold, is read for 1 s before the hunt starts, and stays through the
  hunt; the reveal line, dealt to fit beneath it within the combined cap, types
  beneath it in the text colour as the poster grows. While the check runs, its
  line types beneath the reply, and goes once the check is done. A reply that
  self-destructs is the exception: its fuse owns the line. "Just pick one!"
  deals a rush line, which stands in the reply's place by every rule above. On `Show me another` and "Roll again" a nope line
  and a reveal line are dealt together within the combined cap: when a pair
  is over it, the longer line goes back unshown and its set deals the next
  that fits beside the other, then, if the pair is still over, the other is
  redealt the same way, and a set with no line left that fits gives its
  shortest line. The nope line types in gold at the tap and stays through the
  wait and the hunt, and the reveal line types beneath it in the text colour
  as the new poster grows. Where the check turned a film away, its reason
  types in gold in the nope line's place and stays, and only the reveal line
  is redealt to fit beneath it within the cap. The reason names a
  DoesTheDogDie topic, so its credit stands in the foot band before the reason
  starts to type and for the rest of the pick (Credits, below); on the resting
  page a note beneath the line holds the "What were you going to show me?"
  action. A pick with no film speaks no quip; its line types its first sentence in
  gold and the rest in cream.

  `Show me another` asks for the next film at the tap and carries the resting
  poster back from where it rests to its cell on the wall, at the wall's size
  and strength, over 0.45 s while the wall's dimming lifts (at once under
  reduced motion; with no poster at rest the dimming alone lifts over 0.45 s).
  The wall then drifts, and the returned poster rests in its cell, until the
  next film is known; the check's line does not type, and the nope line holds
  the screen. The next hunt starts
  from where the wall stands, by every rule above. "Roll again", after three
  films in a row were turned away, is a new pick: its nope line types in gold
  at the tap, as on `Show me another`, and its check line types beneath it.
  "Just show me what you picked" asks for no new pick, so no check line types.

  An answer in the Back panel, the browser's back, the wordmark, "Switch
  profiles" (from the profile menu or My profile), a confirmed "Delete this
  profile" or `Start over` ends the pick at the tap: the
  hunt stops where it is, the wall drifts again, and the pick changes nothing
  further. A film the hunt placed keeps its cell until the next pool's
  posters take over.

  While a DoesTheDogDie check runs, the page types "Let me check this one against
  your list." and the wall keeps drifting.

  The wall's geometry and re-sort plan, the hop plan and its speed limit, the
  glow colour and the quip deal are modules that touch no page. Their tests
  under `tests/js/` run with `node --test` from `./check.sh`. The page's
  mechanical design rules (`DESIGN_STANDARDS.md` section 9) are held by
  `tests/test_design_standards.py`, which reads the stylesheet and the page
  scripts as text, not this Markdown. They do not measure rendered contrast,
  tap targets or screen geometry. Browser review under the design standards
  verifies those outcomes.
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
  the scorch. "Show me another" and every later pick speak as usual.
- **The pick's foot.** The pick shows no trail and no TMDB credit, at any
  width. Its actions stand in the foot. On a desktop they sit in the foot bar,
  a row kept across the bottom of the screen from the moment the pick screen
  opens, so nothing moves when they arrive: "‹ Back", "Something wrong?" and "Rate
  it" at its left, `Show me another` at its exact centre at every width with "Hide
  film" beside it on its right, its right end empty. From 601 to 1080 px wide
  the bar keeps two rows from the start: `Show me another` centred on the first
  with "Hide film" beside it, "‹ Back", "Something wrong?" and "Rate it" side by side
  at the left of the second, and DoesTheDogDie's credit, where it stands, at
  the second's right end. A phone's
  foot holds the actions under Matinee's line (above). `Show me another` is the
  same size as every other action; it stands out by its rose words, its thread
  drawn at all times and a faint rose glow. "Something wrong?" shows only on a pick
  that came through a door (section 10); "Rate it" and "Hide film" show on every
  pick of a film. After a hide, a plain "Undo" stands in the foot while the
  next pick hunts: at the foot bar's left on a desktop, in the foot on a phone
  (below). A pick with no film (every film left
  trips the list, three in a row did, or the pool is used up; section 9) shows
  "‹ Back" alone in the foot, and its other actions, `Start over` among them,
  beneath the line.
- **The pick's panel.** "‹ Back", "Something wrong?", "Rate it", "Hide film" and
  the names on the household's line open one shared panel; `Show me another`
  never opens one. On a desktop it stands over the left column, from one gap under the
  top bar down to the foot bar, always at that full height whatever the column
  holds, and is placed again when the window changes size; the left column is
  not drawn beneath it. On a phone it stands over everything under the top
  bar, to the screen's edges and foot; a window that narrows to a phone's width
  closes it, while a phone's own resizing, as its keyboard opens, leaves it
  open. It is a solid panel headed by the action's name in Matinee's
  display face, in gold, with a × at its top right; its contents scroll inside
  it when taller. The ×, Escape, a tap or click outside it, and the same action
  again each close it. A tap outside it on a button or a link closes it and
  does that button's or link's work at once, so `Show me another` with a panel
  open draws the next film; a tap on anything else outside it closes it and
  does nothing else. My profile's poster
  overlay opens the same panel over its own words (above).
  Opening another action's panel replaces it. While it is open the parts it
  covers are out of reach of the keyboard. Focus moves into it as it opens, to
  its first control (else the ×), and returns to the action that opened it as
  it closes; that action shows its thread while its panel is open. On a
  desktop the panel does not cover the foot bar. A panel opens with its explanation at 18 px, the
  synopsis's size; its lists are plain rows that light faintly under the
  pointer and show the gold focus ring, and a section of a list is named in
  quiet text.
- **The Back panel.** "‹ Back" opens the panel headed "Go back to…". It holds,
  from the top:
  - under "Change an answer", every answer of the walk in the order given, each
    an outlined row with a gold "‹" at its left, its question, and the answer
    beneath in quiet text (14 px), so the row reads as the question it returns
    to: the source answer
    when the source question was asked, the door, then each later answer. A
    pick that "Just pick one!" made before any door lists only the answers
    given before it. With no answer to list, neither the rows nor the heading
    show. A tap on a row
    leaves the pick and asks that question again, forgetting that answer and
    every later one: the source answer asks the source question again, the door
    shows the doors (with the source answer's reply), and a later answer asks
    its question again;
  - at the panel's foot above `Start over`, under a 3 px gold rule when answers
    are listed above it, "Shown this run · <N> films" ("1 film" for one), then
    every film the run
    has shown on screen, newest first, each a row with its small poster
    (34 by 51 px, a plain card when the picture fails), title and year. The
    film showing now is marked "Showing now" and does nothing. The list has no
    limit; it is three rows tall and scrolls on its own past them, its scrollbar
    showing, while the answers and `Start over` stay in place. With no film shown yet the section does not show;
  - `Start over` at the panel's foot.

  A run starts when the viewer goes in from the door. `Start over` (in the
  panel, beneath a pick with no film, or on a question screen) and the wordmark
  end it and empty the list; changing an answer or the door keeps it. Each film is held once, as it was shown on
  screen: a film shown again moves to the newest place. A film the check turned
  away unseen is never listed. The panel's list lives in the page alone, so a
  reload empties it. The profile's history (section 7.6) is kept apart, on the
  server, under the run's key, which is new each time a run starts: each film
  is sent to it as it comes to rest on screen, a film brought back included,
  and never a film the check turned away, even one the viewer asked to see. A
  failure to keep one is logged and the pick goes on.

  A tap on another film brings it back as the pick, without asking for a new
  pick and without asking DoesTheDogDie anything: the resting poster goes back
  to the wall as on `Show me another`, no hunt runs (the wall cuts straight to the
  film's poster, which brightens and grows as on any pick; its line is not
  held for reading first), and the film shows with the line it rested
  with (none when a fuse burnt it away), DoesTheDogDie's credit in the foot band
  when it stood there, its content note and lookup action when it had them,
  and the door and walk it was first drawn under, so its rank counts among that
  door and a note on it records that walk. Never the film a check turned away.
  Its details, rank, tags and pictures load as on any pick, and it is a pick
  like any other: `Show me another` draws the next film as usual.
- **"Rate it"** opens the panel headed "Rate it": "Seen <film>? Your answer is
  kept on My profile, where you can change it.", then the five answers stacked
  best first, "Loved it!" at the top, the viewer's current one checked; then
  "Short review (optional)" over a three-line box ("This movie will melt
  your brain" until written in), with no Save of its own. A short review is
  one line: a line break typed or pasted into the box becomes a space. An answer saves at once
  and says "Saved. Add a short review if you like.". The field waits for a
  rating, inactive until the film has one. It saves itself one second after
  typing stops, on leaving the field, and on Enter, one save at a time and never
  a text already saved; "✓ Saved" (or "✓ Cleared" when emptied) then shows at
  the box's bottom left until typing resumes. It holds the
  viewer's short review when the panel opens, so it can be changed or cleared.
  It counts as the store does (section 7.4) and never takes a 101st character:
  its bottom right always says how many are left ("12 left"), and a keystroke past
  the limit gives its edge a thin rose line that fades, shakes it (not under
  reduced motion) and shows "Short and sweet, please. About 15 words.", which
  fades in and out. A refusal says why in the panel. A rating made here names
  the run, where the film is marked rated, and the household's reading panel
  shows it at once as "My review". The words "note" and "remark" never name a
  short review.
- **"Hide film"** opens the panel headed "Hide film": "Matinee won't pick
  <film> for you until then, and rolls again now. You can bring it back any
  time from My profile.", over "3 months", "6 months", "1 year" and "For good",
  none chosen. A choice hides the film for that long (section 7.5), marks it in
  the run, closes the panel and rolls again as `Show me another` does, taking no
  step of the browser's history; a refusal says why in the panel. While the
  next pick hunts, a plain "Undo" stands in the foot and takes the focus; it
  fades as the hunt comes to rest, just before the next pick fills the foot.
  "Undo" brings the film
  back, gives it back the mark its run held before, ends the roll and shows the
  film again as the pick, as the Back panel brings one back. An "Undo" that
  fails is logged, and the film stays hidden until brought back from My
  profile (known gap 19).
- **The reading panel.** A name on the household's line opens the panel
  headed "Household reviews" on that profile's rating, and "+ N more" on the
  first one listed. A card shows the profile's picture, name, its rating as a
  sentence ("Pat loved it", "You loved it" for the viewer's own) and its short
  review, quoted, as text. Beneath, under "Others in the house who shared a
  rating", stand rows for "My review" first, the viewer's own, which reads
  "You haven't rated this one yet." when they have not, then every profile that
  shared one, newest first; activating a row shows its card. The focus starts
  on the row the card shows. My profile's poster overlay offers the same panel.
- **The browser's back on a pick.** While a pick is on screen the page holds
  one history entry at its own address, as About does, and an open panel holds
  one more above it, added by the tap that opens it. The browser's back, or a
  phone's back gesture, with a panel open closes the panel and nothing else.
  With no panel open it steps back one answer. From a pick "Just pick one!"
  ended early, it goes to the question that pick left. Otherwise it goes to the
  question last answered; to the doors where the walk holds a door and no
  answer, or a source answer and no door; and to the walk's first screen where
  it holds neither. A question screen holds no entry, so a further back
  leaves the page. With About
  open over a pick, back closes About alone. Leaving a pick or closing its panel
  any other way takes their entries back off, so a later back never lands on a
  pick or panel that has gone, and a reload starts with none.
- **Credits.** The acknowledgements live on the About page: TMDB's notice and
  logo, the MovieLens citations and DoesTheDogDie's credit (section 14). No
  screen carries a TMDB credit line. The link to the About page is named "About
  Matinee" on every screen: inside the theatre it is the profile menu's last
  item; on the door, the setup note and a problem screen, which have no profile
  menu, it sits at the bottom middle (13 px), and so it does too on the
  theatre's tailoring steps, the welcome's what's-new screen and an empty first
  question. Where DoesTheDogDie's data shows
  (section 14), "Powered by DoesTheDogDie.com" shows too, linked, as its terms
  require. On the trigger picker, while it holds DoesTheDogDie's topics, it
  stands at the door's foot, at the bottom right on a desktop (13 px) and
  centred beneath "About Matinee" on a phone (11 px); on the theatre's topics
  step it stands in the foot band beside "About Matinee". On My profile it is a
  small text link, "Powered by DoesTheDogDie.com ↗", under the explanation of
  "Scenes you don't want to see".
  On the pick it stands in the foot band, on the band, wherever Matinee's line
  names one of its topics: at the foot bar's right end on a desktop (13 px),
  centred beneath Matinee's words on a phone (11 px). Those lines are the
  reason a film was turned away, the three-in-a-row line, the trip of a film
  shown after three in a row, and a film brought back whose line was one of
  these. It is on screen before such a line types and stays for the rest of the
  pick. The exhausted-pool and used-up lines name no topic and carry no credit.
  An unchecked film's note at rest, which stands on the scrim, carries it
  directly after the note. An installation without a DoesTheDogDie key shows the
  credit nowhere on the pick. Every other door screen, a pick showing none of
  that data, and a question or problem screen leave it off. Nowhere on the wall carries it.
- **About.** A screen inside the page, with no address of its own and no
  server route. It opens over whatever screen is showing, as a centred dark
  panel 80 per cent opaque over the poster wall, 1040 px wide on a desktop and
  the screen's width less a 16 px gutter each side on a phone, with no sideways
  scroll. The screen underneath, its foot included, is hidden, never
  rebuilt or paused, so only the posters and the screen's two bands show
  through (Bands, above); it shows again exactly
  as it stood when About closes. The corner mark stands at the theatre
  wordmark's place, a button named "Close About": fixed from 1400 px wide up, and scrolling away with the page
  below that so it never sits over the text. About scrolls as a page when the panel
  is taller than the screen. "Back" at its top, the corner mark, the browser's Back, a phone's back gesture
  and Escape each close it and return the focus to what opened it ("About
  Matinee" at the foot, or the viewer's button for the profile menu's item): opening it
  adds one history entry at the same address, and a second Back leaves the page
  rather than reopening About. The title is 68 px, the lead 23 px and the
  paragraphs 19 px (on a phone the title is at most 13 per cent of the screen's
  width, the lead 20 px and the paragraphs 17 px); section headings are gold,
  in the display face. The copy, in order: a lead; "Why it exists", whose last paragraph says a
  viewer can tell Matinee where a film fits best through "Something wrong?" and
  that a note the operator agrees with moves the film for
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
  standalone; start URL `/`; icons at 192 and 512 px, drawn from the marquee's crown on a dark rounded tile,
  and a separate 512 px maskable icon whose crown sits inside the central 80 %;
  the browser tab shows `static/icons/icon.svg`, and the iOS home screen the
  maskable art at 180 px)
  lets the page install to a home screen. There is **no service worker.**
  Nothing is cached for offline use.

## 13. Deployment

- **One server process, one worker.** Every DoesTheDogDie limit, hold and
  remembered item id lives in the process (known gap 7). A second worker would
  double every limit. The server's one rebuild process runs beside it
  (section 5.1).
- **The image** (`Dockerfile`) runs on Docker's official `python:3.13-slim`,
  pulled from its ECR Public copy (`public.ecr.aws/docker/library`), which does
  not turn away CI builds as Docker Hub's anonymous limit does. It installs the
  package editable, so it finds `data/` beside `src/` as a checkout does. It
  runs as an unprivileged user (uid 1000), with `uvicorn --factory
  matinee.web.main:build --workers 1` on port 8000, no server header and no access log, so no visitor's address is logged. It
  trusts forwarded headers from any address, so it must sit behind a reverse
  proxy. The image carries `tools/`, from which the server runs the nightly
  rebuild.
- **`compose.yaml`** runs the published image
  (`ghcr.io/ivegonetoplaid/matinee:latest`) once: the server on port 8000,
  with its rebuild inside, reading `.env` and mounting `./state` at `/state`.
  It needs no editing and no checkout beside it; `./state` is ignored by git
  and kept out of the build context.
- **Releases.** Publishing a GitHub release tagged `vX.Y.Z` runs
  `.github/workflows/release.yml`: `./check.sh` must pass, then the image is
  built and must start and serve its page on an empty data folder, natively on
  both amd64 and arm64. Each machine then pushes the image it tested to GHCR
  as `X.Y.Z-amd64` or `X.Y.Z-arm64`, and the two are joined under `X.Y.Z`,
  `X.Y` and `latest`, so what ships is what was tested. Pull requests run the
  same checks and starts without publishing. No step downloads from Docker
  Hub, whose anonymous limit and outages failed CI at random. While the version is 0.x, a release that changes only `Z` needs
  no steps from an installation; one that changes `Y` may, and its release
  notes say so. `pyproject.toml` holds version `0.0.0` in the repository; the
  release writes the tag's `X.Y.Z` into it before building, so the image
  carries the release's number and nobody keeps the file in step.
  The image carries `LICENSE` and `README.md`, for the credits and terms of
  what it redistributes.
- **State** is one directory mounted at `/state` (`DATA_DIR`). It holds
  the film table (`films.sqlite`, and `films.sqlite.kept` while a rebuild
  runs), Matinee's store (`matinee.sqlite`), the door's secret (`door.key`,
  made at the first start with a door word), the TMDB cache
  (`tmdb/films.jsonl`) and its shelf of pictures (`tmdb/pictures/`), the
  rebuild's report (`rebuild.json`), its lock (`rebuild.lock`) and, where the
  household keeps one, its override file (`overrides.json`). None of it is in
  the image. The labels ship in the image with the code (`data/labels.json`).
- **Settings and keys arrive as environment**, never committed, logged or sent
  to a browser. `.dockerignore` keeps `.env` files out of the image.

| Variable | Used by | Holds |
|---|---|---|
| `DATA_DIR` | server, rebuild, notes tool | the data directory |
| `JELLYFIN_URL`, `JELLYFIN_API_KEY` | server, rebuild | a Jellyfin library's address and key |
| `PLEX_URL`, `PLEX_TOKEN` | server, rebuild | a Plex library's address and token |
| `SEERR_URL` | server, optional | the base of the address the pick's poster links to, its strip reading "More on Seerr ↗"; unset or empty means TMDB's page and "More on TMDB ↗" |
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
  About page. The TMDB logo appears there alone, less prominent than Matinee's
  own mark. TMDB's terms ask for the logo to identify the use and for the
  notice shown prominently in the application, not on every screen, so no
  screen's foot carries either. TMDB data is non-commercial under the default licence.
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
  DoesTheDogDie key; each profile's settings, ratings and short reviews (seen
  by others only when it shares them), hidden films and last 50 runs; notes;
  the two cookies, up to 400 days); what leaves the
  computer (the DoesTheDogDie lookup of the picked film only, with a key, the
  topics never leaving and the answer kept at most 30 days; TMDB's records,
  fetched with nothing about a viewer; under `tmdb`, the browser's own picture
  requests); that the library is only read; and that a PIN guards a profile,
  deleting a profile removes it and everything it keeps while its notes stay,
  and whoever runs the installation removes anything else. Each sentence states
  only what the code does, and a change to what Matinee keeps or sends amends
  it.
- **MovieLens tag genome.** Credited on the About page to F. Maxwell Harper and
  Joseph A. Konstan (2015), *The MovieLens Datasets: History and Context*, and
  Jesse Vig, Shilad Sen and John Riedl (2012), *The Tag Genome: Encoding
  Community Knowledge to Support Novel Interaction*. The raw dataset is never
  committed. Each derived table Matinee ships carries the dataset's own
  conditions: `data/reference.json`, `data/genome.json` and `data/tags.json`
  state them in their `licence` field (research and
  non-commercial use, no implied endorsement, redistribution only under the
  same conditions).
- **DoesTheDogDie.** Queried one film at a time, at the moment of a pick. Never
  fetched ahead, never used to build a score. Votes are never kept. The search's
  answer for a film, and the topic list, are remembered for at most 30 days, the
  refresh period the terms set for a performance cache (sections 8 and 9). "Powered by
  DoesTheDogDie.com", linked to `https://www.doesthedogdie.com`, appears
  on every screen that shows its data, as its terms require (section 6, quoted
  in `docs/data-terms.md`): at the door's foot while the trigger
  picker holds its topics, in the foot band of the theatre's topics step, under
  My profile's "Scenes you don't want to see", and on the pick in the foot band
  (section 12, Credits). It also appears on the About page. Nothing of
  DoesTheDogDie enters a profile's history (section 7.6). Where a line is typed from its
  data, the credit is on screen before the line starts to type and stays while
  the line does. The free tier is non-commercial.

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
- a marker on the pick screen for a film the library does not hold;
- ratings synced with Trakt, Movary or any outside service, and ratings from
  other installations;
- ratings steering picks toward a viewer's taste;
- setting or changing a PIN on My profile;
- a way to replay the welcome.

---

# Known gaps

Behaviour that is deliberately absent, still open, or short of the contract,
as the code stood on 2026-10-05, on 2026-10-10 for the pick screen (gap 17),
and on 2026-10-14 for My profile (gaps 18 to 20).

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

15. **The door's request sets no length cap on the word.** Every other request body
    field is capped (section 11.2), and a `run` in a query or a path is not capped
    but is refused when it is not 8 to 64 characters of the key's alphabet
    (`bad_run`); but `POST /api/admission` takes a word of any
    length, from a device not yet admitted, and refuses one over 200
    characters without comparing it, after the usual 2-second wait.
    (`src/matinee/web/app.py::WordIn`, `src/matinee/web/admission.py::MAX_TYPED`)

**Short of the contract, in the page (continued):**

16. **DoesTheDogDie's credit wording lives in two places.** The page writes
    "Powered by DoesTheDogDie.com" itself, and the pick and topic replies carry `credit`
    and `link` as well, which the page reads only for the link's address.
    (`src/matinee/web/static/js/credits.js::dtddCredit`, `dtddFoot`, `dtddBeside`,
    `src/matinee/web/viewing.py::PickOut`, `TopicsOut`)
17. **A pick opened in the moment after the page's own back holds no history
    entry.** The page takes its own entries back off with the browser's back,
    which the browser runs a moment later; a pick screen opened within that
    moment adds no entry, so the browser's back from it leaves the page rather
    than stepping back one answer. (`src/matinee/web/static/js/main.js::holdPickEntry`,
    `dropPickEntry`)

**Open in My profile, as built on 2026-10-14:**

18. **A profile without a PIN keeps nothing private from the household.** It
    opens on any admitted device in one tap, which may then read its ratings,
    hidden films, history and settings, and no PIN can be added once a profile
    is made (setting one on My profile is out of scope). (`src/matinee/web/app.py::add_door_routes`)
19. **An "Undo" that fails says nothing to the viewer.** The page logs it, the
    roll goes on, and the film stays hidden until brought back from My profile.
    (`src/matinee/web/static/js/main.js::undoHide`)
20. **A welcome whose mark fails to save can show again.** "Show me" and "Not
    now" mark the profile without waiting; a failed mark is only logged, so the
    next visit shows the welcome once more. (`src/matinee/web/static/js/main.js::welcomeIfNew`)
---

# Part 2 — Map

A pointer to where each part lives, never proof of what it does. Each entry
names a file and, where it points inside one, a symbol defined there, as
`path::symbol`; a later symbol on the same line, as `/ symbol`, is in the same
file, and words in parentheses say what to look for. A stylesheet or file named
bare may be followed by a comma list of its selectors or properties. No entry carries a line
number or a date: search the file for the symbol. `./check.sh` fails when an
entry names a file that does not exist or a symbol the file does not define
(`tests/test_spec_map.py`), so the map can point at the wrong thing only by
describing it wrongly, never by naming something gone.

### Boundaries and the library

- `src/matinee/library/__init__.py::Library`
- `src/matinee/library/__init__.py::LibraryFilm`
- `src/matinee/library/jellyfin.py::JellyfinReader`
- `src/matinee/library/jellyfin.py::JellyfinReader.films` / `_page` / `_items` / `AUDIO_FIELDS` / `AUDIO_PAGE` (with audio, the streams read 5,000 items to a request)
- `src/matinee/library/jellyfin.py::_audio` (an item's audio tracks' languages, never its subtitles)
- `src/matinee/library/jellyfin.py::JellyfinReader._get_json` (the key in an unredirected header)
- `src/matinee/library/jellyfin.py::JellyfinReader.image` (no key, size and type caps)
- `src/matinee/library/jellyfin.py::ITEM_ID`
- `src/matinee/library/jellyfin.py::parse_film` (`{tmdb-N}` folder tag)
- `src/matinee/library/plex.py::PlexReader` (every movie section)
- `src/matinee/library/plex.py::PlexReader._with_audio` / `audio_of` / `AUDIO_STREAM` / `DETAILS_BATCH` (each film's details, 100 to a request, for its audio)
- `src/matinee/library/plex.py::PlexReader._get` (GET only; the token in an unredirected header)
- `src/matinee/library/plex.py::parse_film` / `_tmdb` / `certificate` (runtime, rating, folder tag)
- `src/matinee/library/plex.py::ITEM_ID` / `TMDB_GUID` / `LEGACY_TMDB_GUID` / `US_PREFIX`
- `src/matinee/library/choice.py::configured_server` (the server whose settings are filled in; none, or refused for both)
- `src/matinee/library/choice.py::MediaServer` / `ServerChoiceError` / `open_reader`
- `src/matinee/__init__.py::USER_AGENT` (every outbound request names Matinee)

### Conversation model

- `data/first_question.json` (lines, answers, labels)
- `data/first_question.json` `source` (the source question's wording, answers and replies)
- `src/matinee/trees.py::parse_tree`
- `src/matinee/trees.py::Tree.apart` (a flavour the tree does not define is refused)
- `src/matinee/trees.py::Question.footnote`
- `src/matinee/trees.py::SOLE_SIGNALS` / `_check_flavours` (`labelled`, `specials`, `always_shown`)
- `src/matinee/trees.py::load_trees` (duplicate names refused)
- `src/matinee/trees.py::FILTER_KEYS` / `OPTION_KEYS` / `QUESTION_KEYS`
- `src/matinee/trees.py::parse_filter`
- `src/matinee/engine.py::STOP_UNDER`
- `src/matinee/engine.py::Source` / `SOURCES` (the three pools)
- `src/matinee/engine.py::Viewer.source` (bounds every pool, count and pick of the walk)
- `src/matinee/engine.py::SourceOption`
- `src/matinee/engine.py::Catalog.sources` (per source, the films it holds)
- `src/matinee/engine.py::source_masks` (`held` from the live list; none without one)
- `src/matinee/engine.py::load_catalog`
- `src/matinee/engine.py::_first_option` (label required)
- `src/matinee/engine.py::first_question`
- `src/matinee/engine.py::base_pool` (the source, the topic skip, then the viewer's allowed films and floor)
- `src/matinee/engine.py::walk`
- `src/matinee/engine.py::_gate` (`only_if_pool_over`, `skip_if_topics`)
- `src/matinee/engine.py::_shown` (empty answers hidden, `not_after`, small kinds hidden)
- `src/matinee/engine.py::KIND_MIN_FILMS`
- `src/matinee/engine.py::_too_small` (`always_shown`, a kind another answer leaves out; counted in the source)
- `src/matinee/engine.py::_answer_masks` / `Catalog.small` (`small` per source)
- `src/matinee/engine.py::_hold_apart` / `Catalog.apart`
- `src/matinee/engine.py::opening_pool`
- `src/matinee/engine.py::_served` (apart films stay out until their answer)
- `src/matinee/engine.py::_asked` / `Asked.footnote` (footnote and asterisks dropped with the apart answer)
- `src/matinee/web/viewing.py::asks_source` (asked while the library can be used and both pools hold a film)
- `src/matinee/web/viewing.py::source_for` (before an answer, the library's films; unasked, every film)
- `src/matinee/web/viewing.py::fallback_for` (`held` or `new` while the library does not answer or turned down the key)
- `src/matinee/web/viewing.py::walk_notice` (the walk's strip: the library's fallback, then Seerr not answering)
- `src/matinee/web/setup.py::fallback_line` (the fallback notice's wording)
- `src/matinee/web/viewing.py::SourceQuestionOut` / `SourceOptionOut`
- `src/matinee/web/viewing.py::everything` (the first question's pool)
- `src/matinee/web/viewing.py::QuestionOut.footnote`
- `src/matinee/engine.py::_plain_mask` / `_range_mask` (unknown values pass)
- `src/matinee/engine.py::walk_ends` / `reachable`
- `data/trees/comedy.json` room question (ceilings)
- `data/trees/comedy.json` kind question (standup answer, footnote), `standup` flavour, `apart`
- `data/trees/thriller.json` kind question (spies `self_destruct`)
- `data/trees/action.json`, `data/trees/drama.json`, `data/trees/scifi.json`, `data/trees/fantasy.json`, `data/trees/romance.json`, `data/trees/animation.json`, `data/trees/war.json` (kind questions); `data/trees/western.json` (no question)
- `data/trees/kids.json` age and kind questions (labelled, always shown)
- `data/trees/crime.json` kind question
- `tests/test_source.py::test_the_source_question_is_asked_first_in_its_order_and_bounds_every_later_answer`

### The checker

- `tools/check_trees.py::main` (the shipped labels unless `--labels`; the library's films when the table names one)
- `tools/check_trees.py::SAMPLES`
- `tools/check_trees.py::check_answer_coverage`
- `tools/check_trees.py::check_same_answers`
- `tools/check_trees.py::check_sample`
- `tools/check_trees.py::check_homes`
- `tools/check_trees.py::door_pools` (only doors are homes)
- `tools/check_trees.py::check_apart`
- `tools/check_trees.py::check_kinds` / `report_waiting`
- `tools/check_trees.py::check_hidden` (the whole source's small kinds)
- `tools/check_trees.py::check_pins_in_key`
- `tools/check_trees.py::SPECIALS_KIND` (a `specials` pin's fixture)
- `tools/check_trees.py::check_gore`
- `tools/check_trees.py::check_lists`
- `tools/check_trees.py::check_data`
- `tools/check_trees.py::check_quips`
- `data/answer_key.json` list tags
- `data/answer_key.json` `hidden`

### The pick's lines

- `data/quips.json` (caps, categories)
- `src/matinee/quips.py::Quips` / `QuipSet` / `Caps` (universal must hold every set)
- `src/matinee/quips.py::load_quips` / `QuipsError`
- `src/matinee/quips.py::quip_problems` / `line_problems` / `in_title_case`
- `tests/test_quips.py::test_the_caps_are_the_measured_ones`
- `tests/test_openers.py::stock_openers` / `opens_stock` / `KEPT` / `NOT_SPOKEN` (only named lines open in the stock form)

### The pick's rank and tags

- `src/matinee/engine.py::VOTE_FLOOR` (200 votes; `matinee.ranks` reads it from the engine)
- `src/matinee/ranks.py::DOOR_WORDS` (each door's word, by tree)
- `src/matinee/ranks.py::BANDS` / `BASIS` / `Rank` / `band` (a place to its words and standing; an edge reads as the higher band)
- `src/matinee/ranks.py::door_films` (the door's pool, or every door's before one)
- `src/matinee/ranks.py::rank_among` / `rank` (None under the floor or without a score, where `rank` gives `thin_rank`'s line; None for a tree with no word)
- `src/matinee/ranks.py::thin_rank` / `NEW_YEARS` (a film under the floor: too new or too little-known, and where its few votes place it)
- `tests/test_ranks.py::test_a_film_under_the_vote_floor_says_why_and_where_its_few_votes_place_it`
- `tests/test_ranks.py::test_a_film_reads_the_band_its_place_falls_in_and_an_edge_reads_as_the_higher`
- `tests/test_ranks.py::test_every_door_the_first_question_offers_has_its_rank_word`
- `src/matinee/tags.py::TAGS_FILE` / `SKIP_FILE` / `WORDS_PER_FILM` / `SHOWN` (40 shipped, 4 shown)
- `src/matinee/tags.py::Tags` / `Tags.of`
- `src/matinee/tags.py::strongest` / `write_tags` (the first MovieLens film wins; `alike` on one line)
- `src/matinee/tags.py::ALIKE` / `ENDINGS` / `forms` / `alike_pairs` (words that say nearly the same thing)
- `src/matinee/tags.py::_first_distinct` (four words, passing over one alike to a word already shown)
- `src/matinee/tags.py::read_skip` / `load_tags` / `TagsError` (the skip list applied once at load; a warning for a word no film carries)
- `data/tags.json` (`licence`, `source`, `words`, `films` as positions)
- `data/tag_skip.txt` (four groups)
- `tools/build_genome.py::main` (`--tags-out`, after the release check)
- `src/matinee/web/app.py::shipped_tags` / `NO_TAGS` (an unreadable file is a setup fault; picks go without tags)
- `tests/test_tags.py::test_no_skip_list_word_reaches_any_films_tags_and_every_covered_film_shows_four`
- `tests/test_tags.py::test_no_film_shows_two_words_that_say_nearly_the_same_thing`
- `tests/test_tags.py::test_every_skip_list_entry_is_a_genome_word_so_none_is_a_silent_typo`
- `tests/test_tags.py::test_written_tags_pair_word_forms_and_words_that_move_together_and_the_pick_shows_one_of_each`
- `tests/test_web_library.py::test_the_film_card_ranks_among_the_door_it_names_and_overall_without_one`
- `tests/test_web_library.py::test_unreadable_tags_leave_picks_without_them_and_say_so_in_the_setup_note`
- `tests/test_setup.py::test_the_server_hands_the_shipped_tags_to_the_app_with_the_setup_notes_faults`

### Labels and the household override file

- `data/labels.json` (format 2, shipped)
- `src/matinee/labels.py::LABELS` (the shipped file's path)
- `src/matinee/labels.py::load_labels` / `Labels` / `TreeLabels` (format 2; anything else refused, naming the path)
- `src/matinee/labels.py::_mend` (how a broken file is mended, by whose it is)
- `src/matinee/labels.py::OVERRIDES` (`overrides.json` in the data directory)
- `src/matinee/labels.py::load_overrides`
- `src/matinee/labels.py::with_overrides` (a named film takes its whole placement from the household)
- `src/matinee/labels.py::Labels.named` / `overridden`
- `src/matinee/pools.py::House.without` (the pins of a household-placed film give way, its gore pail kept)
- `src/matinee/engine.py::label_problems` (a tree no file defines, a kind it does not label)
- `src/matinee/engine.py::household_problems` (bands only under kids; a kids film needs kinds and band)
- `src/matinee/engine.py::_check_labels` (the engine refuses to prepare)
- `src/matinee/web/main.py::household` / `OVERRIDES_BROKEN` (the file laid over, or a fault)
- `src/matinee/web/main.py::build` (the shipped labels, an unread `labels.json` in the data directory warned of)
- `tools/rebuild_table.py::household_films` (the rebuild fetches the films the household names)
- `tests/test_overrides.py::test_a_film_the_household_names_takes_its_whole_placement_from_the_file`

### Pools and reference statistics

- `src/matinee/pools.py::build_pools` (labelled films, the waiting room and pins; comedy holds the specials)
- `src/matinee/pools.py::kids_bands` / `kids_band` / `CERTIFICATE_BANDS` (a pin applies to a film not held only on a passing certificate)
- `src/matinee/pools.py::waiting` / `WAITING_ROOM` / `GENRE_DOORS`
- `src/matinee/pools.py::standup_specials`
- `src/matinee/pools.py::specials` (the rule plus `specials` pins)
- `src/matinee/reference.py::reference_films`
- `src/matinee/reference.py::compute_tree`
- `src/matinee/reference.py::problems`
- `src/matinee/reference.py::LICENCE`
- `tools/build_reference.py::main`
- `data/reference.json` (horror gore cuts)
- `tests/test_reference.py::test_shipped_reference_covers_every_tree`

### Scales and pins

- `src/matinee/scales.py::scale_of`
- `src/matinee/scales.py::film_scores` (bonus only with a genome entry)
- `src/matinee/scales.py::band_index`
- `src/matinee/scales.py::membership` (unscored bands, pins)
- `src/matinee/engine.py::scale_members`
- `data/trees/horror.json` gore scale
- `data/trees/horror.json` gore question, `skip_if_topics`, `treat_as`
- `data/trees/horror.json` labelled flavours (the kinds' rules)
- `src/matinee/pools.py::load_house` / `House` (`House.specials`)
- `src/matinee/engine.py::house_flavour` (a `specials` flavour holds the standup specials)
- `data/house_overrides.json` scale pins
- `data/house_overrides.json` `specials` pins

### Film table and nightly rebuild

- `tools/rebuild_table.py::main` (`TMDB_TOKEN`, `TMDB_RATE`, the server whose settings are filled in)
- `tools/rebuild_table.py::daily_time` / `daily_arg` / `seconds_until` (`--daily HH:MM`, validated before the first rebuild)
- `tools/rebuild_table.py::rebuild_time` / `DEFAULT_DAILY` (`REBUILD_TIME` for `--daily` alone; 04:30 when unset or not a time, logged)
- `tools/rebuild_table.py::one_at_a_time` / `LOCK` (`rebuild.lock`; a second rebuild waits)
- `src/matinee/web/main.py::Rebuilds` / `REBUILD` / `RESTART_AFTER_S` (the server runs the rebuild beside itself; restarted five minutes after it exits)
- `tools/rebuild_table.py::rebuild` (no key: compact and stop; an unexpected failure puts the kept table back and reports its error)
- `tools/rebuild_table.py::library_films` / `_say_waiting` / `_keep_terms` / `BEGAN` / `KEEP_EVERY_S` (a media server that does not answer is waited for, reporting `waiting`; the retention sweeps still run daily; the one read that asks for audio tracks)
- `tools/rebuild_table.py::_keep` / `_compact_cache` (`films.sqlite.kept`)
- `tools/rebuild_table.py::_sweep_pictures` (every rebuild sweeps the picture shelf)
- `tools/rebuild_table.py::_rebuild` (the start line; save before any fetch; most-voted order)
- `tools/rebuild_table.py::_Run` / `save` / `tick` (a save every `SAVE_EVERY` records)
- `tools/rebuild_table.py::SAVE_EVERY` / `FAILED`
- `tools/rebuild_table.py::tmdb_rate` (any positive number; anything else the default, logged)
- `src/matinee/progress.py::RebuildStatus` / `State` / `STATUS_FILE` (`rebuild.json`; `waiting`, `running`, `finished`, `stopped`)
- `src/matinee/progress.py::write_status` / `read_status` / `_well_formed`
- `src/matinee/tmdb.py::refresh` (one shared pacer; compaction in `finally`)
- `src/matinee/tmdb.py::fetch_order` (held vote counts, else TMDB's list)
- `src/matinee/tmdb.py::most_voted` / `VOTE_PAGES` (`VOTE_PAGES`, progress after every page)
- `src/matinee/tmdb.py::Pacer` / `wait` / `hold` / `_held_until` (a 429 holds every request)
- `src/matinee/tmdb.py::DEFAULT_RATE` / `MAX_WORKERS` / `workers_for`
- `src/matinee/tmdb.py::get_json`
- `src/matinee/tmdb.py::_fetch_all` / `_Tally` / `Tick` / `TICK_EVERY`
- `src/matinee/tmdb.py::_Tally.records` / `so_far` / `take`
- `src/matinee/tmdb.py::TmdbFilm` (title, year, genres, synopsis, vote count, US rating)
- `src/matinee/tmdb.py::fetch_film` / `_us_certification`
- `src/matinee/tmdb.py::TmdbRefused` / `Refreshed` / `NETWORK_FAILURES`
- `src/matinee/tmdb.py::NO_KEY` / `KEY_REFUSED` / `NOT_ANSWERING`
- `src/matinee/tmdb.py::REFETCH_AFTER` / `MAX_AGE`
- `src/matinee/tmdb.py::compact`
- `src/matinee/tmdb.py::load_cache` / `_record` (a damaged line, its fetch time included, is skipped)
- `src/matinee/tmdb.py::needs_fetch` / `picture_path` / `PICTURE_PATH`
- `src/matinee/genome.py::load_genome` (links.csv join, stamped cache)
- `src/matinee/genome.py::Genome.scores` (the tags read, by TMDB id; the first MovieLens film wins)
- `src/matinee/genome.py::Scores`
- `src/matinee/genome_file.py::GENOME_FILE` / `tags_read` / `write_scores` / `load_scores`
- `tools/build_genome.py` (writes `data/genome.json` and `data/tags.json`; refuses a release other than `data/reference.json`'s)
- `tests/test_genome_file.py::test_every_reader_finds_its_tags_in_a_table_built_from_the_shipped_scores`
- `src/matinee/table.py::build_table` / `BuildReport` / `BuildReport.with_audio` (the library and every labelled film with a usable record; films with audio languages counted)
- `src/matinee/table.py::_either` (every copy's audio languages together)
- `src/matinee/table.py::_library_rows` / `_listed_rows` / `_from_library` / `_from_tmdb`
- `src/matinee/table.py::FORMAT` / `COLUMNS` / `SHOWN` / `TMDB_COLUMNS` / `INSERT_FILM` / `LATER_COLUMNS` (a table without `audio` is read with none)
- `src/matinee/table.py::write_table` / `_cell`
- `src/matinee/table.py::load_table` / `_read` / `_text` (format 2 with every column, else refused; a stale table is read)
- `src/matinee/table.py::empty_table`
- `src/matinee/table.py::is_stale` (the oldest TMDB fact 183 days old or more)
- `src/matinee/table.py::with_live` / `_offered` / `_aligned` (held from the live list; the films the labels name)
- `src/matinee/table.py::library_films`
- `src/matinee/web/theatre.py::Theatre.showing` / `_read_library` / `_ttl` (`LIVE_TTL`, `RETRY_AFTER`)
- `src/matinee/web/theatre.py::Theatre` (`listed`, `on_reload`; an absent or unreadable table counts as empty)

### Profiles and devices

- `src/matinee/store.py::MAX_PROFILES` (and the other limits)
- `src/matinee/store.py::AVATARS` / `clean_avatar` / `Profile.avatar` (an unknown avatar reads as none)
- `src/matinee/store.py::name_key` / `clean_name` / `clean_pin`
- `src/matinee/store.py::Store.__init__` (brings the file to its shape)
- `src/matinee/store.py::Store._issue` (token pruning)
- `src/matinee/store.py::Store.create` (a profile made now has seen the welcome)
- `src/matinee/store.py::Store.holding`
- `src/matinee/store.py::Store.everyone` (every profile, sorted by name)
- `src/matinee/store.py::Store._held` / `_issued` (the token check inside the write's transaction)
- `src/matinee/store.py::Store.writing` / `reading` (a profile's own records opened only for a device holding it)
- `src/matinee/store.py::Store.rename` (the rules of a new name; `name_taken` for another's)
- `src/matinee/store.py::now` (the store's time, ISO 8601 in UTC)
- `src/matinee/store.py::Store.set_topics` / `set_avatar`
- `src/matinee/store.py::Store.delete` (everything the profile keeps goes with it; notes stay)
- `src/matinee/store.py::shown_avatar` (one rule for profiles and shared ratings)
- `src/matinee/store.py::Store.clear_pin`
- `src/matinee/store.py::Store.open` / `_check_pin` (lockout)
- `src/matinee/web/common.py::TOKENS_COOKIE` / `MAX_TOKENS`
- `src/matinee/web/common.py::PROFILE_LINES` / `ErrorCode` (each refusal's words; `walk_gone`)
- `src/matinee/web/common.py::Seat` / `Tile` / `Deleted` / `Door` (what the page is told of a profile)
- `src/matinee/web/common.py::NewProfile` / `AvatarChoice` / `PinEntry` / `NameChoice` (request caps)
- `src/matinee/web/common.py::over_https` / `set_tokens` / `with_token`
- `src/matinee/web/app.py::add_door_routes` (`GET /api/door`, create, open)
- `src/matinee/web/app.py::add_avatar_route` (`PUT /api/profiles/{id}/avatar`)
- `src/matinee/web/app.py::add_delete_route` (`DELETE /api/profiles/{id}`)
- `src/matinee/web/app.py::add_rename_route` (`PUT /api/profiles/{id}/name`)
- `src/matinee/web/viewing.py::ViewerIn` (a profile id only)
- `src/matinee/web/viewing.py::held_profile`
- `src/matinee/web/viewing.py::resolve` (no profile: the front door's pool; no key: stored topics ignored; a held profile's narrowing read afresh)
- `src/matinee/web/viewing.py::resolve_held` (walks and picks need a held profile)
- `tests/test_profiles.py::test_a_write_never_lands_on_a_new_profile_that_reuses_a_deleted_ones_id`
- `tests/test_avatar_images.py` (two square sizes each; the size budget)
- `src/matinee/web/static/avatars/` (`<avatar>-256.webp` and `<avatar>-80.webp`)

### The store file

- `src/matinee/upgrade.py::SHAPE` / `TABLES` (the current shape; the settings' columns; the unread `exclusions` column)
- `src/matinee/upgrade.py::RECORDS` (`ratings`, `hidden`, `runs`, `run_films`, each going with its profile)
- `src/matinee/upgrade.py::FROM_SHAPE_1` (the settings at their defaults, every profile unmarked)
- `src/matinee/upgrade.py::BELONGS_FROM_CORRECTIONS` (where an old genre note's film belongs)
- `src/matinee/upgrade.py::FROM_SHAPE_0`
- `src/matinee/upgrade.py::ShapeError`
- `src/matinee/upgrade.py::_stranded` / `_refuse_stranded` (notes in an old `feedback` table)
- `src/matinee/upgrade.py::_keep_copy` (one copy, never overwritten)
- `src/matinee/upgrade.py::_upgrade` (every step from the file's shape in one transaction; the count and foreign-key guards)
- `src/matinee/upgrade.py::prepare`
- `tests/test_upgrade.py::shape_1` / `layout` (a shape-1 store built in the test; an upgraded store's shape is a new one's)

### What a profile keeps

- `src/matinee/records.py::Records` (a profile's own records, through the store's ownership checks)
- `src/matinee/records.py::Records.rate` / `unrate` / `review` / `ratings` (the same answer keeps its first time; a review alone never moves it; newest first)
- `src/matinee/records.py::clean_score` / `clean_review` / `MAX_REVIEW` / `LINE_BREAKING` / `SOURCE` (1 to 5; one line of 100 code points, refused never cut)
- `src/matinee/records.py::Records.shared` / `Shared` (other sharing profiles' ratings of a film, newest first)
- `src/matinee/records.py::LENGTHS` / `months_on` / `hide_until` / `Hidden` (calendar months, the day clamped; none for good)
- `src/matinee/records.py::Records.hide` / `unhide` / `hidden` (a hide replaced; ended hides left out)
- `src/matinee/records.py::Walk` / `Shown` / `Run` / `Run.walk` (each kept film with its own walk; a run's walk is its latest film's)
- `src/matinee/records.py::Records.show` / `history` / `_drop_oldest` / `MAX_RUNS` (kept once its first film shows; the 50 newest runs)
- `src/matinee/records.py::RUN_KEY` / `clean_run` (8 to 64 letters, digits, - or _)
- `src/matinee/records.py::MARKING` / `mark_in_run` (rated, reported, hid, undo; a hide keeps the mark it replaced)
- `src/matinee/web/mine.py::add_rating_routes` / `offered` / `ScoreIn` / `ReviewIn` / `REVIEW_CAP` / `RatingOut` / `RatedOut` / `rated_out` / `Cleared` (the rating routes; a film not offered answers 404)
- `src/matinee/web/mine.py::SharedOut` / `shared_out` (`GET /api/profiles/{id}/shared/{tmdb}`)
- `src/matinee/web/mine.py::add_hide_routes` / `HideIn` / `HiddenOut` / `HiddenListedOut` / `hidden_listed`
- `src/matinee/web/mine.py::add_run_routes` / `walk_of` / `run_out` / `ShownIn` / `KeptOut` / `RunOut` / `ShownOut` / `WalkOut` (a walk the catalogue does not hold refused; films off the table left out)
- `tests/test_records.py::test_a_short_review_over_the_limit_or_on_two_lines_is_refused_never_cut`
- `tests/test_records.py::test_the_same_answer_again_records_nothing_and_keeps_the_first_time`
- `tests/test_history.py::test_a_profile_keeps_its_fifty_newest_runs`
- `tests/test_history.py::test_a_note_and_its_reported_mark_are_kept_together_or_not_at_all`
- `tests/test_sharing.py::test_nothing_of_a_profile_but_what_it_shares_reaches_another_device`

### Tailoring settings and the narrowed pool

- `src/matinee/store.py::FLOORS` / `RATED_OUT` / `Profile` / `Settings` (the choices; a profile with its settings; a change)
- `src/matinee/store.py::Store.profile` / `set_settings` / `welcome` (a ticked language kept when the table drops it; the welcome mark)
- `src/matinee/web/mine.py::add_settings_routes` / `SettingsIn` / `SettingsOut` / `settings_out` / `LanguageOut` (`GET /api/languages`, the settings, the welcome mark)
- `src/matinee/languages.py::held` / `PLACEHOLDERS` (the languages the films are in, most first; never `xx`)
- `src/matinee/languages.py::codes` / `two_letter` / `audio_languages` (a tag to TMDB's two-letter code, or untagged)
- `src/matinee/languages.py::extra_track` / `EXTRA_TRACK` (a commentary, description or score track names no language)
- `src/matinee/languages.py::heard_only` / `src/matinee/web/viewing.py::heard_out` / `HeardOut` / `src/matinee/engine.py::Viewer.languages` (a pick reached only through its copy's audio names those languages)
- `data/languages.json` / `codes` (ISO 639-2 to TMDB's codes)
- `src/matinee/library/__init__.py::LibraryFilm.audio` / `Library.films` (read only when asked)
- `src/matinee/engine.py::Viewer.allowed` / `Viewer.floor` / `Catalog.places` (a viewer's narrowing; door places worked out once per catalogue)
- `src/matinee/engine.py::FLOOR_EDGES` / `places` / `_door_places` (the floor's edges, the rank bands'; a film with no place always passes)
- `src/matinee/engine.py::allowed_films` (hidden, rated out, and the language check)
- `src/matinee/engine.py::walk_kept` (a pick's walk after a hide)
- `src/matinee/web/viewing.py::Seating` / `Seating.allowed` (the narrowing read afresh for each request)
- `src/matinee/web/viewing.py::unsettled` / `FirstOut.unsettled` (the films the first question would hold without the settings)
- `tests/test_narrowing.py::test_a_viewer_at_every_default_sees_exactly_the_pools_matinee_shows_today`
- `tests/test_narrowing.py::test_narrowing_one_viewer_never_changes_the_shared_masks`
- `tests/test_narrowing.py::test_the_floor_keeps_out_films_below_its_edge_and_never_one_with_no_place`
- `tests/test_audio.py::test_a_tag_reads_as_the_two_letter_code_tmdb_uses_or_as_untagged`
- `tests/test_settings.py::test_the_front_door_never_carries_a_profiles_settings`

### The door word

- `src/matinee/web/admission.py::COOKIE` / `LIFE_S` / `RELAXED_MIN` / `STRICT_MIN` / `KEY_FILE` / `MAX_TYPED` / `CLOCK_SKEW_S`
- `src/matinee/web/admission.py::edits` / `relaxed_key` (relaxed matching)
- `src/matinee/web/admission.py::too_long` / `too_short`
- `src/matinee/web/admission.py::load_secret` (made once, owner-only)
- `src/matinee/web/admission.py::Admission` (`issue`, `admits`, `matches`)
- `src/matinee/web/config.py::GREETINGS`
- `src/matinee/web/config.py::_door` (a wrong lock refuses the start; with no word, a bad mode is a fault)
- `src/matinee/web/app.py::AdmissionOut` / `WordIn`
- `src/matinee/web/app.py::open_before_admission`
- `src/matinee/web/app.py::add_admission` (the gate, `GET`/`POST /api/admission`, the 2-second wait)
- `tests/test_admission.py`

### Notes and the notes tool

- `src/matinee/store.py::Note` (`belongs`; `kind` None or `tags`)
- `src/matinee/store.py::NOTE_SELECT` / `FiledNote` / `one_line` / `MAX_REASON`
- `src/matinee/store.py::Store.note`
- `src/matinee/store.py::Store.notes` / `filed` / `rule`
- `src/matinee/web/viewing.py::NoteOut` / `NoteIn` (request caps)
- `src/matinee/web/viewing.py::NOTED` / `answer_says` / `check_belongs` / `check_says` (a note says something)
- `src/matinee/web/viewing.py::add_note_routes` / `WALK_GONE` (`POST /api/notes`; a film Matinee does not offer now is refused; a walk gone refused in words)
- `src/matinee/web/viewing.py::NoteIn.run` (the run a note marks reported)
- `src/matinee/records.py::Records.report` / `src/matinee/store.py::Store.note` (the note and its mark in one write)
- `tools/notes.py::Names` / `load_names` (titles and door labels)
- `tools/notes.py::printable`
- `tools/notes.py::what_was_wrong` / `sorted_wrong` / `describe`
- `tools/notes.py::list_open` / `rule` / `clear_pin` / `clear_topics`
- `tools/notes.py::note_id` / `parser` / `main` (exit statuses)
- `src/matinee/store.py::Store.clear_topics` (`clear-topics`)
- `tests/test_notes.py`, `tests/test_review.py`, `tests/test_notes_tool.py`

### Topics and the DoesTheDogDie check

- `src/matinee/web/config.py::Config.dtdd_key` (optional)
- `src/matinee/web/app.py::create_app` (one `topics_on`; a picker that disagrees is refused)
- `src/matinee/web/viewing.py::add_topic_routes` (`GET /api/topics`, `PUT /api/profiles/{id}/topics`, only with a key)
- `src/matinee/web/viewing.py::save_topics`
- `src/matinee/web/viewing.py::FirstOut.checked` (whether this viewer's picks are checked)
- `src/matinee/web/common.py::Door.dtdd` (`GET /api/door` says whether a key is set)
- `src/matinee/web/main.py::warn_kept_topics` / `TOPICS_KEPT` / `WARN_EVERY` (kept topics without a key)
- `src/matinee/pick.py::Picker.dtdd` / `_checked` (none without a key)
- `src/matinee/dtdd.py::Dtdd.get` / `_pace` (`BURST`, `RATE_PER_S`)
- `src/matinee/dtdd.py::Dtdd._check_holds` / `_refused` / `_note_remaining` (`REQUESTS_PER_HOUR`, `MONTH_RESERVE`, `RESERVE_HOLD_S`, `BACKOFF_S`)
- `src/matinee/dtdd.py::Dtdd.topics` (`TOPICS_REFRESH_S`, `TOPICS_KEEP_S`)
- `src/matinee/pick.py::failing` (`MIN_VOTES`)
- `src/matinee/pick.py::_count` (a DoesTheDogDie number: a plain non-negative integer, never a boolean)
- `src/matinee/pick.py::_the_film` (the one Movie with the film's TMDB id; a malformed item id is unreadable)
- `src/matinee/pick.py::ItemIds` (`ID_KEEP_S`)
- `src/matinee/pick.py::ItemIds._drop_expired` (nothing held past 30 days)
- `src/matinee/pick.py::look_up` (`LOOKUP_S`)
- `src/matinee/pick.py::DeviceCap` (`LOOKUPS_PER_HOUR`)
- `src/matinee/pick.py::candidates`
- `src/matinee/engine.py::gentlest`
- `src/matinee/pick.py::Picker.pick` (`PICK_TRIES`)
- `src/matinee/pick.py::Pick` (`last` / `last_hits`: the third film of three in a row; `item`: an unchecked film's item)
- `src/matinee/pick.py::Picker._item` (the item as held after any lookup)
- `src/matinee/web/viewing.py::device_id` / `DEVICE_COOKIE`
- `src/matinee/web/viewing.py::SWAP_LINE` / `UNCHECKED_LINES` / `EXHAUSTED` / `TIRED` / `PICKED`
- `src/matinee/web/viewing.py::LastOut` / `PickOut` (`last`, `dtdd_item`)
- `src/matinee/web/viewing.py::_swap_out` / `_last_out` / `pick_out`
- `src/matinee/web/viewing.py::pick_pool` (the walk kept after a hide; an empty pool is used up)
- `src/matinee/web/viewing.py::add_pick_routes`
- `tests/test_pick.py::test_three_in_a_row_hold_the_third_film_with_its_own_topic` / `test_a_pick_that_asks_to_skip_the_check_is_still_checked`
- `tests/test_without_dtdd.py::test_stored_topics_stay_in_the_store_and_change_no_walk_or_pick`

### Settings, the setup note and the logs

- `src/matinee/web/config.py::from_env` (refuses only `DATA_DIR` and a wrong lock; everything else a fault)
- `src/matinee/web/config.py::Config` / `faults` / `server_unusable` / `server`
- `src/matinee/web/config.py::_server` / `_seerr` / `_images`
- `src/matinee/web/config.py::ImageSource` (`POSTERS_FROM`: `server` or `tmdb`)
- `src/matinee/web/setup.py::SetupNote` (`warning` while the data is stale)
- `src/matinee/web/setup.py::note` / `library_away` / `rebuild_lines` / `stalled` (a waiting report stalls like a running one)
- `src/matinee/web/setup.py::HEADING` / `MEANWHILE` / `STOPPED` / `STALE` / `STALLED_AFTER` (every line's words)
- `src/matinee/web/app.py::setup_faults` (the configured, start-up and run-time faults)
- `src/matinee/web/app.py::add_setup_route` (`GET /api/setup`)
- `src/matinee/web/theatre.py::NothingToShow` (shipped data that cannot make a catalog)
- `src/matinee/web/theatre.py::Theatre._catalog`
- `src/matinee/web/theatre.py::Showing.library` / `UNUSABLE` / `warn_library` (`none`, `usable`, `unreachable`, `refused`; INFO while Matinee has just started)
- `src/matinee/web/theatre.py::Theatre.table_films` / `stale` / `oldest_tmdb`
- `src/matinee/web/seerr.py::SeerrCheck` / `away` / `say_away` (checked every `outage.RETRY_S`; picks link to TMDB while it does not answer)
- `src/matinee/outage.py::Outage` / `RETRY_S` / `STARTING_S` (household services never given up on; INFO just after start, warned once after)
- `src/matinee/web/logbook.py::describe` / `StateLog` / `state_log` / `CHECK_EVERY` (the state line)
- `src/matinee/web/logbook.py::Quiet` / `QUIET_FOR` / `SERVER_NAMES` (a repeating warning once a minute, with a count)
- `src/matinee/web/app.py::add_state_log` / `QUIET`
- `tests/test_setup.py::test_only_a_wrong_lock_and_a_missing_data_directory_refuse_to_start`
- `tests/test_logbook.py::test_the_state_line_names_every_part_and_no_secret`

### Web surface

- `src/matinee/web/main.py::build` (reads the labels, the household file and the film tags; faults go on the note)
- `src/matinee/web/app.py::create_app` (docs disabled)
- `src/matinee/web/app.py::security_headers` / `CONTENT_SECURITY_POLICY`
- `src/matinee/web/app.py::add_page`
- `src/matinee/web/app.py::add_quip_routes` (`GET /api/quips`; 503 when the lines cannot be read)
- `src/matinee/web/app.py::add_film_routes` / `IMAGE_WIDTHS` / `IMAGE_CACHE` (`GET /api/pictures`; `GET /api/film/{tmdb}?door=`, a door naming no tree refused)
- `src/matinee/web/app.py::film_link` / `FilmCard` (Seerr, else TMDB; `rank`, `standing`, `tags`)
- `src/matinee/web/app.py::Held` / `held` / `stored_path`
- `src/matinee/web/app.py::film_image` / `tmdb_image` / `TMDB_IMAGE_CACHE` (the media server's, else TMDB's; 30 days for a film the library does not hold)
- `src/matinee/web/app.py::Shelf` / `from_shelf` (each TMDB picture fetched once for every viewer)
- `src/matinee/tmdb.py::shelf_file` / `read_shelf` / `shelve` / `sweep_shelf` / `PICTURE_KEEP` (150 days)
- `src/matinee/web/app.py::film_synopsis` (the media server's, else TMDB's)
- `src/matinee/tmdb.py::fetch_picture` / `IMAGES` / `IMAGE_SIZES` / `TmdbImageError`
- `src/matinee/tmdb.py::ImageGate` / `IMAGE_GATE` / `IMAGE_RATE` (50 a second, 20,000 an hour, a hold after a 429 or 503)
- `src/matinee/web/app.py::add_error_handlers`
- `src/matinee/web/common.py::Problem`
- `src/matinee/web/viewing.py::add_viewing_routes` (`POST /api/first` with the source question, `POST /api/walk`)
- `src/matinee/web/viewing.py::WalkIn` / `PickIn` / `FirstIn` (request caps; no field skips the check)
- `tests/test_user_agent.py::test_every_outbound_request_names_matinee`

### The page

- `src/matinee/web/static/js/main.js::boot` / `frontDoor` / `lockedDoor` (`GET /api/admission` first, then the setup note)
- `src/matinee/web/static/js/main.js::saidSetup` / `setupNote` (once per page load with a way in; every time without)
- `src/matinee/web/static/js/main.js::showWarning` (the stale-data strip; the stage starts beneath it)
- `src/matinee/web/static/js/main.js::showFallback` (the fallback notice after the stale-data warning)
- `src/matinee/web/static/js/main.js::start` / `freshWalk` (the source question, or the doors; nothing carried from the last walk)
- `src/matinee/web/static/js/main.js::chooseSource` / `doors` / `showFirst`
- `src/matinee/web/static/js/main.js::walkSteps` / `lastStep` (the walk's steps, which "Back" counts)
- `src/matinee/web/static/js/main.js::backTo` / `wayBack` (a question screen's one action, "‹ Back" or `Start over`, at the foot's left)
- `src/matinee/web/static/js/main.js::goTo` / `reask` / `step` (`Start` asks again; the source answer shows the doors)
- `src/matinee/web/static/js/main.js::lockStage` / `leaveTo` (drops the pick's history entries)
- `src/matinee/web/static/js/main.js::frame` / `ask` (the footnote)
- `src/matinee/web/static/js/main.js::checking` / `fadeTalk` (`READ_MS`)
- `src/matinee/web/static/js/main.js::pickLines`
- `src/matinee/web/static/js/main.js::clearForPick` / `requestPick` / `openPick`
- `src/matinee/web/static/js/main.js::pickNow`
- `src/matinee/web/static/js/main.js::pickActions` (`notThatOne`, `rollAgain`, `showPicked`, `startOver`, `backPanel`, `remember`, `household`, `hide`, `noteLink`)
- `src/matinee/web/static/js/main.js::showPicked` ("Just show me what you picked", from the reply held)
- `src/matinee/web/static/js/main.js::pickFrame` (the foot bar kept from the start on a desktop; no trail and no TMDB line; DoesTheDogDie's credit in the foot band; the panel)
- `src/matinee/web/static/js/main.js::PICK_ENTRY` / `PANEL_ENTRY` / `holdPickEntry` / `dropPickEntry` / `panelHistory` / `onBack` (the browser's back on a pick)
- `src/matinee/web/static/js/main.js::answerRow` / `filmRow` / `backPanel` (the Back panel)
- `src/matinee/web/static/js/main.js::bringBack` (a film of the run shown again, no new pick)
- `src/matinee/web/static/js/way-back.js::answerRows` / `forget` / `wayTo` / `stepBack`
- `src/matinee/web/static/js/run.js::remember` / `newestFirst` / `kept` / `asPick` (the films a run has shown; `asked` keeps a turned-away film out of the history)
- `src/matinee/web/static/js/run.js::runKey` / `shownBody` (a run's key; what the history keeps of a film shown)
- `tests/js/way-back.test.mjs`, `tests/js/run.test.mjs`
- `src/matinee/web/static/js/panel.js::pickPanel` / `place` / `swallowNextClick` / `onThePick` (the shared panel and its closing rules, a tap outside on a button or link doing its work; where it stands)
- `src/matinee/web/static/js/panel.js::OPENER` / `panelAction` (a cream action that opens the panel)
- `src/matinee/web/static/js/main.js::enter` (the start asked at the tap, the first screen after the landing)
- `src/matinee/web/static/js/main.js::topbar` (settles a landed name)
- `src/matinee/web/static/js/main.js::problem` (`keep`: the failed start's posters; "About Matinee" at the foot)
- `src/matinee/web/static/js/main.js::countText` (the films left, beside "Just pick one!")
- `src/matinee/web/static/js/main.js::loadQuips` (asked once admitted)
- `src/matinee/web/static/js/main.js::wordmark` / `startOver` (a link doing `Start over`; a new run)
- `src/matinee/web/static/js/main.js::nameTag` / `redrawTag` (the viewer and its menu's actions; drawn again after a new name or picture)
- `src/matinee/web/static/js/main.js::askPictures` (once per visit)
- `src/matinee/web/static/js/offers.js::offers` / `learnOffers` (whether a DoesTheDogDie key is set, from `/api/door`)
- `src/matinee/web/static/js/door.js::Door`
- `src/matinee/web/static/js/door.js::Door.open` (the tiles, or a new profile)
- `src/matinee/web/static/js/door.js::Door.build` (a standing marquee adopted, never rebuilt; "About Matinee" in the foot)
- `src/matinee/web/static/js/door.js::Door.talk` (a question typed onto the wall; `detail`, a body-type line beneath)
- `src/matinee/web/static/js/door.js::Door.enter` (entered once)
- `src/matinee/web/static/js/door.js::Door.leave` / `settle` / `bringBack` (the marquee leaves and returns)
- `src/matinee/web/static/js/door.js::Door.picker` (the first tailoring step for a profile just made; sets the phone's lit strip)
- `src/matinee/web/static/js/door.js::Door.fillTopics` / `topicsTrouble` (DoesTheDogDie's topics alone, their count, "Read about these on DoesTheDogDie ↗")
- `src/matinee/web/static/js/topics.js::topicButton` (a topic or a language as a letterbox that toggles, with a check mark)
- `src/matinee/web/static/js/door.js::Door.build` (DoesTheDogDie's credit, `dtddCredit`, shown on the picker and hidden on every other door screen)
- `src/matinee/web/static/js/door.js::marqueeReady` / `drawing` / `litStrip` (the drawing fetched once, its style attributes set through the style object; the phone's strip)
- `src/matinee/web/static/js/door.js::buildMarquee` / `showCount` ("Private screening" until admitted)
- `src/matinee/web/static/js/door.js::tile` / `newTile` (`.seat-label` carries the name's scrim)
- `src/matinee/web/static/js/door.js::Door.greet` / `choose`
- `src/matinee/web/static/js/door.js::Door.lock` / `refresh` / `refused`
- `src/matinee/web/static/js/door.js::Door.first` / `askName` / `taken` / `askAvatar` / `askPin` / `create` / `offerTailoring` / `done` (making a profile)
- `src/matinee/web/static/js/door.js::Door.offerTailoring` / `tailor` (the offer; the steps after the topics, on the door's own screens)
- `src/matinee/web/static/js/door.js::Door.talk` / `heldBack` (a step's answers apart from its actions; `compact`)
- `src/matinee/web/static/js/door.js::Door.pin` (a PIN asked at a tile)
- `src/matinee/web/static/js/door.js::Door.seatOf` / `enterAs`
- `src/matinee/web/static/js/door.js::Door.neverMind` (the picker's "Skip", on to the next step)
- `src/matinee/web/static/js/door.js::Door.save` (`PUT /api/profiles/{id}/topics`)
- `src/matinee/web/static/js/door-rules.js::doorLines` / `opensAtOnce` / `nameKey` / `findTaken` / `twoParts`
- `src/matinee/web/static/js/mark.js::initials` / `avatarSrc` / `mark`
- `src/matinee/web/static/js/mark.js::AVATAR_NAMES` / `avatarChoices`
- `src/matinee/web/static/js/viewer.js::SHORT_NAME`
- `src/matinee/web/static/js/viewer.js::viewerTag` (the profile menu: "My profile", "Switch profiles", "About Matinee")
- `src/matinee/web/static/js/locked.js::WALL_FADE_MS` / `bandsAt` / `WIPE_MS` (the band wipe)
- `src/matinee/web/static/js/locked.js::LockedDoor` (`show`, `place`, `measure`, `greet`, `slide`, `shut`)
- `src/matinee/web/static/js/locked.js::LockedDoor.open` / `wipe` (the opening)
- `src/matinee/web/static/js/locked.js::LockedDoor.toggle` / `give` (the eye; a word given)
- `src/matinee/web/static/door/door.webp`, `src/matinee/web/static/door/subway-tile.svg`, `src/matinee/web/static/door/eye.svg` (the locked door's art)
- `tests/js/door-rules.test.mjs`, `tests/js/locked.test.mjs`, `tests/js/mark.test.mjs`
- `src/matinee/web/static/js/flight.js::fly` (`FLIGHT_MS`, the fail-open)
- `src/matinee/web/static/js/flight.js::nameAt` / `markAt` / `cornerMark` / `copyAt` / `HANDOVER_MS` (take-off from the drawing's lettering, landing on the corner mark's)
- `src/matinee/web/static/js/about.js::openAbout` (the focus returns to what opened it)
- `src/matinee/web/static/js/about.js::close` (popstate; Escape steps back)
- `src/matinee/web/static/js/about.js::keeps` (the privacy statement, "What Matinee keeps")
- `src/matinee/web/static/js/about.js::copy` (the About page's words and links; no steering section without a key; "Good company" always; names "Something wrong?")
- `src/matinee/web/static/js/wall-grid.js::posterAcross` / `ACROSS` / `GAP`
- `src/matinee/web/static/js/wall-grid.js::wallLayout`
- `src/matinee/web/static/js/wall-grid.js::bestStride` / `repeatDistance`
- `src/matinee/web/static/js/wall-grid.js::filmIndex` / `nearestCell` / `filmAt`
- `src/matinee/web/static/js/wall-grid.js::pictureSize`
- `src/matinee/web/static/js/wall-grid.js::rankPool` (the page's order)
- `src/matinee/web/static/js/wall-grid.js::resortAnchor`
- `src/matinee/web/static/js/wall-grid.js::resortPlan`
- `src/matinee/web/static/js/hunt-plan.js::HOP_TABLE` / `hopCount`
- `src/matinee/web/static/js/hunt-plan.js::hopOffset` / `TICK_PX` (the tick)
- `src/matinee/web/static/js/hunt-plan.js::peakStep` / `limitedTime` (the speed limit)
- `src/matinee/web/static/js/hunt-plan.js::settledCamera`
- `src/matinee/web/static/js/hunt-plan.js::planHunt` / `halfSpan` (hop lengths as shares of the screen, landing off screen, no reversal)
- `src/matinee/web/static/js/hunt-plan.js::hopCell` / `placeLanding`
- `src/matinee/web/static/js/glow.js::posterGlow` / `GOLD`
- `src/matinee/web/static/js/quips.js::setFor`
- `src/matinee/web/static/js/quips.js::Deck`
- `src/matinee/web/static/js/quips.js::dealPair` / `dealBeneath`
- `src/matinee/web/static/js/wall.js::Wall`
- `src/matinee/web/static/js/wall.js::Wall.show` / `fadeIn` / `clear` / `whenStill`
- `src/matinee/web/static/js/wall.js::Wall.endPick`
- `src/matinee/web/static/js/wall.js::Wall.hunt` / `travel` / `jump` / `readyToHunt` / `settle` / `hop` (`quick`: a film brought back cuts to its poster)
- `src/matinee/web/static/js/wall.js::Wall.stepBack` / `grownScale`
- `src/matinee/web/static/js/wall.js::Wall.useSharp` (the front element)
- `src/matinee/web/static/js/wall.js::Wall.bringForward`
- `src/matinee/web/static/js/wall.js::Wall.dress` / `glowShadow` / `glowAt`
- `src/matinee/web/static/js/wall.js::glowOf`
- `src/matinee/web/static/js/wall.js::Wall.usePictures` / `posterUrl` (and the `fromTmdb` flag it sets)
- `src/matinee/web/static/js/pictures.js::posterUrl` / `backdropUrl` / `posterPaths` / `corsImage` (`TMDB_WIDTHS`)
- `src/matinee/web/static/js/wall.js::Wall.putBack` / `returnPoster` / `liftDim` / `settleBack`
- `src/matinee/web/static/js/wall.js::Wall.relayout` / `makeTiles`
- `src/matinee/web/static/js/wall.js::Wall.prepare` (the re-sort's wait)
- `src/matinee/web/static/js/wall.js::Wall.frame` (the drift, `DRIFT_PX_S`)
- `src/matinee/web/static/js/wall.js::Wall.place` / `lay` / `picture` / `request` (`BLANK`)
- `src/matinee/web/static/js/wall.js::Wall.resort` / `slide` / `depart`
- `src/matinee/web/static/js/api.js::del`
- `src/matinee/web/static/js/api.js::call` (a device no longer admitted goes back to the door)
- `src/matinee/web/static/js/pick.js::showPick` / `huntLift`
- `src/matinee/web/static/js/pick.js::goldLine`
- `src/matinee/web/static/js/pick.js::bringOut`
- `src/matinee/web/static/js/pick.js::toRest` (`BEAT_MS`, `STILL_HOLD_MS`)
- `src/matinee/web/static/js/pick.js::fetchFilm` / `picture` (the card asked with `?door=`; the backdrop waits for the card under `tmdb`)
- `src/matinee/web/static/js/pick.js::restingPoster`
- `src/matinee/web/static/js/pick.js::rest` / `factsUnderLine` / `lineSaid`
- `src/matinee/web/static/js/pick.js::settle` / `fit` / `posterLink` / `landed` (the poster as the link, above its strip)
- `src/matinee/web/static/js/pick.js::rankLine` / `tagList` / `facts` (the rank and tags)
- `src/matinee/web/static/js/fuse.js::lightFuse` / `fuseTimeline`
- `src/matinee/trees.py::_self_destruct` / `_one_self_destruct`
- `src/matinee/web/static/js/pick.js::feature`
- `src/matinee/web/static/js/pick.js::underLine` / `backAction` / `fillBar` / `pickBar` (the foot bar: "Rate it" after "Something wrong?", "Hide film" beside "Show me another")
- `src/matinee/web/static/js/pick.js::showNoFilm`
- `src/matinee/web/static/js/pick.js::firstPickReveal`
- `src/matinee/web/static/js/pick.js::showCredit` (DoesTheDogDie's credit in the foot band, for a line naming one of its topics)
- `src/matinee/web/static/js/pick.js::lookUp` ("Look it up on DoesTheDogDie ↗")
- `src/matinee/web/static/js/note.js::noteLink` / `kindChoices` / `walkOf` ("Something wrong?" in the panel; one sort tick stands; the walk and run a note records; `walk_gone` leaves Save disabled)
- `src/matinee/web/static/js/credits.js::credits` (the door's credit line: DoesTheDogDie's credit, built hidden)
- `src/matinee/web/static/js/credits.js::dtddCredit` (built hidden) / `dtddFoot` (the pick's foot band, built hidden) / `dtddBeside` (after an unchecked film's note)
- `src/matinee/web/static/js/credits.js::aboutLink` ("About Matinee"; `around`, the door)
- `src/matinee/web/static/js/dom.js::h` (text nodes only)
- `src/matinee/web/static/js/type.js::typeLine` (`shown`: a gold line kept while the rest types beneath)
- `src/matinee/web/static/manifest.webmanifest`
- `src/matinee/web/static/css/matinee.css` `:root` (the standard's colour tokens, `--shade`, `--band-fade`)
- `src/matinee/web/static/css/matinee.css` `.stage` (starts beneath the warning strip, `--warning-h`)
- `src/matinee/web/static/css/matinee.css` `.warning-strip` (the stale-data warning)
- `src/matinee/web/static/css/matinee.css` `.talk > .setup-lines`, `.talk.setup` (the setup note)
- `src/matinee/web/static/css/matinee.css` `.door-foot > .about-link`, `.bottombar > .about-link` ("About Matinee" at the foot's middle)
- `src/matinee/web/static/css/matinee.css` `.way-back` (a question screen's way back, at the foot's left; the pick's place on a phone)
- `src/matinee/web/static/css/matinee.css` `.action`, `.action.rose`, `.action.petrol`, `.action.cream` (gold is the base rule)
- `src/matinee/web/static/css/matinee.css` `.letterbox` (one size)
- `src/matinee/web/static/css/matinee.css` `.answers`, `.answers.many` (the doors run across and wrap)
- `src/matinee/web/static/css/matinee.css` the scrims: `.line:not(.locked-line, .viewer-line) > :is(.ack, .ask)`, `.countdown`, `.note`, `.footnote`, `.count`, `.seat-label`, `.feature-text`, `.rank`, `.facts .household`
- `src/matinee/web/static/css/matinee.css` the bands: `.topbar::before`, `.bottombar::before`, `.door-foot::before`, `.stage.at-door.behind-about::before`
- `src/matinee/web/static/css/matinee.css` `.showing` (the pick's left column)
- `src/matinee/web/static/css/matinee.css` `.topic-list`, `.topic`, `.topic-foot` (the picker's topics)
- `tests/test_design_standards.py::declarations` / `built` / `enclosing` / `PERMITTED` / `ARTWORK` (the standard's mechanical rules)
- `src/matinee/web/static/css/matinee.css` reduced-motion rules (the marquee and the door's words change at once)
- `src/matinee/web/static/css/matinee.css` `.wall`, `.wall-tiles`, `.tile` (`--tile`, the one strength; the dark cell)
- `src/matinee/web/static/css/matinee.css` `.marquee` (the top fade, the short windows' scaling)
- `src/matinee/web/static/css/matinee.css` `.marquee.lifted`, `.stage.leaving`, `.flying-name` (going in)
- `src/matinee/web/static/css/matinee.css` `.mq-drawings`, `.mq-frame`, `.mq text`, `@keyframes mq-chase`, `.mq-strip`
- `src/matinee/web/static/css/matinee.css` `.door-wall`, `.door-talk`, `.door-foot`
- `src/matinee/web/static/css/matinee.css` `.picker`
- `src/matinee/web/static/css/matinee.css` phone door: `.marquee` sizes, `.marquee.compact` (the lit strip)
- `src/matinee/web/static/css/matinee.css` `.credits`, `.bottombar .credits`, `.inline-link`
- `src/matinee/web/static/css/matinee.css` `.stage.behind-about`, `.about`, `.about-wordmark`, `.about-panel`
- `src/matinee/web/static/css/matinee.css` `.pick-line` (size, four lines reserved), `.pick-line.rested`, `.hushed`
- `src/matinee/web/static/css/matinee.css` `.poster-link`, `.poster-strip`
- `src/matinee/web/static/css/matinee.css` `.facts`, `.rank`, `.rank-words`, `.rank-by`, `.tags`, `.tag`
- `src/matinee/web/static/css/matinee.css` `.note-form` ("Something wrong?"'s form)
- `src/matinee/web/static/css/matinee.css` `.pick-panel`, `.panel-head`, `.panel-title`, `.panel-close`, `.panel-body`, `.panel-lede`, `.panel-section`, `.panel-row`, `.answer-row`, `.films`, `.film-row`, `.panel-foot`, `.action.open`
- `src/matinee/web/static/css/matinee.css` `.foot-bar`, `.bar-left` (one row; two rows from 601 to 800 px; a phone's rows), desktop `.showing` and `.feature` (the details scroll with a fade)
- `src/matinee/web/static/css/matinee.css` `.bar-right` (DoesTheDogDie's credit at the foot bar's right end)
- `src/matinee/web/static/css/matinee.css` `.action.lead` ("Show me another": thread always, rose glow)
- `src/matinee/web/static/css/matinee.css` `.beside-credit` (DoesTheDogDie's credit after an unchecked film's note)
- `tests/test_design_standards.py::PERMITTED` (the panel's ×, `answerRow`, `filmRow`, `posterLink`, `dtddBeside`, `dtddFoot`)
- `src/matinee/web/static/css/matinee.css` `.talk > .footnote`
- `src/matinee/web/static/css/matinee.css` `a.wordmark`, `.corner-mark` (64 px on a desktop, 40 px on a phone)
- `src/matinee/web/static/css/matinee.css` `.just-pick-row` (the count beside the button)
- `src/matinee/web/static/css/matinee.css` `.mark`, `.seats`, `.seat` (the tiles; the short window's sizes)
- `src/matinee/web/static/css/matinee.css` `.avatar-choices`
- `src/matinee/web/static/css/matinee.css` `.viewer`, `.viewer-menu` (the phone's initials)
- `src/matinee/web/static/css/matinee.css` the locked door: `.locked`, `.subway`, `.door-frame`, `.locked-door`, `.slot`, `.peek`, `.line.locked-line`
- `src/matinee/web/static/blank.svg` (a tile with no picture)

### My profile, the pick's new actions and the welcome

- `src/matinee/web/static/js/main.js::myProfile` / `saveAvatar` (opening My profile over the theatre; its parts and actions)
- `src/matinee/web/static/js/main.js::keepShown` / `household` / `hideAndRoll` / `undoHide` / `standUndo` (the history kept; the household's ratings; a hide, its roll and "Undo")
- `src/matinee/web/static/js/main.js::welcomeIfNew` / `whatsNew` / `allSet` / `tailorScreen` / `enter` (the one-time welcome, its steps in the theatre and "You're all set up.")
- `src/matinee/web/static/js/main.js::nothingLeft` (the empty first question and "Change my settings")
- `src/matinee/web/static/js/profile.js::openProfile` / `showPage` / `close` / `cover` / `frame` / `part` / `PARTS` / `DELETE_LINE` (the page, its history entry, its parts' words)
- `src/matinee/web/static/js/profile.js::nameEditor` / `avatarEditor` / `deleter` / `jump` (rename, picture, delete, the jumps)
- `src/matinee/web/static/js/profile.js::records` / `fill` / `fillPart` / `refreshFilms` / `profileLayer` (the parts filled from the viewer's records, and again after a change)
- `src/matinee/web/static/js/settings.js::settingsPart` / `ROWS` / `FLOORS` / `RATED` / `SHARING` (the rows' words and answers; saves queued in order)
- `src/matinee/web/static/js/settings.js::row` / `singleRow` / `languagesRow` / `topicsRow` / `topicList` / `chooser` (a row, its picture and open panel; it stays open, saying "✓ Saved", until "Done")
- `src/matinee/web/static/js/settings.js::languageName` / `languageOrder` (named through the browser, `cn` as Cantonese; the browser's language first)
- `src/matinee/web/static/js/settings.js::heardWords` / `src/matinee/web/static/js/pick.js::heardLine` (the language line's words; the line beneath the rank)
- `src/matinee/web/static/js/settings.js::languagesFirst` / `moreLanguages` (the 15 most-held languages, the browser's and the ticked first; "+ More languages" shows the rest)
- `src/matinee/web/static/js/topics.js::topicButton`
- `src/matinee/web/static/js/credits.js::dtddSetting` (DoesTheDogDie's credit under the topics row)
- `src/matinee/web/static/js/cases.js::filmCase` / `CASES` / `tiers` / `ratedPart` (a film in its case, around a poster already on the page where given; the rated tiers)
- `src/matinee/web/static/js/pick.js::dress` / `redress` / `settle` / `CASE_RATIO` (a rated pick rests in its case; a rating on the pick dresses it at once)
- `src/matinee/web/static/js/cases.js::shimmerOnce` / `mostlyOnScreen` / `glowUnder` / `SETTLE_MS` (the gold case's light)
- `src/matinee/web/static/js/cases.js::hiddenPart` / `hiddenUntil` (the hidden films, their return, "Bring back")
- `src/matinee/web/static/js/shelves.js::shownPart` / `dayShelf` / `runShelf` / `runGroups` / `runCaption` / `didWith` / `byDay` / `dayCount` (the day shelves)
- `src/matinee/web/static/js/overlay.js::openOverlay` / `load` / `overlayPanel` / `posterSide` / `aboutFilm` / `overlayActions` (the poster overlay)
- `src/matinee/web/static/js/overlay.js::keptWalk` / `noteWalk` / `FROM_PICKS` (how a film was found; a note from the overlay names no run)
- `src/matinee/web/static/js/tailor.js::tailorSteps` / `OFFER` / `STEPS` / `stepKeys` / `stepFor` / `singleStep` / `languagesStep` / `topicsStep` / `WELCOME` / `WHATS_NEW` / `ALL_SET` (the tailoring steps and the welcome's words)
- `src/matinee/web/static/js/rate.js::rateLink` / `ratePanel` / `fitted` / `roomLeft` / `oneLine` / `length` / `MAX_REVIEW` / `autosaver` / `PAUSE_MS` ("Rate it" and its field's rules; the review saves itself)
- `src/matinee/web/static/js/hide.js::hideLink` / `undoLink` / `LENGTHS` ("Hide film" and "Undo")
- `src/matinee/web/static/js/household.js::householdLine` / `nameButton` / `readingPanel` / `personRow` / `focusShown` (the household's line and reading panel)
- `src/matinee/web/static/js/ratings.js::ANSWERS` / `said` / `answerOf` (the five answers; the shared sentence)
- `src/matinee/web/static/js/pick.js::facts` / `rest` / `toRest` (the household's line among the facts; "Undo" fades before rest)
- `src/matinee/web/static/js/mark.js::mark` (a `panel` size)
- `src/matinee/web/static/css/matinee.css` `--house`, `.household`, `.reading-card`, `.person-row` (the household's colour, one job)
- `src/matinee/web/static/css/matinee.css` `.ticked`, `.rate-answers`, `.review-field`, `@keyframes shake`, `.undo-link`, `.bar-centre`
- `src/matinee/web/static/css/matinee.css` `--felt`, `--placard`, `.my-profile`, `.pin`, `.part`, `.placard`, `.jump-bar`, `.part-note`
- `src/matinee/web/static/css/matinee.css` `.set`, `.sethead`, `.stitle`, `.thumb`, `.thumb-inner`, `.setbody`, `.set-choices`, `.set-band`
- `src/matinee/web/static/css/matinee.css` `.case`, `.plate`, `.win`, `.sheen`, `.bloom`, `.tier`, `.rated-film`, `.hidden-film`
- `src/matinee/web/static/css/matinee.css` `.day`, `.day-stub`, `.day-head`, `.day-peek`, `.chev`, `.run`, `.shown-film`, `.shown-did`
- `src/matinee/web/static/css/matinee.css` `.overlay`, `.overlay-poster`, `.overlay-words`, `.overlay-actions`
- `src/matinee/web/static/css/matinee.css` `.door-talk.tailoring`, `.tailor-talk`, `.welcome`, `.welcome-scrim`, `.topbar.lit`
- `src/matinee/web/static/profile/curtain-wide.webp`, `src/matinee/web/static/profile/curtain-tall.webp` (the curtains)
- `src/matinee/web/static/profile/case-gold.webp`, `src/matinee/web/static/profile/case-silver.webp`, `src/matinee/web/static/profile/case-neutral.webp`, `src/matinee/web/static/profile/case-weathered.webp`, `src/matinee/web/static/profile/case-distressed.webp` (the five cases)
- `tests/js/profile.test.mjs`, `tests/js/settings.test.mjs`, `tests/js/cases.test.mjs`, `tests/js/shelves.test.mjs`, `tests/js/overlay.test.mjs`, `tests/js/tailor.test.mjs`, `tests/js/rate.test.mjs`, `tests/js/hide.test.mjs`, `tests/js/ratings.test.mjs`
- `tests/test_design_standards.py::PERMITTED` / `past_parameters` (the household's text buttons, "Undo", My profile's cases and rows)
- `tests/test_spec_map.py::problem` (every handle here names a file and a symbol defined in it)

### Deployment

- `Dockerfile` (one worker, uid 1000, `/state`, `DATA_DIR`)
- `.dockerignore`
- `example.env` (every setting of section 13, none filled in)
- `tests/test_example_env.py::test_example_env_names_every_setting_the_spec_lists_and_fills_in_none`
