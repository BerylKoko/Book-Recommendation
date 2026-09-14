"""Regression tests for the staged live recommendation retriever."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "book-recommendation"))
import discovery
import recommendation


def live_book(book_id, title, description, subjects=()):
    return {
        "id": book_id,
        "title": title,
        "subtitle": "",
        "authorNames": ["Example Author"],
        "authors": "Example Author",
        "year": 2024,
        "subjects": list(subjects),
        "description": description,
        "cover": "https://example.org/cover.jpg",
        "coverFallbacks": [],
        "editions": 1,
        "isbns": [],
        "url": "https://example.org/book",
        "source": "Google Books",
        "providerRank": 0,
        "retrievedConcepts": [],
    }


class RecommendationTests(unittest.TestCase):
    def setUp(self):
        discovery.CACHE.clear()
        discovery.COOLDOWN.clear()

    def test_mm_sports_college_uses_loose_and_sport_specific_queries(self):
        tasks = recommendation.build_queries(["mm", "sports", "college"])
        queries = [query.lower() for _, query, _ in tasks]
        self.assertTrue(any(query == "gay romance" for query in queries))
        self.assertTrue(any("college" in query for query in queries))
        for sport in ("hockey", "football", "baseball", "basketball", "soccer"):
            self.assertTrue(any(sport in query for query in queries))
        self.assertLessEqual(len(tasks), recommendation.MAX_QUERY_TASKS)

    @patch("recommendation.discovery.provider_books")
    def test_mm_sports_college_returns_live_exact_matches(self, provider):
        iced_out = live_book(
            "google:iced-out",
            "Iced Out",
            "An M/M college hockey romance between rival teammates.",
            ["Fiction / Romance / LGBTQ+ / Gay", "Sports romance"],
        )
        football = live_book(
            "google:football",
            "Campus Rivals",
            "A gay romance between two male college football players.",
            ["Gay romance", "Sports romance"],
        )

        def response(source, query, limit):
            query = query.lower()
            books = []
            if source == "Google Books" and "hockey" in query:
                books = [iced_out]
            if source == "Google Books" and "football" in query:
                books = [football]
            return {"books": books, "ok": True, "provider": source}

        provider.side_effect = response
        result = recommendation.recommend(["mm", "sports", "college"])
        self.assertGreaterEqual(result["exactCount"], 2)
        self.assertEqual(
            {"Iced Out", "Campus Rivals"},
            {book["title"] for book in result["books"]},
        )
        self.assertTrue(all(book["exactMatch"] for book in result["books"]))

    @patch("recommendation.discovery.provider_books")
    def test_search_membership_never_proves_mm(self, provider):
        straight = live_book(
            "google:straight",
            "Straight Hockey Romance",
            "A college hockey romance between a woman and a man.",
            ["Sports romance"],
        )
        provider.return_value = {
            "books": [straight],
            "ok": True,
            "provider": "Google Books",
        }
        result = recommendation.recommend(["mm", "sports", "college"])
        self.assertEqual([], result["books"])
        self.assertEqual(0, result["exactCount"])


if __name__ == "__main__":
    unittest.main()
