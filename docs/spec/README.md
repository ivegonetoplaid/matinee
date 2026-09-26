---
purpose: Index of Matinee's behaviour specifications — what each spec covers, how much to trust it against the code, and the policy that keeps the two reconciled.
updated: 2026-09-26
---

# Matinee Specs

Each document here states the contract Matinee holds to, in whole or in part: what it
must do, what it must refuse, and why.

## How to read these

**A spec and its code move together.** A change to behaviour amends the spec in
the same commit that changes the code. A review finding that changes a contract
is not closed until the spec carries the change.

A spec holds two kinds of claim, and they carry opposite trust rules.

- **Contract** — what the software must do, what it must refuse, the
  invariants, and what is out of scope. The document is authoritative. Code
  that disagrees with the contract is a defect in the code.
- **Map** — where the code lives, and what the current arrangement is. The
  document is a pointer and never an authority. Read the map to learn where to
  look, then look. Never quote it as proof of what the code does.

### When a spec and the code disagree

Documents drift even where everybody means well. The useful question is which
one moved last.

- **The spec moved last.** Somebody stated the contract and the code does not
  meet it. The code is wrong.
- **The code moved last.** The spec is behind. A change that altered the
  contract owes an amendment now, and that amendment belongs to the work in
  hand. A tweak inside the contract leaves the spec true and incomplete.

A spec that is behind is silent about what came after it. It is not false, and
it still binds on what it does state. Do not discard a spec for being out of
date, and do not treat one as the final word on behaviour.

Those two cases are the common ones, not the only ones. Read both sides and
judge. One spec runs behind in one section and ahead in another. A rename reads
as a contradiction when nothing changed. Where a spec names the paths it
governs, one command lists what to read:

```sh
git log --oneline --since=<updated> -- <governs>
```

Nothing checks any of this. The rule earns its keep by being worth following.

The policy has one hard edge: a spec nobody is prepared to keep reconciled is
deleted rather than left standing. Git history holds it.

## The specs

- [`matinee.md`](matinee.md) — the whole of Matinee's first build: the
  conversation model (the first question, trees and modes as data files,
  answers as filters, and the checker that keeps every film reachable), the
  pool rules, the reference statistics, the gore scale and house pins, the
  offline film table and its nightly rebuild, profiles and device tokens,
  exclusions, the DoesTheDogDie check at the moment of a pick, personal
  corrections, the web surface and its security headers, the page, the
  deployment shape, and the terms of the three data sources. Written from the
  code on 2026-09-26. It ends with a list of known gaps: behaviour deliberately
  absent, still open, or short of the contract.
