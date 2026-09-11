export const normalise = (s) => {
    return String(s).trim().toLocaleLowerCase();
};

const authors = (book) => {
    const names =
        book.authorNames ||
        String(book.authors || "").split(",");

    return names
        .map(normalise)
        .filter((author) => author && author !== "unknown author");
};

export function rankBooks(
    candidates,
    seed,
    subjects,
    { newAuthor = true, era = "any" } = {}
) {
    const wanted = new Set(subjects.map(normalise));
    const seen = new Set();
    const seedAuthors = new Set(authors(seed));

    const uniqueBooks = candidates.filter((book) => {
        if (book.id === seed.id) {
            return false;
        }

        if (seen.has(book.id)) {
            return false;
        }

        seen.add(book.id);
        return true;
    });

    const booksWithMatches = uniqueBooks.map((book) => {
        const matches = [
            ...new Set(
                (book.subjects || []).filter((subject) =>
                    wanted.has(normalise(subject))
                )
            )
        ];

        return {
            ...book,
            matches: matches
        };
    });

    const filteredBooks = booksWithMatches.filter((book) => {
        const hasMatchingSubject = book.matches.length > 0;

        const differentAuthor =
            !newAuthor ||
            !authors(book).some((author) =>
                seedAuthors.has(author)
            );

        const correctEra =
            era === "any" ||
            (
                Number.isFinite(book.year) &&
                (
                    era === "recent"
                        ? book.year >= 2000
                        : book.year < 2000
                )
            );

        return (
            hasMatchingSubject &&
            differentAuthor &&
            correctEra
        );
    });

    filteredBooks.sort((a, b) => {
        const matchDifference =
            b.matches.length - a.matches.length;

        if (matchDifference !== 0) {
            return matchDifference;
        }

        return a.title.localeCompare(b.title);
    });

    return filteredBooks;
}