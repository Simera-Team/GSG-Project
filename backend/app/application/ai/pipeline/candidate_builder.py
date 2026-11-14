"""Flattens the model's nested answer into one candidate value per field.

The extraction schema is nested because that is the shape a CV has; the output
contract is flat because every single value has to be checkable on its own.
This module is the pure mapping between the two, and the only place that knows
which schema attribute feeds which catalogue field.

Entities are numbered in order of appearance within this source. The number is
local to the source: matching the same job across sources is the merge stage's
job (M-01).
"""

from collections.abc import Iterator

from app.application.ai.schemas.extracted_profile import (
    ExtractedCertification,
    ExtractedEducation,
    ExtractedLanguage,
    ExtractedProfile,
    ExtractedProject,
    ExtractedValue,
    ExtractedWorkExperience,
    PersonalInformation,
)
from app.application.ai.schemas.field_record import (
    PROFILE_ENTITY_KEY,
    CandidateValue,
    EntityType,
    FieldName,
    build_entity_key,
)

#: Which personal-information attribute feeds which profile field.
_PROFILE_FIELDS: tuple[tuple[str, FieldName], ...] = (
    ("first_name", FieldName.FIRST_NAME),
    ("last_name", FieldName.LAST_NAME),
    ("email", FieldName.EMAIL),
    ("phone", FieldName.PHONE),
    ("city", FieldName.CITY),
    ("country", FieldName.COUNTRY),
    ("title", FieldName.TITLE),
    ("summary", FieldName.SUMMARY),
)

_WORK_FIELDS: tuple[tuple[str, FieldName], ...] = (
    ("company", FieldName.COMPANY),
    ("title", FieldName.TITLE),
    ("start_date", FieldName.START_DATE),
    ("end_date", FieldName.END_DATE),
    ("description", FieldName.DESCRIPTION),
)

_EDUCATION_FIELDS: tuple[tuple[str, FieldName], ...] = (
    ("institution", FieldName.INSTITUTION),
    ("degree", FieldName.DEGREE),
    ("field", FieldName.FIELD),
    ("start_date", FieldName.START_DATE),
    ("end_date", FieldName.END_DATE),
)

_CERTIFICATION_FIELDS: tuple[tuple[str, FieldName], ...] = (
    ("name", FieldName.NAME),
    ("issuer", FieldName.ISSUER),
    ("issue_date", FieldName.ISSUE_DATE),
    ("url", FieldName.URL),
)

_PROJECT_FIELDS: tuple[tuple[str, FieldName], ...] = (
    ("name", FieldName.NAME),
    ("description", FieldName.DESCRIPTION),
    ("url", FieldName.URL),
)

_LANGUAGE_FIELDS: tuple[tuple[str, FieldName], ...] = (
    ("name", FieldName.NAME),
    ("proficiency", FieldName.PROFICIENCY),
)


def build_candidates(profile: ExtractedProfile) -> list[CandidateValue]:
    """Return one candidate per value the model reported, in reading order."""
    return list(_iter_candidates(profile))


def _iter_candidates(profile: ExtractedProfile) -> Iterator[CandidateValue]:
    if profile.personal_information:
        yield from _personal_information(profile.personal_information)

    for link in profile.links:
        candidate = _candidate(
            link.url,
            entity=EntityType.PROFILE,
            entity_key=PROFILE_ENTITY_KEY,
            field=FieldName.LINK,
        )
        if candidate:
            yield candidate.model_copy(update={"raw_type": _plain_value(link.type)})

    for index, skill in enumerate(profile.skills, start=1):
        yield from _entity_candidates(
            skill, EntityType.SKILL, index, (("name", FieldName.NAME),)
        )

    for index, job in enumerate(profile.work_experience, start=1):
        yield from _entity_candidates(
            job, EntityType.WORK_EXPERIENCE, index, _WORK_FIELDS
        )

    for index, study in enumerate(profile.education, start=1):
        yield from _entity_candidates(
            study, EntityType.EDUCATION, index, _EDUCATION_FIELDS
        )

    for index, project in enumerate(profile.projects, start=1):
        yield from _entity_candidates(
            project, EntityType.PROJECT, index, _PROJECT_FIELDS
        )
        yield from _project_tech_stack(project, index)

    for index, certification in enumerate(profile.certifications, start=1):
        yield from _entity_candidates(
            certification, EntityType.CERTIFICATION, index, _CERTIFICATION_FIELDS
        )

    for index, language in enumerate(profile.languages, start=1):
        yield from _entity_candidates(
            language, EntityType.LANGUAGE, index, _LANGUAGE_FIELDS
        )


def _personal_information(
    personal_information: PersonalInformation,
) -> Iterator[CandidateValue]:
    for attribute, field in _PROFILE_FIELDS:
        candidate = _candidate(
            getattr(personal_information, attribute),
            entity=EntityType.PROFILE,
            entity_key=PROFILE_ENTITY_KEY,
            field=field,
        )
        if candidate:
            yield candidate


def _entity_candidates(
    entity_data: (
        ExtractedWorkExperience
        | ExtractedEducation
        | ExtractedProject
        | ExtractedCertification
        | ExtractedLanguage
        | object
    ),
    entity: EntityType,
    index: int,
    fields: tuple[tuple[str, FieldName], ...],
) -> Iterator[CandidateValue]:
    entity_key = build_entity_key(entity, index)

    for attribute, field in fields:
        candidate = _candidate(
            getattr(entity_data, attribute, None),
            entity=entity,
            entity_key=entity_key,
            field=field,
        )
        if candidate:
            yield candidate


def _project_tech_stack(
    project: ExtractedProject, index: int
) -> Iterator[CandidateValue]:
    entity_key = build_entity_key(EntityType.PROJECT, index)

    for technology in project.tech_stack:
        candidate = _candidate(
            technology,
            entity=EntityType.PROJECT,
            entity_key=entity_key,
            field=FieldName.TECH_STACK,
        )
        if candidate:
            yield candidate


def _candidate(
    extracted: ExtractedValue | None,
    *,
    entity: EntityType,
    entity_key: str,
    field: FieldName,
) -> CandidateValue | None:
    """Build a candidate, or ``None`` when the source did not state the field.

    An absent field is simply absent (R-05); it is never carried forward as an
    empty string.
    """
    raw_value = _plain_value(extracted)
    if raw_value is None:
        return None

    return CandidateValue(
        entity=entity,
        entity_key=entity_key,
        field=field,
        raw_value=raw_value,
        evidence_snippet=extracted.evidence if extracted else None,
        block_id=extracted.block_id if extracted else None,
    )


def _plain_value(extracted: ExtractedValue | None) -> str | None:
    """Return the model's value as text, or ``None`` when there is nothing to keep."""
    if extracted is None or extracted.value is None:
        return None

    text = str(extracted.value).strip()
    return text or None
