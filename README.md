# Bookmatch

A full-stack book discovery and recommendation web application built with Flask and vanilla JavaScript. Bookmatch helps readers move beyond a generic title search: choose a book you liked, select the subjects you want more of, refine the match, and explore related books using live Open Library data.

**Live Demo:** https://book-recommendation-1-e4km.onrender.com/

> The live demo is hosted on Render's free tier, so the first request after a period of inactivity may take a short time to wake the server.

## What Bookmatch Does

Bookmatch supports two connected discovery flows:

- **Book search** — search Open Library by title or author and browse paginated results.
- **Related-book recommendations** — choose a seed book, select up to three subjects you liked about it, optionally require a different author, choose a publication-era preference, and rank related books by shared subjects.

Users can also save books to a persistent reading list in the browser and inspect additional book details without leaving the application.

## Features

- Search books by title or author
- Generate recommendations from a selected seed book
- Select up to three subject preferences for recommendation matching
- Rank recommendations by the number of shared selected subjects
- Filter recommendations by author and publication era
- Paginate ordinary searches through the API
- Collect and rank recommendation candidates across multiple Open Library result pages
- Paginate recommendation matches locally after ranking
- Save and remove books from a browser-based reading list using `localStorage`
- View book details in an interactive dialog
- Responsive interface for different screen sizes
- Loading, empty, and error states for API-driven interactions
- Short-lived server-side caching to reduce repeated external requests

## Tech Stack

**Backend**
- Python
- Flask
- Requests
- Gunicorn

**Frontend**
- HTML
- CSS
- Vanilla JavaScript
- Browser `localStorage`

**Data & Deployment**
- Open Library Search API
- Render
- Git / GitHub

## How It Works

The application uses Flask as a small backend layer between the browser and Open Library.

1. A user searches for a book or starts a recommendation request in the browser.
2. JavaScript sends the request to Bookmatch's Flask API.
3. Flask queries Open Library and normalizes the returned book data into a consistent structure.
4. For recommendations, the frontend compares candidate subjects with the user's selected preferences, removes unsuitable or duplicate results, applies optional filters, and ranks books by the number of matching subjects.
5. JavaScript renders the resulting books dynamically and manages UI state, pagination, dialogs, and the saved reading list.

This separation keeps the external data-provider logic in the backend while allowing the frontend to focus on interaction, ranking, and presentation.

## Recommendation Logic

Bookmatch intentionally uses **OR-style matching** rather than requiring every selected subject to appear on a book. A candidate must share at least one selected subject, and books matching more selected subjects rank higher.

For recommendation requests, Bookmatch gathers candidates from multiple Open Library result pages before ranking them. The surviving recommendation matches are then paginated locally in groups of 12, so navigation reflects the books that actually passed Bookmatch's matching and filtering logic rather than Open Library's raw result count.

## API

The Flask backend exposes an internal `/api/books` endpoint used by the frontend. It handles query parameters for search, pagination, sorting, and recommendation-mode requests, then returns normalized JSON to the browser.

The backend also:

- validates Open Library work identifiers
- normalizes title, author, publication year, cover, edition, subject, and work-link data
- limits response sizes for search and matching modes
- caches repeated queries for a short period
- handles upstream request failures without crashing the application

## Project Structure

```text
Book-Recommendation/
├── README.md
└── book-recommendation/
    ├── app.py
    ├── requirements.txt
    ├── templates/
    │   ├── index.html
    │   └── recommendations.html
    └── static/
        ├── books.js
        ├── recommend.js
        └── style.css
```

## Run Locally

From the repository root:

```bash
cd book-recommendation
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

On Windows, activate the environment with:

```bash
.venv\Scripts\activate
```

Then open the local Flask address shown in the terminal.

## Deployment

Bookmatch is deployed as a Python web service on Render using Gunicorn.

```text
Root directory: book-recommendation
Build command:  pip install -r requirements.txt
Start command:  gunicorn app:app
```

No API key or application-specific environment variable is required because the app uses Open Library's public API.

## Development & Debugging

Building Bookmatch involved more than connecting an API to a search box. Several iterations focused on the behavior of the recommendation system and the difference between raw provider results and useful application results.

Notable improvements included:

- separating ordinary search behavior from recommendation matching
- normalizing external API data before exposing it to the frontend
- improving candidate collection for recommendation requests
- preventing raw Open Library result counts from creating misleading recommendation pagination
- moving recommendation pagination to the client after filtering and ranking
- handling duplicate works and seed-book exclusion
- adding browser persistence for the reading list
- adding caching and error handling around external requests
- deploying the Flask application with Gunicorn on Render

## Data Limitations

Bookmatch relies on Open Library's community-maintained metadata. Subject coverage varies considerably between books, particularly for newer, niche, or independently published titles. As a result, a relevant book may exist in Open Library while still lacking enough subject metadata to appear in a highly specific recommendation.

The application treats this as a data-source limitation rather than fabricating missing genres or tropes. Recommendation quality therefore depends both on Bookmatch's matching logic and on the metadata available upstream.

## Future Possibilities

Possible future improvements include evaluating richer metadata providers, expanding explainability around why individual books matched, and adding more discovery controls. These are intentionally outside the current scope so the project remains focused on a complete, usable recommendation workflow.

## Author

**Beryl Koko**
