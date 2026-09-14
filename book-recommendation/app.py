"""Book Recommendation for searching and recommending books through Open Library
Author: BERYL KOKO
"""

from collections import OrderedDict
import re
import time

import requests
from flask import Flask, jsonify, render_template, request


app = Flask(
    __name__
)

cache = OrderedDict()

SEARCH_LIMIT = 12
MATCH_LIMIT = 24


def get_books(query, page=1, sort="relevance", matching=False):
    cache_key = (query, page, sort, matching)

    # Use cached results for up to 10 minutes
    if cache_key in cache:
        saved_time, saved_result = cache[cache_key]

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

        # Only keep valid Open Library work IDs
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

    # Save result in cache
    cache[cache_key] = (
        time.monotonic(),
        result
    )

    # Prevent cache from growing forever
    if len(cache) > 128:
        cache.popitem(last=False)

    return result


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
            result = get_books(query)
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
        result = get_books(
            query,
            page,
            sort,
            matching
        )

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


if __name__ == "__main__":
    app.run(port=5001)