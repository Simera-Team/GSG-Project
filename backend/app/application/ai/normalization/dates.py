"""Date normalization (N-DATE-01 to N-DATE-06).

Dates keep the precision the source stated. A month or a day is never invented,
because padding ``2022`` to ``2022-01-01`` would turn a precision difference
into a false conflict.
"""

import re
from datetime import date

from app.application.ai.rules import RuleId
from app.application.ai.schemas.normalization import NormalizationOutcome
from app.application.ai.schemas.normalized_value import (
    DatePrecision,
    PartialDate,
    PresentDate,
)

#: Values that mean an ongoing role (N-DATE-04). Valid for an end date only.
_PRESENT_MARKERS = frozenset(
    {"present", "current", "currently", "now", "to date", "till date", "ongoing"}
)

_MONTH_NAMES: dict[str, int] = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}

#: Earliest year a working life can plausibly start (N-DATE-06).
_EARLIEST_YEAR = 1950

_ISO_DAY = re.compile(r"^(?P<year>\d{4})-(?P<month>\d{1,2})-(?P<day>\d{1,2})$")
_ISO_MONTH = re.compile(r"^(?P<year>\d{4})[-/](?P<month>\d{1,2})$")
_MONTH_YEAR = re.compile(r"^(?P<month>\d{1,2})[/.-](?P<year>\d{4})$")
_YEAR_ONLY = re.compile(r"^(?P<year>\d{4})$")
_NUMERIC_TRIPLE = re.compile(r"^(?P<first>\d{1,2})[/.-](?P<second>\d{1,2})[/.-](?P<year>\d{4})$")
_NAMED_MONTH = re.compile(
    r"^(?P<name>[a-z]+)\.?\s*,?\s*(?P<year>\d{4})$", re.IGNORECASE
)
_NAMED_MONTH_SUFFIX = re.compile(
    r"^(?P<year>\d{4})\s*,?\s*(?P<name>[a-z]+)\.?$", re.IGNORECASE
)


def normalize_date(
    raw_value: str,
    *,
    allow_present: bool = False,
    today: date | None = None,
) -> NormalizationOutcome:
    """Normalize one date as written in the source.

    ``allow_present`` is set for end dates only, since an ongoing marker makes
    no sense as a start date.
    """
    text = raw_value.strip()
    if not text:
        return NormalizationOutcome.rejected(RuleId.R_02, "Empty date")

    lowered = text.casefold().rstrip(".")

    if lowered in _PRESENT_MARKERS:
        if not allow_present:
            return NormalizationOutcome.rejected(
                RuleId.R_02, "An ongoing marker is valid for an end date only"
            )
        return NormalizationOutcome.ok(PresentDate(), RuleId.N_DATE_04)

    parsed = _parse(text)
    if parsed is None:
        return NormalizationOutcome.rejected(
            RuleId.R_02, f"Unrecognised date format: {text!r}"
        )

    partial, rule, validation = parsed

    if not _is_plausible(partial, today or date.today()):
        return NormalizationOutcome.rejected(
            RuleId.R_02, f"Date outside the plausible range ({RuleId.N_DATE_06})"
        )

    if validation < 1.0:
        return NormalizationOutcome.repaired(partial, rule, validation)
    return NormalizationOutcome.ok(partial, rule)


def _parse(text: str) -> tuple[PartialDate, RuleId, float] | None:
    """Return the date, the rule that read it, and its validation factor."""
    if match := _ISO_DAY.match(text):
        year, month, day = (int(match["year"]), int(match["month"]), int(match["day"]))
        if not _valid_day(year, month, day):
            return None
        return (
            PartialDate(year=year, month=month, day=day, precision=DatePrecision.DAY),
            RuleId.N_DATE_01,
            1.0,
        )

    if match := _ISO_MONTH.match(text):
        month = int(match["month"])
        if not 1 <= month <= 12:
            return None
        return (
            PartialDate(year=int(match["year"]), month=month, precision=DatePrecision.MONTH),
            RuleId.N_DATE_01,
            1.0,
        )

    if match := _NUMERIC_TRIPLE.match(text):
        return _parse_numeric_triple(
            int(match["first"]), int(match["second"]), int(match["year"])
        )

    if match := _MONTH_YEAR.match(text):
        month = int(match["month"])
        if not 1 <= month <= 12:
            return None
        return (
            PartialDate(year=int(match["year"]), month=month, precision=DatePrecision.MONTH),
            RuleId.N_DATE_01,
            1.0,
        )

    for pattern in (_NAMED_MONTH, _NAMED_MONTH_SUFFIX):
        if match := pattern.match(text):
            month = _MONTH_NAMES.get(match["name"].casefold())
            if month is None:
                continue
            return (
                PartialDate(
                    year=int(match["year"]), month=month, precision=DatePrecision.MONTH
                ),
                RuleId.N_DATE_01,
                1.0,
            )

    if match := _YEAR_ONLY.match(text):
        return (
            PartialDate(year=int(match["year"]), precision=DatePrecision.YEAR),
            RuleId.N_DATE_02,
            1.0,
        )

    return None


def _parse_numeric_triple(
    first: int, second: int, year: int
) -> tuple[PartialDate, RuleId, float] | None:
    """Read ``05/03/2022``-style dates, where the part order may be ambiguous."""
    if first > 12 and second <= 12:
        # Unambiguous day-first.
        if not _valid_day(year, second, first):
            return None
        return (
            PartialDate(year=year, month=second, day=first, precision=DatePrecision.DAY),
            RuleId.N_DATE_01,
            1.0,
        )

    if second > 12 and first <= 12:
        # Unambiguous month-first.
        if not _valid_day(year, first, second):
            return None
        return (
            PartialDate(year=year, month=first, day=second, precision=DatePrecision.DAY),
            RuleId.N_DATE_01,
            1.0,
        )

    if first <= 12 and second <= 12:
        # N-DATE-03: either part could be the month, so the day and the month
        # are both dropped rather than guessed.
        return (
            PartialDate(year=year, precision=DatePrecision.YEAR),
            RuleId.N_DATE_03,
            0.80,
        )

    return None


def _valid_day(year: int, month: int, day: int) -> bool:
    try:
        date(year, month, day)
    except ValueError:
        return False
    return True


def _is_plausible(value: PartialDate, today: date) -> bool:
    """Reject a year before 1950 or a date too far in the future (N-DATE-06)."""
    if value.year < _EARLIEST_YEAR:
        return False
    return value.year <= today.year + 1


def repair_date_order(
    start: PartialDate | PresentDate | None,
    end: PartialDate | PresentDate | None,
) -> tuple[PartialDate | PresentDate | None, PartialDate | PresentDate | None, bool]:
    """Swap a start and end date that are the wrong way round (N-DATE-05).

    Returns the pair in order and whether a swap happened; the caller lowers the
    validation factor of both fields when it did.
    """
    if not isinstance(start, PartialDate) or not isinstance(end, PartialDate):
        return start, end, False

    if start.as_sort_key() > end.as_sort_key():
        return end, start, True

    return start, end, False
