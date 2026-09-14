# Bookmatch

Book recommendations built by Beryl Koko with Flask and vanilla JavaScript. Start with a book, choose up to three subjects or tropes, inspect why each recommendation matches, and save books to a reading list on your device.

The recommendation engine now answers combinations such as **MM + sports + college**, instead of intersecting the first page of three generic subject lists. The existing layout, cards, preferences, details dialog, reading list, and Previous/Next controls remain.

## Try it

```bash
cd book-recommendation
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5001.

- Search **Tempting Venom** or **Iced Out**, choose “Use this book,” and select `mm`, `sports`, and `college`.
- Or enter **mm+sports+college** directly in the same search box. This optional shortcut uses the same preference panel and recommendation endpoint.
- Add other tropes in “Add a subject or trope.” You can change which three are selected.
- “Suggest a different author” excludes all books by the starting book's author. Turn it off to include their other books. The starting book itself is always excluded.
- Open Details for per-concept evidence and a link to the book's author, publisher, retailer, or library reading options.

Google Books works without an app key when public quota is available. Set `GOOGLE_BOOKS_API_KEY` in the server environment to use your own project quota. This is optional; no credentials belong in source control. API failures never remove indexed books from results.

## What changed and why

The old backend searched up to eight aliases for each chosen subject, fetched only 24 results for each alias, and counted which search lists a book appeared in. A book with all three traits could be absent from those broad first pages. Related terms in `genres.json` could also manufacture false matches: “athletes” is not proof of hockey, and “queer romance” is not proof of MM.

The new engine in `book-recommendation/discovery.py` separates **finding candidates** from **establishing matches**:

1. Search complete combinations and pairwise combinations in Open Library. Search Google Books as an independent source, including contextual sport variants for sports requests. Requests are bounded and cached.
2. Add a versioned, source-backed trope index. The initial index contains **24 books**, with particularly strong coverage of MM campus sports. It stores book-specific factual annotations and source links, not copied full blurbs. The existing 200-entry genre vocabulary is a retrieval aid, **not a 200-book catalog**.
3. Merge matching title/author records across sources. Keep separate books with the same title but different authors and preserve distinguishing series subtitles. Preserve alternate provider IDs for seed exclusion.
4. Check each selected concept against reviewed annotations, catalog subjects, or explicit description evidence. Broader retrieval terms cannot award matches. Directional relationships are allowed: hockey implies sports; sports does not imply hockey. New adult does not imply college. Generic LGBTQ+ does not imply MM.
5. Require the selected MM/FF pairing. For three-concept requests, omit one-concept filler. Rank all-three matches ahead of partials; use evidence quality as the tie-breaker. Cards explicitly identify unconfirmed concepts. Source notes are visible in Details.
6. Apply existing author/year preferences in the client, then paginate the complete returned pool in groups of 12. No arbitrary 72-book client cutoff.

This is a transparent, content-based recommendation system, not collaborative filtering. Its value is checking a reader's combination across book-level evidence and retaining niche titles that general metadata misses. Goodreads and other specialist sites have their own discovery tools; this project does not claim universal superiority or exhaustive coverage.

## Verified coverage

The following are deterministic results from the bundled index, before excluding the seed or its author. Available live metadata can add further matches.

| Combination | Full matches |
| --- | ---: |
| MM + sports + college | 18 |
| MM + hockey + college | 10 |
| MM + baseball + college | 3 |
| MM + friends to lovers + college | 4 |
| MM + dark romance + mafia romance | 2 |

The 18 include **Iced Out**, **Tempting Venom**, **Hidden Scars**, **Don't You Dare**, and **Never Have I Ever: Had a Bromance with a Teammate**, along with CU Hockey titles, The Jock, The Quarterback, For the Fans, Rule Breaker, and others. `college` describes the setting: Puck Drills & Quick Thrills is a university coach/professor romance, and its evidence says so.

Known coverage limits:

- The source-backed index is small and maintained explicitly. Changing the matching algorithm cannot invent missing trope facts for the rest of the world's books.
- Live recommendation calls return bounded candidate pools, not every work in either provider. Title search currently combines up to 100 Open Library hits, 40 Google Books hits, and relevant indexed records, then paginates that stable pool. Displayed totals count discovered records, not entire catalog totals.
- Description matching is conservative phrase matching, not full plot understanding. It ignores common recommendation/author marketing sentences and simple negations; ambiguous plot details should be reviewed and annotated.
- First publication dates remain unknown where only an edition date is available. Such books are excluded by an era filter. Default “Any year” includes them.
- Covers and reading links are external and may change. The existing no-cover fallback remains.

## API

- `GET /api/books?q=Iced%20Out&page=1`: merged title/author discovery.
- `GET /api/recommend?subject=mm&subject=sports&subject=college`: evidence-ranked recommendations.
- `GET /`: main application.
- `GET` or `POST /recommendations`: non-JavaScript title search fallback.

Recommendations retain the original book fields and add `conceptMatches`, `conceptEvidence`, `missingConcepts`, `exactMatch`, `evidenceScore`, and `alternateIds`. Response metadata includes `exactCount`, `sources`, `unavailableSources`, and coverage information. A failed live source is reported while indexed recommendations remain available. Unknown title searches return a retryable error when both live providers fail.

## Extend the catalog

Edit `book-recommendation/data/catalog.json` or prepare a separate JSON list with the same schema:

```json
[
  {
    "id": "catalog:stable-book-id",
    "title": "Book title",
    "authorNames": ["Author name"],
    "year": null,
    "url": "https://publisher.example/book",
    "evidence": {
      "college": {
        "url": "https://publisher.example/book",
        "note": "The publisher identifies a university setting.",
        "checked": "2026-09-14"
      }
    }
  }
]
```

Use factual, original notes with deep source links. Prefer author/publisher descriptions; distinguish review-based evidence. Do not infer all of a series' tags for every volume or label any queer book MM. Use the same ID to correct a book, and keep first publication dates null until verified.

From the repo root, with Python dependencies installed:

```bash
python scripts/catalog.py --check
python scripts/catalog.py --import-file additions.json
```

Imports validate the complete replacement before saving. Commit new annotations with their sources. New titles automatically participate in all combinations; there is no title-specific recommendation branch.

## Tests

```bash
python -m unittest discover -s tests -v
npm ci
npm test
```

Python tests cover anchor-title recall, exact-first ordering, narrower combinations, false-positive exclusions, cross-source merging, series identity, new unindexed live candidates, outages, metadata parsing, pagination, and endpoint validation. JavaScript tests cover ranking, preferences, seed exclusion, the trope shortcut, and the DOM interaction flow through search, details, save/reload, and Previous/Next.

To run the DOM integration test against a running Flask server instead of response fixtures:

```bash
BOOKMATCH_TEST_URL=http://127.0.0.1:5001 npm test
```

DOM integration tests do not replace visual browser QA. The hosted browser available during this update could not reach the local preview, so visual rendering was not verified in that browser. No CSS was changed.
