# Rehabilitation changes

## Recovered checkpoint

The interrupted implementation was recovered and pushed before this revision. It was not treated as release-ready.

## Product revision

Added a seed-book flow, selectable subject preferences, author/year constraints, transparent subject-overlap ranking, and reasons shown on suggestions. Replaced the shared serif hero with a book-selection workspace. Retained reading-list data and details.

## Validation / remaining work

4 Flask tests and 1 recommendation-logic test pass. Candidate matching requests use up to 48 catalog records. Captured preference state prevents stale responses from using changed inputs. Hosted live API integration and full browser matching flow remain incomplete.

The direct live catalog request was stopped because network approval was cancelled; preview requests also return 502. No successful live recommendation flow is claimed for this revision.

2026-09-08: Live standalone API verification passed. Hosted preview integration remains unverified; no release-ready claim.
