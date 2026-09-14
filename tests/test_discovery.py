"""Regression tests for live multi-source discovery."""
import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "book-recommendation"))
import discovery as d
from app import app


def book(
    book_id,
    title,
    subjects=(),
    description="",
    authors=("Example Author",),
    cover=None,
    rank=0,
    retrieved=(),
    isbns=(),
):
    return {
        "id": book_id,
        "title": title,
        "subtitle": "",
        "authorNames": list(authors),
        "authors": ", ".join(authors),
        "year": 2024,
        "subjects": list(subjects),
        "description": description,
        "cover": cover,
        "coverFallbacks": [],
        "editions": 1,
        "isbns": list(isbns),
        "url": "https://example.org/book",
        "source": "Google Books",
        "providerRank": rank,
        "retrievedConcepts": list(retrieved),
    }


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        d.CACHE.clear()
        d.COOLDOWN.clear()

    def test_mm_false_positive_is_rejected(self):
        good = book(
            "good",
            "Good",
            ["Fiction / Romance / LGBTQ+ / Gay"],
            "A college hockey romance between two men.",
        )
        bad = book(
            "bad",
            "Bad",
            ["Romance"],
            "A college hockey romance between a woman and a man.",
        )
        rows = d.rank_candidates([bad, good], ["mm", "sports", "college"])
        self.assertEqual([row["id"] for row in rows], ["good"])
        self.assertTrue(rows[0]["exactMatch"])

    def test_targeted_google_query_can_supply_weak_missing_metadata(self):
        sparse = book(
            "sparse",
            "Sparse",
            retrieved=["mm", "sports", "college"],
        )
        rows = d.rank_candidates([sparse], ["mm", "sports", "college"])
        self.assertTrue(rows[0]["exactMatch"])
        self.assertEqual(rows[0]["evidenceScore"], 3)
        self.assertEqual(
            rows[0]["conceptEvidence"]["mm"]["kind"],
            "search relevance",
        )

    def test_merge_prefers_google_cover_and_keeps_library_link(self):
        google = book(
            "google:bride",
            "Bride",
            ["Romance"],
            authors=("Ali Hazelwood",),
            cover="https://google.example/bride.jpg",
            isbns=("9780593641033",),
        )
        library = book(
            "/works/OL37588041W",
            "Bride",
            ["Fantasy"],
            authors=("Ali Hazelwood",),
            cover="https://covers.openlibrary.org/b/id/1-M.jpg",
            isbns=("9780593641033",),
        )
        library["source"] = "Open Library"
        library["readingUrl"] = "https://openlibrary.org/works/OL37588041W"
        row = d.merge_books([google, library])[0]
        self.assertEqual(row["cover"], "https://google.example/bride.jpg")
        self.assertIn(
            "https://covers.openlibrary.org/b/id/1-M.jpg",
            row["coverFallbacks"],
        )
        self.assertEqual(
            row["readingUrl"],
            "https://openlibrary.org/works/OL37588041W",
        )

    @patch("discovery.provider_books")
    def test_title_search_ranks_exact_match_and_pages_without_repeats(self, provider):
        bride = book(
            "google:bride",
            "Bride",
            ["Romance"],
            authors=("Ali Hazelwood",),
            cover="https://example.org/bride.jpg",
            rank=3,
        )
        others = [book(f"google:{i}", f"Bride Story {i}", rank=i) for i in range(20)]

        def response(source, query, limit):
            if source == "Google Books" and query.startswith("intitle:"):
                return {"books": [bride, *others], "ok": True, "provider": source}
            return {"books": [], "ok": True, "provider": source}

        provider.side_effect = response
        first = d.search_books("Bride", 1)
        second = d.search_books("Bride", 2)
        self.assertEqual(first["books"][0]["title"], "Bride")
        self.assertFalse(
            {row["id"] for row in first["books"]}
            & {row["id"] for row in second["books"]}
        )

    def test_sports_retrieval_checks_multiple_actual_sports(self):
        tasks = d.build_queries(["mm", "sports", "college"])
        self.assertLessEqual(len(tasks), d.MAX_RECOMMENDATION_QUERIES)
        text = "\n".join(query for _, query, _ in tasks)
        for sport in ("hockey", "football", "baseball", "basketball", "soccer"):
            self.assertIn(sport, text)

    @patch("discovery.requests.get")
    def test_provider_metadata_includes_year_and_cover_fallbacks(self, get):
        get.return_value.json.return_value = {
            "items": [{
                "id": "ABC_123",
                "volumeInfo": {
                    "title": "Live Book",
                    "authors": ["A"],
                    "publishedDate": "2025-02-01",
                    "categories": ["Romance"],
                    "description": "A <b>college</b> story.",
                    "industryIdentifiers": [{"identifier": "9780593641033"}],
                    "imageLinks": {"thumbnail": "http://books.google.com/cover"},
                },
            }]
        }
        result = d.provider_books("Google Books", "example")
        row = result["books"][0]
        self.assertEqual(row["year"], 2025)
        self.assertEqual(row["cover"], "https://books.google.com/cover")
        self.assertTrue(row["coverFallbacks"])
        self.assertNotIn("<b>", row["description"])

    def test_ranker_does_not_mutate_input(self):
        candidate = book(
            "x",
            "X",
            ["hockey"],
            "A college hockey romance between two men.",
        )
        before = copy.deepcopy(candidate)
        d.rank_candidates([candidate], ["mm", "sports", "college"])
        self.assertEqual(candidate, before)

    def test_validation_and_homepage(self):
        client = app.test_client()
        for path in (
            "/api/books?q=",
            "/api/books?q=x&page=nope",
            "/api/books?q=x&page=0",
            "/api/recommend",
            "/api/recommend?subject=a&subject=b&subject=c&subject=d",
        ):
            self.assertEqual(client.get(path).status_code, 400)
        page = client.get("/")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"custom-trait", page.data)


if __name__ == "__main__":
    unittest.main()
