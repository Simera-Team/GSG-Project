"""Deterministic conflict resolution when sources disagree (FR-031 to FR-034).

When a candidate has more than one source, the same field can arrive with
different values: a CV says Amman, a LinkedIn export says Dubai; one says the
job ended in 2022, the other 2024. The requirements give an order for settling
that, and only the last step involves a person:

* ``C-01`` a vetted value beats a self-reported one (FR-032).
* ``C-02`` otherwise the newer source wins, but only for fields whose rule
  allows recency (FR-031). The list of those fields is :data:`FIELD_POLICIES`,
  the "list kept in code configuration" the requirement asks for.
* ``C-03`` still tied: the higher-priority source kind wins, but only for
  fields whose rule allows it. A claim whose truth does not depend on which
  file it arrived in — a degree level — switches this off, so a disagreement
  between two self-reported sources reaches a person instead.
* ``C-04`` the same value at different precision is not a conflict; the more
  precise one is kept.
* ``C-05`` / ``C-06`` nothing decided: keep every value with its source and
  ask a person (FR-033). A personal fact goes to the candidate, a claim about
  their history goes to a reviewer.

Every rule is a fixed code rule with no LLM, no clock and no randomness, so
the same records always give the same answer (FR-034, NFR-023). Each decision
returns the rule that made it, which is stored on the field record so the
choice can be explained later (FR-035, FR-051).
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.domain.entities.field_record import FieldRecord

#: Bumped whenever a row in FIELD_POLICIES changes, so a job processed under
#: the old table stays explainable (NFR-023).
#: 1.1.0 — source priority may now be switched off per field; it is off for
#: ("education", "degree"), which used to be settled by C-03.
POLICY_VERSION = "1.1.0"


class ConflictRule:
    """Identifier of the rule that settled (or failed to settle) a field."""

    VETTED_WINS = "C-01"
    NEWER_WINS = "C-02"
    SOURCE_PRIORITY = "C-03"
    MORE_PRECISE = "C-04"
    ASK_CANDIDATE = "C-05"
    ASK_REVIEWER = "C-06"
    AGREED = "C-00"          # every source said the same thing


class Fallback:
    """Who is asked when no rule decides."""

    CANDIDATE = "candidate"
    REVIEWER = "reviewer"


#: Source kinds in the order they are trusted when recency does not decide.
#: A vetting result is handled by C-01 before this is consulted.
DEFAULT_SOURCE_PRIORITY = ("vetting", "linkedin", "cv")


@dataclass(frozen=True)
class FieldPolicy:
    """How one field behaves when sources disagree.

    ``recency`` and ``priority`` are each a licence for one rung of the ladder
    (C-02 and C-03). Switching one off does not pick a different value — it
    makes that rung decline to decide, so the field falls through to the
    person named by ``fallback``. That is the only safe way to say "no rule we
    have can settle this": never guessing is the point (FR-033).
    """

    recency: bool = True
    #: Whether the more trusted *kind* of source may settle the field (C-03).
    #: Off where the kind of file says nothing about the truth of the claim.
    priority: bool = True
    fallback: str = Fallback.REVIEWER
    source_priority: tuple[str, ...] = DEFAULT_SOURCE_PRIORITY


#: Per-field rules. A field with no row here uses the default: recency, then
#: source priority, then a reviewer. The default never silently picks a value
#: that no rule supports.
#:
#: Keys are (entity_type, field_name) as the field records spell them.
FIELD_POLICIES: dict[tuple[str, str], FieldPolicy] = {
    # A name does not become more true because a file is newer: people keep a
    # stale headline on LinkedIn for years but write their CV deliberately.
    ("personal_info", "first_name"): FieldPolicy(
        recency=False, source_priority=("cv", "linkedin", "vetting")),
    ("personal_info", "last_name"): FieldPolicy(
        recency=False, source_priority=("cv", "linkedin", "vetting")),

    # The headline is the one thing people do keep current on LinkedIn.
    ("personal_info", "title"): FieldPolicy(
        recency=True, source_priority=("linkedin", "cv", "vetting")),
    ("personal_info", "summary"): FieldPolicy(
        recency=True, source_priority=("linkedin", "cv", "vetting")),

    # Only the candidate can settle where they live, so a disagreement is
    # asked of them rather than guessed by a reviewer (FR-044).
    ("personal_info", "city"): FieldPolicy(recency=True, fallback=Fallback.CANDIDATE),
    ("personal_info", "country"): FieldPolicy(recency=True, fallback=Fallback.CANDIDATE),

    # Dates: recency is allowed, and C-04 settles a precision difference
    # before it ever counts as a conflict.
    ("work_experience", "start_date"): FieldPolicy(recency=True),
    ("work_experience", "end_date"): FieldPolicy(recency=True),
    ("education", "start_date"): FieldPolicy(recency=True),
    ("education", "end_date"): FieldPolicy(recency=True),

    # A degree is a claim about the past; a newer file does not make it truer,
    # so an unresolved disagreement goes to a reviewer (FR-033). Neither does
    # the kind of file: a bachelor's in the CV against a master's on LinkedIn
    # is not settled by preferring LinkedIn, because one of the two is simply
    # wrong and only a person can say which. Both rungs are therefore off and
    # the conflict reaches C-06 with both values (M-01 is what brings the two
    # rows together in the first place).
    ("education", "degree"): FieldPolicy(recency=False, priority=False),
    ("education", "field"): FieldPolicy(recency=False),

    # A language level is self-reported until a vetting result says otherwise,
    # which C-01 handles above this table.
    ("languages", "proficiency"): FieldPolicy(recency=False),
}


def policy_for(entity_type: str, field_name: str) -> FieldPolicy:
    """The policy for one field, or the safe default."""
    return FIELD_POLICIES.get((entity_type, field_name), FieldPolicy())


@dataclass
class Resolution:
    """The outcome of applying the rules to one field's competing values."""

    rule: str
    winner: FieldRecord | None = None
    #: Values that were not chosen; kept so the reviewer sees all of them and
    #: so FR-035 can store what was rejected.
    others: list[FieldRecord] = field(default_factory=list)
    #: Who to ask when the rules did not decide. None when they did.
    ask: str | None = None

    @property
    def decided(self) -> bool:
        return self.winner is not None and self.ask is None


def resolve_field(candidates: list[FieldRecord]) -> Resolution:
    """Settle one field's competing values, or say who should be asked.

    ``candidates`` are the accepted records for one entity and field name,
    from one candidate's sources. An empty list or a single value needs no
    rule; identical values agree (C-00).
    """
    usable = [c for c in candidates if c.value is not None]
    if not usable:
        return Resolution(ConflictRule.AGREED)
    if len(usable) == 1:
        return Resolution(ConflictRule.AGREED, usable[0])

    # Values that are equal after normalisation are not a conflict at all.
    if len({_compare_key(c.value) for c in usable}) == 1:
        return Resolution(ConflictRule.AGREED, usable[0], usable[1:])

    policy = policy_for(usable[0].entity_type, usable[0].field_name)

    # C-01: a vetted value beats anything self-reported (FR-032).
    vetted = [c for c in usable if c.source_kind == "vetting"]
    if vetted:
        if len({_compare_key(c.value) for c in vetted}) == 1:
            return Resolution(ConflictRule.VETTED_WINS, vetted[0],
                              [c for c in usable if c is not vetted[0]])
        # Two vetting results disagreeing is not something a rule should pick
        # between; it falls through to the fallback below.
        usable = vetted

    # C-04: the same value at two precisions is a precision difference, not a
    # disagreement, so the more precise one is kept (FR-028 keeps precision).
    precise = _more_precise(usable)
    if precise is not None:
        return Resolution(ConflictRule.MORE_PRECISE, precise,
                          [c for c in usable if c is not precise])

    # C-02: the newer source wins, for fields whose policy allows recency.
    if policy.recency:
        newest = _only_newest(usable)
        if newest is not None:
            return Resolution(ConflictRule.NEWER_WINS, newest,
                              [c for c in usable if c is not newest])

    # C-03: still tied, so the more trusted kind of source wins — where the
    # policy allows it. A vetted value has already won at C-01, so what is
    # left here is one self-reported file against another.
    if policy.priority:
        by_priority = _only_highest_priority(usable, policy.source_priority)
        if by_priority is not None:
            return Resolution(ConflictRule.SOURCE_PRIORITY, by_priority,
                              [c for c in usable if c is not by_priority])

    # C-05 / C-06: no rule decides. Every value is kept with its source and a
    # person is asked; nothing unsupported is ever auto-picked (FR-033).
    rule = (ConflictRule.ASK_CANDIDATE if policy.fallback == Fallback.CANDIDATE
            else ConflictRule.ASK_REVIEWER)
    return Resolution(rule, others=usable, ask=policy.fallback)


def _compare_key(value) -> str:
    """Compare values the way a person would: case and spacing do not matter."""
    if isinstance(value, dict):
        # Normalised dates and countries are dicts; compare their stored value.
        inner = value.get("value") or value.get("code") or value
        return str(inner).strip().casefold()
    return str(value).strip().casefold()


def _more_precise(candidates: list[FieldRecord]) -> FieldRecord | None:
    """The one candidate that is a more precise form of all the others (C-04).

    Only normalised dates carry a precision. "2022-03" against "2022" is the
    same date known to different accuracy, so the month wins without a person
    being asked. Returns None when the values genuinely differ.
    """
    dates = [c for c in candidates
             if isinstance(c.value, dict) and "precision" in c.value]
    if len(dates) != len(candidates):
        return None

    months = [c for c in dates if c.value["precision"] == "month"]
    years = [c for c in dates if c.value["precision"] == "year"]
    if not months or not years:
        return None

    # Every month value must agree, and every year value must be that year.
    if len({c.value["value"] for c in months}) != 1:
        return None
    month_value = months[0].value["value"]
    if any(c.value["value"] != month_value[:4] for c in years):
        return None
    return months[0]


def _only_newest(candidates: list[FieldRecord]) -> FieldRecord | None:
    """The single newest candidate, or None when the newest time is shared."""
    timed = [c for c in candidates if c.source_uploaded_at is not None]
    if len(timed) < len(candidates) or not timed:
        return None
    newest = max(_as_utc(c.source_uploaded_at) for c in timed)
    winners = [c for c in timed if _as_utc(c.source_uploaded_at) == newest]
    return winners[0] if len(winners) == 1 else None


def _only_highest_priority(candidates: list[FieldRecord],
                           priority: tuple[str, ...]) -> FieldRecord | None:
    """The single candidate from the most trusted source kind, or None."""
    ranked = [(priority.index(c.source_kind), c) for c in candidates
              if c.source_kind in priority]
    if len(ranked) < len(candidates) or not ranked:
        return None
    best = min(rank for rank, _ in ranked)
    winners = [c for rank, c in ranked if rank == best]
    return winners[0] if len(winners) == 1 else None


def _as_utc(moment: datetime) -> datetime:
    """Compare times that may or may not carry a timezone."""
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)
