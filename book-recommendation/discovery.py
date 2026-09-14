"""Evidence-based discovery. Retrieval synonyms are not proof of a trope.

Author/publisher annotations supplement live catalogs; every candidate goes
through the same matcher, regardless of its provider or the requested query.
"""
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from itertools import combinations
from pathlib import Path
import html
import json
import os
import re
import threading
import time
import unicodedata
from urllib.parse import quote

import requests


def normalise(value):
    value = unicodedata.normalize('NFKD', str(value or '')).encode('ascii', 'ignore').decode()
    return re.sub(r'\s+', ' ', re.sub(r'[^a-z0-9]+', ' ', value.lower().replace('&', ' and '))).strip()


# Only equivalent or narrower evidence belongs here. genres.json remains a
# retrieval vocabulary; its related topics must never become inferred facts.
EQUIVALENTS = {
    'mm': ['m/m', 'm m', 'mm romance', 'm/m romance', 'male male', 'male/male romance', 'gay romance', 'gay love stories', 'male x male'],
    'ff': ['f/f', 'f f', 'ff romance', 'lesbian romance', 'sapphic romance'],
    'college': ['university', 'universities', 'campus', 'college romance', 'university romance', 'campus romance', 'college students', 'undergraduates'],
    'sports': ['sport', 'sports romance', 'sports fiction', 'athlete', 'athletes', 'athletic romance'],
    'hockey': ['ice hockey', 'hockey players', 'college hockey'],
    'football': ['american football', 'college football', 'football players', 'nfl'],
    'baseball': ['college baseball', 'baseball players', 'mlb'],
    'enemies to lovers': ['rivals to lovers', 'hate to love', 'enemies romance'],
    'friends to lovers': ['best friends to lovers', 'friendship to romance'],
    'fake dating': ['fake relationship', 'pretend dating', 'fake boyfriend', 'fake girlfriend'],
    'dark romance': ['dark romantic fiction', 'dark mm romance', 'dark gay romance'],
    'roommates': ['roommate', 'roommate romance', 'housemates'],
    'hurt comfort': ['hurt/comfort', 'hurt and comfort', 'comfort after trauma'],
    'stepbrothers': ['stepbrother', 'step brothers', 'stepbrother romance'],
    'queer romance': ['lgbtq romance', 'lgbt romance', 'lgbtq+ romance'],
}
SPORTS = ('hockey', 'football', 'soccer', 'baseball', 'basketball', 'tennis',
          'swimming', 'figure skating', 'motorsport', 'formula one', 'boxing',
          'mma', 'rugby', 'lacrosse', 'volleyball', 'gymnastics', 'fencing', 'wrestling', 'water polo')
IMPLIES = {sport: ['sports'] for sport in SPORTS}
IMPLIES.update({'mm': ['queer romance', 'romance'], 'ff': ['queer romance', 'romance'],
                'dark romance': ['romance'], 'roommates': ['forced proximity']})
ALIASES = {normalise(term): key for key, values in EQUIVALENTS.items() for term in [key, *values]}


def canonical(value):
    value = normalise(value)
    return ALIASES.get(value, value)


def contains(text, term):
    return bool(term and f' {normalise(term)} ' in f' {normalise(text)} ')


def identity(book):
    # Subtitle/edition variants merge only with the same author; no fuzzy title guessing.
    title = re.sub(r'\s*\([^)]*(?:edition|cover|book \d|#\d)[^)]*\)', '', book.get('title', ''), flags=re.I)
    title = re.sub(r':\s*(?:an? (?:mm|m/m|gay|novel|romance)\b).*$', '', title, flags=re.I)
    title = re.sub(r"['’]", '', title)
    authors = book.get('authorNames') or [book.get('authors', '')]
    return normalise(title), tuple(sorted(re.sub(r'[^a-z0-9]', '', normalise(a)) for a in authors))


def load_catalog(path=None):
    path = path or Path(__file__).with_name('data') / 'catalog.json'
    if not path.exists():
        return []
    rows = json.loads(path.read_text(encoding='utf-8'))
    ids = set()
    for row in rows:
        if row['id'] in ids or not row['id'].startswith('catalog:'):
            raise ValueError('Catalog IDs must be unique and stable')
        ids.add(row['id'])
        if not row.get('title') or not row.get('authorNames') or not row.get('evidence'):
            raise ValueError('Catalog entries need a title, authors and sourced evidence')
        for tag, evidence in row['evidence'].items():
            if not evidence.get('note') or not evidence.get('url', '').startswith('https://'):
                raise ValueError(f'Missing provenance: {row["id"]} / {tag}')
        row['subjects'] = list(row['evidence'])
        row['authors'] = ', '.join(row['authorNames'])
        row['source'] = 'Bookmatch trope index'
        row.setdefault('year', None)
        row.setdefault('editions', 0)
        row.setdefault('cover', None)
        row.setdefault('url', next(iter(row['evidence'].values()))['url'])
    return rows


CATALOG = load_catalog()
CACHE = OrderedDict()
LOCK = threading.Lock()
COOLDOWN = {}


def cached(key, make):
    with LOCK:
        entry = CACHE.get(key)
        ttl = 60 if entry and (entry[1].get('ok') is False or entry[1].get('unavailableSources')) else 600
        if entry and time.monotonic() - entry[0] < ttl:
            return deepcopy(entry[1])
    result = make()
    with LOCK:
        CACHE[key] = (time.monotonic(), deepcopy(result))
        while len(CACHE) > 128:
            CACHE.popitem(last=False)
    return result


def provider_books(provider, query, limit=40):
    """Bounded calls, independent provider failures, and a short circuit breaker."""
    with LOCK:
        if COOLDOWN.get(provider, 0) > time.monotonic():
            return {'books': [], 'ok': False, 'provider': provider}
    def fetch():
        try:
            if provider == 'Open Library':
                url = 'https://openlibrary.org/search.json'
                params = {'q': query, 'limit': limit, 'fields': 'key,title,author_name,first_publish_year,cover_i,edition_count,subject,isbn'}
            else:
                url = 'https://www.googleapis.com/books/v1/volumes'
                params = {'q': query, 'maxResults': min(limit, 40), 'printType': 'books'}
                if os.environ.get('GOOGLE_BOOKS_API_KEY'):
                    params['key'] = os.environ['GOOGLE_BOOKS_API_KEY']
            response = requests.get(url, params=params, timeout=(4, 6),
                                    headers={'User-Agent': 'BerylBookDiscovery/2.0 (book recommendation project)'})
            response.raise_for_status()
            data = response.json()
            books = []
            if provider == 'Open Library':
                for item in data.get('docs', []):
                    if not re.fullmatch(r'/works/OL\d+W', item.get('key', '')):
                        continue
                    authors = item.get('author_name') or []
                    cover = item.get('cover_i')
                    books.append({'id': item['key'], 'title': item.get('title') or 'Untitled',
                        'authorNames': authors, 'authors': ', '.join(authors) or 'Unknown author',
                        'year': item.get('first_publish_year'), 'subjects': item.get('subject') or [],
                        'cover': f'https://covers.openlibrary.org/b/id/{cover}-M.jpg' if cover else None,
                        'editions': item.get('edition_count', 0), 'isbns': item.get('isbn') or [],
                        'url': 'https://openlibrary.org' + item['key'], 'source': provider})
            else:
                for item in data.get('items', []):
                    info = item.get('volumeInfo', {})
                    book_id = item.get('id', '')
                    if not re.fullmatch(r'[A-Za-z0-9_-]+', book_id):
                        continue
                    authors = info.get('authors') or []
                    year = re.match(r'\d{4}', info.get('publishedDate', ''))
                    cover = info.get('imageLinks', {}).get('thumbnail')
                    books.append({'id': 'google:' + book_id, 'title': info.get('title') or 'Untitled',
                        'subtitle': info.get('subtitle', ''), 'authorNames': authors,
                        'authors': ', '.join(authors) or 'Unknown author',
                        # Google dates describe this edition, not necessarily first publication.
                        'year': None, 'editionYear': int(year[0]) if year else None,
                        'subjects': info.get('categories') or [],
                        'description': html.unescape(re.sub('<[^>]*>', ' ', info.get('description', ''))),
                        'cover': cover.replace('http://', 'https://') if cover else None,
                        'editions': 0, 'isbns': [i['identifier'] for i in info.get('industryIdentifiers', []) if i.get('identifier')],
                        'url': 'https://books.google.com/books?id=' + quote(book_id), 'source': provider})
            return {'books': books, 'ok': True, 'provider': provider}
        except (requests.RequestException, ValueError, TypeError, KeyError):
            with LOCK:
                COOLDOWN[provider] = time.monotonic() + 60
            return {'books': [], 'ok': False, 'provider': provider}
    return cached(('provider', provider, query, limit), fetch)


def merge_books(books):
    merged = {}
    ids = {}
    for original in books:
        book = deepcopy(original)
        key = identity(book)
        # Never merge unknown authors solely by title.
        if not key[1] or key[1] == ('unknownauthor',):
            key = ('id', book['id'])
        key = ids.get(book['id'], key)
        ids[book['id']] = key
        if key not in merged:
            merged[key] = book
            merged[key]['alternateIds'] = list(book.get('alternateIds', []))
            continue
        row = merged[key]
        row['alternateIds'] = list(dict.fromkeys([*row['alternateIds'], book['id'], *book.get('alternateIds', [])]))
        row['subjects'] = list(dict.fromkeys(row.get('subjects', []) + book.get('subjects', [])))
        for field in ('cover', 'year', 'description', 'subtitle'):
            if not row.get(field) and book.get(field):
                row[field] = book[field]
        row.setdefault('evidence', {}).update(book.get('evidence', {}))
        if book['id'].startswith('/works/'):
            row['readingUrl'] = book['url']
    return list(merged.values())


def concept_evidence(book, concept):
    # Source-backed annotations include directional implications (hockey -> sports).
    for tag, evidence in book.get('evidence', {}).items():
        tag = canonical(tag)
        if concept == tag or concept in IMPLIES.get(tag, []):
            return {**evidence, 'kind': 'reviewed', 'tag': tag}
    terms = [concept, *EQUIVALENTS.get(concept, [])]
    terms += [tag for tag, parents in IMPLIES.items() if concept in parents]
    for subject in book.get('subjects', []):
        if canonical(subject) == concept or any(contains(subject, term) for term in terms):
            return {'kind': 'catalog subject', 'note': subject, 'url': book.get('url', '')}
    # Titles alone are not evidence: "College Hockey Guide" is not MM fiction.
    description = ' '.join(sentence for sentence in re.split(r'(?<=[.!?])\s+', ' '.join([book.get('subtitle', ''), book.get('description', '')]))
                           if not re.search(r'for (?:fans|readers) of|also by|author of|graduated from', sentence, re.I))
    for term in terms:
        if contains(description, term):
            # Reject simple explicit negation. Richer semantics require reviewed tags.
            if any(contains(description, f'{negative} {term}') for negative in ('not', 'no', 'without')):
                continue
            return {'kind': 'catalog description', 'note': f'Description mentions {term}.', 'url': book.get('url', '')}
    return None


def rank_candidates(books, subjects):
    concepts = [(label, canonical(label)) for label in subjects]
    ranked = []
    for book in merge_books(books):
        evidence = {label: found for label, concept in concepts if (found := concept_evidence(book, concept))}
        # Pairing is a requirement when explicitly selected. Do not fill an MM
        # request with MF/FF books just because both are about campus hockey.
        if any(concept in ('mm', 'ff') and label not in evidence for label, concept in concepts):
            continue
        if len(evidence) < (2 if len(concepts) == 3 else 1):
            continue
        book['conceptMatches'] = list(evidence)
        book['conceptEvidence'] = evidence
        book['missingConcepts'] = [label for label, _ in concepts if label not in evidence]
        book['exactMatch'] = len(evidence) == len(concepts)
        book['evidenceScore'] = sum({'reviewed': 3, 'catalog subject': 2, 'catalog description': 1}[e['kind']] for e in evidence.values())
        book['aliasMatchCount'] = 0  # Compatibility: repeated synonyms are not extra matches.
        ranked.append(book)
    return sorted(ranked, key=lambda b: (-len(b['conceptMatches']), -b['evidenceScore'], normalise(b['title']), b['id']))


def build_queries(subjects, genre_map=None):
    concepts = list(dict.fromkeys(canonical(s) for s in subjects))
    phrases = {'mm': '"gay romance"', 'ff': '"lesbian romance"', 'sports': '"sports romance"'}
    groups = []
    for concept in concepts:
        terms = [concept, *EQUIVALENTS.get(concept, [])[:3]]
        if concept == 'sports':
            terms += ['hockey', 'football', 'baseball', 'basketball', 'fencing']
        groups.append('(' + ' OR '.join('"' + normalise(term) + '"' for term in dict.fromkeys(terms)) + ')')
    queries = [('Open Library', ' AND '.join(groups))]
    queries.append(('Google Books', ' '.join(phrases.get(c, '"' + c + '"') for c in concepts)))
    # Pairwise queries recover sparse metadata without first-page broad-list intersection.
    if len(groups) == 3:
        queries += [('Open Library', ' AND '.join(pair)) for pair in combinations(groups, 2)]
    if 'sports' in concepts:
        for sport in ('hockey', 'football', 'baseball'):
            queries.append(('Google Books', ' '.join(phrases.get(c, '"' + c + '"') if c != 'sports' else sport for c in concepts)))
    elif genre_map:
        # Related words may broaden retrieval, but never the evidence classifier.
        expanded = [phrases.get(c, '"' + normalise((genre_map.get(c) or [c])[0]) + '"') for c in concepts]
        queries.append(('Google Books', ' '.join(expanded)))
    return list(dict.fromkeys(queries))[:8]


def recommend(subjects, genre_map=None):
    unique = {}
    for subject in subjects:
        unique.setdefault(canonical(subject), subject)
    subjects = list(unique.values())
    def make():
        tasks = build_queries(subjects, genre_map)
        with ThreadPoolExecutor(max_workers=8) as pool:
            responses = list(pool.map(lambda task: provider_books(*task), tasks))
        books = rank_candidates([*CATALOG, *(book for response in responses for book in response['books'])], subjects)
        exact = sum(book['exactMatch'] for book in books)
        available = sorted({r['provider'] for r in responses if r['ok']})
        return {'books': books, 'candidateCount': len(books), 'exactCount': exact,
            'checkedQueries': sum(r['ok'] for r in responses), 'totalQueries': len(tasks),
            'concepts': [{'label': s, 'canonical': canonical(s)} for s in subjects],
            'sources': ['Bookmatch trope index', *available],
            'unavailableSources': sorted({r['provider'] for r in responses if not r['ok']} - set(available)),
            'coverage': 'Results from the trope index and available catalog metadata; not an exhaustive bibliography.'}
    return cached(('recommend', tuple(subjects)), make)


def search_books(query, page=1, limit=12):
    def make():
        words = normalise(query).split()
        local = [b for b in CATALOG if all(word in normalise(b['title'] + ' ' + b['authors']) for word in words)]
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(lambda provider: provider_books(provider, query, 100 if provider == 'Open Library' else 40), ['Open Library', 'Google Books']))
        # Enrich live hits with reviewed tags even when the query only matches a subtitle.
        live = [b for r in responses for b in r['books']]
        live_keys = {identity(b) for b in live}
        annotations = [b for b in CATALOG if identity(b) in live_keys]
        books = merge_books([*local, *annotations, *live])
        unavailable = [r['provider'] for r in responses if not r['ok']]
        if not books and len(unavailable) == 2:
            raise requests.RequestException('Live catalogs are unavailable and no indexed title matched.')
        return {'books': books, 'unavailableSources': unavailable}
    result = cached(('search', query), make)
    start = (page - 1) * limit
    return {**result, 'books': result['books'][start:start + limit], 'total': len(result['books']),
            'page': page, 'limit': limit, 'source': 'Bookmatch + Open Library + Google Books'}
