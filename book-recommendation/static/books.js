import { rankBooks } from "./recommend.js";
const $ = (selector) => document.querySelector(selector);
const KEY = "bookmatch:reading-list:v1";
const RECOMMENDATION_PAGE_SIZE = 12;
const MAX_MATCH_PAGES = 3;
const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (character) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"})[character]);
const normaliseTag = (value) => String(value ?? "").trim().toLocaleLowerCase();
const genreMapPromise = fetch("/static/genres.json")
    .then((response) => response.ok ? response.json() : {})
    .catch(() => ({}));

function buildConcepts(subjects, genreMap) {
    const aliases = new Map();

    for (const [canonical, related] of Object.entries(genreMap || {})) {
        const canonicalTag = normaliseTag(canonical);
        const terms = [...new Set([canonicalTag, ...(related || []).map(normaliseTag)].filter(Boolean))];

        for (const term of terms) {
            if (!aliases.has(term)) aliases.set(term, new Set());
            aliases.get(term).add(canonicalTag);
        }
    }

    return subjects.map((subject) => {
        const selected = normaliseTag(subject);
        let terms = [selected];

        if (genreMap?.[selected]) {
            terms = [selected, ...genreMap[selected].map(normaliseTag)];
        } else {
            const owners = [...(aliases.get(selected) || [])];
            if (owners.length && owners.length <= 2) {
                for (const owner of owners) {
                    terms.push(owner, ...(genreMap[owner] || []).map(normaliseTag));
                }
            }
        }

        return {
            label: subject,
            terms: [...new Set(terms.filter(Boolean))].slice(0, 10)
        };
    });
}

function buildSubjectQuery(concepts) {
    return [...new Set(concepts.flatMap((concept) => concept.terms))]
        .map((term) => term.replace(/["\\():]/g, " ").trim())
        .filter(Boolean)
        .map((term) => `subject:"${term}"`)
        .join(" OR ");
}

let saved = [];
let corrupt = false;
try {
    const value = JSON.parse(localStorage.getItem(KEY) || "[]");
    if (!Array.isArray(value)) throw Error();
    saved = value.filter((book) => book && /^\/works\/OL\d+W$/.test(book.id));
} catch { corrupt = true; }

let rows = [];
let recommendationRows = [];
let recommendationCandidateCount = 0;
let recommendationCheckedPages = 0;
let seed = null;
let view = "search";
let sequence = 0;
let page = 1;
let total = 0;
let controller;
let currentQuery = "";
let currentMatching = false;
let searchQuery = "";
let searchPage = 1;

function count() { $("#count").textContent = saved.length; }

function setView(next) {
    view = next;
    $("#discover").setAttribute("aria-pressed", String(next !== "saved"));
    $("#saved").setAttribute("aria-pressed", String(next === "saved"));
}

function render(books) {
    $("#books").replaceChildren();
    if (!books.length) {
        $("#books").innerHTML = `<div class="empty"><h3>${view === "saved" ? "No books saved yet." : "No matches in this sample."}</h3><p>${view === "saved" ? "Open a book and save it to your reading list." : view === "matches" ? "Try fewer subjects, any publication year, or allow the same author." : "Try a different title or author."}</p></div>`;
        return;
    }
    for (const book of books) {
        const card = document.createElement("article");
        card.className = "book";
        card.innerHTML = `<div class="cover-wrap">${book.cover ? `<img src="${esc(book.cover)}" alt="" loading="lazy">` : `<span class="no-cover">No cover</span>`}</div><div class="book-info"><h3>${esc(book.title)}</h3><p>${esc(book.authors)}</p><small>${book.year || "Year unavailable"}${saved.some((item) => item.id === book.id) ? " · Saved" : ""}</small>${book.matches ? `<p class="reason">Match strength: ${book.matchCount}/${book.matchTotal} selected subjects<br>Matches: ${book.matches.map(esc).join(" · ")}</p>` : ""}<div class="book-actions"><button class="details">Details</button>${view === "search" ? `<button class="choose">Use this book</button>` : ""}</div></div>`;
        card.querySelector("img")?.addEventListener("error", (event) => {
            const replacement = document.createElement("span");
            replacement.className = "no-cover";
            replacement.textContent = "No cover";
            event.target.replaceWith(replacement);
        });
        card.querySelector(".details").onclick = () => detail(book);
        const choose = card.querySelector(".choose");
        if (choose) choose.onclick = () => chooseSeed(book);
        $("#books").appendChild(card);
    }
}

function renderRecommendationPage() {
    const start = (page - 1) * RECOMMENDATION_PAGE_SIZE;
    const end = start + RECOMMENDATION_PAGE_SIZE;
    rows = recommendationRows.slice(start, end);
    render(rows);
    $("#status").textContent = `${recommendationRows.length} suggestions from ${recommendationCandidateCount} catalog results · Page ${page} · Checked ${recommendationCheckedPages} ${recommendationCheckedPages === 1 ? "catalog page" : "catalog pages"}`;
    $("#previous").hidden = page <= 1;
    $("#more").hidden = end >= recommendationRows.length;
}

function chooseSeed(book) {
    seed = book;
    $("#preferences").hidden = false;
    $("#seed").innerHTML = `<strong>${esc(book.title)}</strong><span>${esc(book.authors)}</span>`;
    const subjects = [...new Set(book.subjects || [])].filter((subject) => subject.length < 50).slice(0, 16);
    $("#traits").innerHTML = subjects.map((subject, index) => `<label class="trait"><input type="checkbox" value="${esc(subject)}" ${index < 2 ? "checked" : ""}>${esc(subject)}</label>`).join("");
    $("#preference-status").textContent = subjects.length ? "Select the parts you want more of." : "This book has no usable subjects. Choose another starting book.";
    $("#recommend").disabled = !subjects.length;
    $("#preferences").scrollIntoView({block:"nearest"});
}

function detail(book) {
    $("#detail-body").innerHTML = `<h2 id="book-title">${esc(book.title)}</h2><p>${esc(book.authors)}</p><p>First published ${book.year || "year unavailable"} · ${book.editions || "Unknown number of"} editions</p>${book.matches ? `<p class="reason">Match strength: ${book.matchCount}/${book.matchTotal} selected subjects<br>Suggested because of: ${book.matches.map(esc).join(", ")}</p>` : ""}<div class="tags">${(book.subjects || []).slice(0,12).map((subject) => `<span>${esc(subject)}</span>`).join("")}</div><p><a href="https://openlibrary.org${esc(book.id)}" target="_blank" rel="noreferrer">View editions and reading options ↗</a></p><button id="save-book" class="primary"></button><p id="save-status" role="status"></p>`;
    const update = () => { $("#save-book").textContent = saved.some((item) => item.id === book.id) ? "Remove from reading list" : "Save to reading list"; };
    update();
    $("#save-book").onclick = () => {
        const exists = saved.some((item) => item.id === book.id);
        const next = exists ? saved.filter((item) => item.id !== book.id) : [...saved, book];
        try {
            localStorage.setItem(KEY, JSON.stringify(next));
            saved = next;
            update(); count(); render(view === "saved" ? saved : rows);
            $("#save-status").textContent = exists ? "Removed from your list." : "Saved on this device.";
        } catch { $("#save-status").textContent = "This browser could not save your change. Check storage permissions."; }
    };
    $("#detail").showModal();
}

async function fetchBookPage(query, requestedPage, matching, signal) {
    const params = new URLSearchParams({q:query,page:String(requestedPage),mode:matching ? "match" : "search"});
    const response = await fetch("/api/books?" + params, {signal});
    const data = await response.json();
    if (!response.ok) throw Error(data.error || `Catalog returned ${response.status}.`);
    if (!Array.isArray(data.books)) throw Error("Unexpected catalog response.");
    return data;
}

async function requestBooks(query, matching = false, matchConcepts = null) {
    if (!query) return;
    currentQuery = query;
    currentMatching = matching;
    if (!matching) { searchQuery = query; searchPage = page; }
    controller?.abort();
    controller = new AbortController();
    const abort = controller;
    const matchSeed = seed;
    const traits = matchConcepts || selectedSubjects();
    const preferences = {newAuthor:$("#new-author").checked,era:$("#era").value};
    const id = ++sequence;
    setView(matching ? "matches" : "search");
    $("#back-to-search").hidden = !matching;
    $("#status").textContent = matching ? "Finding related books…" : "Searching the catalog…";
    $("#books").setAttribute("aria-busy", "true");
    $("#previous").hidden = true;
    $("#more").hidden = true;
    $("#shelf-title").textContent = matching ? "Related books" : "Choose a starting book";
    const timeout = setTimeout(() => abort.abort(), 16000);
    try {
        if (matching) {
            const firstPage = await fetchBookPage(query, 1, true, abort.signal);
            if (id !== sequence) return;
            const limit = firstPage.limit || 24;
            const pagesToCheck = Math.min(MAX_MATCH_PAGES, Math.max(1, Math.ceil(firstPage.total / limit)));
            let candidates = [...firstPage.books];
            if (pagesToCheck > 1) {
                const remainingPages = await Promise.all(Array.from({length:pagesToCheck - 1}, (_, index) => fetchBookPage(query, index + 2, true, abort.signal)));
                if (id !== sequence) return;
                for (const data of remainingPages) candidates.push(...data.books);
            }
            total = firstPage.total;
            recommendationRows = rankBooks(candidates, matchSeed, traits, preferences);
            recommendationCandidateCount = candidates.length;
            recommendationCheckedPages = pagesToCheck;
            page = 1;
            renderRecommendationPage();
        } else {
            recommendationRows = [];
            const data = await fetchBookPage(query, page, false, abort.signal);
            if (id !== sequence) return;
            rows = data.books;
            total = data.total;
            searchPage = page;
            searchQuery = query;
            render(rows);
            $("#status").textContent = `${total.toLocaleString()} results · Page ${page}`;
            const limit = data.limit || 12;
            $("#previous").hidden = page <= 1;
            $("#more").hidden = !rows.length || page * limit >= total;
        }
    } catch (error) {
        if (id === sequence) {
            rows = []; recommendationRows = [];
            $("#books").replaceChildren();
            $("#previous").hidden = true;
            $("#more").hidden = true;
            $("#status").textContent = `Search could not load. ${error.name === "AbortError" ? "The request timed out." : error.message}`;
        }
    } finally {
        clearTimeout(timeout);
        if (id === sequence) $("#books").removeAttribute("aria-busy");
    }
}

const selectedSubjects = () => [...document.querySelectorAll("#traits input:checked")].map((input) => input.value);

$("#recommend").onclick = async () => {
    const subjects = selectedSubjects();
    if (!subjects.length || subjects.length > 3) { $("#preference-status").textContent = "Choose between 1 and 3 subjects."; return; }
    $("#preference-status").textContent = "";
    page = 1;
    const genreMap = await genreMapPromise;
    const concepts = buildConcepts(subjects, genreMap);
    const subjectQuery = buildSubjectQuery(concepts);
    requestBooks(subjectQuery, true, concepts);
};

$("#search-form").onsubmit = (event) => {
    event.preventDefault();
    const query = $("#query").value.trim();
    if (!query) return;
    page = 1; searchPage = 1; searchQuery = query;
    requestBooks(query);
};

$("#more").onclick = () => {
    if (currentMatching) {
        const nextStart = page * RECOMMENDATION_PAGE_SIZE;
        if (nextStart < recommendationRows.length) { page++; renderRecommendationPage(); }
        return;
    }
    page++;
    requestBooks(currentQuery, false);
};

$("#previous").onclick = () => {
    if (page <= 1) return;
    page--;
    if (currentMatching) {
        renderRecommendationPage();
        return;
    }
    requestBooks(currentQuery, false);
};

$("#back-to-search").onclick = () => {
    controller?.abort(); sequence++;
    if (!searchQuery) return;
    page = searchPage;
    $("#back-to-search").hidden = true;
    requestBooks(searchQuery, false);
};

$("#saved").onclick = () => {
    controller?.abort(); sequence++;
    setView("saved");
    $("#back-to-search").hidden = true;
    $("#books").removeAttribute("aria-busy");
    $("#shelf-title").textContent = "Your reading list";
    $("#status").textContent = `${saved.length} ${saved.length === 1 ? "book" : "books"} saved on this device`;
    $("#previous").hidden = true;
    $("#more").hidden = true;
    render(saved);
};

$("#discover").onclick = () => {
    const query = $("#query").value.trim();
    $("#back-to-search").hidden = true;
    if (!query) {
        setView("search");
        $("#shelf-title").textContent = "Choose a starting book";
        $("#status").textContent = "";
        $("#books").replaceChildren();
        $("#previous").hidden = true;
        $("#more").hidden = true;
        return;
    }
    page = 1;
    requestBooks(query);
};

$("#close").onclick = () => { $("#detail").close(); };
count();
if (corrupt) $("#preference-status").textContent = "Your saved list could not be read. Search is still available.";