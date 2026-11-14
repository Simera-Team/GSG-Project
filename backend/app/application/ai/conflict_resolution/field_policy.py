"""The field policy table: which rules decide each field, and in what order.

Each field has a fixed order of conflict rules; the first rule that decides
wins. Only a field with a reviewer or candidate fallback can ever reach a
person, so the table is also the complete list of what a human can be asked
about.

The table lives in code and is versioned with the rules: changing a row changes
:data:`POLICY_VERSION`, which every later job records. Moving it to a
configuration file is a later step and needs no change above this module, since
callers only ever ask :func:`policy_for`.
"""

from typing import Final

from pydantic import ConfigDict

from app.application.ai.rules import RuleId
from app.application.ai.schemas.base import AIBaseSchema
from app.application.ai.schemas.document_text import SourceKind
from app.application.ai.schemas.field_record import EntityType, FieldName
from app.application.ai.schemas.merge import ConflictFallback, FieldKind

#: Bumped whenever a row below changes, so an old job stays explainable.
POLICY_VERSION: Final[str] = "0.1.0"


class FieldPolicy(AIBaseSchema):
    """How one field behaves when sources disagree."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: FieldKind
    rules: tuple[RuleId, ...] = ()
    fallback: ConflictFallback = ConflictFallback.NONE
    source_priority: tuple[SourceKind, ...] = ()


_SINGLE_NEWER = FieldPolicy(kind=FieldKind.SINGLE, rules=(RuleId.C_02,))

#: Union rules never conflict, so they need no fallback.
_LIST_UNION = FieldPolicy(kind=FieldKind.LIST, rules=(RuleId.M_02,))
_LIST_CONTACT = FieldPolicy(kind=FieldKind.LIST, rules=(RuleId.M_03,))

_DEFAULT_SINGLE = FieldPolicy(
    kind=FieldKind.SINGLE,
    rules=(RuleId.C_02, RuleId.C_03),
    fallback=ConflictFallback.REVIEWER,
    source_priority=(SourceKind.LINKEDIN, SourceKind.CV),
)

FIELD_POLICIES: Final[dict[tuple[EntityType, FieldName], FieldPolicy]] = {
    # --- profile ---------------------------------------------------------
    # A person's name comes from their CV first; LinkedIn headlines are often
    # stale, so for the name the CV is the better source.
    (EntityType.PROFILE, FieldName.FIRST_NAME): FieldPolicy(
        kind=FieldKind.SINGLE,
        rules=(RuleId.C_03,),
        source_priority=(SourceKind.CV, SourceKind.LINKEDIN),
    ),
    (EntityType.PROFILE, FieldName.LAST_NAME): FieldPolicy(
        kind=FieldKind.SINGLE,
        rules=(RuleId.C_03,),
        source_priority=(SourceKind.CV, SourceKind.LINKEDIN),
    ),
    # The headline is the one thing people keep current on LinkedIn.
    (EntityType.PROFILE, FieldName.TITLE): FieldPolicy(
        kind=FieldKind.SINGLE,
        rules=(RuleId.C_02, RuleId.C_03),
        source_priority=(SourceKind.LINKEDIN, SourceKind.CV),
    ),
    (EntityType.PROFILE, FieldName.SUMMARY): FieldPolicy(
        kind=FieldKind.SINGLE,
        rules=(RuleId.C_03,),
        source_priority=(SourceKind.LINKEDIN, SourceKind.CV),
    ),
    # Only the candidate can settle where they live.
    (EntityType.PROFILE, FieldName.CITY): FieldPolicy(
        kind=FieldKind.SINGLE,
        rules=(RuleId.C_02,),
        fallback=ConflictFallback.CANDIDATE,
    ),
    (EntityType.PROFILE, FieldName.COUNTRY): FieldPolicy(
        kind=FieldKind.SINGLE,
        rules=(RuleId.C_02,),
        fallback=ConflictFallback.CANDIDATE,
    ),
    (EntityType.PROFILE, FieldName.EMAIL): _LIST_CONTACT,
    (EntityType.PROFILE, FieldName.PHONE): _LIST_CONTACT,
    (EntityType.PROFILE, FieldName.LINK): _LIST_CONTACT,
    # --- work_experience -------------------------------------------------
    # The company name decides entity matching (M-01), so variants are separate
    # entities and never conflict within one.
    (EntityType.WORK_EXPERIENCE, FieldName.COMPANY): FieldPolicy(
        kind=FieldKind.SINGLE, rules=(RuleId.M_01,)
    ),
    (EntityType.WORK_EXPERIENCE, FieldName.TITLE): FieldPolicy(
        kind=FieldKind.SINGLE,
        rules=(RuleId.C_02, RuleId.C_03),
        source_priority=(SourceKind.LINKEDIN, SourceKind.CV),
    ),
    (EntityType.WORK_EXPERIENCE, FieldName.START_DATE): FieldPolicy(
        kind=FieldKind.SINGLE,
        rules=(RuleId.C_04, RuleId.C_02),
        fallback=ConflictFallback.REVIEWER,
    ),
    (EntityType.WORK_EXPERIENCE, FieldName.END_DATE): FieldPolicy(
        kind=FieldKind.SINGLE,
        rules=(RuleId.C_04, RuleId.C_02),
        fallback=ConflictFallback.REVIEWER,
    ),
    (EntityType.WORK_EXPERIENCE, FieldName.DESCRIPTION): _SINGLE_NEWER,
    # --- education -------------------------------------------------------
    (EntityType.EDUCATION, FieldName.INSTITUTION): FieldPolicy(
        kind=FieldKind.SINGLE, rules=(RuleId.M_01, RuleId.C_02)
    ),
    # A degree level is a claim, so an unresolved one goes to a reviewer (C-06)
    # rather than back to the candidate who made it.
    (EntityType.EDUCATION, FieldName.DEGREE): FieldPolicy(
        kind=FieldKind.SINGLE,
        rules=(RuleId.C_02,),
        fallback=ConflictFallback.REVIEWER,
    ),
    (EntityType.EDUCATION, FieldName.FIELD): _SINGLE_NEWER,
    (EntityType.EDUCATION, FieldName.START_DATE): FieldPolicy(
        kind=FieldKind.SINGLE,
        rules=(RuleId.C_04, RuleId.C_02),
        fallback=ConflictFallback.REVIEWER,
    ),
    (EntityType.EDUCATION, FieldName.END_DATE): FieldPolicy(
        kind=FieldKind.SINGLE,
        rules=(RuleId.C_04, RuleId.C_02),
        fallback=ConflictFallback.REVIEWER,
    ),
    # --- skill, language -------------------------------------------------
    (EntityType.SKILL, FieldName.NAME): _LIST_UNION,
    (EntityType.LANGUAGE, FieldName.NAME): _LIST_UNION,
    # Vetting beats anything the candidate claims about their own level.
    (EntityType.LANGUAGE, FieldName.PROFICIENCY): FieldPolicy(
        kind=FieldKind.SINGLE,
        rules=(RuleId.C_01, RuleId.C_02),
        fallback=ConflictFallback.REVIEWER,
    ),
    # --- certification, project ------------------------------------------
    (EntityType.CERTIFICATION, FieldName.NAME): FieldPolicy(
        kind=FieldKind.SINGLE, rules=(RuleId.M_01,)
    ),
    (EntityType.CERTIFICATION, FieldName.ISSUER): FieldPolicy(
        kind=FieldKind.SINGLE, rules=(RuleId.M_01,)
    ),
    (EntityType.CERTIFICATION, FieldName.ISSUE_DATE): FieldPolicy(
        kind=FieldKind.SINGLE, rules=(RuleId.C_04, RuleId.C_02)
    ),
    (EntityType.CERTIFICATION, FieldName.URL): _SINGLE_NEWER,
    (EntityType.PROJECT, FieldName.NAME): FieldPolicy(
        kind=FieldKind.SINGLE, rules=(RuleId.M_01,)
    ),
    (EntityType.PROJECT, FieldName.DESCRIPTION): _SINGLE_NEWER,
    (EntityType.PROJECT, FieldName.URL): _SINGLE_NEWER,
    (EntityType.PROJECT, FieldName.TECH_STACK): _LIST_UNION,
}


def policy_for(entity: EntityType, field: FieldName) -> FieldPolicy:
    """Return the policy for one field.

    A field with no row falls back to recency then source priority with a
    reviewer as the last resort, which is the safe default: it never silently
    picks a value when the rules do not decide.
    """
    return FIELD_POLICIES.get((entity, field), _DEFAULT_SINGLE)
