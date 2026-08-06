"""
Client-side search matchers — a direct Python port of `ui/src/fuzzyMatch.ts`.

Kept behaviorally identical to the web UI on purpose, so the TUI's "By
rule ID" (substring) and "By group" (typo-tolerant fuzzy) search modes
match the same things the web UI's search box does. See
`ui/src/fuzzyMatch.ts` for the full rationale/docstring on the matching
strategy — not repeated here beyond the essentials.
"""

import math
import re

MIN_FUZZ_LEN = 3
_SEP_RE = re.compile(r"[-_.\s]+")


def _normalize(s: str) -> str:
    return _SEP_RE.sub("-", s.lower())


def _levenshtein(a: str, b: str) -> int:
    m, n = len(a), len(b)
    if m == 0:
        return n
    if n == 0:
        return m

    prev = list(range(n + 1))
    curr = [0] * (n + 1)
    for i in range(1, m + 1):
        curr[0] = i
        for j in range(1, n + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            curr[j] = min(
                prev[j] + 1,  # deletion
                curr[j - 1] + 1,  # insertion
                prev[j - 1] + cost,  # substitution
            )
        prev, curr = curr, prev
    return prev[n]


def fuzzy_matches(query: str, candidate: str) -> bool:
    """True if `query` fuzzy-matches `candidate` (typo-tolerant prefix match)."""
    nq = _normalize(query.strip())
    nc = _normalize(candidate.strip())
    if not nq:
        return False
    if len(nc) < len(nq):
        return False

    prefix = nc[: len(nq)]
    threshold = 0 if len(nq) < MIN_FUZZ_LEN else max(1, math.ceil(len(nq) * 0.2))
    return _levenshtein(nq, prefix) <= threshold


def fuzzy_filter(query: str, candidates: list[str]) -> list[str]:
    """Filters `candidates` to those that fuzzy-match `query`, preserving input order."""
    return [c for c in candidates if fuzzy_matches(query, c)]


def substring_matches(query: str, candidate: str) -> bool:
    """Plain case-insensitive substring match, normalizing separators like `fuzzy_matches` does."""
    nq = _normalize(query.strip())
    nc = _normalize(candidate.strip())
    if not nq:
        return False
    return nq in nc


def substring_filter(query: str, candidates: list[str]) -> list[str]:
    """Filters `candidates` to those that substring-match `query`, preserving input order."""
    return [c for c in candidates if substring_matches(query, c)]
