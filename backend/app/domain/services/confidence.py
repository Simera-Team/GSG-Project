"""The confidence score: a product of four factors the code can verify.

A field's confidence used to be the number the language model reported about
its own answer, nudged by two factors. That number is not evidence of
anything: a model that invents a company name reports the same 0.95 it reports
for a name copied from the page. So confidence is now computed here, from
checks that can be re-run and argued with, and the model's own number is kept
only as ``model_confidence`` for comparison — it never enters the formula and
never decides anything.

    confidence = base x evidence x validation x mapping

rounded to two decimals, then compared with the review limit
(:data:`DEFAULT_REVIEW_CONFIDENCE`, which an administrator can change per
FR-046/FR-067). Each factor answers one question:

* ``base`` — how readable was the text this value was read from? A text layer
  is taken at face value; a scanned page is worth what the OCR engine thought
  of it.
* ``evidence`` — how well did the quoted snippet match the source text?
  :data:`EVIDENCE_FACTORS` prices an exact quote, a near quote and a weak one.
  Below :data:`EVIDENCE_WEAK_SIMILARITY` the snippet is not really in the
  document, so the value is rejected outright (``R-03``) rather than priced.
* ``validation`` — did the value pass its format check as written, or only
  after a repair? A repair is a judgement the code made on the source's
  behalf, so it costs something (:data:`REPAIR_RULES`).
* ``mapping`` — did the value match a reference table exactly, or did it have
  to be matched fuzzily (:data:`MAPPING_RULES`)?

Because the four parts are stored on the record, every confidence in the
system can be explained by reading them back: 0.68 is "a 0.80 scan quoted
almost exactly", not an opinion.

One thing raises a score rather than lowering it. When two *different* sources
state the same value, that agreement is evidence in itself, so the value gets
:data:`AGREEMENT_BOOST` once (``M-04``) — see :func:`apply_agreement_boost`.

No LLM, no clock, no randomness: the same checks always give the same score
(FR-034, NFR-023).
"""

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, replace

from app.domain.entities.field_record import DECISION_RULE, FieldRecord, ReviewReason
from app.domain.services.contacts import ContactRule
from app.domain.services.countries import GeoRule
from app.domain.services.dates import DateRule
from app.domain.services.skills import SkillRule

#: FR-046: fields scoring below this go to a person. An administrator can
#: change the limit in force (FR-067); this is what applies when nothing is
#: stored, and it is the one place the number is written down.
DEFAULT_REVIEW_CONFIDENCE = 0.65


class ConfidenceRule:
    """Identifiers the confidence model cites on a record or a rejection."""

    #: The snippet was not in the source text, or did not support the value.
    #: The value is dropped, not queued: see :func:`grade_evidence`.
    EVIDENCE_REJECTED = "R-03"
    #: Two different sources stated the same value.
    AGREEMENT = "M-04"


class EvidenceGrade:
    """How well a value's snippet matched the source text."""

    VERIFIED = "verified"              # the snippet is in the text
    VERIFIED_FUZZY = "verified_fuzzy"  # near miss: OCR noise, a stray space
    VERIFIED_WEAK = "verified_weak"    # recognisably the same span, but worn
    NOT_REQUIRED = "not_required"      # nothing to quote (a null, or vetting)
    MISSING = "missing"                # no snippet was given
    NOT_FOUND = "not_found"            # the snippet is not in the document


#: Similarity at or above which a snippet counts as a near quote.
EVIDENCE_FUZZY_SIMILARITY = 0.90

#: Similarity at or above which a snippet is still recognisably the same span.
#: Below this the snippet is not in the document and the value is rejected.
EVIDENCE_WEAK_SIMILARITY = 0.75

#: What each grade of match is worth.
EVIDENCE_FACTORS: dict[str, float] = {
    EvidenceGrade.VERIFIED: 1.00,
    EvidenceGrade.VERIFIED_FUZZY: 0.85,
    EvidenceGrade.VERIFIED_WEAK: 0.60,
    EvidenceGrade.NOT_REQUIRED: 1.00,
}

#: A value that only passed its format check after a repair is less certain
#: than one that passed as written.
REPAIRED_VALIDATION_FACTOR = 0.80

#: Repairs that cost :data:`REPAIRED_VALIDATION_FACTOR`. Each is a decision the
#: code made because the source was unclear, not because the source said so.
REPAIR_RULES = frozenset({
    DateRule.AMBIGUOUS_ORDER,   # N-DATE-03: either part could be the month
    DateRule.SWAPPED,           # N-DATE-05: start and end the wrong way round
    ContactRule.PHONE,          # N-PHONE-01: only when a country was borrowed
})

#: A value reached through a fuzzy table match is less certain than an exact
#: one, however right it looks.
FUZZY_MAPPING_FACTOR = 0.85

#: Matches that cost :data:`FUZZY_MAPPING_FACTOR`.
MAPPING_RULES = frozenset({
    SkillRule.FUZZY,              # N-SKILL-03: a corrected spelling
    GeoRule.INFERRED_FROM_CITY,   # N-GEO-02: a country read from a city
})

#: Added once to a value two different sources state (M-04).
AGREEMENT_BOOST = 0.05


@dataclass(frozen=True)
class ConfidenceParts:
    """The factors whose product is a field's confidence, stored with it.

    Defaults are the neutral case — a clean text layer, an exact quote, no
    repair, an exact table match — so a record that needed nothing scores 1.00
    and says so.
    """

    base: float = 1.0
    evidence: float = 1.0
    validation: float = 1.0
    mapping: float = 1.0
    #: What the agreement of other sources added to this record's own product
    #: (M-04). Added, not multiplied, so ``product + agreement`` is always the
    #: stored confidence. Zero unless two different sources agreed.
    agreement: float = 0.0

    @property
    def product(self) -> float:
        """base x evidence x validation x mapping, rounded to two decimals."""
        return round(self.base * self.evidence * self.validation * self.mapping, 2)

    @property
    def confidence(self) -> float:
        """The stored confidence: the product, plus any agreement, capped at 1."""
        return round(min(1.0, self.product + self.agreement), 2)

    def to_dict(self) -> dict:
        """The four parts, plus ``agreement`` only when one was given.

        A reader can multiply what is here and get the stored confidence back,
        which is the whole point of keeping the parts.
        """
        parts = {"base": self.base, "evidence": self.evidence,
                 "validation": self.validation, "mapping": self.mapping}
        if self.agreement:
            parts["agreement"] = self.agreement
        return parts


def evidence_factor(grade: str) -> float:
    """What a match of this grade is worth, or 0 for a grade that is rejected."""
    return EVIDENCE_FACTORS.get(grade, 0.0)


def grade_evidence(similarity: float) -> str | None:
    """The grade a snippet of this similarity earns, or ``None`` to reject it.

    ``None`` means less than :data:`EVIDENCE_WEAK_SIMILARITY` of the snippet is
    in the source text, so the value was rewritten or invented: it is rejected
    under ``R-03`` rather than scored low, because a score cannot express
    "this is not in the document" (NFR-028).
    """
    if similarity >= 1.0:
        return EvidenceGrade.VERIFIED
    if similarity >= EVIDENCE_FUZZY_SIMILARITY:
        return EvidenceGrade.VERIFIED_FUZZY
    if similarity >= EVIDENCE_WEAK_SIMILARITY:
        return EvidenceGrade.VERIFIED_WEAK
    return None


def validation_factor(repaired: bool) -> float:
    return REPAIRED_VALIDATION_FACTOR if repaired else 1.0


def mapping_factor(fuzzy: bool) -> float:
    return FUZZY_MAPPING_FACTOR if fuzzy else 1.0


def page_base_factor(page_confidence: float | None) -> float:
    """What the text on a page is worth: a text layer 1.00, a scan its score.

    ``None`` means the page was read from a text layer, which is taken at face
    value — there is no recognition step to doubt.
    """
    if page_confidence is None:
        return 1.0
    return round(max(0.0, min(1.0, page_confidence)), 4)


def apply_agreement_boost(
    records: Iterable[FieldRecord],
    threshold: float = DEFAULT_REVIEW_CONFIDENCE,
) -> list[FieldRecord]:
    """Raise the confidence of values that two different sources state (M-04).

    A second file saying the same thing is evidence the first file did not
    have, so the value is worth more than either reading of it alone: the
    highest confidence among the agreeing records plus
    :data:`AGREEMENT_BOOST`, capped at 1.00, added **once** however many
    sources agree.

    The agreement belongs to the *value*, not to one reading of it, so every
    record in the group carries that score — whichever of them the conflict
    rules later pick as the profile value, the profile value is the one two
    sources confirmed. Each record stores what the agreement added to its own
    product as ``confidence_parts.agreement``, so the stored number is still
    the sum of what is written down next to it.

    Two mentions inside one source are not agreement — a CV repeating itself
    confirms nothing — so the boost counts distinct sources, not records.

    A record held back **only** for low confidence is reconsidered here, which
    is the point of doing this before the profile is built: two scans of the
    same CV at 0.62 each reach 0.67 together and are accepted, where either
    one alone would have gone to a person. A record held back for any other
    reason (an unknown skill, an unreadable date) keeps its reason: agreement
    about what the page says is not agreement that the value is usable.

    Returns the records it changed, for callers that want to report on them.
    """
    groups: dict[tuple[str, str, str], list[FieldRecord]] = defaultdict(list)
    for record in records:
        # A reviewer's decision is not a source agreeing, and a null value is
        # not a value two sources could agree on.
        if record.value is None or record.rule == DECISION_RULE:
            continue
        groups[(record.entity_type, record.field_name,
                _agreement_key(record.value))].append(record)

    boosted: list[FieldRecord] = []
    for group in groups.values():
        if len({record.source for record in group}) < 2:
            continue

        highest = max(record.confidence for record in group)
        together = round(min(1.0, highest + AGREEMENT_BOOST), 2)

        for record in group:
            record.confidence = together
            if record.confidence_parts is not None:
                record.confidence_parts = replace(
                    record.confidence_parts,
                    agreement=round(together - record.confidence_parts.product, 2),
                )
            if record.review_reasons == [ReviewReason.LOW_CONFIDENCE] and \
                    together >= threshold:
                record.review_reasons = []
            boosted.append(record)

    return boosted


def _agreement_key(value) -> str:
    """Compare values the way C-00 does: case and spacing are not differences."""
    if isinstance(value, dict):
        inner = value.get("value") or value.get("code") or value
        return str(inner).strip().casefold()
    return str(value).strip().casefold()
