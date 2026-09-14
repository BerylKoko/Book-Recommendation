"""Book Recommendation for searching and recommending books through Open Library
Author: BERYL KOKO
"""

from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
import re
import threading
import time

import requests
import discovery
from flask import Flask, jsonify, render_template, request


app = Flask(
    __name__
)

cache = OrderedDict()
cache_lock = threading.Lock()

SEARCH_LIMIT = 12
MATCH_LIMIT = 24
MAX_CONCEPT_ALIASES = 8
MAX_RECOMMENDATION_CANDIDATES = 72
MAX_FANOUT_WORKERS = 8


def normalise_tag(value):
    value = str(value or "").strip().lower()
    value = value.replace("&", " and ").replace("+", " and ")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def load_genre_map():
    path = Path(__file__).with_name("static") / "genres.json"

    try:
        with path.open("r", encoding="utf-8") as file:
            raw = json.load(file)
    except (OSError, json.JSONDecodeError):
        return {}

    genre_map = {}

    for canonical, related in raw.items():
        canonical_tag = normalise_tag(canonical)
        if not canonical_tag:
            continue

        genre_map[canonical_tag] = list(
            dict.fromkeys(
                normalise_tag(term)
                for term in (related or [])
                if normalise_tag(term)
            )
        )

    return genre_map


GENRE_MAP = load_genre_map()
ALIAS_OWNERS = {}

for canonical_tag, related_tags in GENRE_MAP.items():
    for alias in related_tags:
        ALIAS_OWNERS.setdefault(alias, []).append(canonical_tag)

CONCEPT_BRIDGES = {
    "mm": "gay romance",
    "m m": "gay romance"
}

CONCEPT_SEARCH_EXTRAS = {
    "gay romance": [
        "mm",
        "m m",
        "gay romance",
        "gay men",
        "gay fiction",
        "mm romance",
        "queer romance",
        "lgbtq romance"
    ]
}


def resolve_concept(label):
    selected = normalise_tag(label)
    canonical = None

    if selected in GENRE_MAP:
        canonical = selected
    elif selected in CONCEPT_BRIDGES:
        canonical = CONCEPT_BRIDGES[selected]
    else:
        owners = ALIAS_OWNERS.get(selected, [])
        if len(owners) == 1:
            canonical = owners[0]

    terms = []

    def add(term):
        term = normalise_tag(term)
        if term and term not in terms:
            terms.append(term)

    add(selected)

    if canonical:
        for term in CONCEPT_SEARCH_EXTRAS.get(canonical, []):
            add(term)
        add(canonical)
        for term in GENRE_MAP.get(canonical, []):
            add(term)

    return {
        "label": label,
        "canonical": canonical or selected,
        "aliases": terms[:MAX_CONCEPT_ALIASES]
    }


def subject_query(term):
    cleaned = str(term).replace('"', " ").replace("\\", " ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return f'subject:"{cleaned}"'


def get_books(query, page=1, sort="relevance", matching=False):
    cache_key = (query, page, sort, matching)

    with cache_lock:
        cached = cache.get(cache_key)

    if cached:
        saved_time, saved_result = cached

        if time.monotonic() - saved_time < 600:
            return saved_result

    url = "https://openlibrary.org/search.json"
    limit = MATCH_LIMIT if matching else SEARCH_LIMIT

    params = {
        "q": query,
        "page": page,
        "limit": limit,
        "fields": (
            "key,title,author_name,first_publish_year,"
            "cover_i,edition_count,subject"
        )
    }

    if sort == "new":
        params["sort"] = "new"

    response = requests.get(
        url,
        params=params,
        headers={
            "User-Agent": "BerylBookDiscovery/1.0 (portfolio student project)"
        },
        timeout=12
    )

    response.raise_for_status()
    data = response.json()

    books = data.get("docs", [])
    clean_books = []

    for item in books:
        book_id = item.get("key", "")

        if not re.fullmatch(r"/works/OL\d+W", book_id):
            continue

        cover_id = item.get("cover_i")

        if cover_id:
            cover = (
                f"https://covers.openlibrary.org/"
                f"b/id/{cover_id}-M.jpg"
            )
        else:
            cover = None

        author_names = list(
            dict.fromkeys(
                item.get("author_name") or []
            )
        )

        if author_names:
            authors = ", ".join(author_names)
        else:
            authors = "Unknown author"

        book_url = (
            "https://openlibrary.org"
            + book_id
        )

        clean_book = {
            "id": book_id,
            "title": item.get("title") or "Untitled",
            "authors": authors,
            "authorNames": author_names,
            "year": item.get("first_publish_year"),
            "cover": cover,
            "editions": item.get("edition_count", 0),
            "subjects": (item.get("subject") or [])[:100],
            "url": book_url
        }

        clean_books.append(clean_book)

    result = {
        "books": clean_books,
        "total": data.get("numFound", 0),
        "page": page,
        "limit": limit,
        "source": "Open Library"
    }

    with cache_lock:
        cache[cache_key] = (
            time.monotonic(),
            result
        )

        if len(cache) > 128:
            cache.popitem(last=False)

    return result


def get_recommendation_candidates(subjects):
    return discovery.recommend(subjects, GENRE_MAP)


@app.route("/")
def index():
    return render_template("index.html")


@app.route(
    "/recommendations",
    methods=["POST", "GET"]
)
def recommendations():
    query = request.values.get("query") or ""
    query = query.strip()
    query = query[:200]

    try:
        if query:
            result = discovery.search_books(query)
        else:
            result = {
                "books": []
            }

        error = None

    except (
        requests.RequestException,
        ValueError
    ):
        result = {
            "books": []
        }

        error = (
            "Book search is temporarily unavailable. "
            "Please try again."
        )

    return render_template(
        "recommendations.html",
        books=result["books"],
        query=query,
        error=error
    )


@app.get("/api/books")
def api_books():
    query = request.args.get("q") or ""
    query = query.strip()

    if not query or len(query) > 200:
        return jsonify(
            error=(
                "Enter a title, author or subject "
                "(up to 200 characters)."
            )
        ), 400

    try:
        page = int(
            request.args.get(
                "page",
                "1"
            )
        )

    except ValueError:
        return jsonify(
            error="Invalid page."
        ), 400

    if not 1 <= page <= 100:
        return jsonify(
            error="Invalid page."
        ), 400

    if request.args.get("sort") == "new":
        sort = "new"
    else:
        sort = "relevance"

    matching = (
        request.args.get("mode")
        == "match"
    )

    try:
        result = discovery.search_books(query, page)

        return jsonify(result)

    except (
        requests.RequestException,
        ValueError
    ):
        return jsonify(
            error=(
                "Book search is temporarily unavailable. "
                "Please try again."
            )
        ), 502


@app.get("/api/recommend")
def api_recommend():
    subjects = [
        subject.strip()
        for subject in request.args.getlist("subject")
        if subject.strip()
    ]

    if not 1 <= len(subjects) <= 3:
        return jsonify(
            error="Choose between 1 and 3 subjects."
        ), 400

    if any(len(subject) > 100 for subject in subjects):
        return jsonify(
            error="A selected subject is too long."
        ), 400

    try:
        return jsonify(
            get_recommendation_candidates(subjects)
        )
    except (
        requests.RequestException,
        ValueError
    ):
        return jsonify(
            error=(
                "Book recommendations are temporarily unavailable. "
                "Please try again."
            )
        ), 502


if __name__ == "__main__":
    app.run(port=5001)