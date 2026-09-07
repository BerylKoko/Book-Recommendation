import importlib.util
from pathlib import Path
from unittest.mock import patch,Mock
import requests
spec=importlib.util.spec_from_file_location('books',Path(__file__).parents[1]/'book-recommendation/app.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

def test_invalid_search():
 c=m.app.test_client()
 assert c.get('/api/books').status_code==400
 assert c.get('/api/books?q=test&page=no').status_code==400

def test_missing_author_and_cover():
 response=Mock();response.json.return_value={'docs':[{'key':'/works/OL1W','title':'One'}],'numFound':1}
 with patch.object(m.requests,'get',return_value=response):
  m.cache.clear();r=m.app.test_client().get('/api/books?q=test').json
 assert r['books'][0]['authors']=='Unknown author'
 assert r['books'][0]['cover'] is None

def test_upstream_failure_is_not_empty_results():
 with patch.object(m.requests,'get',side_effect=requests.Timeout):
  m.cache.clear();r=m.app.test_client().get('/api/books?q=test')
 assert r.status_code==502
 assert 'error' in r.json

def test_server_rendered_fallback():
 with patch.object(m,'get_books',return_value={'books':[]}):
  r=m.app.test_client().post('/recommendations',data={'query':'test'})
 assert r.status_code==200
 assert b'No matches' in r.data
