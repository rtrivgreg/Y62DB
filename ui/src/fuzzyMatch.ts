/**
 * Client-side fuzzy matcher for the "By rule ID" / "By group" search box.
 *
 * The API only supports exact-match lookups (`GET /rules/{ruleId}/bindings`,
 * `GET /groups/{group}/bindings`) — there's no server-side full-text search.
 * To let the search box tolerate typos and separator differences (e.g.
 * "access-keys.rotated" matching "access-keys-rotated"), we fetch the full
 * list of candidate rule IDs / groups (`GET /rules` / `GET /groups`) once
 * per search and fuzzy-match the typed query against them here, then fan
 * out an exact-match lookup for every candidate that matches.
 *
 * Matching strategy — "typo-tolerant prefix match":
 *   1. Normalize both query and candidate: lowercase, collapse any run of
 *      separator-like characters (-, _, ., space) to a single "-". This
 *      alone handles pure separator differences with zero edit distance.
 *   2. A candidate SHORTER than the normalized query never matches. The
 *      query is treated as the more-specific string, so e.g. querying
 *      "access-keys-rotated2" must NOT match the shorter "access-keys-rotated"
 *      — the trailing "2" is a meaningful part of a distinct rule ID in
 *      this domain, not noise to fuzz away.
 *   3. Otherwise, compare the query against the same-length PREFIX of the
 *      candidate using Levenshtein edit distance, allowing up to ~20% error
 *      (minimum 1). This is what makes an incomplete/typo'd query like
 *      "acces" (missing the final "s") still match "access-keys-rotated"
 *      and "access-keys-rotated2" — both share that prefix — while a full,
 *      separator-normalized query like "access-keys-rotated" matches both
 *      the exact rule and any rule that extends it (e.g. the "2" variant),
 *      since we're only comparing against its own length's worth of prefix.
 */

function normalize(s: string): string {
  return s.toLowerCase().replace(/[-_.\s]+/g, "-");
}

/** Classic Levenshtein edit distance between two strings. */
function levenshtein(a: string, b: string): number {
  const m = a.length;
  const n = b.length;
  if (m === 0) return n;
  if (n === 0) return m;

  let prev = Array.from({ length: n + 1 }, (_, j) => j);
  let curr = new Array(n + 1).fill(0);

  for (let i = 1; i <= m; i++) {
    curr[0] = i;
    for (let j = 1; j <= n; j++) {
      const cost = a[i - 1] === b[j - 1] ? 0 : 1;
      curr[j] = Math.min(
        prev[j] + 1, // deletion
        curr[j - 1] + 1, // insertion
        prev[j - 1] + cost, // substitution
      );
    }
    [prev, curr] = [curr, prev];
  }
  return prev[n];
}

/** True if `query` fuzzy-matches `candidate` per the strategy documented above. */
export function fuzzyMatches(query: string, candidate: string): boolean {
  const nq = normalize(query.trim());
  const nc = normalize(candidate.trim());
  if (!nq) return false;
  if (nc.length < nq.length) return false;

  const prefix = nc.slice(0, nq.length);
  const threshold = Math.max(1, Math.ceil(nq.length * 0.2));
  return levenshtein(nq, prefix) <= threshold;
}

/** Filters `candidates` to those that fuzzy-match `query`, preserving input order. */
export function fuzzyFilter(query: string, candidates: string[]): string[] {
  return candidates.filter((c) => fuzzyMatches(query, c));
}
