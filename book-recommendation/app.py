from flask import Flask, render_template, request
import requests

app = Flask(__name__)

# Function to get book recommendations from Google Books API
def get_books(query):
    url = f'https://www.googleapis.com/books/v1/volumes?q={query}&maxResults=10'
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        books = []
        for item in data.get('items', []):
            title = item['volumeInfo'].get('title', 'N/A')
            authors = ', '.join(item['volumeInfo'].get('authors', 'Unknown'))
            books.append({'title': title, 'authors': authors})
        return books
    return []

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/recommendations', methods=['POST'])
def recommendations():
    query = request.form['query']
    books = get_books(query)
    return render_template('recommendations.html', books=books, query=query)

if __name__ == '__main__':
    app.run(debug=True, port=5001)

