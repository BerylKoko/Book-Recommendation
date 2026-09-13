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
            const matches = [
                ...new Set(
                    (b.subjects || []).filter(
                        s =>
                            wanted.has(
                                normalise(s)
                            )
                    )
                )
            ];

            return {
                ...b,
                matches
            };
        })
        .filter(
            b =>
                b.matches.length > 0 &&
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
                b.matches.length -
                    a.matches.length ||
                a.title.localeCompare(
                    b.title
                )
        );
}