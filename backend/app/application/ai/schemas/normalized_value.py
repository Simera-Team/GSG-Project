"""Normalized value types: the catalogue formats a field record stores.

Two values that mean the same thing must compare as equal, otherwise the merge
stage sees a conflict that is not there. That is why dates keep their precision
instead of being padded, and why countries and languages are stored as ISO
codes rather than as the spellings found in the document.
"""

from enum import Enum
from typing import Literal

from pydantic import Field, model_validator

from app.application.ai.schemas.base import AIBaseSchema


class DatePrecision(str, Enum):
    """How much of a date the source actually stated."""

    YEAR = "year"
    MONTH = "month"
    DAY = "day"


class PartialDate(AIBaseSchema):
    """A date kept at the precision the source stated it.

    A month or a day is never invented: ``2022`` stays year-precise.
    """

    year: int = Field(ge=1950)
    month: int | None = Field(default=None, ge=1, le=12)
    day: int | None = Field(default=None, ge=1, le=31)
    precision: DatePrecision

    @model_validator(mode="after")
    def _check_parts_match_precision(self) -> "PartialDate":
        if self.precision is DatePrecision.YEAR and (self.month or self.day):
            raise ValueError("A year-precision date carries no month or day")
        if self.precision is DatePrecision.MONTH:
            if self.month is None:
                raise ValueError("A month-precision date needs a month")
            if self.day is not None:
                raise ValueError("A month-precision date carries no day")
        if self.precision is DatePrecision.DAY and (self.month is None or self.day is None):
            raise ValueError("A day-precision date needs both a month and a day")
        return self

    @property
    def precision_rank(self) -> int:
        """Higher is more precise. Used by C-04."""
        return {DatePrecision.YEAR: 0, DatePrecision.MONTH: 1, DatePrecision.DAY: 2}[
            self.precision
        ]

    def coarser_than(self, other: "PartialDate") -> bool:
        """Whether ``self`` states the same date as ``other`` but less precisely."""
        if self.year != other.year:
            return False
        if self.precision_rank >= other.precision_rank:
            return False
        if self.month is not None and self.month != other.month:
            return False
        return True

    def as_sort_key(self) -> tuple[int, int, int]:
        """Comparable key that treats missing parts as the start of the period."""
        return (self.year, self.month or 1, self.day or 1)


class PresentDate(AIBaseSchema):
    """Marker for an ongoing role.

    An ongoing role is not the same as a missing end date: a missing end date is
    simply an absent field.
    """

    kind: Literal["present"] = "present"


DateValue = PartialDate | PresentDate


class LinkType(str, Enum):
    """The kinds of profile link the catalogue allows."""

    LINKEDIN = "linkedin"
    GITHUB = "github"
    PORTFOLIO = "portfolio"
    WEBSITE = "website"
    OTHER = "other"


class ProfileLink(AIBaseSchema):
    """A typed profile link, stored as ``{type, url}``."""

    type: LinkType
    url: str


class DegreeLevel(str, Enum):
    """Closed vocabulary for ``education.degree``."""

    DIPLOMA = "diploma"
    BACHELOR = "bachelor"
    MASTER = "master"
    DOCTORATE = "doctorate"
    OTHER = "other"


class LanguageProficiency(str, Enum):
    """Closed vocabulary for ``language.proficiency``."""

    NATIVE = "native"
    FLUENT = "fluent"
    PROFESSIONAL = "professional"
    BASIC = "basic"


#: Every shape a normalized value can take in a field record. Country codes are
#: ISO 3166-1 alpha-2 and language codes ISO 639-1, both carried as ``str``;
#: the interface shows the full English name instead, so candidates and clients
#: never see the codes.
NormalizedValue = (
    str | int | PartialDate | PresentDate | ProfileLink | DegreeLevel | LanguageProficiency
)
