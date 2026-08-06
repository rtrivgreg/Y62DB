"""
Sanity checks that fuzzy_match.py is a faithful port of ui/src/fuzzyMatch.ts.
Mirrors the exact examples documented in the TS file's own docstring.
"""

from tui.fuzzy_match import (
    fuzzy_filter,
    fuzzy_matches,
    substring_filter,
    substring_matches,
)


def test_fuzzy_exact_match():
    assert fuzzy_matches("access-keys-rotated", "access-keys-rotated") is True


def test_fuzzy_separator_normalization():
    # Pure separator differences (- vs . vs _) have zero edit distance after normalize.
    assert fuzzy_matches("access-keys.rotated", "access-keys-rotated") is True


def test_fuzzy_shorter_candidate_never_matches():
    # A candidate shorter than the query never matches.
    assert fuzzy_matches("access-keys-rotated2", "access-keys-rotated") is False


def test_fuzzy_prefix_extension_matches():
    # A full query matches a candidate that extends it (e.g. a "2" variant).
    assert fuzzy_matches("access-keys-rotated", "access-keys-rotated2") is True


def test_fuzzy_typo_tolerant_missing_char():
    # Missing trailing "s" should still match via ~20% edit-distance tolerance.
    assert fuzzy_matches("acces", "access-keys-rotated") is True


def test_fuzzy_short_query_guardrail():
    # Below MIN_FUZZ_LEN (3), only an exact prefix match (0 edits) is allowed —
    # "a2" must NOT fuzzy-match "abcdef" (second char differs).
    assert fuzzy_matches("a2", "abcdef") is False
    assert fuzzy_matches("ab", "abcdef") is True


def test_fuzzy_empty_query_never_matches():
    assert fuzzy_matches("", "anything") is False


def test_fuzzy_filter_preserves_order():
    candidates = ["zzz-rule", "access-keys-rotated", "access-keys-rotated2", "other"]
    assert fuzzy_filter("access-keys-rotated", candidates) == [
        "access-keys-rotated",
        "access-keys-rotated2",
    ]


def test_substring_basic():
    assert substring_matches("keys", "access-keys-rotated") is True
    assert substring_matches("zzz", "access-keys-rotated") is False


def test_substring_separator_normalization():
    assert substring_matches("access.keys", "access-keys-rotated") is True


def test_substring_filter_preserves_order():
    candidates = ["other", "access-keys-rotated", "access-keys-rotated2"]
    assert substring_filter("access-keys", candidates) == [
        "access-keys-rotated",
        "access-keys-rotated2",
    ]


def test_substring_is_not_typo_tolerant():
    # Unlike fuzzy_matches, substring_matches requires an exact substring —
    # a typo'd query should NOT match.
    assert substring_matches("acces-keys", "access-keys-rotated") is False
