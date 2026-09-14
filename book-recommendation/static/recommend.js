export const normalise = s =>
    String(s)
        .trim()
        .toLocaleLowerCase()
        .replace(/[&+]/g, " and ")
        .replace(/[^a-z0-9]+/g, " ")
        .trim()
        .replace(/\s+/g, " ");

const CONCEPT_GROUPS = [
    [
        "mm", "m m", "m/m", "mm romance", "m/m romance",
        "male male romance", "male male relationships", "gay romance",
        "gay love stories", "gay men", "gay men fiction", "gay fiction",
        "gay relationships", "male homosexuality"
    ],
    [
        "dark romance", "dark romantic fiction", "dark romance fiction",
        "dark romantic", "obsessive romance", "dangerous romance",
        "morally gray romance", "morally grey romance"
    ],
    [
        "college", "college romance", "college students", "college life",
        "university", "university romance", "university students",
        "campus", "campus romance", "campus life", "undergraduates",
        "student life", "higher education"
    ],
    [
        "hockey", "ice hockey", "hockey romance", "hockey players",
        "hockey teams", "professional hockey", "college hockey"
    ],
    [
        "sports romance", "athlete romance", "sports fiction romance",
        "professional athletes", "college athletes"
    ],
    [
        "enemies to lovers", "rivals to lovers", "hate to love",
        "romantic rivalry", "adversaries to lovers", "enemies romance"
    ],
    [
        "friends to lovers", "best friends to lovers", "friendship to romance",
        "friends romance", "childhood friends romance", "platonic to romantic"
    ],
    [
        "fake dating", "fake relationship", "pretend dating",
        "relationship of convenience", "pretend couple"
    ],
    [
        "forced proximity", "stuck together", "close quarters romance",
        "forced together", "trapped together romance", "shared space romance"
    ],
    [
        "slow burn", "slow burn romance", "gradual romance",
        "slow relationship development", "romantic longing"
    ]
].map(group => new Set(group.map(normalise)));

const conceptAliases = subject => {
    const selected = normalise(subject);
    const group = CONCEPT_GROUPS.find(aliases => aliases.has(selected));
    return group || new Set([selected]);
};

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
    const concepts = subjects.map(subject => ({
        label: subject,
        aliases: conceptAliases(subject)
    }));

    const seen = new Set();
    const seedAuthors = new Set(authors(seed));

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
                (b.subjects || []).map(normalise)
            );

            const matches = concepts
                .filter(concept =>
                    [...concept.aliases].some(alias => bookSubjects.has(alias))
                )
                .map(concept => concept.label);

            const searchMatchCount = Array.isArray(b.searchMatches)
                ? new Set(
                    b.searchMatches
                        .map(normalise)
                        .filter(Boolean)
                ).size
                : 0;

            const matchScore = concepts.length
                ? matches.length / concepts.length
                : 0;

            return {
                ...b,
                matches,
                matchCount: matches.length,
                matchTotal: concepts.length,
                matchScore,
                searchMatchCount
            };
        })
        .filter(
            b =>
                b.matchScore > 0 &&
                (
                    !newAuthor ||
                    !authors(b).some(
                        a => seedAuthors.has(a)
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
                b.searchMatchCount - a.searchMatchCount ||
                a.title.localeCompare(b.title)
        );
}