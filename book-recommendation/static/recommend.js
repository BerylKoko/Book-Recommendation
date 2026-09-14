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
    const concepts = subjects.map(subject =>
        typeof subject === "string"
            ? {
                label: subject,
                terms: [normalise(subject)]
            }
            : {
                label: subject.label,
                terms: [
                    ...new Set(
                        (subject.terms || [subject.label])
                            .map(normalise)
                            .filter(Boolean)
                    )
                ]
            }
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
            const bookSubjects = new Set(
                (b.subjects || [])
                    .map(normalise)
                    .filter(Boolean)
            );

            const matches = concepts
                .filter(concept =>
                    concept.terms.some(term =>
                        bookSubjects.has(term)
                    )
                )
                .map(concept => concept.label);

            const matchScore =
                concepts.length
                    ? matches.length / concepts.length
                    : 0;

            return {
                ...b,
                matches,
                matchCount: matches.length,
                matchTotal: concepts.length,
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