"""Date normalisation (FR-028, N-DATE-01 to N-DATE-06).

"03/2022", "March 2022" and "2022" all become one format, keeping the
source's precision: "2022-03" (month) or "2022" (year). A day is never
invented, and a day given in the source is dropped (precision stays month).
"Present"/"Current" is recognised as an ongoing job, which is different
from a missing end date.

Rules, with the identifiers the field record cites so a decision stays
explainable later (FR-035, FR-051):

* ``N-DATE-01`` month precision recognised.
* ``N-DATE-02`` year-only kept at year precision.
* ``N-DATE-03`` ambiguous day/month order (``04/05/2022``): the year is
  certain whichever part is the month, so it is kept at year precision and
  the field is flagged for a reviewer, who can restore the month. Nothing is
  guessed and nothing is thrown away.
* ``N-DATE-04`` ongoing-role marker.
* ``N-DATE-05`` start and end the wrong way round; see :func:`repair_date_order`.
* ``N-DATE-06`` date too far in the future to be real (OCR misreads).
"""

import re
from dataclasses import dataclass
from datetime import date

MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}

CURRENT_WORDS = {"present", "current", "currently", "now", "today", "ongoing",
                 "to date", "till date", "till now", "until now"}

_MONTH_NAME = "|".join(sorted(MONTHS, key=len, reverse=True))
_YEAR = r"(19\d{2}|20\d{2})"

#: A year further ahead than this many years is a misreading, not a date
#: (N-DATE-06). One year of slack keeps a legitimately future end date
#: ("graduating 2027") usable.
FUTURE_YEAR_SLACK = 1


class DateRule:
    """Identifier stored on the field record for the rule that read the date."""

    MONTH = "N-DATE-01"
    YEAR = "N-DATE-02"
    AMBIGUOUS_ORDER = "N-DATE-03"
    CURRENT_MARKER = "N-DATE-04"
    SWAPPED = "N-DATE-05"


@dataclass(frozen=True)
class PartialDate:
    year: int
    month: int | None = None

    @property
    def precision(self) -> str:
        return "month" if self.month else "year"

    @property
    def iso(self) -> str:
        return f"{self.year:04d}-{self.month:02d}" if self.month else f"{self.year:04d}"

    def sort_key(self) -> tuple[int, int]:
        """Order two dates of possibly different precision.

        A year-only date sorts as the start of that year, which is what makes
        "2020" and "2020-03" compare without inventing a month on either.
        """
        return (self.year, self.month or 0)

    def to_dict(self) -> dict:
        return {"value": self.iso, "precision": self.precision}


@dataclass(frozen=True)
class DateResult:
    kind: str                     # date | current | empty | invalid
    date: PartialDate | None = None
    rule: str | None = None       # which N-DATE rule read it
    ambiguous: bool = False       # N-DATE-03: year kept, month needs a reviewer


def parse_date(text: str | None, *, today: date | None = None) -> DateResult:
    if text is None or not text.strip():
        return DateResult("empty")

    s = text.strip().lower()
    s = re.sub(r"[.,]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()

    if s in CURRENT_WORDS:
        return DateResult("current", rule=DateRule.CURRENT_MARKER)

    result = _parse_known_formats(s)
    if result.kind != "date" or result.date is None:
        return result

    # N-DATE-06: a year beyond next year is a misreading, not a date.
    limit = (today or date.today()).year + FUTURE_YEAR_SLACK
    if result.date.year > limit:
        return DateResult("invalid")

    return result


def _parse_known_formats(s: str) -> DateResult:
    # 2022-03 or 2022-03-15 / 2022/03
    m = re.fullmatch(_YEAR + r"[-/](\d{1,2})(?:[-/]\d{1,2})?", s)
    if m:
        return _with_month(int(m.group(1)), int(m.group(2)))

    # 03/2022, 3-2022, 03 2022
    m = re.fullmatch(r"(\d{1,2})[/\-\s]" + _YEAR, s)
    if m:
        return _with_month(int(m.group(2)), int(m.group(1)))

    # 15/03/2022 or 03/15/2022
    m = re.fullmatch(r"(\d{1,2})[/\-](\d{1,2})[/\-]" + _YEAR, s)
    if m:
        a, b, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if a > 12 >= b:
            return _with_month(year, b)        # day/month/year
        if b > 12 >= a:
            return _with_month(year, a)        # month/day/year
        if a == b:
            return _with_month(year, a)
        if a > 12 and b > 12:
            return DateResult("invalid")       # neither part can be a month
        # N-DATE-03: either part could be the month ("04/05/2022"). The year is
        # certain, so it is kept and the month is left to a reviewer rather
        # than guessed or discarded.
        return DateResult("date", PartialDate(year),
                          rule=DateRule.AMBIGUOUS_ORDER, ambiguous=True)

    # March 2022, Mar 2022, 15 March 2022, March 15 2022
    m = re.fullmatch(r"(?:\d{1,2} )?(" + _MONTH_NAME + r")(?: \d{1,2})? " + _YEAR, s)
    if m:
        return _with_month(int(m.group(2)), MONTHS[m.group(1)])

    # 2022 March / 2022 Mar: the same date written the other way round.
    m = re.fullmatch(_YEAR + r" (" + _MONTH_NAME + r")", s)
    if m:
        return _with_month(int(m.group(1)), MONTHS[m.group(2)])

    # 2022 (also "Summer 2022", "Fall 2021": year precision only)
    m = re.fullmatch(r"(?:(?:spring|summer|autumn|fall|winter) )?" + _YEAR, s)
    if m:
        return DateResult("date", PartialDate(int(m.group(1))), rule=DateRule.YEAR)

    return DateResult("invalid")


def _with_month(year: int, month: int) -> DateResult:
    if not 1 <= month <= 12:
        return DateResult("invalid")
    return DateResult("date", PartialDate(year, month), rule=DateRule.MONTH)


@dataclass(frozen=True)
class EmploymentEnd:
    status: str                   # current | ended | unknown
    date: PartialDate | None = None
    conflict: bool = False        # marked current but an end date is also given


def resolve_employment_end(end_text: str | None, is_current: bool) -> EmploymentEnd:
    """Tell an ongoing job apart from a job whose end date is missing (FR-028)."""
    result = parse_date(end_text)

    if result.kind == "current":
        return EmploymentEnd("current")
    if result.kind == "date":
        return EmploymentEnd("ended", result.date, conflict=is_current)
    if is_current:
        return EmploymentEnd("current")
    return EmploymentEnd("unknown")


def repair_date_order(
    start: PartialDate | None, end: PartialDate | None
) -> tuple[PartialDate | None, PartialDate | None, bool]:
    """Swap a start and end date that are the wrong way round (N-DATE-05).

    Returns the pair in order and whether a swap happened. A reversed pair is a
    reading mistake with one sensible repair, so it is repaired rather than
    sent to a person; the caller lowers the confidence of both fields and
    records the rule, so the repair stays visible (FR-035).

    Dates of different precision are left alone: "2020" against "2020-03"
    is a precision difference, not a reversal.
    """
    if start is None or end is None:
        return start, end, False
    if start.precision != end.precision:
        return start, end, False
    if start.sort_key() <= end.sort_key():
        return start, end, False
    return end, start, True
