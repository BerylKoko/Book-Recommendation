"""Beryl's Flask discovery app, extended with normalized metadata and API states."""
from flask import Flask, render_template, request, jsonify
import requests, time, re
from collections import OrderedDict
from pathlib import Path
app = Flask(__name__, root_path=str(Path(__file__).resolve().parent))
cache=OrderedDict()

def get_books(query, page=1, sort='relevance', matching=False):
    key=(query,page,sort,matching)
    if key in cache and time.monotonic()-cache[key][0]<600:return cache[key][1]
    params={'q':query,'page':page,'limit':48 if matching else 12,'fields':'key,title,author_name,first_publish_year,cover_i,edition_count,subject'}
    if sort=='new':params['sort']='new'
    response=requests.get('https://openlibrary.org/search.json',params=params,headers={'User-Agent':'BerylBookDiscovery/1.0 (portfolio student project)'},timeout=12)
    response.raise_for_status();data=response.json()
    books=[]
    for item in data.get('docs',[]):
        if not re.fullmatch(r'/works/OL\d+W',item.get('key','')):continue
        books.append({'id':item['key'],'title':item.get('title') or 'Untitled','authors':', '.join(dict.fromkeys(item.get('author_name') or ['Unknown author'])),'authorNames':list(dict.fromkeys(item.get('author_name') or [])),'year':item.get('first_publish_year'),'cover':f"https://covers.openlibrary.org/b/id/{item['cover_i']}-M.jpg" if item.get('cover_i') else None,'editions':item.get('edition_count',0),'subjects':(item.get('subject') or [])[:24],'url':'https://openlibrary.org'+item['key']})
    result={'books':books,'total':data.get('numFound',0),'page':page,'source':'Open Library'}
    cache[key]=(time.monotonic(),result)
    if len(cache)>128:cache.popitem(last=False)
    return result

@app.route('/')
def index():return render_template('index.html')

@app.route('/recommendations', methods=['POST','GET'])
def recommendations():
    query=(request.values.get('query') or '').strip()[:200]
    try:result=get_books(query) if query else {'books':[]};error=None
    except (requests.RequestException,ValueError):result={'books':[]};error='Book search is temporarily unavailable. Please try again.'
    return render_template('recommendations.html',books=result['books'],query=query,error=error)

@app.get('/api/books')
def api_books():
    query=(request.args.get('q') or '').strip()
    if not query or len(query)>200:return jsonify(error='Enter a title, author or subject (up to 200 characters).'),400
    try:page=int(request.args.get('page','1'))
    except ValueError:return jsonify(error='Invalid page.'),400
    if not 1<=page<=100:return jsonify(error='Invalid page.'),400
    try:return jsonify(get_books(query,page,'new' if request.args.get('sort')=='new' else 'relevance',request.args.get('mode')=='match'))
    except (requests.RequestException,ValueError):return jsonify(error='Book search is temporarily unavailable. Please try again.'),502

if __name__=='__main__':app.run(port=5001)
