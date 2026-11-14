"""Closed-vocabulary normalization (N-ENUM-01).

Some fields have a fixed catalogue of allowed values rather than free text:
a degree level, a language proficiency, a language code. Mapping onto them in
code is what keeps "BSc" and "Bachelor of Science" from looking like different
degrees to the merge stage.
"""

from typing import Final

from app.application.ai.rules import RuleId
from app.application.ai.schemas.normalization import NormalizationOutcome
from app.application.ai.schemas.normalized_value import DegreeLevel, LanguageProficiency
from app.application.ai.text_matching import canonical_text

_DEGREE_ALIASES: Final[dict[str, DegreeLevel]] = {
    "diploma": DegreeLevel.DIPLOMA,
    "associate": DegreeLevel.DIPLOMA,
    "associate degree": DegreeLevel.DIPLOMA,
    "higher diploma": DegreeLevel.DIPLOMA,
    "certificate": DegreeLevel.DIPLOMA,
    "bachelor": DegreeLevel.BACHELOR,
    "bachelors": DegreeLevel.BACHELOR,
    "bachelor's": DegreeLevel.BACHELOR,
    "bachelor degree": DegreeLevel.BACHELOR,
    "bachelor's degree": DegreeLevel.BACHELOR,
    "bsc": DegreeLevel.BACHELOR,
    "b.sc": DegreeLevel.BACHELOR,
    "bs": DegreeLevel.BACHELOR,
    "ba": DegreeLevel.BACHELOR,
    "be": DegreeLevel.BACHELOR,
    "beng": DegreeLevel.BACHELOR,
    "bachelor of science": DegreeLevel.BACHELOR,
    "bachelor of arts": DegreeLevel.BACHELOR,
    "bachelor of engineering": DegreeLevel.BACHELOR,
    "undergraduate": DegreeLevel.BACHELOR,
    "master": DegreeLevel.MASTER,
    "masters": DegreeLevel.MASTER,
    "master's": DegreeLevel.MASTER,
    "master degree": DegreeLevel.MASTER,
    "master's degree": DegreeLevel.MASTER,
    "msc": DegreeLevel.MASTER,
    "m.sc": DegreeLevel.MASTER,
    "ms": DegreeLevel.MASTER,
    "ma": DegreeLevel.MASTER,
    "meng": DegreeLevel.MASTER,
    "mba": DegreeLevel.MASTER,
    "master of science": DegreeLevel.MASTER,
    "master of arts": DegreeLevel.MASTER,
    "postgraduate": DegreeLevel.MASTER,
    "doctorate": DegreeLevel.DOCTORATE,
    "doctoral": DegreeLevel.DOCTORATE,
    "phd": DegreeLevel.DOCTORATE,
    "ph.d": DegreeLevel.DOCTORATE,
    "dphil": DegreeLevel.DOCTORATE,
    "doctor of philosophy": DegreeLevel.DOCTORATE,
}

_PROFICIENCY_ALIASES: Final[dict[str, LanguageProficiency]] = {
    "native": LanguageProficiency.NATIVE,
    "native speaker": LanguageProficiency.NATIVE,
    "mother tongue": LanguageProficiency.NATIVE,
    "first language": LanguageProficiency.NATIVE,
    "bilingual": LanguageProficiency.NATIVE,
    "fluent": LanguageProficiency.FLUENT,
    "fluency": LanguageProficiency.FLUENT,
    "advanced": LanguageProficiency.FLUENT,
    "proficient": LanguageProficiency.FLUENT,
    "c2": LanguageProficiency.FLUENT,
    "c1": LanguageProficiency.FLUENT,
    "professional": LanguageProficiency.PROFESSIONAL,
    "professional working": LanguageProficiency.PROFESSIONAL,
    "working": LanguageProficiency.PROFESSIONAL,
    "working proficiency": LanguageProficiency.PROFESSIONAL,
    "intermediate": LanguageProficiency.PROFESSIONAL,
    "upper intermediate": LanguageProficiency.PROFESSIONAL,
    "b2": LanguageProficiency.PROFESSIONAL,
    "b1": LanguageProficiency.PROFESSIONAL,
    "basic": LanguageProficiency.BASIC,
    "beginner": LanguageProficiency.BASIC,
    "elementary": LanguageProficiency.BASIC,
    "limited": LanguageProficiency.BASIC,
    "a2": LanguageProficiency.BASIC,
    "a1": LanguageProficiency.BASIC,
}

#: English language names to ISO 639-1, stored as codes so that every spelling
#: of the same language compares as equal.
_LANGUAGE_CODES: Final[dict[str, str]] = {
    "arabic": "ar",
    "english": "en",
    "french": "fr",
    "german": "de",
    "spanish": "es",
    "italian": "it",
    "portuguese": "pt",
    "dutch": "nl",
    "russian": "ru",
    "turkish": "tr",
    "hebrew": "he",
    "persian": "fa",
    "farsi": "fa",
    "urdu": "ur",
    "hindi": "hi",
    "bengali": "bn",
    "chinese": "zh",
    "mandarin": "zh",
    "japanese": "ja",
    "korean": "ko",
    "indonesian": "id",
    "malay": "ms",
    "swedish": "sv",
    "norwegian": "no",
    "danish": "da",
    "finnish": "fi",
    "polish": "pl",
    "romanian": "ro",
    "greek": "el",
    "czech": "cs",
    "ukrainian": "uk",
    "swahili": "sw",
    "kurdish": "ku",
}

_LANGUAGE_CODE_VALUES: Final[frozenset[str]] = frozenset(_LANGUAGE_CODES.values())


def normalize_degree_level(raw_value: str) -> NormalizationOutcome:
    """Map a stated degree onto the catalogue's five levels.

    A degree that matches nothing becomes ``other``, which is itself a
    catalogue value: the level is unknown, not wrong.
    """
    text = canonical_text(raw_value).rstrip(".")
    if not text:
        return NormalizationOutcome.rejected(RuleId.R_02, "Empty degree")

    if level := _DEGREE_ALIASES.get(text):
        return NormalizationOutcome.ok(level, RuleId.N_ENUM_01)

    # Degrees are usually written as "Bachelor of Computer Engineering", so a
    # leading alias is matched before falling back.
    for alias, level in _DEGREE_ALIASES.items():
        if text.startswith(f"{alias} ") or text.startswith(f"{alias},"):
            return NormalizationOutcome.ok(level, RuleId.N_ENUM_01)

    return NormalizationOutcome.ok(DegreeLevel.OTHER, RuleId.N_ENUM_01)


def normalize_language_proficiency(raw_value: str) -> NormalizationOutcome:
    """Map a stated proficiency onto the catalogue's four levels.

    Unlike a degree the catalogue has no ``other`` level here, so a proficiency
    that matches nothing is rejected rather than flattened.
    """
    text = canonical_text(raw_value)
    if not text:
        return NormalizationOutcome.rejected(RuleId.R_02, "Empty proficiency")

    if level := _PROFICIENCY_ALIASES.get(text):
        return NormalizationOutcome.ok(level, RuleId.N_ENUM_01)

    return NormalizationOutcome.rejected(
        RuleId.R_02, f"No catalogue proficiency matches {raw_value!r}"
    )


def normalize_language_name(raw_value: str) -> NormalizationOutcome:
    """Map a language name to its ISO 639-1 code.

    A language the table does not know becomes a system decision (R-09), the
    same way an unknown country does, so an approved mapping is added once and
    serves every later candidate.
    """
    text = canonical_text(raw_value)
    if not text:
        return NormalizationOutcome.rejected(RuleId.R_02, "Empty language")

    if len(text) == 2 and text in _LANGUAGE_CODE_VALUES:
        return NormalizationOutcome.ok(text, RuleId.N_ENUM_01)

    if code := _LANGUAGE_CODES.get(text):
        return NormalizationOutcome.ok(code, RuleId.N_ENUM_01)

    return NormalizationOutcome(
        value=None,
        rule=RuleId.N_ENUM_01,
        rejected_by=RuleId.R_09,
        detail=f"No language matches {raw_value!r}",
        needs_system_decision=True,
    )
