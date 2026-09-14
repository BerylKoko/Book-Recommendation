"""Live, multi-source book discovery and trope matching.

The engine uses Google Books and Open Library directly. The trope JSON is a
retrieval vocabulary only; no manually indexed books are required.
"""
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import html
import os
import re
import threading
import time
import unicodedata
from urllib.parse import quote

import requests


CACHE = OrderedDict()
LOCK = threading.Lock()
COOLDOWN = {}
MAX_CACHE = 128
SEARCH_PAGE_SIZE = 12
GOOGLE_LIMIT = 40
OPEN_LIBRARY_LIMIT = 80
MAX_RECOMMENDATION_QUERIES = 8


def normalise(value):
    value = unicodedata.normalize("NFKD", str(value or ""))
    value = value.encode("ascii", "ignore").decode()
    value = value.lower().replace("&", " and ").replace("+", " and ")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", value)).strip()


EQUIVALENTS = {
    "mm": [
        "m/m", "m m", "mm romance", "m/m romance", "male male romance",
        "male/male romance", "gay romance", "gay love stories", "gay men",
        "gay fiction",
    ],
    "ff": ["f/f", "f f", "ff romance", "lesbian romance", "sapphic romance"],
    "college": [
        "university", "campus", "college romance", "university romance",
        "campus romance", "college students", "university students",
        "undergraduates", "college life", "student life",
    ],
    "sports": [
        "sport", "sports romance", "sports fiction", "athlete", "athletes",
        "athlete romance", "college athletes",
    ],
    "hockey": ["ice hockey", "hockey romance", "hockey players", "college hockey"],
    "football": ["american football", "football romance", "football players", "college football", "nfl"],
    "baseball": ["baseball romance", "baseball players", "college baseball", "mlb"],
    "basketball": ["basketball romance", "basketball players", "college basketball", "nba"],
    "soccer": ["footballers", "soccer romance", "soccer players", "college soccer"],
    "dark romance": ["dark romantic fiction", "dark romance fiction", "dark romantic"],
    "enemies to lovers": ["rivals to lovers", "hate to love", "enemies romance"],
    "friends to lovers": ["best friends to lovers", "friendship to romance", "friends romance"],
    "fake dating": ["fake relationship", "pretend dating", "relationship of convenience"],
    "forced proximity": ["stuck together", "close quarters romance", "forced together"],
    "roommates": ["roommate", "roommate romance", "housemates"],
    "hurt comfort": ["hurt/comfort", "hurt and comfort", "comfort after trauma"],
    "slow burn": ["slow burn romance", "gradual romance", "romantic longing"],
    "queer romance": ["lgbtq romance", "lgbt romance", "lgbtq+ romance", "queer love stories"],
}
SPORTS = (
    "hockey", "football", "soccer", "baseball", "basketball", "tennis",
    "swimming", "figure skating", "motorsport", "formula one", "boxing",
    "mma", "rugby", "lacrosse", "volleyball", "gymnastics", "fencing",
    "wrestling", "water polo",
)
IMPLIES = {sport: ["sports"] for sport in SPORTS}
IMPLIES.update({
    "mm": ["queer romance", "romance"],
    "ff": ["queer romance", "romance"],
    "dark romance": ["romance"],
    "roommates": ["forced proximity"],
})
ALIASES = {
    normalise(term): concept
    for concept, values in EQUIVALENTS.items()
    for term in [concept, *values]
}


def genre_alias_owners(genre_map):
    owners = {}
    for canonical_name, aliases in (genre_map or {}).items():
        canonical_name = normalise(canonical_name)
        for alias in aliases or []:
            owners.setdefault(normalise(alias), set()).add(canonical_name)
    return owners


def canonical(value, genre_map=None):
    value = normalise(value)
    if value in ALIASES:
        return ALIASES[value]
    if genre_map:
        if value in genre_map:
            return value
        owners = genre_alias_owners(genre_map).get(value, set())
        if len(owners) == 1:
            return next(iter(owners))
    return value


def contains(text, term):
    term = normalise(term)
    return bool(term and f" {term} " in f" {normalise(text)} ")


def clean_description(value):
    value = html.unescape(str(value or ""))
    return re.sub(r"\s+", " ", re.sub(r"<[^>]*>", " ", value)).strip()


def clean_cover(value):
    value = str(value or "").strip()
    if not value:
        return None
    if value.startswith("http://"):
        value = "https://" + value[len("http://"):]
    return value if value.startswith("https://") else None


def isbn_cover(isbns):
    for isbn in isbns or []:
        isbn = re.sub(r"[^0-9Xx]", "", str(isbn))
        if len(isbn) in (10, 13):
            return f"https://covers.openlibrary.org/b/isbn/{isbn}-M.jpg?default=false"
    return None


def unique(values):
    return list(dict.fromkeys(value for value in values if value))


def cached(key, make):
    with LOCK:
        entry = CACHE.get(key)
        if entry:
            saved_at, result = entry
            ttl = 60 if result.get("ok") is False else 600
            if time.monotonic() - saved_at < ttl:
                return deepcopy(result)
    result = make()
    with LOCK:
        CACHE[key] = (time.monotonic(), deepcopy(result))
        while len(CACHE) > MAX_CACHE:
            CACHE.popitem(last=False)
    return result


def provider_books(provider, query, limit=40):
    """Fetch one bounded result set from a live provider."""
    cache_key = ("provider", provider, query, limit)

    def make():
        with LOCK:
            if COOLDOWN.get(provider, 0) > time.monotonic():
                return {"books": [], "ok": False, "provider": provider}

        try:
            if provider == "Google Books":
                url = "https://www.googleapis.com/books/v1/volumes"
                params = {
                    "q": query,
                    "maxResults": min(int(limit), GOOGLE_LIMIT),
                    "orderBy": "relevance",
                    "printType": "books",
                    "projection": "full",
                }
                if os.environ.get("GOOGLE_BOOKS_API_KEY"):
                    params["key"] = os.environ["GOOGLE_BOOKS_API_KEY"]
            elif provider == "Open Library":
                url = "https://openlibrary.org/search.json"
                params = {
                    "q": query,
                    "limit": min(int(limit), 100),
                    "fields": (
                        "key,title,author_name,first_publish_year,cover_i,"
                        "edition_count,subject,isbn"
                    ),
                }
            else:
                raise ValueError("Unknown provider")

            response = requests.get(
                url,
                params=params,
                timeout=(4, 8),
                headers={
                    "User-Agent": "BerylBookDiscovery/3.0 (portfolio student project)"
                },
            )
            response.raise_for_status()
            data = response.json()
            books = []

            if provider == "Google Books":
                for rank, item in enumerate(data.get("items", [])):
                    info = item.get("volumeInfo", {})
                    book_id = item.get("id", "")
                    if not re.fullmatch(r"[A-Za-z0-9_-]+", book_id):
                        continue
                    authors = info.get("authors") or []
                    published = str(info.get("publishedDate") or "")
                    year_match = re.match(r"\d{4}", published)
                    image_links = info.get("imageLinks") or {}
                    cover_candidates = unique(
                        clean_cover(image_links.get(size))
                        for size in (
                            "extraLarge", "large", "medium", "small",
                            "thumbnail", "smallThumbnail",
                        )
                    )
                    isbns = [
                        identifier.get("identifier")
                        for identifier in info.get("industryIdentifiers", [])
                        if identifier.get("identifier")
                    ]
                    fallback = isbn_cover(isbns)
                    if fallback:
                        cover_candidates.append(fallback)
                    books.append({
                        "id": "google:" + book_id,
                        "title": info.get("title") or "Untitled",
                        "subtitle": info.get("subtitle") or "",
                        "authorNames": authors,
                        "authors": ", ".join(authors) or "Unknown author",
                        "year": int(year_match.group()) if year_match else None,
                        "subjects": info.get("categories") or [],
                        "description": clean_description(info.get("description")),
                        "cover": cover_candidates[0] if cover_candidates else None,
                        "coverFallbacks": cover_candidates[1:],
                        "editions": 0,
                        "isbns": isbns,
                        "url": clean_cover(info.get("canonicalVolumeLink"))
                               or clean_cover(info.get("infoLink"))
                               or f"https://books.google.com/books?id={quote(book_id)}",
                        "source": provider,
                        "providerRank": rank,
                        "retrievedConcepts": [],
                    })
            else:
                for rank, item in enumerate(data.get("docs", [])):
                    book_id = item.get("key", "")
                    if not re.fullmatch(r"/works/OL\d+W", book_id):
                        continue
                    authors = item.get("author_name") or []
                    isbns = item.get("isbn") or []
                    cover_candidates = []
                    cover_id = item.get("cover_i")
                    if cover_id:
                        cover_candidates.append(
                            f"https://covers.openlibrary.org/b/id/{cover_id}-M.jpg"
                        )
                    fallback = isbn_cover(isbns)
                    if fallback:
                        cover_candidates.append(fallback)
                    books.append({
                        "id": book_id,
                        "title": item.get("title") or "Untitled",
                        "subtitle": "",
                        "authorNames": authors,
                        "authors": ", ".join(authors) or "Unknown author",
                        "year": item.get("first_publish_year"),
                        "subjects": item.get("subject") or [],
                        "description": "",
                        "cover": cover_candidates[0] if cover_candidates else None,
                        "coverFallbacks": cover_candidates[1:],
                        "editions": item.get("edition_count", 0),
                        "isbns": isbns,
                        "url": "https://openlibrary.org" + book_id,
                        "readingUrl": "https://openlibrary.org" + book_id,
                        "source": provider,
                        "providerRank": rank,
                        "retrievedConcepts": [],
                    })

            return {"books": books, "ok": True, "provider": provider}

        except (requests.RequestException, ValueError, TypeError, KeyError):
            with LOCK:
                COOLDOWN[provider] = time.monotonic() + 45
            return {"books": [], "ok": False, "provider": provider}

    return cached(cache_key, make)


def same_book(left, right):
    left_isbns = {re.sub(r"[^0-9Xx]", "", str(x)) for x in left.get("isbns", []) if x}
    right_isbns = {re.sub(r"[^0-9Xx]", "", str(x)) for x in right.get("isbns", []) if x}
    if left_isbns & right_isbns:
        return True

    left_title = normalise(left.get("title"))
    right_title = normalise(right.get("title"))
    if not left_title or left_title != right_title:
        return False

    left_authors = {normalise(a).replace(" ", "") for a in left.get("authorNames", []) if a}
    right_authors = {normalise(a).replace(" ", "") for a in right.get("authorNames", []) if a}
    return bool(left_authors and right_authors and left_authors & right_authors)


def merge_two(base, incoming):
    row = deepcopy(base)
    row["alternateIds"] = unique([
        *row.get("alternateIds", []), incoming.get("id"),
        *incoming.get("alternateIds", []),
    ])
    row["subjects"] = unique([*row.get("subjects", []), *incoming.get("subjects", [])])
    row["isbns"] = unique([*row.get("isbns", []), *incoming.get("isbns", [])])
    row["retrievedConcepts"] = unique([
        *row.get("retrievedConcepts", []), *incoming.get("retrievedConcepts", [])
    ])
    row["providerRank"] = min(
        int(row.get("providerRank", 9999)),
        int(incoming.get("providerRank", 9999)),
    )

    if incoming.get("source") == "Google Books":
        cover_order = [
            incoming.get("cover"), *incoming.get("coverFallbacks", []),
            row.get("cover"), *row.get("coverFallbacks", []),
        ]
    else:
        cover_order = [
            row.get("cover"), *row.get("coverFallbacks", []),
            incoming.get("cover"), *incoming.get("coverFallbacks", []),
        ]
    all_covers = unique([*cover_order, isbn_cover(row["isbns"])])
    row["cover"] = all_covers[0] if all_covers else None
    row["coverFallbacks"] = all_covers[1:]

    for field in ("description", "subtitle", "year", "readingUrl"):
        if not row.get(field) and incoming.get(field):
            row[field] = incoming[field]
    if incoming.get("source") == "Google Books" and incoming.get("description"):
        row["description"] = incoming["description"]
    if incoming.get("readingUrl"):
        row["readingUrl"] = incoming["readingUrl"]
    if row.get("authors") == "Unknown author" and incoming.get("authors"):
        row["authors"] = incoming["authors"]
        row["authorNames"] = incoming.get("authorNames", [])
    return row


def merge_books(books):
    merged = []
    for original in books:
        book = deepcopy(original)
        book.setdefault("alternateIds", [])
        book.setdefault("coverFallbacks", [])
        book.setdefault("retrievedConcepts", [])
        match_index = next(
            (index for index, row in enumerate(merged) if same_book(row, book)),
            None,
        )
        if match_index is None:
            covers = unique([
                book.get("cover"), *book.get("coverFallbacks", []),
                isbn_cover(book.get("isbns", [])),
            ])
            book["cover"] = covers[0] if covers else None
            book["coverFallbacks"] = covers[1:]
            merged.append(book)
        else:
            merged[match_index] = merge_two(merged[match_index], book)
    return merged


def search_score(book, query):
    query_n = normalise(query)
    title = normalise(book.get("title"))
    authors = normalise(" ".join(book.get("authorNames") or []))
    query_words = set(query_n.split())
    title_words = set(title.split())
    overlap = len(query_words & title_words) / max(1, len(query_words))

    score = 0
    if title == query_n:
        score += 120
    elif title.startswith(query_n):
        score += 85
    elif query_n and query_n in title:
        score += 65
    elif query_words and query_words <= title_words:
        score += 50
    score += round(overlap * 35)

    if authors == query_n:
        score += 70
    elif query_n and query_n in authors:
        score += 35

    score += max(0, 25 - int(book.get("providerRank", 25)))
    if book.get("cover"):
        score += 12
    if book.get("description"):
        score += 6
    if book.get("subjects"):
        score += 4
    if book.get("year"):
        score += 2
    return score


def search_books(query, page=1, limit=SEARCH_PAGE_SIZE):
    query = str(query or "").strip()

    def make():
        title_query = f'intitle:"{query}"'
        tasks = [
            ("Google Books", title_query, GOOGLE_LIMIT),
            ("Google Books", query, GOOGLE_LIMIT),
            ("Open Library", f'title:"{query}"', OPEN_LIBRARY_LIMIT),
            ("Open Library", query, OPEN_LIBRARY_LIMIT),
        ]
        with ThreadPoolExecutor(max_workers=4) as pool:
            responses = list(pool.map(lambda task: provider_books(*task), tasks))

        books = merge_books([
            book
            for response in responses
            for book in response["books"]
        ])
        for book in books:
            book["searchScore"] = search_score(book, query)
        books.sort(key=lambda book: (-book["searchScore"], normalise(book["title"])))
        available_set = {r["provider"] for r in responses if r["ok"]}
        unavailable = sorted(
            {r["provider"] for r in responses if not r["ok"]} - available_set
        )
        available = sorted(available_set)
        if not books and not available:
            raise requests.RequestException("Book catalogs are temporarily unavailable.")
        return {"books": books, "unavailableSources": unavailable, "sources": available}

    result = cached(("search", normalise(query)), make)
    start = (page - 1) * limit
    return {
        **result,
        "books": result["books"][start:start + limit],
        "total": len(result["books"]),
        "page": page,
        "limit": limit,
        "source": "Google Books + Open Library",
    }


def resolve_concepts(subjects, genre_map=None):
    unique_concepts = []
    seen = set()
    for label in subjects:
        concept = canonical(label, genre_map)
        if not concept or concept in seen:
            continue
        seen.add(concept)
        unique_concepts.append((str(label).strip(), concept))
    return unique_concepts


def retrieval_terms(concept, genre_map=None):
    terms = [concept, *EQUIVALENTS.get(concept, [])]
    if genre_map:
        terms.extend(genre_map.get(concept, []) or [])
    if concept == "mm":
        terms = ["gay romance", "m/m romance", "mm romance", *terms]
    elif concept == "ff":
        terms = ["lesbian romance", "sapphic romance", *terms]
    return unique(normalise(term) for term in terms)[:8]


def quote_term(term):
    term = str(term).strip()
    return f'"{term}"' if " " in term or "/" in term else term


def query_variants(concept, genre_map=None):
    special = {
        "mm": ["mm romance", "gay romance", "m/m romance", "male male romance"],
        "ff": ["lesbian romance", "f/f romance", "sapphic romance"],
        "sports": ["sports romance", "athlete romance", "sports"],
        "college": ["college", "university", "campus"],
        "dark romance": ["dark romance", "dark romantic fiction"],
        "enemies to lovers": ["enemies to lovers", "rivals to lovers"],
        "friends to lovers": ["friends to lovers", "best friends to lovers"],
        "fake dating": ["fake dating", "fake relationship"],
        "forced proximity": ["forced proximity", "stuck together"],
        "slow burn": ["slow burn", "slow burn romance"],
    }
    raw = special.get(concept, retrieval_terms(concept, genre_map)[:3] or [concept])
    if concept in ("mm", "ff"):
        return unique(raw)
    return [quote_term(term) for term in unique(raw)]


def query_phrase(concept, genre_map=None):
    return query_variants(concept, genre_map)[0]


def build_queries(subjects, genre_map=None):
    concepts = [concept for _, concept in resolve_concepts(subjects, genre_map)]
    if not concepts:
        return []

    tasks = []

    def add(provider, query, evidence_concepts=()):
        item = (provider, query, tuple(evidence_concepts))
        if query and item not in tasks:
            tasks.append(item)

    variants = {concept: query_variants(concept, genre_map) for concept in concepts}
    all_variant_count = 2 if "sports" in concepts else 3
    for index in range(all_variant_count):
        query = " ".join(
            variants[concept][index % len(variants[concept])]
            for concept in concepts
        )
        add("Google Books", query, concepts)

    if "sports" in concepts and not any(sport in concepts for sport in SPORTS):
        others = [concept for concept in concepts if concept != "sports"]
        for index, sport in enumerate(("hockey", "football", "baseball", "basketball", "soccer")):
            query_parts = [
                variants[concept][index % len(variants[concept])]
                for concept in others
            ]
            query_parts.append(sport)
            add("Google Books", " ".join(query_parts), [*others, "sports"])

    open_library_query = " ".join(query_phrase(concept, genre_map) for concept in concepts)
    add("Open Library", open_library_query)

    if len(concepts) == 3 and len(tasks) < MAX_RECOMMENDATION_QUERIES:
        pairs = ((0, 1), (0, 2), (1, 2))
        for left, right in pairs:
            pair = [concepts[left], concepts[right]]
            add(
                "Google Books",
                " ".join(query_phrase(concept, genre_map) for concept in pair),
                pair,
            )
            if len(tasks) >= MAX_RECOMMENDATION_QUERIES:
                break

    return tasks[:MAX_RECOMMENDATION_QUERIES]


def explicit_mm_evidence(text):
    text = normalise(text)
    return bool(re.search(
        r"\b(m m|mm romance|gay romance|gay men|male male|male x male|two men|two guys|two male)\b",
        text,
    ))


def concept_evidence(book, concept):
    concept = normalise(concept)
    subjects = book.get("subjects", []) or []
    terms = unique([concept, *EQUIVALENTS.get(concept, [])])
    implied_children = [child for child, parents in IMPLIES.items() if concept in parents]
    terms.extend(implied_children)

    joined_subjects = " ".join(str(subject) for subject in subjects)
    if concept == "mm" and (
        explicit_mm_evidence(joined_subjects)
        or (contains(joined_subjects, "gay") and contains(joined_subjects, "romance"))
    ):
        return {
            "kind": "category",
            "note": "Catalog categories identify gay/M/M romance.",
            "url": book.get("url", ""),
        }
    if concept == "ff" and (
        contains(joined_subjects, "lesbian romance")
        or contains(joined_subjects, "sapphic romance")
        or (contains(joined_subjects, "lesbian") and contains(joined_subjects, "romance"))
    ):
        return {
            "kind": "category",
            "note": "Catalog categories identify lesbian/F/F romance.",
            "url": book.get("url", ""),
        }

    for subject in subjects:
        subject_n = normalise(subject)
        if canonical(subject) == concept:
            return {"kind": "category", "note": subject, "url": book.get("url", "")}
        if any(contains(subject_n, term) for term in terms):
            return {"kind": "category", "note": subject, "url": book.get("url", "")}

    description = " ".join([
        book.get("subtitle", ""),
        book.get("description", ""),
    ])
    if concept == "mm" and explicit_mm_evidence(description):
        return {
            "kind": "description",
            "note": "The catalog description identifies an M/M or gay male romance.",
            "url": book.get("url", ""),
        }
    for term in terms:
        if contains(description, term):
            return {
                "kind": "description",
                "note": f"The catalog description mentions {term}.",
                "url": book.get("url", ""),
            }

    if concept in set(book.get("retrievedConcepts", [])):
        return {
            "kind": "search relevance",
            "note": f"Matched a targeted Google Books search for {concept}.",
            "url": book.get("url", ""),
        }
    return None


def rank_candidates(books, subjects, genre_map=None):
    concepts = resolve_concepts(subjects, genre_map)
    ranked = []
    for book in merge_books(books):
        evidence = {}
        for label, concept in concepts:
            found = concept_evidence(book, concept)
            if found:
                evidence[label] = found

        if any(concept in ("mm", "ff") and label not in evidence for label, concept in concepts):
            continue
        minimum = 2 if len(concepts) == 3 else 1
        if len(evidence) < minimum:
            continue

        book["conceptMatches"] = list(evidence)
        book["conceptEvidence"] = evidence
        book["missingConcepts"] = [label for label, _ in concepts if label not in evidence]
        book["exactMatch"] = len(evidence) == len(concepts)
        weights = {"category": 3, "description": 2, "search relevance": 1}
        book["evidenceScore"] = sum(weights[item["kind"]] for item in evidence.values())
        ranked.append(book)

    ranked.sort(key=lambda book: (
        -len(book["conceptMatches"]),
        -book["evidenceScore"],
        -int(bool(book.get("cover"))),
        int(book.get("providerRank", 9999)),
        normalise(book.get("title")),
    ))
    return ranked


def recommend(subjects, genre_map=None):
    concepts = resolve_concepts(subjects, genre_map)
    labels = [label for label, _ in concepts]

    def make():
        tasks = build_queries(labels, genre_map)

        def run(task):
            provider, query, evidence_concepts = task
            result = provider_books(
                provider,
                query,
                GOOGLE_LIMIT if provider == "Google Books" else OPEN_LIBRARY_LIMIT,
            )
            if result["ok"] and provider == "Google Books" and evidence_concepts:
                for book in result["books"]:
                    book["retrievedConcepts"] = unique([
                        *book.get("retrievedConcepts", []), *evidence_concepts
                    ])
            return result

        with ThreadPoolExecutor(max_workers=min(MAX_RECOMMENDATION_QUERIES, max(1, len(tasks)))) as pool:
            responses = list(pool.map(run, tasks)) if tasks else []

        books = rank_candidates(
            [book for response in responses for book in response["books"]],
            labels,
            genre_map,
        )
        exact = sum(bool(book.get("exactMatch")) for book in books)
        available = sorted({r["provider"] for r in responses if r["ok"]})
        unavailable = sorted({r["provider"] for r in responses if not r["ok"]} - set(available))
        if not books and not available:
            raise requests.RequestException("Book catalogs are temporarily unavailable.")
        return {
            "books": books,
            "candidateCount": len(books),
            "exactCount": exact,
            "checkedQueries": sum(r["ok"] for r in responses),
            "totalQueries": len(tasks),
            "concepts": [{"label": label, "canonical": concept} for label, concept in concepts],
            "sources": available,
            "unavailableSources": unavailable,
            "coverage": "Live results from Google Books and Open Library.",
        }

    cache_key = ("recommend", tuple((label, concept) for label, concept in concepts))
    return cached(cache_key, make)
