# Contributing to Matinee

Come on in. Anyone is welcome to help: a fix, a feature, a sharper line of
dialogue, a better sort. Here is how the house runs.

## Every household, not just yours

Matinee runs in living rooms it will never see, against libraries of every size
and shape. "Works on my machine" isn't enough: a change has to hold up for a
household with ten films, one with ten thousand, and one with no library at all.
Size things against the films the shipped labels name, not your own shelf.

## Agents welcome, slop not

AI agents are welcome contributors, and `AGENTS.md` tells them how this place
works. What isn't welcome is a low-effort or vibe-coded change: code nobody
read, tests that test nothing, a pull request that hasn't run once. Whoever or
whatever wrote it, you're the one standing behind it.

## The house rules

- Follow `CODING_STANDARDS.md` for every line of code and `DESIGN_STANDARDS.md`
  for everything a viewer sees. Matinee has a personality, a little dry and a
  little theatrical: match its voice in anything it says, and its look in
  anything it shows.
- A large change starts as an issue, so we can agree on the shape before you
  spend a weekend on it. Ideas for how Matinee should work go there too.
- `./check.sh` passes before a pull request is opened. Run `./bootstrap.sh`
  once first.
- One change per pull request, and say how you tested it.
- A change in behaviour updates `docs/spec/` in the same pull request. The spec
  is the contract; code that drifts from it is a bug in one or the other.
- Never commit a key, a `.env` file, or anything that identifies a home:
  hostnames, addresses, names, paths from your machine.
- The data terms bind contributions too. No TMDB records, no film table, no
  raw MovieLens files, and nothing fetched from DoesTheDogDie. `AGENTS.md` lists
  each source's terms.
- Contributions are licensed under the GNU Affero General Public License v3,
  the same as Matinee (`LICENSE`).
- Be kind. Everyone here is trying to pick a good film.

## Where films belong

Matinee is opinionated about one thing: where films belong. Each film sits
behind the doors it truly fits, and no more. When every film may belong
everywhere, as with TMDB's keywords, a horror search turns up a cartoon. We
would rather be wrong now and then than vague all the time.

Disagree with a call? Override it on your own install: write an
`overrides.json` in your data directory, in the labels file's shape, and your
Matinee will sort the way you see it. Updates never undo it. A film you name
there takes its whole placement from your file, so a kids film carries both
its kinds and its age band. The spec (section 2.6) has the details.

If you think your call is right for everyone, open a **Sorting suggestion** in
the issue tracker and paste in your override file. I read every one. Some I'll
take and some I won't. That's the deal with an opinionated sort, and it's never
personal. The shipped labels have one editor and no vote, so they stay a sort
rather than a pile of tags.
