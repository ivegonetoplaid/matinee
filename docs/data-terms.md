# Matinee — Data Terms

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
  tag genome. The full citations are in [README.md](../README.md).
