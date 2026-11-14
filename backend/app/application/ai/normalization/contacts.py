"""Email, phone and link normalization (N-EMAIL-01, N-PHONE-01, N-ENUM-01)."""

import re
from urllib.parse import urlparse

from pydantic import TypeAdapter, ValidationError
from pydantic.networks import EmailStr

from app.application.ai.rules import RuleId
from app.application.ai.normalization.places import DIAL_CODES
from app.application.ai.schemas.normalization import (
    NormalizationContext,
    NormalizationOutcome,
)
from app.application.ai.schemas.normalized_value import LinkType, ProfileLink

_EMAIL_ADAPTER = TypeAdapter(EmailStr)

_NON_DIGITS = re.compile(r"[^\d+]")

#: E.164 allows at most fifteen digits after the plus sign.
_E164 = re.compile(r"^\+[1-9]\d{6,14}$")

#: Hosts that identify a link's type without looking at the path.
_LINK_HOSTS: dict[str, LinkType] = {
    "linkedin.com": LinkType.LINKEDIN,
    "github.com": LinkType.GITHUB,
    "gitlab.com": LinkType.GITHUB,
    "behance.net": LinkType.PORTFOLIO,
    "dribbble.com": LinkType.PORTFOLIO,
}

_LINK_TYPE_ALIASES: dict[str, LinkType] = {
    "linkedin": LinkType.LINKEDIN,
    "linked in": LinkType.LINKEDIN,
    "github": LinkType.GITHUB,
    "gitlab": LinkType.GITHUB,
    "portfolio": LinkType.PORTFOLIO,
    "personal site": LinkType.PORTFOLIO,
    "website": LinkType.WEBSITE,
    "web site": LinkType.WEBSITE,
    "homepage": LinkType.WEBSITE,
    "blog": LinkType.WEBSITE,
    "other": LinkType.OTHER,
}


def normalize_email(raw_value: str) -> NormalizationOutcome:
    """Lowercase and validate an email address (N-EMAIL-01)."""
    text = raw_value.strip().casefold()
    if not text:
        return NormalizationOutcome.rejected(RuleId.R_02, "Empty email")

    try:
        _EMAIL_ADAPTER.validate_python(text)
    except ValidationError:
        return NormalizationOutcome.rejected(
            RuleId.R_02, f"Not a valid email address: {raw_value!r}"
        )

    return NormalizationOutcome.ok(text, RuleId.N_EMAIL_01)


def normalize_phone(
    raw_value: str,
    context: NormalizationContext | None = None,
    *,
    repaired_validation_factor: float = 0.80,
) -> NormalizationOutcome:
    """Put a phone number into E.164 form (N-PHONE-01).

    A number without a country code borrows the profile's country, which counts
    as a deterministic repair; with no country to borrow from, the number is
    rejected rather than assigned a guessed prefix.
    """
    text = _NON_DIGITS.sub("", raw_value.strip())
    if not text:
        return NormalizationOutcome.rejected(RuleId.R_02, "Empty phone number")

    if text.startswith("00"):
        text = "+" + text[2:]

    if text.startswith("+"):
        candidate = "+" + text[1:].lstrip("+")
        if _E164.match(candidate):
            return NormalizationOutcome.ok(candidate, RuleId.N_PHONE_01)
        return NormalizationOutcome.rejected(
            RuleId.R_02, f"Not a valid E.164 number: {raw_value!r}"
        )

    country = (context.profile_country if context else None) or None
    dial_code = DIAL_CODES.get(country) if country else None
    if dial_code is None:
        return NormalizationOutcome.rejected(
            RuleId.R_02,
            "Phone number has no country code and the profile country is unknown",
        )

    national = text.lstrip("0")
    candidate = f"+{dial_code}{national}"
    if not _E164.match(candidate):
        return NormalizationOutcome.rejected(
            RuleId.R_02, f"Not a valid E.164 number: {raw_value!r}"
        )

    return NormalizationOutcome.repaired(
        candidate,
        RuleId.N_PHONE_01,
        repaired_validation_factor,
        detail=f"Country code taken from the profile country {country}",
    )


def normalize_url(raw_value: str) -> NormalizationOutcome:
    """Validate a URL and give it a scheme if it has none."""
    text = raw_value.strip()
    if not text:
        return NormalizationOutcome.rejected(RuleId.R_02, "Empty URL")

    normalized, repaired = _with_scheme(text)
    parsed = urlparse(normalized)

    if parsed.scheme not in {"http", "https"} or "." not in parsed.netloc:
        return NormalizationOutcome.rejected(
            RuleId.R_02, f"Not a valid URL: {raw_value!r}"
        )

    if repaired:
        return NormalizationOutcome.repaired(
            normalized, RuleId.N_ENUM_01, 0.80, detail="Missing scheme added"
        )
    return NormalizationOutcome.ok(normalized)


def normalize_link(
    raw_type: str | None,
    raw_url: str,
) -> NormalizationOutcome:
    """Build a ``{type, url}`` link, classifying the type from the host.

    The host is trusted over the label the document used, because a label like
    "Profile" says nothing while ``github.com`` does.
    """
    url_outcome = normalize_url(raw_url)
    if not url_outcome.accepted:
        return url_outcome

    url = str(url_outcome.value)
    link_type = _classify_link(url, raw_type)

    return NormalizationOutcome.ok(
        ProfileLink(type=link_type, url=url), RuleId.N_ENUM_01
    )


def _with_scheme(text: str) -> tuple[str, bool]:
    if "://" in text:
        return text, False
    return f"https://{text.lstrip('/')}", True


def _classify_link(url: str, raw_type: str | None) -> LinkType:
    host = (urlparse(url).netloc or "").casefold().removeprefix("www.")

    for known_host, link_type in _LINK_HOSTS.items():
        if host == known_host or host.endswith(f".{known_host}"):
            return link_type

    if raw_type:
        label = " ".join(raw_type.split()).casefold()
        if link_type := _LINK_TYPE_ALIASES.get(label):
            return link_type

    return LinkType.WEBSITE
