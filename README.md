# Bookmatch (Book-Recommendation rehabilitation)

A seed-book discovery app retaining the original Flask foundation. Choose a book and up to three catalog subjects, then compare suggestions with explicit matching reasons. Includes author/year constraints, details, and a local reading list.

## Run locally

```sh
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python book-recommendation/app.py
```

Open http://localhost:5001. No API key is required for Open Library. The server needs outbound HTTPS access to openlibrary.org; covers are loaded from covers.openlibrary.org.

## Tests

```sh
pip install pytest
python -m pytest tests -q
node --test tests/recommend.test.mjs
```

## Status

Product revision is checkpointed, not release-ready. Unit tests pass. Live catalog verification is blocked in the current environment; do not present the hosted preview as fully functional yet.

See docs/BEFORE.md, CHANGELOG.md, ARCHITECTURE.md and INTERVIEW.md for provenance, limitations and learning notes. Private source has not been made public.
