# Matinee

Tonight's film, picked for you.

Matinee is a film picker for a home media library. Instead of a grid of posters
and twenty minutes of scrolling, it asks two or three questions in plain
language (what are we choosing from, what are we in the mood for, then a
question or two about that mood) and hands you one film, presented as
tonight's showing. Don't fancy it? Roll again.

It reads your Jellyfin or Plex library, TMDB and a slice of the MovieLens tag
genome, and writes to none of them. No library? It still works: it picks from
roughly 10,000 of the films TMDB's users have voted on most.

- [What you need](#what-you-need)
- [Install it](#install-it)
- [The first few minutes](#the-first-few-minutes)
- [Why do I have to download all this TMDB data myself?](#why-do-i-have-to-download-all-this-tmdb-data-myself)
- [Where films belong](#where-films-belong)
- [Running it day to day](#running-it-day-to-day)
- [Development](#development) · [Data and credits](#data-and-credits) · [Licence](#licence)

## What you need

**Required**

- **A TMDB API key.** Free. Make an account at
  [themoviedb.org](https://www.themoviedb.org), then under
  [Settings → API](https://www.themoviedb.org/settings/api) copy the long
  **API Read Access Token** (not the short API key). This is where Matinee gets
  every film's details and posters.
- **Somewhere to run it.** Docker is easiest. Without Docker you need Python
  3.12 or newer.
- **A folder Matinee can call its own** for its film table, profiles and
  fetched TMDB records. Back it up; it's the only state Matinee keeps.

**Optional add-ons**, each switched on by filling in its setting:

- **Your library: Jellyfin _or_ Plex** (never both). Matinee only ever reads it.
  Jellyfin wants its address and an API key (Dashboard → API Keys). Plex wants
  its address and your
  [Plex token](https://support.plex.tv/articles/204059436-finding-an-authentication-token-x-plex-token/).
  With a library, every walk starts by asking whether to pick from what you
  have, from what you don't, or from both.
- **Seerr** (Overseerr or Jellyseerr): each pick links to the film on your
  Seerr, where you can request it. Without it, the link goes to TMDB.
- **DoesTheDogDie**: with your own API key from
  [DoesTheDogDie](https://www.doesthedogdie.com), each viewer can keep a list
  of things they'd rather not see, and every pick is checked against it before
  it's shown. Without a key there's no list and no check.
- **A door word**, if your Matinee faces the internet: a device types it once
  before it sees anything.

## Install it

1. **Get the code.**

   ```sh
   git clone <this repository> matinee
   cd matinee
   ```

2. **Write your settings.** Every setting lives in one file.

   ```sh
   cp example.env .env
   ```

   Open `.env`, uncomment the lines you need (remove the `# `) and write each
   value straight after the `=`, with no spaces and no quotes. The file
   explains every setting. The least that starts Matinee is `DATA_DIR` and
   `TMDB_TOKEN` (with Docker Compose, leave `DATA_DIR` commented out: the
   compose file below sets it, and your data lives in `./state`). Never commit
   `.env`.

3. **Start it.** Matinee is two processes from one image: the **server** (the
   site) and the **rebuild** (which fetches film details and builds the film
   table, then again every night). Both read the same `.env` and the same data
   folder. With Docker Compose, save this as `compose.yaml` beside `.env`:

   ```yaml
   services:
     matinee:
       build: .
       image: matinee
       env_file: .env
       environment:
         DATA_DIR: /state
       volumes:
         - ./state:/state
       ports:
         - "8000:8000"
       restart: unless-stopped
     rebuild:
       image: matinee
       env_file: .env
       environment:
         DATA_DIR: /state
       volumes:
         - ./state:/state
       command: python tools/rebuild_table.py --daily 04:30
       restart: unless-stopped
   ```

   ```sh
   mkdir -p state && sudo chown 1000:1000 state   # the image runs as uid 1000
   docker compose up -d --build
   ```

   Then open `http://<your server>:8000`.

   Inside the image the data folder is `/state`, so the compose file sets
   `DATA_DIR` and your data lives in `./state`. Run exactly one server worker (the image does): every
   DoesTheDogDie limit lives in that one process.

   **Facing the internet?** Put Matinee behind a reverse proxy that serves it
   over HTTPS, and set a `DOOR_WORD`. The door's cookie is only ever sent over
   HTTPS.

   **Without Docker:**

   ```sh
   python3 -m venv .venv && .venv/bin/pip install -e .
   set -a; . ./.env; set +a           # Matinee reads its environment, not the file
   .venv/bin/python tools/rebuild_table.py --daily 04:30 &
   .venv/bin/uvicorn --factory matinee.web.main:build --workers 1 --port 8000
   ```

## The first few minutes

The first rebuild has the most to do: it fetches a TMDB record for every
film Matinee knows (about 10,300, plus anything in your library it doesn't), at
30 a second by default. That takes around six minutes. You don't have to wait
for all of it:

- **With a library**, your own films can be picked within seconds: the rebuild
  saves your library before it fetches anything.
- **Without one**, picks start in about a minute. The rebuild fetches the
  most-voted films first and saves as it goes, so the choice grows while it
  works.

Until then, and whenever something's off, Matinee opens with a short **setup
note** saying what it sees, in plain words: still fetching, your library not
answering, a setting it can't use. It never lets you into an empty room. If
the rebuild can't fetch at all, the note says why:

- **No TMDB key set**, or **TMDB turned the key down**: fix `TMDB_TOKEN` in
  `.env` and run `docker compose up -d` (it recreates a service whose settings
  changed; without Docker, restart the rebuild).
- **TMDB isn't answering**: it tries again at the next nightly run; run
  `docker compose restart rebuild` to try sooner.

The logs say the same, plus one line with Matinee's whole state at start and
whenever it changes: `docker compose logs matinee` and
`docker compose logs rebuild`.

## Why do I have to download all this TMDB data myself?

Because the labels can travel and TMDB's data can't.

What ships with Matinee is its own work: which films go behind which door, and
what kind of film each one is, for about 10,300 films. That's the opinionated
part, and it's Matinee's to share. The film details themselves (titles, posters,
synopses, ratings, age ratings) belong to TMDB. TMDB's
[terms](https://www.themoviedb.org/api-terms-of-use) let an application keep
that data for six months at most, and the licence they grant can't be passed
on. A copy shipped in this repository would break both: it would go stale past
six months, and it would hand out TMDB's content as Matinee's own.

So each Matinee fetches the details under its own free key, keeps them no
longer than TMDB allows, and refreshes them every night. Keep the nightly
rebuild running: it refetches each record before it's six months old. If it
ever falls behind, Matinee keeps picking but shows a warning on every screen
until a rebuild catches up.

## Where films belong

Matinee is opinionated about one thing: where films belong. Each film sits
behind the doors it truly fits, and no more. When every film may belong
everywhere, as with TMDB's keywords, a horror search turns up a cartoon. We
would rather be wrong now and then than vague all the time.

Disagree with a call? Override it on your own install: your Matinee will sort
the way you see it, and updates never undo it. Write an `overrides.json` in
your data folder, in the same shape as `data/labels.json`. A film you name
there takes its whole placement from your file (a film for the kids needs both
its kinds and its age band):

```json
{"format": 2,
 "trees": {"western": {"kinds": {"11969": []}},
           "kids": {"kinds": {"9340": ["adventure"]}, "bands": {"9340": "family"}}}}
```

Run `docker compose restart matinee` to read it; the next rebuild fetches any film it names that
Matinee didn't know. If the file can't be used, the setup note says why and
Matinee sorts as it ships until it's fixed. The spec
(section 2.6) has every detail.

If you think your call is right for everyone, open a **Sorting suggestion** in
the issue tracker and paste in your override file. I read every one. Some I'll
take and some I won't. That's the deal with an opinionated sort, and it's never
personal.

## Running it day to day

- `tools/notes.py`, run inside the image against the data folder, goes through
  viewers' "Something wrong with this pick?" notes, clears a forgotten PIN, and
  clears DoesTheDogDie topics kept after a key was removed:
  `docker compose exec matinee python tools/notes.py list`.
- To change a setting, edit `.env` and run `docker compose up -d`: it recreates
  each service whose settings changed. (A plain `restart` keeps the old ones.)
- To update, `git pull`, then `docker compose up -d --build`. Your data folder
  and `overrides.json` are untouched.
- Everything Matinee promises is written down in
  [`docs/spec/matinee.md`](docs/spec/matinee.md).

## Development

```sh
./bootstrap.sh     # venv, dev tools, pre-commit hooks
./check.sh         # the standards gate
```

Want to help? Read [`CONTRIBUTING.md`](CONTRIBUTING.md). AI agents start at
[`AGENTS.md`](AGENTS.md).

The layout, briefly:

- `src/matinee/`: the engine, the film table, profiles, the DoesTheDogDie
  check and the web server; `src/matinee/web/static/` is the page.
- `data/`: the question trees and modes, the labels, the shipped genome
  scores, and what the trees are checked against.
- `tools/`: the nightly rebuild, the tree checker, the notes tool and the
  builders for the shipped genome files.
- `docs/spec/`: the specification.

## Data and credits

This product uses the TMDB API but is not endorsed or certified by TMDB.

Content warnings are Powered by DoesTheDogDie.com.

Tag genome data from MovieLens:

- F. Maxwell Harper and Joseph A. Konstan. 2015. The MovieLens Datasets: History
  and Context. ACM Transactions on Interactive Intelligent Systems 5, 4:
  19:1-19:19. https://doi.org/10.1145/2827872
- Jesse Vig, Shilad Sen and John Riedl. 2012. The Tag Genome: Encoding Community
  Knowledge to Support Novel Interaction. ACM Transactions on Interactive
  Intelligent Systems 2, 3.

## Licence

Matinee is free software: you can redistribute it and modify it under the terms
of the GNU Affero General Public License, version 3 or (at your option) any
later version. The full text is in `LICENSE`. If you run a modified Matinee for
other people over a network, the licence asks you to offer them its source.

That covers everything in this repository except the third-party material,
which stays under its owners' terms:

- `data/genome.json` and `data/reference.json` are derived from the MovieLens
  tag genome and carry that dataset's conditions, stated in their `licence`
  fields: research and non-commercial use only, and redistribution only under
  the same conditions.
- `src/matinee/web/static/credits/tmdb.svg` is TMDB's logo, used under TMDB's
  terms.
- Data fetched at run time from TMDB, DoesTheDogDie and your media server is
  governed by those services' own terms. TMDB's default licence and
  DoesTheDogDie's free tier are both non-commercial.
- Dependencies keep their own licences.
