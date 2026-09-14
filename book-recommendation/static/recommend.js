export const normalise = s =>
    String(s)
        .trim()
        .toLocaleLowerCase()
        .replace(/[&+]/g, " and ")
        .replace(/[^a-z0-9]+/g, " ")
        .trim()
        .replace(/\s+/g, " ");

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
    const wanted = subjects.map(subject => ({
        label: subject,
        normalised: normalise(subject)
    }));

    const seen = new Set();
    const seedAuthors = new Set(authors(seed));

    return candidates
        .filter(b => {
            if (
                b.id === seed.id ||
                (b.alternateIds || []).includes(seed.id) ||
                (seed.alternateIds || []).includes(b.id) ||
                seen.has(b.id)
            ) {
                return false;
            }

            seen.add(b.id);
            return true;
        })
        .map(b => {
            const suppliedMatches = new Set(
                (b.conceptMatches || []).map(normalise)
            );

            const matches = wanted
                .filter(subject =>
                    suppliedMatches.has(subject.normalised)
                )
                .map(subject => subject.label);

            const matchTotal = wanted.length;
            const matchCount = matches.length;
            const matchScore = matchTotal
                ? matchCount / matchTotal
                : 0;

            return {
                ...b,
                matches,
                matchCount,
                matchTotal,
                matchScore,
                aliasMatchCount: Number(b.aliasMatchCount) || 0
            };
        })
        .filter(
            b =>
                b.matchCount > 0 &&
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
                b.matchCount - a.matchCount ||
                (b.evidenceScore || 0) - (a.evidenceScore || 0) ||
                a.title.localeCompare(b.title)
        );
}
// Explicit + notation is an optional shortcut; title/author search stays intact.
export function parseTropeQuery(query) {
    const parts = query.split("+").map(s => s.trim()).filter(Boolean);
    const known = new Set(["mm", "m m", "gay romance", "ff", "f f", "lesbian romance", "queer romance", "sports", "sports romance", "college", "university", "hockey", "football", "baseball", "basketball", "dark romance", "mafia romance", "enemies to lovers", "friends to lovers", "roommates", "hurt comfort", "fake dating", "paranormal romance", "fantasy", "slow burn"]);
    return parts.length >= 2 && parts.every(part => known.has(normalise(part))) ? [...new Set(parts)] : null;
}
