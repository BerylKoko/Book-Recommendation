"""Validate or merge independently sourced book records into the trope index.

Usage: python scripts/catalog.py --check
       python scripts/catalog.py --import-file additions.json
The import file uses the same list-of-records format as data/catalog.json.
"""
import argparse
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'book-recommendation'))
from discovery import identity, load_catalog

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--check', action='store_true')
parser.add_argument('--import-file', type=Path)
args = parser.parse_args()
path = ROOT / 'book-recommendation' / 'data' / 'catalog.json'
if args.import_file:
    incoming = load_catalog(args.import_file)
    records = {b['id']: b for b in json.loads(path.read_text(encoding='utf-8'))}
    raw = json.loads(args.import_file.read_text(encoding='utf-8'))
    for book in raw:
        records[book['id']] = book
    keys = [identity(book) for book in records.values()]
    if len(keys) != len(set(keys)):
        raise SystemExit('Duplicate title/author: reuse the existing catalog ID instead.')
    # Validate the complete replacement before atomically updating the tracked file.
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', dir=path.parent, delete=False, encoding='utf-8') as tmp:
        json.dump(list(records.values()), tmp, ensure_ascii=False, indent=2)
        tmp.write('\n')
        temporary = Path(tmp.name)
    try:
        load_catalog(temporary)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    print(f'Merged {len(incoming)} records; {len(records)} books in the index.')
else:
    print(f'Validated {len(load_catalog(path))} sourced books.')
