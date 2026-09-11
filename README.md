# 📚 Book Discovery & Recommendation Engine

An interactive web application designed to help readers discover niche sub-genres (e.g., sports romance, trope-based fiction) and connect directly to public library borrowing options via the Open Library API.

## 🚀 Features
- **Dynamic Tag Search:** Filter books by specific sub-genres, tropes, and themes.
- **Open Library API Integration:** Pulls real-time book metadata, cover images, and availability.
- **Direct Library Links:** Instant routing to digital checkout resources.

## 🛠️ Tech Stack
- **Frontend:** React.js / JavaScript (ES6+), HTML5, CSS3
- **API:** Open Library REST API
- **Deployment:** Vercel / GitHub Pages

## 💡 How It Works
1. The user selects or searches for specific genre tags.
2. The application constructs an asynchronous `fetch()` query to `https://openlibrary.org/subjects/{tag}.json`.
3. Results are filtered on the client side and rendered into interactive cards with direct borrowing links.