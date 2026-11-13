"""Date normalisation (FR-028).

"03/2022", "March 2022" and "2022" all become one format, keeping the
source's precision: "2022-03" (month) or "2022" (year). A day is never
invented, and a day given in the source is dropped (precision stays month).
"Present"/"Current" is recognised as an ongoing job, which is different
from a missing end date.
"""

import re
from dataclasses import dataclass

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

    def to_dict(self) -> dict:
        return {"value": self.iso, "precision": self.precision}


@dataclass(frozen=True)
class DateResult:
    kind: str                     # date | current | empty | invalid
    date: PartialDate | None = None


def parse_date(text: str | None) -> DateResult:
    if text is None or not text.strip():
        return DateResult("empty")

    s = text.strip().lower()
    s = re.sub(r"[.,]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()

    if s in CURRENT_WORDS:
        return DateResult("current")

    # 2022-03 or 2022-03-15 / 2022/03
    m = re.fullmatch(_YEAR + r"[-/](\d{1,2})(?:[-/]\d{1,2})?", s)
    if m:
        return _with_month(int(m.group(1)), int(m.group(2)))

    # 03/2022, 3-2022, 03 2022
    m = re.fullmatch(r"(\d{1,2})[/\-\s]" + _YEAR, s)
    if m:
        return _with_month(int(m.group(2)), int(m.group(1)))

    # 15/03/2022 or 03/15/2022 - only accept when the order is unambiguous
    m = re.fullmatch(r"(\d{1,2})[/\-](\d{1,2})[/\-]" + _YEAR, s)
    if m:
        a, b, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if a > 12 >= b:
            return _with_month(year, b)        # day/month/year
        if b > 12 >= a:
            return _with_month(year, a)        # month/day/year
        if a == b:
            return _with_month(year, a)
        return DateResult("invalid")           # e.g. 04/05/2022: which is the month?

    # March 2022, Mar 2022, 15 March 2022, March 15 2022
    m = re.fullmatch(r"(?:\d{1,2} )?(" + _MONTH_NAME + r")(?: \d{1,2})? " + _YEAR, s)
    if m:
        return _with_month(int(m.group(2)), MONTHS[m.group(1)])

    # 2022 (also "Summer 2022", "Fall 2021": year precision only)
    m = re.fullmatch(r"(?:(?:spring|summer|autumn|fall|winter) )?" + _YEAR, s)
    if m:
        return DateResult("date", PartialDate(int(m.group(1))))

    return DateResult("invalid")


def _with_month(year: int, month: int) -> DateResult:
    if not 1 <= month <= 12:
        return DateResult("invalid")
    return DateResult("date", PartialDate(year, month))


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
