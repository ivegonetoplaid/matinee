# Getting started with Matinee

[← Back to Matinee](../README.md)

This is the installation and operations guide. For an introduction and an interactive preview, start with the [project README](../README.md) or the [demo](https://ivegonetoplaid.github.io/).

## Before you start

**Required**

- **A TMDB API Read Access Token.** Create a free account at [TMDB](https://www.themoviedb.org), open [Settings → API](https://www.themoviedb.org/settings/api), and copy the long **API Read Access Token**, not the short API key. Matinee uses it to fetch film details and posters.
- **Somewhere to run Matinee.** Docker with Compose is the supported, simplest path. Without Docker, use Python 3.12 or newer.
- **A persistent data folder.** It holds the film table, profiles, and fetched TMDB records. Back it up: it is the only state Matinee keeps.

**Optional integrations**

| Integration | What it does | What to configure |
| --- | --- | --- |
| **Jellyfin** or **Plex** | Reads your library without changing it; lets you choose films you own, don't own, or both | Jellyfin URL and API key (**Dashboard → API Keys**), **or** Plex URL and [token](https://support.plex.tv/articles/204059436-finding-an-authentication-token-x-plex-token/) — **not both** |
| **Seerr** (including Overseerr/Jellyseerr) | Opens a picked film's request page; without it, Matinee links to TMDB | Seerr URL |
| **DoesTheDogDie** | Lets viewers avoid chosen content topics; checks each pick before displaying it | Your own API key from your [DoesTheDogDie profile](https://www.doesthedogdie.com/profile) |
| **Door word** | Gives internet-facing installations a simple admission gate | `DOOR_WORD` (and HTTPS; see below) |

The optional content-topic checks are **best-effort**, not guarantees. A film with no community votes may not have enough data to check. No DoesTheDogDie key means no topic list or check.

## Install with Docker Compose

### 1. Get the two files

Matinee runs from a ready-made image, so you need only its Compose file and its settings template:

```sh
mkdir matinee && cd matinee
curl -fsSLO https://raw.githubusercontent.com/ivegonetoplaid/matinee/main/compose.yaml
curl -fsSL https://raw.githubusercontent.com/ivegonetoplaid/matinee/main/example.env -o .env
```

### 2. Set up the environment

Edit `.env`. Uncomment the lines you need (remove `# `), and put the value immediately after `=` without extra spaces or surrounding quotes. The file explains every setting.

The minimum settings outside Docker are `DATA_DIR` and `TMDB_TOKEN`. **With the supplied Docker Compose file, leave `DATA_DIR` commented out**: Compose sets it to `/state`, backed by `./state` on your host. Set `TMDB_TOKEN` to your own API Read Access Token.

Fill in optional media-server, Seerr, content-topic, and door-word settings only when you use those services. Never commit `.env`.

### 3. Start both processes

Matinee uses one image to run two services:

- **`matinee`:** the site on port 8000, with exactly one server worker.
- **`rebuild`:** builds the film table immediately and refreshes it every night at `REBUILD_TIME` (in the time zone set by `TZ`).

Both services read the same `.env` and persistent data folder. The `compose.yaml` needs no edits for the default installation.

```sh
mkdir -p state && sudo chown 1000:1000 state
docker compose up -d
```

The image is published for both regular PCs (amd64) and ARM boards such as a 64-bit Raspberry Pi (arm64); Docker picks the right one.

The image runs as UID 1000, so the data folder must be writable by that user. Open `http://<your-server>:8000`. To publish Matinee outside your LAN, read [Internet access and HTTPS](#internet-access-and-https) before exposing the port.

### 4. Let the film table populate

The first rebuild downloads a TMDB record for roughly 10,300 films, plus any films in your library that aren't already in the shipped list. At the default 30 records per second, the initial fetch takes around six minutes.

You don't have to wait for the full rebuild:

- **With Jellyfin or Plex**, your own library can be picked within seconds. The rebuild saves it first.
- **Without a library**, picks can start after roughly a minute. Popular films are fetched first and saved as they arrive.

While Matinee is starting, or if a service is unavailable, its **setup note** explains the current state instead of dropping you into an empty interface. The server and rebuild logs report the same state.

## Internet access and HTTPS

If Matinee faces the internet, put it behind a reverse proxy serving **HTTPS** and set `DOOR_WORD`. The admission cookie is only sent over HTTPS. The door word is a lightweight household gate, not a replacement for the protections you'd use on a security-sensitive public service.

Keep API tokens in `.env`, not in a public URL or a repository. As shipped, Compose publishes port 8000 and the image trusts forwarded headers from any address. Restrict direct access to the backend to trusted proxy clients when using a reverse proxy; configure your network and proxy exposure intentionally.

## Troubleshooting your first run

Start with the logs:

```sh
docker compose logs matinee
docker compose logs rebuild
```

- **No TMDB key or a rejected key:** fix `TMDB_TOKEN` in `.env`, then run `docker compose up -d`. That recreates services when their environment changes; `docker compose restart` alone retains the previous environment.
- **TMDB isn't answering:** Matinee tries again on the next nightly rebuild. To try sooner, run `docker compose restart rebuild`.
- **Your library isn't answering, a setting is invalid, or the rebuild is still fetching:** read the setup note and matching logs. Matinee reports these states explicitly.
- **A stale-data warning appears:** the nightly rebuild has not refreshed records in time. Check the rebuild logs and restore its schedule; Matinee continues picking while it warns.

## Day-to-day operation

| Task | Command or location |
| --- | --- |
| Check logs | `docker compose logs matinee` / `docker compose logs rebuild` |
| Change a setting | Edit `.env`, then `docker compose up -d` to recreate affected services |
| Change the nightly time | Set `REBUILD_TIME` (`HH:MM`) and `TZ` in `.env`, then `docker compose up -d` |
| Retry the rebuild | `docker compose restart rebuild` |
| Update Matinee | `docker compose pull`, then `docker compose up -d` |
| Review viewers' reports | `docker compose exec matinee python tools/notes.py list` |
| Back up Matinee | Back up the persistent `./state` folder (or the folder you configured) |

`tools/notes.py` can review "Something wrong with this pick?" notes, clear a forgotten PIN, and remove DoesTheDogDie topics left after an API key was removed. The [specification](spec/matinee.md) documents the operator details.

Run **exactly one server worker**. The DoesTheDogDie limits are enforced inside that process; additional workers would duplicate them. Your own data and `overrides.json` live outside the image and are not overwritten by the normal update command.

### Versions and updates

Each [release](https://github.com/ivegonetoplaid/matinee/releases) has a number and notes saying what changed. The image is tagged three ways: the exact version (`0.1.4`), its release line (`0.1`), and `latest`, which follows every release. The shipped `compose.yaml` uses `latest`.

Matinee is in beta, so its numbers start with 0. Within a release line, an update is always safe. A new line (0.1 to 0.2) may need steps, and its release notes give them before you update. To move to a new line only when you choose, replace `latest` with the line's number (for example `:0.1`) in both services in `compose.yaml`.

## Make the film classifications your own

Matinee deliberately chooses where films belong. Films are placed behind the doors they truly fit rather than relying on every keyword they happen to carry. That means someone will occasionally disagree — and that is expected.

To make a local change, write `overrides.json` in your persistent data folder, using the shape of `data/labels.json`:

```json
{"format": 2,
 "trees": {"western": {"kinds": {"11969": []}},
           "kids": {"kinds": {"9340": ["adventure"]}, "bands": {"9340": "family"}}}}
```

An override takes **the whole placement** of each named film, not just one extra tag. For a kids film, include both kinds and age band. Restart the site to read it:

```sh
docker compose restart matinee
```

The next rebuild fetches any film named in the overrides that Matinee doesn't already know. If the override file is invalid, the setup note explains why and Matinee uses its shipped classifications until you fix it. Updates never overwrite your override file. See [spec section 2.6](spec/matinee.md) for the full format.

Think the correction should apply to everyone? Open a [Sorting suggestion](https://github.com/ivegonetoplaid/matinee/issues/new/choose), include the relevant override, and explain why. Maintainers review these individually; not every suggestion will be accepted.

## Without Docker

Docker Compose is the supported installation path. To run the processes yourself, get the code and install the Python package into a virtual environment from the repository root:

```sh
git clone https://github.com/ivegonetoplaid/matinee.git && cd matinee
python3 -m venv .venv && .venv/bin/pip install -e .
```

To build the Docker image from the code instead of pulling it, run `docker build -t ghcr.io/ivegonetoplaid/matinee:latest .` in the repository, then start Compose as above without `docker compose pull`. A pull replaces your build with the published image.

Matinee reads the **process environment**, not the `.env` file directly. In each shell that launches a process, load the file this way (it preserves values containing spaces, unlike a naive `source`):

```sh
while IFS= read -r line || [ -n "$line" ]; do case $line in ""|"#"*) ;; *) export "$line" ;; esac; done < .env
```

Set both `DATA_DIR` and `TMDB_TOKEN` for this installation. Then run the rebuild and the site as separate long-running processes, with the environment loaded in each:

```sh
.venv/bin/python tools/rebuild_table.py --daily &
.venv/bin/uvicorn --factory matinee.web.main:build --workers 1 --port 8000 --no-access-log
```

The example starts the rebuild in the background of the current shell, but doesn't configure permanent service management. Arrange that yourself if you choose this path. Keep **one** web worker.

## Why every installation fetches its own TMDB data

**Matinee can ship its classifications, but it cannot redistribute the TMDB records those classifications refer to.** The repository contains Matinee's opinions about which films fit which doors and kinds. Titles, posters, synopses, ratings and certificates come from TMDB, whose API terms impose cache-age and redistribution limits.

Each installation therefore downloads those details under its **own** API token and keeps the data locally. The nightly rebuild refreshes records before the permitted six-month cache window expires. If records get stale, Matinee warns on every screen until the rebuild catches up.

That separation is deliberate: it makes the classification system shareable without packaging content Matinee doesn't own. See the [TMDB API Terms of Use](https://www.themoviedb.org/api-terms-of-use).

## Development

```sh
./bootstrap.sh     # Virtualenv, development tools and pre-commit hooks
./check.sh         # Format, lint, type and test checks
```

See [CONTRIBUTING.md](../CONTRIBUTING.md) before opening a PR and [AGENTS.md](../AGENTS.md) for AI-agent instructions. The [specification](spec/matinee.md) is the behaviour contract.

The source lives in `src/matinee/` (engine, library integration, profiles, content checks and site), `data/` (question trees, classifications, genome scores, checker fixtures), `tools/` (rebuild and operator tools), and `docs/spec/` (specification).

## Data terms and credits

**Matinee's own code and words** are licensed under [GNU AGPL v3 or later](../LICENSE). If you modify Matinee and make it available to others over a network, the licence requires you to offer the corresponding source code under its terms.

**Third-party material keeps its own terms.** AGPL does not make everything in the repository available for commercial use:

- `data/genome.json` and `data/reference.json` are derived from the **MovieLens tag genome** and carry research, non-commercial-use and redistribution conditions in their `licence` fields. Do not assume the AGPL grants you commercial rights to those datasets.
- `src/matinee/web/static/credits/tmdb.svg` is **TMDB's logo**, used under TMDB's terms.
- Data fetched from **TMDB**, **DoesTheDogDie**, or your media server at runtime is governed by each service's terms. TMDB's default API licence and DoesTheDogDie's free tier are non-commercial.
- Dependencies retain their own licences.

This product uses the TMDB API but is not endorsed or certified by TMDB.

Content warnings are Powered by [DoesTheDogDie.com](https://www.doesthedogdie.com).

**MovieLens papers:**

- F. Maxwell Harper and Joseph A. Konstan. 2015. *The MovieLens Datasets: History and Context.* ACM Transactions on Interactive Intelligent Systems 5, 4: 19:1–19:19. https://doi.org/10.1145/2827872
- Jesse Vig, Shilad Sen and John Riedl. 2012. *The Tag Genome: Encoding Community Knowledge to Support Novel Interaction.* ACM Transactions on Interactive Intelligent Systems 2, 3.

See [data terms](data-terms.md) for the detailed project restrictions and upstream sources. Review those sources before commercial deployment, redistribution or changing data use. This summary does not replace the original licences and API agreements.
