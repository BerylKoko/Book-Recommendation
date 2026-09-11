"""Book Recommendation for searching and recommending books through Open Library
Author: BERYL KOKO"""

from flask import Flask, render_template, request, jsonify
import requests
import time
import re
from collections import OrderedDict
cache = OrderedDict()
from pathlib import Path

app = Flask(__name__)
def get_books(query, page=1, sort='relevance', matching=False):
    url = "https://openlibrary.org/search.json"

    params = {
        "q": query
    }
    response = requests.get(url, params=params)

    data = response.json()

    books = data.get("docs", [])

    clean_books = []

    for item in books:
        cover_id = item.get("cover_i")

        if cover_id:
            cover = f"https://covers.openlibrary.org/b/id/{cover_id}-M.jpg"
        else:
            cover = None

        book_url = "https://openlibrary.org" + item.get("key", "")

        clean_book = {
            "id": item.get("key"),
            "title": item.get("title", "Untitled"),
            "authors": item.get("author_name", ["Unknown author"]),
            "year": item.get("first_publish_year"),
            "cover": cover,
            "editions": item.get("edition_count", 0),
            "subjects": item.get("subject", []),
            "url": book_url
        }

        clean_books.append(clean_book)

    result = {
    "books": clean_books,
    "total": data.get("numFound", 0),
    "page": page,
    "source": "Open Library"
}

    return result

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/recommendations', methods=['POST', 'GET'])
def recommendations():
    query = request.values.get("query") or ""
    query = query.strip()
    query = query[:200]

    try:
        if query:
            result = get_books(query)
        else:
            result = {"books": []}

        error = None

    except (requests.RequestException, ValueError):
        result = {"books": []}
        error = "Book search is temporarily unavailable. Please try again."

    return render_template(
    'recommendations.html',
    books=result['books'],
    query=query,
    error=error
)

@app.get('/api/books')
def api_books():
    query = (request.args.get('q') or '')
    query = query.strip()

    if not query or len(query) > 200:
    return jsonify(
        error='Enter a title, author or subject (up to 200 characters).'
    ), 400

    try:
        page = int(request.args.get('page', '1'))
    except ValueError:
        return jsonify(error='Invalid page.'), 400

    if not 1 <= page <= 100:
    return jsonify(error='Invalid page.'), 400


    if request.args.get('sort') == 'new':
        sort = 'new'
    else:
        sort = 'relevance'

    matching = request.args.get('mode') == 'match'

    result = get_books(query, page, sort, matching)

    return jsonify(result)

    except (requests.RequestException, ValueError):
        return jsonify(
            error='Book search is temporarily unavailable. Please try again.'
        ), 502

if __name__ == '__main__':
    app.run(port=5001)


