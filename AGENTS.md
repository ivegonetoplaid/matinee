# Matinee — Instructions for Agents

These instructions are for any AI agent working in this repository, whether it
is changing Matinee or installing it for someone. Read the whole file before you
act. The rules near the end bind every agent.

## What Matinee is

Matinee is a film picker for a home media library. Instead of a grid of posters,
it asks a viewer two or three questions in plain language and hands them one
film, presented as tonight's showing.

How a viewing goes:

1. A viewer opens or makes a profile on this device. There are no accounts.
   An installation may lock the site behind a door word first.
2. While the library can be used, Matinee first asks "what are we choosing from
   tonight?": only what the library holds, only films it lacks, or both. That
   answer bounds the whole walk and is asked again at every start.
3. Matinee asks "So, what are we in the mood for?" and offers its doors: Comedy,
   Drama, Horror, For the kids, Something to fall asleep to, and the rest.
4. Each door leads to a question tree (or a mode), which asks a question or two
   more about that mood.
5. Matinee draws one film from what is left. The pick screen offers
   `Not that one` (draw again), "More on Seerr ↗" or "More on TMDB ↗" (the film's
   page, in a new tab) and `Start over`. Matinee does not start the film; the
   viewer plays it on their media server as usual.

Where the films come from:

- **The library.** Matinee reads a Jellyfin or a Plex library, or runs with no
  library at all. It only ever reads.
- **The labels.** `data/labels.json` places roughly 10,300 films (TMDB's
  most-voted films, and more) behind doors and into kinds. Matinee offers the
  films the library holds and the labelled films it does not.
- **The offline film table.** `tools/rebuild_table.py` builds one SQLite file in
  the data directory from the library, TMDB and the shipped tag-genome scores.
  It runs nightly at `REBUILD_TIME` (`--daily`). The server reads that table and never
  queries TMDB or the genome while a viewer waits.
- **DoesTheDogDie**, optionally. A viewer may name topics they would rather not
  see (a dog dying, say). When a pick is drawn, Matinee looks that one film up
  and draws again if it carries one of the viewer's topics.

The behaviour Matinee promises is written down in `docs/spec/matinee.md`. That
spec is the contract: when it and the code disagree, the spec says how to read
the disagreement.

## Where things live

- `src/matinee/`: the engine, the film table, profiles, the DoesTheDogDie check
  and the web server. `src/matinee/web/static/` is the page; it has no build
  step.
- `data/trees/` and `data/modes/`: the question trees and modes, as data.
- `data/labels.json`, `data/house_overrides.json`, `data/answer_key.json`,
  `data/fixtures/`: the labels, the hand-set pins, and what the trees are
  checked against.
- `tools/`: the nightly rebuild, the tree checker, the notes tool and the
  builders for the shipped genome files.
- `docs/spec/`: the specification.

## If you are changing Matinee

What it needs:

- Python 3.12 or newer (the image uses 3.13) and Node with npm.
- Run `./bootstrap.sh` once. It makes `.venv`, installs the development tools
  and the page's lint tools, and installs the pre-commit hooks.
- Run `./check.sh` before you report any change as done. It is the standards
  gate: formatting, lint, complexity, type checks, the page's lint and tests,
  and the test suite. A change that does not pass it is not finished.

What you must follow:

- **`CODING_STANDARDS.md` binds every line of code.**
- **`DESIGN_STANDARDS.md` binds every surface** a viewer sees.
- **Amend `docs/spec/` in the same change as any behaviour change.** A change
  that alters what Matinee does, and leaves the spec saying the old thing, is
  incomplete.
- **Never bypass the pre-commit hooks.** When a gate blocks a commit, fix the
  cause.
- **Keep working notes out of the repository.** Build reports, review rounds and
  scratch files do not belong here. The repository holds code and the
  contracts the code honours.
- **Build for any library.** One household's library is only ever a test.
  Design and size doors, kinds, answer wording and every threshold against the
  films the shipped labels name, and report a count for that set first, then
  any single library beside it. A kind, an answer or a rule that works only
  because of one library's mix is a defect. Before you propose wording or a
  build for a door, check where every film the labels place behind that door is
  reached.
- **The labels alone decide which doors and kinds a film belongs to.** Never
  place a film behind a door by its genome scores, genre tags or a catch-all
  rule, never explain a result by them, and never add such a rule as a
  fallback. The one exception is the spec's waiting room: a film the labels do
  not list waits behind the doors its TMDB genres name until it is labelled.
  Every film behind a door belongs to at least one of that door's kinds.
- **Keep every film reachable.** Every film must be reachable through at least
  one complete path of answers behind some door. A film leaves a door only when
  it barely fits that door and has another home. `tools/check_trees.py` holds
  the trees to that and to the answer key, against a film table the rebuild
  wrote. A rule change must leave it passing.

## If you are installing Matinee

Ask your user these questions before you write any settings. Each one changes
what Matinee does.

1. **Which media server: Jellyfin, Plex, or neither?** Matinee reads one. With
   neither, it picks from the labelled films alone and the viewer finds them
   elsewhere. Never set both.
2. **Do they run Seerr?** With Seerr, the pick's link opens the film on their
   Seerr. Without it, the link opens the film's TMDB page.
3. **Do they want DoesTheDogDie content warnings?** That needs their own
   DoesTheDogDie API key. Without one, Matinee runs and offers nothing that
   needs DoesTheDogDie.
4. **Do they want a door word?** A door word locks the site until a device
   types it once. Matching is relaxed by default (case and punctuation ignored,
   one typo forgiven) or strict.
5. **Where should the data directory live?** It holds the film table, every
   profile, the TMDB cache and the door's secret. It must survive restarts and
   upgrades, and it is the thing to back up.
6. **When should the nightly rebuild run?** Any quiet time, as `HH:MM` in
   `REBUILD_TIME`, in the time zone `TZ` names (04:30 when unset).

The keys and settings:

- **`TMDB_TOKEN` is required.** It is a TMDB API read access token from the
  user's own TMDB account. Without it the rebuild fetches nothing and Matinee
  has no films to offer.
- **`DATA_DIR` is required.** The server refuses to start without it. The
  image already sets it to `/state`; mount the data directory there.
- Optional: `JELLYFIN_URL` with `JELLYFIN_API_KEY`, or `PLEX_URL` with
  `PLEX_TOKEN`; `SEERR_URL`; `DTDD_API_KEY`; `DOOR_WORD`, `DOOR_MATCH`,
  `DOOR_GREETING`; `POSTERS_FROM`; `TMDB_RATE`; `REBUILD_TIME`; `TZ`. Section 13 of the spec lists
  every setting and what it takes. An optional service is on when its setting
  is filled in and off when it is empty.

The steps:

1. Copy `example.env` to `.env`, uncomment the lines the answers above call
   for, and write each value straight after the `=`, with no spaces and no
   quotes. Matinee reads its settings from its environment and never opens
   `.env` itself, so the file must be handed to each process that runs.
2. From the repository's folder, make `./state` writable by uid 1000 (the
   image's user) and start both processes with the shipped `compose.yaml`:
   `mkdir -p state && sudo chown 1000:1000 state && docker compose up -d --build`
   It runs the server on port 8000 and the rebuild, which rebuilds at once and
   then every night at `REBUILD_TIME`. For a data directory elsewhere, change
   `./state` in both `volumes` lines. The first fetch takes a while; it saves
   the film table as it goes, so the site starts picking as films arrive, and
   the site's setup note says what it sees meanwhile.
3. Put the server behind a reverse proxy that serves it over HTTPS. The image
   trusts forwarded headers from any address, and the door word's cookie is
   only sent over HTTPS.

Without Docker, install the package into a virtualenv (`pip install -e .`),
load the file into the shell with the README's line, which takes each value
as written, the way Docker does (`. ./.env` breaks on a value with a space),
and run
`uvicorn --factory matinee.web.main:build --workers 1 --no-access-log` and
`python tools/rebuild_table.py --daily` from the repository root, each in
a shell that loaded the file.

Run exactly one server worker. Every DoesTheDogDie limit and hold lives in the
process, so a second worker would double them.

A household that disagrees with where the shipped labels put a film can keep an
`overrides.json` in the data directory, in the labels file's shape. Matinee
reads it and never writes it, and an upgrade never touches it (spec 2.6).

## Rules for every agent

- **Never write to the user's media server.** Every request Matinee makes to
  Jellyfin or Plex is a read. Its own state lives in its own store.
- **Never commit a key, a `.env` file or anything that identifies a home.** That
  includes hostnames, LAN addresses, internal domains, people's names and file
  paths from someone's machine. Server addresses and keys arrive as settings.
- **Never put a key or a setting's secret in a log, a URL or a response to a
  browser.**
- **Never commit TMDB records or raw MovieLens files.** That covers the TMDB
  cache, the film table and any ordering derived from TMDB.
- **Never fetch DoesTheDogDie data ahead of a pick**, keep its votes, or build a
  score from it.
- **Never remove a credit or a required notice** (see below).
- **Never set both media servers**, and never run more than one server worker.

## Data terms

Each source's terms are part of Matinee's design. These are the terms at the
time of writing (2026-10-05). Terms change: read the source itself before you
change how Matinee uses its data.

### TMDB

Source: TMDB API Terms of Use, https://www.themoviedb.org/api-terms-of-use
(last updated 2023-10-20).

- **Cache nothing longer than six months.** The terms forbid caching any
  information obtained from TMDB for longer than six months (section 1.C).
  Matinee refetches a record at 150 days and drops any record 183 days old.
- **Credit TMDB.** The terms require the notice that the application uses TMDB
  and the TMDB APIs but is not endorsed, certified or otherwise approved by
  TMDB, and the TMDB logo, less prominent than the application's own marks
  (section 3). Matinee shows "This product uses the TMDB API but is not
  endorsed or certified by TMDB." and the logo on its About page, and the logo
  in its credit line on a desktop.
- **No commercial use without TMDB's agreement.** Deriving revenue from TMDB
  content, directly or indirectly, needs a separate written agreement with TMDB
  (section 2.A).

### DoesTheDogDie

Source: DoesTheDogDie API Terms of Service, https://www.doesthedogdie.com/api/terms
(version 1.0, effective 2026-08-07), which incorporate its Terms of Use,
https://www.doesthedogdie.com/terms (last modified 2026-08-07).

- **One film at a time.** The terms forbid systematically downloading,
  harvesting or extracting the data, or reconstructing any substantial part of
  it (section 3). Look a film up only when it has been drawn for a pick. Never
  fetch ahead and never fetch in bulk.
- **Cache only for speed, and for at most 30 days.** Data may be cached locally
  only to improve the application's performance, must be refreshed at least
  every 30 days, and must never stand in for querying the API (section 3).
  Matinee keeps a film's item id (or that it has none) and the topic list in
  memory for at most 30 days, and nothing else. A restart clears both.
- **Build nothing from it.** The terms forbid using the API to train or improve
  any model, classifier or automated detection system (section 3). Never build
  a score from its data and never keep its votes.
- **Never claim it is complete.** The data must not be presented as complete,
  verified or guaranteed (section 13.3). Matinee's About page says the check is
  best effort and a film nobody has voted on cannot be checked.
- **Credit it.** "Powered by DoesTheDogDie.com", visible and linked to
  `https://www.doesthedogdie.com`, wherever its data is shown (section 6).
- **One key per installation.** Each household uses its own key; the terms
  forbid letting anyone else use your credentials (section 3). Matinee stays
  under the free tier's published rate.
- **Its free tier is non-commercial.** It may not serve anything that charges
  its users, earns from advertising, sponsorship or data, or runs for a
  for-profit business (section 9.1).
- **The key's holder carries the terms.** Whoever sets `DTDD_API_KEY` has
  accepted these terms for their installation, including keeping a privacy
  policy for it (section 2.4(b)).

### MovieLens tag genome

Source: the MovieLens dataset README, "Usage License",
https://files.grouplens.org/datasets/movielens/ml-latest-README.html

- **Never commit the raw data.** No installation downloads MovieLens. Matinee
  ships small files derived from the tag genome (`data/genome.json`,
  `data/reference.json`), and each states the dataset's conditions in its
  `licence` field.
- **Redistribute only under the same conditions.** The licence allows
  redistributing the data, transformations included, only under the same
  licence conditions.
- **No commercial use** without permission from a faculty member of the
  GroupLens Research Project, and no stated or implied endorsement by the
  University of Minnesota or GroupLens.
- **Credit the papers.** F. Maxwell Harper and Joseph A. Konstan (2015), for the
  MovieLens datasets, and Jesse Vig, Shilad Sen and John Riedl (2012), for the
  tag genome. The full citations are in `README.md`.
