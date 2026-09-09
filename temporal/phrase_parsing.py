"""Relative-position phrase parsing for narrative queries.

Maps English phrases describing narrative position ("near the end",
"in the first third", "by the beginning") to a fractional span over a
book's narrative arc (0.0 = very start, 1.0 = very end), then resolves
that span to concrete temporal bins using the same adaptive binning
scheme as `temporal/binning.py` (README, Week 2: N = clamp(total_relations
/ 15, 6, 20); bin k = floor(position * N / total_span) + 1).

Scope, deliberately locked (ROADMAP Week 6): relative-position phrasing
only. Chapter-relative phrasing ("in chapter 5") and event-relative
phrasing ("after X dies") are explicitly out of scope — see the v2
research summary doc (docs/) for why, and what each would need if
picked up later.

Integration note: this module was written without direct access to
the current `temporal/binning.py` source (this session only has
project documentation, not the live codebase). `resolve_to_bins()`
reimplements the documented bin-assignment formula rather than
importing it — verify the formula and NUM_BINS calculation here still
match the live `binning.py` before wiring this in, per this project's
own "verify, don't assume" discipline.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

RangeKind = Literal["point_window", "cumulative", "fractional_span"]


@dataclass(frozen=True)
class TemporalRange:
    """A parsed relative-position phrase, as a fractional narrative span.

    Attributes:
        start_frac: Start of the span, as a fraction of total narrative
            length (0.0 = very start of the book).
        end_frac: End of the span, same units. Always >= start_frac.
        kind: How the span should be interpreted —
            "point_window": a narrow band around a specific point
                (e.g. "near the end").
            "cumulative": everything from the start up to a point
                (e.g. "by the middle"). Distinct from point_window —
                conflating these silently produces the wrong range for
                one or the other.
            "fractional_span": an explicit named fraction of the book
                (e.g. "the first third").
        matched_phrase: The exact substring that matched, for logging
            and debugging — which pattern fired, on what input.
    """

    start_frac: float
    end_frac: float
    kind: RangeKind
    matched_phrase: str


# --- Vocabulary -------------------------------------------------------

# Canonical anchor point, as a fraction of narrative length.
_ANCHOR_BEGINNING = {"beginning", "start", "outset", "opening"}
_ANCHOR_MIDDLE = {"middle", "midpoint", "halfway point", "half way point",
                   "halfway through", "half way through", "halfway"}
_ANCHOR_END = {"end", "close", "conclusion", "finale"}
_ANCHOR_POSITION = {**{w: 0.0 for w in _ANCHOR_BEGINNING},
                    **{w: 0.5 for w in _ANCHOR_MIDDLE},
                    **{w: 1.0 for w in _ANCHOR_END}}
_ANCHOR_PATTERN = "|".join(sorted(_ANCHOR_POSITION, key=len, reverse=True))

_ORDINAL_INDEX = {
    "first": 0, "second": 1, "third": 2, "fourth": 3, "fifth": 4,
    "sixth": 5, "seventh": 6, "eighth": 7, "ninth": 8, "tenth": 9,
    "last": -1,
}
_ORDINAL_PATTERN = "|".join(_ORDINAL_INDEX)

_FRACTION_DENOMINATOR = {
    "half": 2, "halves": 2, "third": 3, "thirds": 3,
    "quarter": 4, "quarters": 4, "fourth": 4, "fourths": 4,
    "fifth": 5, "fifths": 5, "tenth": 10, "tenths": 10,
}
_FRACTION_PATTERN = "|".join(_FRACTION_DENOMINATOR)

_NUMBER_WORD = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
                "six": 6, "seven": 7, "eight": 8, "nine": 9}
_NUMBER_WORD_PATTERN = "|".join(_NUMBER_WORD)

# Tunable window widths (fraction of total narrative length). These are
# design defaults, not measured values — nothing in ARF tells us how
# wide "near the end" should be. Revisit with real query examples if
# this module's output ever gets evaluated against actual usage.
_NEAR_WINDOW = 0.10
_EXACT_WINDOW = 0.03
_EARLY_LATE_WINDOW = 0.15


def _clamp01(x: float) -> float:
    """Clamp a fraction to the valid [0.0, 1.0] narrative-position range."""
    return max(0.0, min(1.0, x))


# --- Pattern handlers ---------------------------------------------------
# Each handler takes a lowercased, whitespace-normalized query and
# returns a TemporalRange on match, or None. Tried in order in
# parse_temporal_phrase(); first match wins.

def _match_fractional_span(text: str) -> TemporalRange | None:
    """Match phrases like 'the first third', 'last quarter', 'second half'."""
    m = re.search(
        rf"\b(?:the\s+)?({_ORDINAL_PATTERN})\s+({_FRACTION_PATTERN})\b"
        r"(?:\s+of\s+the\s+(?:book|story|narrative))?",
        text,
    )
    if not m:
        return None
    ordinal_word, fraction_word = m.group(1), m.group(2)
    denom = _FRACTION_DENOMINATOR[fraction_word]
    idx = _ORDINAL_INDEX[ordinal_word]
    if idx == -1:  # "last"
        idx = denom - 1
    if idx >= denom:
        return None  # e.g. "fifth half" is nonsensical, decline rather than guess
    start = idx / denom
    end = (idx + 1) / denom
    return TemporalRange(start, end, "fractional_span", m.group(0))


def _match_fraction_of_the_way_through(text: str) -> TemporalRange | None:
    """Match 'two-thirds of the way through', 'a third of the way through',
    and the shorter 'two thirds through the book' form.

    Numerator may be a number word ('two') or bare 'a' (implying one) —
    "a third of the way through" is at least as common in practice as
    "one third of the way through", and was missed until tested against
    real example phrases rather than assumed to be covered.
    """
    m = re.search(
        rf"\b(?:(?P<num>{_NUMBER_WORD_PATTERN})|a)[\s-](?P<frac>{_FRACTION_PATTERN})\s+"
        r"(?:of\s+the\s+way\s+)?through\b",
        text,
    )
    if not m:
        return None
    numerator = _NUMBER_WORD[m.group("num")] if m.group("num") else 1
    denom = _FRACTION_DENOMINATOR[m.group("frac")]
    point = _clamp01(numerator / denom)
    return TemporalRange(
        max(0.0, point - _NEAR_WINDOW / 2),
        min(1.0, point + _NEAR_WINDOW / 2),
        "point_window",
        m.group(0),
    )


def _match_early_late(text: str) -> TemporalRange | None:
    """Match 'early in the story/book' and 'late in the story/book'.

    Deliberately not modeled as a generic modifier on any anchor —
    "early in the middle" isn't meaningful English, so this only
    pairs with the book's absolute edges.
    """
    m = re.search(r"\b(early|late)\s+(?:in|on)\s+the\s+(?:book|story|narrative)\b", text)
    if not m:
        return None
    if m.group(1) == "early":
        return TemporalRange(0.0, _EARLY_LATE_WINDOW, "point_window", m.group(0))
    return TemporalRange(1.0 - _EARLY_LATE_WINDOW, 1.0, "point_window", m.group(0))


def _match_anchor_with_modifier(text: str) -> TemporalRange | None:
    """Match '<modifier> the <anchor>' — e.g. 'near the end', 'by the middle'."""
    m = re.search(
        rf"\b(near|around|about|close to|towards?|by|right at|exactly at)?\s*"
        rf"(?:the\s+)?({_ANCHOR_PATTERN})\b",
        text,
    )
    if not m:
        return None
    modifier, anchor_word = m.group(1), m.group(2)
    point = _ANCHOR_POSITION[anchor_word]

    if modifier == "by":
        # Cumulative: everything from the start up through this point —
        # semantically distinct from a window around the point.
        return TemporalRange(0.0, point, "cumulative", m.group(0))
    if modifier in ("right at", "exactly at"):
        half_width = _EXACT_WINDOW / 2
    else:
        # Covers: near / around / about / close to / towards, and the
        # bare anchor with no modifier at all (e.g. plain "the end") —
        # both read as "in the vicinity of this point," same window.
        half_width = _NEAR_WINDOW / 2
    return TemporalRange(
        _clamp01(point - half_width), _clamp01(point + half_width),
        "point_window", m.group(0),
    )


_HANDLERS = (
    _match_fraction_of_the_way_through,  # more specific patterns first
    _match_fractional_span,
    _match_early_late,
    _match_anchor_with_modifier,  # most general, tried last
)


def parse_temporal_phrase(query: str) -> TemporalRange | None:
    """Parse a relative-position phrase out of a natural-language query.

    Args:
        query: Free-text query, e.g. "who does Tarzan meet near the end
            of the book?".

    Returns:
        The first matching TemporalRange, or None if no known pattern
        matches. Returning None is the safe default — declining to
        guess is preferable to a confident wrong answer, consistent
        with this project's handling of every other ambiguous-signal
        case so far (see docs/ Week 4 and Week 5 findings).
    """
    text = " ".join(query.lower().split())
    for handler in _HANDLERS:
        result = handler(text)
        if result is not None:
            return result
    return None


def resolve_to_bins(span: TemporalRange, num_bins: int) -> tuple[int, int]:
    """Convert a fractional TemporalRange to a concrete (start, end) bin range.

    Reimplements the bin-assignment formula documented in README
    (Week 2): k = floor(position * N / total_span) + 1, using
    start_frac/end_frac in place of raw chunk position (both already
    normalized to [0, 1]). Verify this still matches the live
    `temporal/binning.py` before relying on it — see module docstring.

    Args:
        span: A TemporalRange from parse_temporal_phrase().
        num_bins: This book's adaptive bin count N, from the existing
            temporal index (build_temporal_index() per README).

    Returns:
        (start_bin, end_bin), both 1-indexed and inclusive, clamped to
        [1, num_bins].
    """
    start_bin = int(span.start_frac * num_bins) + 1
    end_bin = int(span.end_frac * num_bins) + 1
    start_bin = max(1, min(num_bins, start_bin))
    end_bin = max(1, min(num_bins, end_bin))
    return (start_bin, max(start_bin, end_bin))
