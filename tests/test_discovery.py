"""Regression checks for actual discovery failures, not provider uptime."""
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'book-recommendation'))
import discovery as d
from app import app


def book(title, subjects=(), description='', author='Example Author', id=None):
    return {'id': id or title, 'title': title, 'authorNames': [author], 'authors': author,
            'subjects': list(subjects), 'description': description, 'url': 'https://example.org/book'}


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        d.CACHE.clear()
        d.COOLDOWN.clear()

    def test_anchor_recall_and_order(self):
        rows = d.rank_candidates(d.CATALOG, ['mm', 'sports', 'college'])
        exact = [b for b in rows if b['exactMatch']]
        self.assertGreaterEqual(len(exact), 18)
        self.assertTrue({'Iced Out', 'Tempting Venom', 'Hidden Scars', "Don't You Dare",
                         'Never Have I Ever: Had a Bromance with a Teammate'} <= {b['title'] for b in exact})
        self.assertTrue(all(b['exactMatch'] for b in rows[:len(exact)]))
        self.assertTrue(all(len(b['conceptEvidence']) == 3 for b in exact))
        self.assertNotIn('You & Me', {b['title'] for b in exact})

    def test_synonyms_are_equivalent_not_related_topics(self):
        expected = {b['id'] for b in d.rank_candidates(d.CATALOG, ['mm', 'sports', 'college']) if b['exactMatch']}
        for terms in [['M/M', 'sports romance', 'university'], ['gay romance', 'sports', 'campus']]:
            actual = {b['id'] for b in d.rank_candidates(d.CATALOG, terms) if b['exactMatch']}
            self.assertEqual(expected, actual)
        for wrong in [book('FF Ice', ['lesbian romance', 'hockey', 'college']),
                      book('Broad queer', ['queer romance', 'hockey', 'college']),
                      book('Gay athletes history', ['gay men', 'sports', 'college'])]:
            self.assertEqual([], d.rank_candidates([wrong], ['mm', 'sports', 'college']))
        self.assertIsNone(d.concept_evidence(book('New adult', ['mm romance', 'new adult']), 'college'))
        self.assertIsNone(d.concept_evidence(book('Athletes', ['sports']), 'hockey'))
        self.assertIsNone(d.concept_evidence(book('MM Hockey Handbook'), 'hockey'))

    def test_narrower_combinations_change_results(self):
        cases = [(['mm', 'baseball', 'college'], {"Don't You Dare", 'Caught Stealing', 'Never Have I Ever: Had a Bromance with a Teammate'}),
                 (['mm', 'dark romance', 'mafia romance'], {'God of Fury', 'Hunt the Villain'})]
        for subjects, expected in cases:
            self.assertEqual(expected, {b['title'] for b in d.rank_candidates(d.CATALOG, subjects) if b['exactMatch']})
        hockey = {b['title'] for b in d.rank_candidates(d.CATALOG, ['mm', 'hockey', 'college']) if b['exactMatch']}
        self.assertNotIn("Don't You Dare", hockey)
        self.assertIn('Iced Out', hockey)

    def test_new_unindexed_book_can_match_from_provider_evidence(self):
        candidate = book('Previously Unindexed Romance', ['Fiction / Romance / LGBTQ+ / Gay'],
                         'A male/male romance between rival college hockey players.')
        rows = d.rank_candidates([candidate], ['mm', 'sports', 'college'])
        self.assertTrue(rows[0]['exactMatch'])
        self.assertEqual('catalog description', rows[0]['conceptEvidence']['college']['kind'])
        candidate['description'] = 'For fans of MM college hockey romance. This is a guide to fishing.'
        candidate['subjects'] = []
        self.assertEqual([], d.rank_candidates([candidate], ['mm', 'sports', 'college']))

    def test_deduplication_keeps_different_authors_and_series_subtitles(self):
        rows = [book('Iced Out', ['hockey'], author='C. E. Ricci', id='catalog:iced-out'),
                book('Iced Out', ['college'], author='CE Ricci', id='/works/OL123W'),
                book('Iced Out', author='Other Author', id='other'),
                *[b for b in d.CATALOG if b['title'].startswith('Never Have I Ever:')]]
        merged = d.merge_books(rows)
        self.assertEqual(5, len(merged))
        self.assertIn('/works/OL123W', merged[0]['alternateIds'])
        self.assertEqual(['hockey', 'college'], merged[0]['subjects'])

    def test_no_mutation_of_cached_or_input_books(self):
        before = copy.deepcopy(d.CATALOG)
        d.rank_candidates(d.CATALOG, ['mm', 'hockey', 'college'])
        self.assertEqual(before, d.CATALOG)
        result = d.cached('x', lambda: {'books': [book('Cached')]})
        result['books'][0]['title'] = 'Changed'
        self.assertEqual('Cached', d.cached('x', lambda: {})['books'][0]['title'])

    @patch('discovery.provider_books')
    def test_outage_still_returns_real_index_matches(self, provider):
        provider.side_effect = lambda source, *args: {'books': [], 'ok': False, 'provider': source}
        client = app.test_client()
        response = client.get('/api/recommend?subject=mm&subject=sports&subject=college')
        self.assertEqual(200, response.status_code)
        self.assertGreaterEqual(response.json['exactCount'], 18)
        self.assertEqual(['Google Books', 'Open Library'], response.json['unavailableSources'])
        search = client.get('/api/books?q=Tempting%20Venom')
        self.assertEqual('Tempting Venom', search.json['books'][0]['title'])
        self.assertIn('college', search.json['books'][0]['subjects'])
        self.assertEqual(502, client.get('/api/books?q=NoSuchUnindexedTitle').status_code)

    @patch('discovery.provider_books')
    def test_live_candidates_are_merged_and_search_pages_do_not_repeat(self, provider):
        live = [book(f'Unindexed Volume {i}', ['mm romance', 'college', 'hockey'], id=f'google:{i}') for i in range(30)]
        provider.side_effect = lambda source, *args: {'books': live if source == 'Google Books' else [], 'ok': source == 'Google Books', 'provider': source}
        result = d.recommend(['mm','sports','college'])
        self.assertGreaterEqual(result['exactCount'], 48)
        page1 = d.search_books('Unindexed', 1)
        page2 = d.search_books('Unindexed', 2)
        self.assertEqual(30, page1['total'])
        self.assertFalse({b['id'] for b in page1['books']} & {b['id'] for b in page2['books']})

    @patch('discovery.requests.get')
    def test_providers_parse_metadata_and_do_not_invent_first_publication(self, get):
        get.return_value.json.return_value = {'items': [{'id':'ABC_123','volumeInfo': {'title':'Live Book', 'authors':['A'], 'publishedDate':'2025-02-01', 'categories':['Romance'], 'description':'A <b>college</b> story.', 'imageLinks':{'thumbnail':'http://books.google.com/cover'}}}]}
        result = d.provider_books('Google Books', 'example')
        self.assertTrue(result['ok'])
        self.assertEqual('google:ABC_123', result['books'][0]['id'])
        self.assertIsNone(result['books'][0]['year'])
        self.assertEqual(2025, result['books'][0]['editionYear'])
        self.assertNotIn('<b>',result['books'][0]['description'])
        get.return_value.json.return_value = {'docs':[{'key':'/works/OL12W','title':'Live OL','subject':['College'],'first_publish_year':1998}]}
        result = d.provider_books('Open Library', 'example')
        self.assertEqual(1998,result['books'][0]['year'])

    def test_queries_search_combinations_with_bounded_fanout(self):
        tasks = d.build_queries(['mm', 'sports', 'college'])
        self.assertLessEqual(len(tasks),8)
        self.assertIn(' AND ',tasks[0][1])
        self.assertTrue(any('hockey' in query and 'college' in query for _,query in tasks))
        self.assertTrue(any('baseball' in query and 'college' in query for _,query in tasks))

    def test_validation_and_html(self):
        client=app.test_client()
        for path in ['/api/books?q=', '/api/books?q=x&page=nope', '/api/books?q=x&page=0',
                     '/api/recommend', '/api/recommend?subject=a&subject=b&subject=c&subject=d']:
            self.assertEqual(400,client.get(path).status_code)
        self.assertEqual(200,client.get('/').status_code)
        self.assertIn(b'custom-trait',client.get('/').data)
        self.assertEqual(len(d.CATALOG),len(d.load_catalog()))

if __name__ == '__main__': unittest.main()
