"""Name and free-text normalization (N-NAME-01)."""

from app.application.ai.rules import RuleId
from app.application.ai.schemas.normalization import NormalizationOutcome

#: Particles that stay lowercase inside a name.
_NAME_PARTICLES = frozenset({"van", "von", "de", "del", "della", "da", "di", "bin", "al"})

#: Shortest token that is title-cased rather than kept as written, so an
#: all-caps acronym such as "IBM" survives but "AHMAD" does not.
_ACRONYM_MAX_LENGTH = 4


def normalize_person_name(raw_value: str) -> NormalizationOutcome:
    """Collapse spacing and title-case a person's name, keeping acronyms (N-NAME-01)."""
    tokens = raw_value.split()
    if not tokens:
        return NormalizationOutcome.rejected(RuleId.R_02, "Empty name")

    normalized = " ".join(_title_case_token(token) for token in tokens)
    if normalized == " ".join(tokens):
        return NormalizationOutcome.ok(normalized)
    return NormalizationOutcome.ok(normalized, RuleId.N_NAME_01)


def normalize_free_text(
    raw_value: str,
    *,
    max_length: int | None = None,
) -> NormalizationOutcome:
    """Trim a free-text field and check it against the catalogue's length limit.

    Over-length text is rejected rather than truncated: cutting a summary in
    half would silently change what the candidate said, while a rejection lands
    in the audit trail with its rule.
    """
    text = " ".join(raw_value.split())
    if not text:
        return NormalizationOutcome.rejected(RuleId.R_02, "Empty text")

    if max_length is not None and len(text) > max_length:
        return NormalizationOutcome.rejected(
            RuleId.R_02,
            f"Longer than the catalogue limit of {max_length} characters",
        )

    return NormalizationOutcome.ok(text)


def _title_case_token(token: str) -> str:
    """Title-case one token, leaving acronyms and name particles alone."""
    if token.isupper() and len(token) <= _ACRONYM_MAX_LENGTH:
        return token

    if token.casefold() in _NAME_PARTICLES:
        return token.casefold()

    # Keep internal punctuation: "o'brien" and "al-masri" each have two parts
    # that are both capitalised.
    result = []
    capitalise_next = True
    for char in token:
        if capitalise_next and char.isalpha():
            result.append(char.upper())
            capitalise_next = False
        elif char in {"-", "'", "."}:
            result.append(char)
            capitalise_next = True
        else:
            result.append(char.lower())
    return "".join(result)
