"""Live trope recommendation retrieval for Bookmatch.

This module deliberately keeps candidate retrieval separate from evidence. Google
Books queries are used to find likely books; Open Library is supplemental. Query
membership can weakly support setting/trope context, but it never proves an M/M
or F/F pairing.
"""
from concurrent.futures import ThreadPoolExecutor

import requests

import discovery


PRIMARY_QUERY_COUNT = 6
TARGET_SUGGESTIONS = 24
TARGET_FULL_MATCHES = 6
MAX_QUERY_TASKS = 12
MAX_WORKERS = 2

PAIRINGS = {"mm", "ff"}
SPORT_FANOUT = ("hockey", "football", "baseball", "basketball", "soccer")


def _query_text(parts):
    return " ".join(str(part).strip() for part in parts if str(part).strip())


def _identity_phrases(concept):
    if concept == "mm":
        return ("gay romance", "m/m romance", "mm romance")
    if concept == "ff":
        return ("lesbian romance", "sapphic romance", "f/f romance")
    return (discovery.query_phrase(concept),)


def _context_phrase(concept):
    preferred = {
        "college": "college",
        "sports": "sports romance",
        "dark romance": "dark romance",
        "enemies to lovers": "enemies to lovers",
        "friends to lovers": "friends to lovers",
        "fake dating": "fake dating",
        "forced proximity": "forced proximity",
        "slow burn": "slow burn",
    }
    return preferred.get(concept, discovery.query_phrase(concept))


def build_queries(subjects, genre_map=None):
    """Build broad-to-specific queries without requiring every term at once."""
    resolved = discovery.resolve_concepts(subjects, genre_map)
    concepts = [concept for _, concept in resolved]
    if not concepts:
        return []

    tasks = []

    def add(provider, query, hints=()):
        query = _query_text([query])
        item = (provider, query, tuple(discovery.unique(hints)))
        if query and item not in tasks:
            tasks.append(item)

    pairing = next((concept for concept in concepts if concept in PAIRINGS), None)
    non_pairing = [concept for concept in concepts if concept not in PAIRINGS]

    if pairing:
        identities = _identity_phrases(pairing)

        # Start with combinations that directly express the reader's niche.
        if "sports" in non_pairing and not any(
            concept in discovery.SPORTS for concept in non_pairing
        ):
            other_context = [
                concept for concept in non_pairing if concept != "sports"
            ]
            for index, sport in enumerate(SPORT_FANOUT):
                identity = identities[index % len(identities)]
                parts = [identity]
                parts.extend(_context_phrase(c) for c in other_context)
                parts.append(sport)
                add(
                    "Google Books",
                    _query_text(parts),
                    [*other_context, "sports"],
                )

        # Pair the identity with each non-pairing concept. These are deliberately
        # looser than requiring every selected term in one provider query.
        for index, concept in enumerate(non_pairing):
            add(
                "Google Books",
                _query_text([
                    identities[index % len(identities)],
                    _context_phrase(concept),
                ]),
                [concept],
            )

        # Identity-only searches recover books whose descriptions/categories
        # contain the remaining selected concepts.
        add("Google Books", identities[0])
        if len(identities) > 1:
            add("Google Books", identities[1])

        # Open Library is supplemental. Its fuzzy query membership is never
        # treated as pairing evidence; only the returned book metadata is.
        open_parts = [identities[0]]
        open_parts.extend(_context_phrase(c) for c in non_pairing[:2])
        add("Open Library", _query_text(open_parts))
        if pairing == "mm":
            add("Open Library", 'subject:"gay men"')
            add("Open Library", 'subject:"gay romance"')
        else:
            add("Open Library", 'subject:"lesbian romance"')
            add("Open Library", 'subject:"lesbians"')

    else:
        # General trope combinations: singles, then pairs, then full combination.
        # This prevents sparse catalog metadata from collapsing recall to zero.
        for concept in concepts:
            add(
                "Google Books",
                _context_phrase(concept),
                [concept],
            )

        for left in range(len(concepts)):
            for right in range(left + 1, len(concepts)):
                pair = [concepts[left], concepts[right]]
                add(
                    "Google Books",
                    _query_text(_context_phrase(c) for c in pair),
                    pair,
                )

        add(
            "Google Books",
            _query_text(_context_phrase(c) for c in concepts),
            concepts,
        )
        add(
            "Open Library",
            _query_text(_context_phrase(c) for c in concepts),
        )

    return tasks[:MAX_QUERY_TASKS]


def _run_batch(tasks):
    if not tasks:
        return []

    def run(task):
        provider, query, hint_concepts = task
        result = discovery.provider_books(
            provider,
            query,
            discovery.GOOGLE_LIMIT
            if provider == "Google Books"
            else discovery.OPEN_LIBRARY_LIMIT,
        )

        if result["ok"] and provider == "Google Books":
            # Search membership is weak evidence only for non-pairing concepts.
            safe_hints = [
                concept for concept in hint_concepts
                if concept not in PAIRINGS
            ]
            for book in result["books"]:
                book["retrievedConcepts"] = discovery.unique([
                    *book.get("retrievedConcepts", []),
                    *safe_hints,
                ])
                book["retrievalHits"] = int(book.get("retrievalHits", 0)) + 1
        return result

    with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(tasks))) as pool:
        return list(pool.map(run, tasks))


def _rank(responses, labels, genre_map):
    books = [
        book
        for response in responses
        for book in response.get("books", [])
    ]
    ranked = discovery.rank_candidates(books, labels, genre_map)
    ranked.sort(key=lambda book: (
        -len(book.get("conceptMatches", [])),
        -int(bool(book.get("exactMatch"))),
        -int(book.get("retrievalHits", 0)),
        -int(book.get("evidenceScore", 0)),
        -int(bool(book.get("cover"))),
        int(book.get("providerRank", 9999)),
        discovery.normalise(book.get("title")),
    ))
    return ranked


def recommend(subjects, genre_map=None):
    resolved = discovery.resolve_concepts(subjects, genre_map)
    labels = [label for label, _ in resolved]
    cache_key = (
        "staged-recommend-v2",
        tuple((label, concept) for label, concept in resolved),
    )

    def make():
        tasks = build_queries(labels, genre_map)
        primary = tasks[:PRIMARY_QUERY_COUNT]
        fallback = tasks[PRIMARY_QUERY_COUNT:]

        responses = _run_batch(primary)
        ranked = _rank(responses, labels, genre_map)
        exact = sum(bool(book.get("exactMatch")) for book in ranked)

        if fallback and (
            len(ranked) < TARGET_SUGGESTIONS
            or exact < TARGET_FULL_MATCHES
        ):
            responses.extend(_run_batch(fallback))
            ranked = _rank(responses, labels, genre_map)
            exact = sum(bool(book.get("exactMatch")) for book in ranked)

        available = sorted({
            response["provider"]
            for response in responses
            if response.get("ok")
        })
        unavailable = sorted(
            {
                response["provider"]
                for response in responses
                if not response.get("ok")
            }
            - set(available)
        )

        if not ranked and not available:
            raise requests.RequestException(
                "Book catalogs are temporarily unavailable."
            )

        return {
            "books": ranked,
            "candidateCount": len(ranked),
            "exactCount": exact,
            "checkedQueries": sum(bool(r.get("ok")) for r in responses),
            "totalQueries": len(responses),
            "concepts": [
                {"label": label, "canonical": concept}
                for label, concept in resolved
            ],
            "sources": available,
            "unavailableSources": unavailable,
            "coverage": (
                "Live Google Books and Open Library discovery; broader searches "
                "are filtered and ranked by the selected concepts."
            ),
        }

    return discovery.cached(cache_key, make)
