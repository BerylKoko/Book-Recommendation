export const normalise = s =>
    String(s).trim().toLocaleLowerCase();

const authors = b =>
    (
        b.authorNames ||
        String(b.authors || "").split(",")
    )
        .map(normalise)
        .filter(
            a =>
                a &&
                a !== "unknown author"
        );

export function rankBooks(
    candidates,
    seed,
    subjects,
    {
        newAuthor = true,
        era = "any"
    } = {}
) {
    const wanted = new Set(
        subjects.map(normalise)
    );

    const seen = new Set();

    const seedAuthors = new Set(
        authors(seed)
    );

    return candidates
        .filter(b => {
            if (
                b.id === seed.id ||
                seen.has(b.id)
            ) {
                return false;
            }

            seen.add(b.id);

            return true;
        })
        .map(b => {
            const searchMatches = Array.isArray(b.searchMatches)
                ? b.searchMatches.filter(
                    subject => wanted.has(normalise(subject))
                )
                : [];

            const exactMatches = [
                ...new Set(
                    (b.subjects || []).filter(
                        s =>
                            wanted.has(
                                normalise(s)
                            )
                    )
                )
            ];

            const matches = searchMatches.length
                ? [...new Set(searchMatches)]
                : exactMatches;

            const matchScore =
                wanted.size
                    ? matches.length / wanted.size
                    : 0;

            return {
                ...b,
                matches,
                matchCount: matches.length,
                matchTotal: wanted.size,
                matchScore
            };
        })
        .filter(
            b =>
                b.matchScore > 0 &&
                (
                    !newAuthor ||
                    !authors(b).some(
                        a =>
                            seedAuthors.has(a)
                    )
                ) &&
                (
                    era === "any" ||
                    (
                        Number.isFinite(b.year) &&
                        (
                            era === "recent"
                                ? b.year >= 2000
                                : b.year < 2000
                        )
                    )
                )
        )
        .sort(
            (a, b) =>
                b.matchScore - a.matchScore ||
                a.title.localeCompare(
                    b.title
                )
        );
}