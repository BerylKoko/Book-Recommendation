# Bookmatch

Bookmatch is a Flask + vanilla JavaScript book-discovery app by **Beryl Koko**. Search for a book, choose up to three subjects or tropes you want more of, and Bookmatch searches live book catalogs for combinations rather than sending you to a single broad genre list.

**Live demo:** https://book-recommendation-1-e4km.onrender.com/

> The demo uses a free Render service, so the first request after inactivity can take a little longer while the service wakes up.

## What the project is trying to solve

A broad catalog can answer “show me romance” or “show me hockey books.” The harder question is closer to **“I want M/M + college + sports”** or **“dark romance + enemies to lovers.”** Bookmatch treats those as combinations, searches more than one catalog, and ranks books by how much evidence it can find for the selected concepts.

The app does **not** use a manually maintained book list. Results come from **Google Books and Open Library at request time**. The bundled `genres.json` file is only a vocabulary of alternate search terms; it does not contain recommendations or preselected books.

## Current recommendation flow

1. Search Google Books and Open Library for the requested title or author.
2. Merge duplicate editions by ISBN or exact title + author.
3. Prefer richer Google Books metadata and cover art while retaining Open Library reading links when available.
4. When the user requests a trope combination, generate several bounded searches using alternate vocabulary instead of relying on one literal subject label.
5. For a broad `sports` request, try concrete sports such as hockey, football, baseball, basketball, and soccer so niche sports romances are not buried behind a generic sports list.
6. Check categories, descriptions, and targeted Google Books search relevance for the selected concepts. Open Library fuzzy-search membership is never treated as proof of a trope.
7. Rank full matches ahead of partial matches, apply the existing different-author/year preferences, then paginate locally in groups of 12.

For pairings such as M/M or F/F, Bookmatch requires evidence for the pairing before a result is shown. This prevents a straight sports romance from being labeled M/M simply because a fuzzy catalog search happened to return it.

## Search and cover handling

Normal title/author search is intentionally separate from trope matching. Each search uses both a broad query and a title-focused query, then reranks the merged pool so exact title matches are not buried behind whichever provider responded first. This is important for short titles such as **Bride**.

Cover art uses a fallback chain:

- the best image returned by Google Books;
- Open Library cover IDs when the same book is found there;
- an ISBN-based Open Library cover URL;
- the existing “No cover” fallback only after those options fail.

The browser automatically tries the next cover candidate when an image URL fails.

## Features

- Title and author search
- Seed-book workflow: search → choose a book → select subjects/tropes
- Direct combination shortcut such as `mm+sports+college`
- Custom trope input
- Multi-source recommendation retrieval
- Explainable match strength and evidence in Details
- Different-author and publication-era filters
- Previous/Next pagination
- Local reading list with `localStorage`
- Responsive existing interface preserved
- Cached backend requests and independent provider failure handling

## Tech stack

- Python
- Flask
- Requests
- Google Books API
- Open Library Search API
- Vanilla JavaScript
- HTML/CSS
- Render

## Project structure

```text
Book-Recommendation/
├── README.md
├── book-recommendation/
│   ├── app.py
│   ├── discovery.py
│   ├── requirements.txt
│   ├── static/
│   │   ├── books.js
│   │   ├── recommend.js
│   │   ├── genres.json
│   │   └── style.css
│   └── templates/
│       ├── index.html
│       └── recommendations.html
└── tests/
    ├── test_discovery.py
    └── recommend.test.mjs
```

## Run locally

```bash
cd book-recommendation
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python app.py
```

Then open `http://127.0.0.1:5001`.

Google Books public search does not require authentication for basic requests. `GOOGLE_BOOKS_API_KEY` can optionally be set in the server environment for a project-specific quota; credentials should never be committed.

## API

```text
GET /api/books?q=Bride&page=1
GET /api/recommend?subject=mm&subject=sports&subject=college
GET /
GET|POST /recommendations
```

Recommendation responses add fields such as `conceptMatches`, `conceptEvidence`, `missingConcepts`, `exactMatch`, and `evidenceScore`. Search responses include provider availability information so one source can fail without silently corrupting the other source's results.

## Tests

```bash
python -m unittest discover -s tests -v
npm ci
npm test
```

The Python regression tests cover false-positive M/M rejection, targeted-search evidence, duplicate merging, exact-title ranking, pagination, provider metadata, cover fallbacks, bounded sports fan-out, and endpoint validation. JavaScript tests cover ranking, preferences, trope shortcuts, search/seed/recommendation flow, Details, paging, and reading-list persistence.

## Limits

This is a content-based discovery project, not Goodreads-scale collaborative filtering. Google Books and Open Library do not expose every reader trope consistently, so the app cannot guarantee exhaustive results for every combination. The architecture deliberately keeps that limitation visible instead of hiding it behind a hand-curated recommendation list.

The goal is to make the live metadata work harder: combine sources, broaden retrieval carefully, use descriptions where available, distinguish evidence from fuzzy retrieval, and explain why a recommendation matched.
