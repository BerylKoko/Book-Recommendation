"""Book Recommendation: title search and evidence-based trope discovery.
Author: BERYL KOKO
"""

import json
from pathlib import Path
import re

import requests
import discovery
from flask import Flask, jsonify, render_template, request


app = Flask(
    __name__
)

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