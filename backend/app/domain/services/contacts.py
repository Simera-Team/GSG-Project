"""Contact and name normalisation (N-PHONE-01, N-EMAIL-01, N-NAME-01).

Dates, countries and skills each had a rule of their own; the remaining
personal fields had none, so a phone number was stored exactly as the CV
wrote it. "+962 7 9000 1234", "0790001234" and "00962790001234" are the same
number, and three spellings of one number is three false conflicts between
sources (FR-033) and a value a recruiter cannot dial.

Every rule here is deterministic, has no clock and no randomness, so the same
input always gives the same output (FR-034, NFR-023).
"""

import re
from dataclasses import dataclass

from app.domain.services.countries import DIAL_CODES

_NON_DIGITS = re.compile(r"[^\d+]")

#: E.164 allows at most fifteen digits after the plus sign.
_E164 = re.compile(r"^\+[1-9]\d{6,14}$")

_EMAIL_RE = re.compile(r"^[\w.+-]+@[\w-]+(\.[\w-]+)+$")

#: Particles that stay lowercase inside a name ("Ali bin Hassan").
_NAME_PARTICLES = frozenset({"van", "von", "de", "del", "della", "da", "di", "bin", "al"})



class ContactRule:
    """Identifier stored on the field record for the rule that set the value."""

    PHONE = "N-PHONE-01"
    EMAIL = "N-EMAIL-01"
    NAME = "N-NAME-01"


@dataclass(frozen=True)
class PhoneResult:
    """A phone number in E.164 form, or the reason it could not be put in it."""

    e164: str | None
    borrowed_country: str | None = None   # country whose dial code was added

    @property
    def ok(self) -> bool:
        return self.e164 is not None


def normalize_phone(raw: str | None, country_code: str | None = None) -> PhoneResult:
    """Put a phone number into E.164 form (N-PHONE-01).

    A number written without a country code borrows the profile's country.
    With no country to borrow from, the number is rejected rather than given a
    guessed prefix: a wrong dial code is worse than a flagged field, because it
    looks correct.
    """
    if not raw or not raw.strip():
        return PhoneResult(None)

    text = _NON_DIGITS.sub("", raw.strip())
    if not text:
        return PhoneResult(None)

    # "00962..." is the same as "+962..."
    if text.startswith("00"):
        text = "+" + text[2:]

    if text.startswith("+"):
        candidate = "+" + text[1:].lstrip("+")
        return PhoneResult(candidate) if _E164.match(candidate) else PhoneResult(None)

    dial_code = DIAL_CODES.get((country_code or "").upper())
    if dial_code is None:
        return PhoneResult(None)

    candidate = f"+{dial_code}{text.lstrip('0')}"
    if not _E164.match(candidate):
        return PhoneResult(None)
    return PhoneResult(candidate, borrowed_country=country_code.upper())


def normalize_email(raw: str | None) -> str | None:
    """Lowercase and validate an address (N-EMAIL-01).

    The local part is case-sensitive in the standard but not at any mail
    provider in practice, and leaving the case alone would make
    "Ahmad@x.com" and "ahmad@x.com" two values of one field.
    """
    if not raw or not raw.strip():
        return None
    text = raw.strip().casefold()
    return text if _EMAIL_RE.match(text) else None


def normalize_person_name(raw: str | None) -> str | None:
    """Collapse spacing and title-case a person's name (N-NAME-01).

    Every token is title-cased, with no exemption for all-caps ones: a CV
    header often writes the name in capitals ("NADA KHAIRALDIN"), and no
    person's name is an acronym, so keeping capitals would leave the shouting
    in the profile. The particle list handles "bin" and "al".
    """
    if not raw or not raw.split():
        return None
    return " ".join(_title_case_token(t) for t in raw.split())


def _title_case_token(token: str) -> str:
    if token.casefold() in _NAME_PARTICLES:
        return token.casefold()

    # Keep internal punctuation: "o'brien" and "al-masri" each have two parts
    # that are both capitalised.
    out, capitalise = [], True
    for char in token:
        if capitalise and char.isalpha():
            out.append(char.upper())
            capitalise = False
        elif char in {"-", "'", "."}:
            out.append(char)
            capitalise = True
        else:
            out.append(char.lower())
    return "".join(out)
