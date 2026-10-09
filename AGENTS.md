# Matinee — Agent Guide

Read this guide before changing or installing Matinee. It applies to every agent
working in this repository and requires no private notes or configuration.

## What Matinee does

Matinee asks a viewer a few questions, then selects one film. It reads Jellyfin
or Plex, or works without a media server. It does not play films or change the
user's library. Profiles are local; an optional door word gates admission.

The server reads an offline film table built by `tools/rebuild_table.py`.
TMDB enrichment runs during rebuilds, not while a viewer waits. Optional
DoesTheDogDie checks look up a film only after it is drawn for a pick.

## Read the contract for your task

| Document | Governs |
|---|---|
| [CODING_STANDARDS.md](CODING_STANDARDS.md) | All code, security, diagnostics and verification |
| [DESIGN_STANDARDS.md](DESIGN_STANDARDS.md) | Every viewer-facing surface and its copy |
| [Behaviour specification](docs/spec/matinee.md) | Features, settings, schemas and architectural contracts |
| [Getting started](docs/getting-started.md) | Installation, updates, troubleshooting and backups |
| [Data terms](docs/data-terms.md) | External-data restrictions, retention and required notices |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Contribution and pull-request workflow |

Follow the coding standards for changes, the design standards for surfaces, and
the relevant spec sections for behaviour. Read the data terms before working on
data integrations. All of these contracts bind; raise conflicts explicitly.

## Repository map

| Path | Purpose |
|---|---|
| `src/matinee/` | Engine, film table, profiles, content checks and web server |
| `src/matinee/web/static/` | Browser interface; no build step |
| `data/trees/` | Question trees |
| `data/labels.json`, `data/house_overrides.json` | Shipped classifications and placement pins |
| `data/answer_key.json`, `data/fixtures/` | Tree-check expectations and fixtures |
| `tools/` | Rebuild, tree checker, operator notes and genome-file builders |
| `docs/spec/` | Behaviour specification |

## Change and verify

- Use Python 3.12 or newer and Node with npm. Run `./bootstrap.sh` once to
  install development tools and pre-commit hooks.
- Run `./check.sh` before reporting a change complete. It checks formatting,
  lint, complexity, types and Python/JavaScript tests. Fix failures; never bypass
  hooks. Report checks that could not run as not run, never as passing.
- Update `docs/spec/` in the same change as any behaviour change. The spec is
  the contract; reconcile drift instead of silently changing what it promises.
- Inspect changed interfaces at phone and desktop widths under the design
  standards. Report unrendered surfaces as `UNVERIFIED`.
- Keep working notes, build reports, review rounds and scratch files out of the
  repository. Put the change summary and validation evidence in the PR.

## Matinee invariants

- **Build for any library.** Design doors, kinds, wording and thresholds against
  the films in the shipped labels. Report counts for that set first, then any
  household's library separately. Before changing a door, check how every film
  labelled for it is reached; one library's mix is never the design boundary.
- **Labels determine placement.** Only labels decide a film's doors and kinds.
  Never substitute genome scores, genre tags or catch-all fallbacks, or explain
  placement by them. The spec's waiting room is the sole exception: unlabelled
  films wait behind their TMDB-genre doors until labelled. Every film behind a
  door belongs to at least one of its kinds.
- **Keep films reachable.** Every film has at least one complete answer path
  behind some door. Remove a film from a door only if it barely fits and has
  another home. Tree-rule changes must pass `tools/check_trees.py` against a
  rebuilt film table, preserving reachability and the answer key.
- **Read media servers only.** Never write to Jellyfin or Plex. Matinee's state
  belongs in its own store; configure at most one media server.
- **Run one web worker.** DoesTheDogDie limits and holds are process-local;
  additional workers duplicate them.
- **Protect household overrides.** `overrides.json` lives in the data directory.
  Matinee reads it; updates do not overwrite it. Its full format is in the spec.
- **Protect secrets and household information.** Never commit keys, `.env`, real
  hostnames, LAN addresses, internal domains, personal names or private machine
  paths. Addresses and credentials arrive through settings. Never expose a key
  or setting secret in logs, URLs or browser responses.
- **Respect data restrictions.** Never commit TMDB records, caches, film tables,
  TMDB-derived ordering or raw MovieLens files. Never prefetch DoesTheDogDie
  data, retain its votes or build scores from it. Preserve required credits and
  notices; [data terms](docs/data-terms.md) gives the full restrictions.

## Installing for someone

Use [getting started](docs/getting-started.md) for commands and operations, and
`example.env` plus the spec for settings. Resolve these choices from the user's
instructions or existing configuration before writing settings; ask for any
missing decisions rather than choosing silently:

1. Jellyfin, Plex or neither; never both.
2. Whether to use Seerr links; otherwise picks link to TMDB.
3. Whether to use DoesTheDogDie checks, with the installation's own API key.
4. Whether to use a door word, and relaxed or strict matching.
5. Where persistent data will live and be backed up.
6. The nightly rebuild time (`REBUILD_TIME`, `HH:MM`) and time zone (`TZ`).

`TMDB_TOKEN` and `DATA_DIR` are required; the shipped Compose file supplies
`DATA_DIR=/state`. Keep persistent storage mounted at that path. Matinee
reads the process environment, not `.env` directly; the installation guide
explains how it receives it. Use HTTPS for the admission cookie and
follow the guide's proxy precautions when exposing the site.
