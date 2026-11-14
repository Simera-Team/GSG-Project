"""Maps each catalogue field to the normalization rules that apply to it.

One table instead of a long branch in the pipeline: adding a field means adding
a row here, and a field with no row falls back to trimmed free text rather than
silently losing its value.
"""

from collections.abc import Callable
from typing import Protocol

from app.application.ai.normalization import contacts, dates, places, text, vocabularies
from app.application.ai.schemas.field_record import CandidateValue, EntityType, FieldName
from app.application.ai.schemas.normalization import (
    NormalizationContext,
    NormalizationOutcome,
)
from app.application.ai.settings import AISettings

#: A rule that turns one raw value into one catalogue value.
SingleNormalizer = Callable[[str, NormalizationContext], NormalizationOutcome]

_FieldKey = tuple[EntityType, FieldName]


class MultiValueNormalizer(Protocol):
    """A rule that can turn one raw entry into several catalogue values.

    Declared structurally so this module does not depend on the skills package;
    the pipeline injects the concrete canonicalizer.
    """

    def canonicalize(self, raw_value: str) -> list[NormalizationOutcome]: ...


#: Fields whose raw entry may name more than one value, so they go through the
#: injected multi-value normalizer instead of the table below.
SKILL_FIELDS: frozenset[_FieldKey] = frozenset(
    {
        (EntityType.SKILL, FieldName.NAME),
        (EntityType.PROJECT, FieldName.TECH_STACK),
    }
)


class FieldNormalizerRegistry:
    """Normalizes a raw value according to the field it belongs to."""

    def __init__(
        self,
        settings: AISettings,
        skill_normalizer: MultiValueNormalizer,
    ) -> None:
        self._settings = settings
        self._skill_normalizer = skill_normalizer
        self._table = self._build_table(settings)

    def normalize(
        self,
        candidate: CandidateValue,
        context: NormalizationContext,
    ) -> list[NormalizationOutcome]:
        """Return one outcome per catalogue value ``candidate`` produced."""
        key = (candidate.entity, candidate.field)

        if key in SKILL_FIELDS:
            return self._skill_normalizer.canonicalize(candidate.raw_value)

        if key == (EntityType.PROFILE, FieldName.LINK):
            return [contacts.normalize_link(candidate.raw_type, candidate.raw_value)]

        normalizer = self._table.get(key, self._free_text())
        return [normalizer(candidate.raw_value, context)]

    def _build_table(self, settings: AISettings) -> dict[_FieldKey, SingleNormalizer]:
        trimmed = self._free_text()
        start_date = self._date(allow_present=False)
        end_date = self._date(allow_present=True)

        return {
            # --- profile ---------------------------------------------------
            (EntityType.PROFILE, FieldName.FIRST_NAME): self._person_name(),
            (EntityType.PROFILE, FieldName.LAST_NAME): self._person_name(),
            (EntityType.PROFILE, FieldName.EMAIL): self._email(),
            (EntityType.PROFILE, FieldName.PHONE): self._phone(settings),
            (EntityType.PROFILE, FieldName.CITY): self._city(),
            (EntityType.PROFILE, FieldName.COUNTRY): self._country(settings),
            (EntityType.PROFILE, FieldName.TITLE): self._free_text(
                settings.max_headline_length
            ),
            (EntityType.PROFILE, FieldName.SUMMARY): self._free_text(
                settings.max_summary_length
            ),
            # --- work_experience -------------------------------------------
            (EntityType.WORK_EXPERIENCE, FieldName.COMPANY): trimmed,
            (EntityType.WORK_EXPERIENCE, FieldName.TITLE): trimmed,
            (EntityType.WORK_EXPERIENCE, FieldName.DESCRIPTION): trimmed,
            (EntityType.WORK_EXPERIENCE, FieldName.START_DATE): start_date,
            (EntityType.WORK_EXPERIENCE, FieldName.END_DATE): end_date,
            # --- education -------------------------------------------------
            (EntityType.EDUCATION, FieldName.INSTITUTION): trimmed,
            (EntityType.EDUCATION, FieldName.FIELD): trimmed,
            (EntityType.EDUCATION, FieldName.DEGREE): self._degree_level(),
            (EntityType.EDUCATION, FieldName.START_DATE): start_date,
            (EntityType.EDUCATION, FieldName.END_DATE): end_date,
            # --- certification ---------------------------------------------
            (EntityType.CERTIFICATION, FieldName.NAME): trimmed,
            (EntityType.CERTIFICATION, FieldName.ISSUER): trimmed,
            (EntityType.CERTIFICATION, FieldName.ISSUE_DATE): start_date,
            (EntityType.CERTIFICATION, FieldName.URL): self._url(),
            # --- project ---------------------------------------------------
            (EntityType.PROJECT, FieldName.NAME): trimmed,
            (EntityType.PROJECT, FieldName.DESCRIPTION): trimmed,
            (EntityType.PROJECT, FieldName.URL): self._url(),
            # --- language --------------------------------------------------
            (EntityType.LANGUAGE, FieldName.NAME): self._language_name(),
            (EntityType.LANGUAGE, FieldName.PROFICIENCY): self._language_proficiency(),
        }

    # Each factory returns a normalizer with the uniform ``(raw, context)``
    # signature, so the table stays a plain mapping.

    @staticmethod
    def _free_text(max_length: int | None = None) -> SingleNormalizer:
        def normalize(raw_value: str, _: NormalizationContext) -> NormalizationOutcome:
            return text.normalize_free_text(raw_value, max_length=max_length)

        return normalize

    @staticmethod
    def _person_name() -> SingleNormalizer:
        def normalize(raw_value: str, _: NormalizationContext) -> NormalizationOutcome:
            return text.normalize_person_name(raw_value)

        return normalize

    @staticmethod
    def _email() -> SingleNormalizer:
        def normalize(raw_value: str, _: NormalizationContext) -> NormalizationOutcome:
            return contacts.normalize_email(raw_value)

        return normalize

    @staticmethod
    def _phone(settings: AISettings) -> SingleNormalizer:
        def normalize(
            raw_value: str, context: NormalizationContext
        ) -> NormalizationOutcome:
            return contacts.normalize_phone(
                raw_value,
                context,
                repaired_validation_factor=settings.repaired_validation_factor,
            )

        return normalize

    @staticmethod
    def _url() -> SingleNormalizer:
        def normalize(raw_value: str, _: NormalizationContext) -> NormalizationOutcome:
            return contacts.normalize_url(raw_value)

        return normalize

    @staticmethod
    def _city() -> SingleNormalizer:
        def normalize(raw_value: str, _: NormalizationContext) -> NormalizationOutcome:
            return places.normalize_city(raw_value)

        return normalize

    @staticmethod
    def _country(settings: AISettings) -> SingleNormalizer:
        def normalize(raw_value: str, _: NormalizationContext) -> NormalizationOutcome:
            return places.normalize_country(
                raw_value, fuzzy_mapping_factor=settings.fuzzy_mapping_factor
            )

        return normalize

    @staticmethod
    def _date(*, allow_present: bool) -> SingleNormalizer:
        def normalize(raw_value: str, _: NormalizationContext) -> NormalizationOutcome:
            return dates.normalize_date(raw_value, allow_present=allow_present)

        return normalize

    @staticmethod
    def _degree_level() -> SingleNormalizer:
        def normalize(raw_value: str, _: NormalizationContext) -> NormalizationOutcome:
            return vocabularies.normalize_degree_level(raw_value)

        return normalize

    @staticmethod
    def _language_name() -> SingleNormalizer:
        def normalize(raw_value: str, _: NormalizationContext) -> NormalizationOutcome:
            return vocabularies.normalize_language_name(raw_value)

        return normalize

    @staticmethod
    def _language_proficiency() -> SingleNormalizer:
        def normalize(raw_value: str, _: NormalizationContext) -> NormalizationOutcome:
            return vocabularies.normalize_language_proficiency(raw_value)

        return normalize
