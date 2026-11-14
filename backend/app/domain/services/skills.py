"""Skill name standardisation (FR-029), merging (FR-030) and review hints (FR-062).

Every name is reduced to a *match key* before lookup, so spelling variants
of the same skill meet without needing an alias each:

    "Node.js", "node js", "NodeJS", "NODE.JS"      -> "nodejs"
    "Pandas (Software)", "Microsoft Access (Basic)" -> qualifier dropped
    "Critical Thinking · 1 endorsements"           -> endorsement count dropped
    "Python 3", "Angular 15"                       -> version dropped
    "Problem-Solving", "problem solving"           -> "problemsolving"
    "Communication skills", "Leadership abilities" -> "skills"/"abilities" dropped
    "C", "C#", "C++"                               -> stay different

Real synonyms ("Postgres" -> "PostgreSQL", "MS Excel" -> "Microsoft Excel")
come from the alias table. Lookup is exact on the match key: deterministic,
no fuzzy guessing (FR-034). A skill matching nothing returns None and goes to
review (FR-062); `suggest()` offers the reviewer the closest standard skill,
but never applies it on its own.
"""

import re
import unicodedata
from collections.abc import Iterable
from difflib import get_close_matches

_ENDORSEMENTS = re.compile(r"\s*[·•|-]?\s*\d+\s+endorsements?\s*$", re.IGNORECASE)
_QUALIFIER = re.compile(r"\s*\([^)]*\)\s*$")                       # "(Software)", "(Basic)"
_LEVEL = re.compile(r"\s*[-–:,]\s*(beginner|basic|elementary|intermediate|advanced|"
                    r"expert|proficient|fluent|native)\s*$", re.IGNORECASE)
_VERSION = re.compile(r"(?<=[a-z])\s+v?\d+(\.\d+)*$")              # "python 3", "angular 15"
_SKILLS_WORD = re.compile(r"(?<=\w)\s+(skills?|abilities|ability)$")  # "communication skills"
_SEPARATORS = re.compile(r"[\s.\-_/]+")                            # keeps "+" and "#"

# One CV entry can name two skills ("React/Redux", "HTML & CSS"). Split on
# these, but only after the whole entry failed to match a standard skill, so
# "CI/CD" and "R&D" are never torn in half (N-SKILL-02).
_COMBINED_ENTRY = re.compile(r"\s*[/&]\s*|\s+and\s+", re.IGNORECASE)

class SkillRule:
    """Identifier stored on the field record for the rule that set the skill."""

    STANDARD = "N-SKILL-01"      # matched the standard list on its match key
    SPLIT = "N-SKILL-02"         # one entry named two skills
    FUZZY = "N-SKILL-03"         # matched an alias within the allowed edit distance
    UNKNOWN = "R-09"             # matched nothing; a person decides


#: Shortest match key that may be fuzzy-matched. Under five characters almost
#: every name is one edit from another one ("Go" / "God", "C#" / "C").
FUZZY_MIN_LENGTH = 5

#: Confidence factor applied to a value reached by a fuzzy match, so a
#: corrected spelling is never as certain as an exact one (N-SKILL-03).
FUZZY_MAPPING_FACTOR = 0.85


SUGGEST_CUTOFF = 0.8
MIN_CONTAINED_KEY = 5   # "leadership" inside "teamleadership" -> suggest Leadership


def skill_match_key(name: str) -> str:
    """The form two names must share to be the same skill."""
    text = unicodedata.normalize("NFKC", name).strip()
    text = _ENDORSEMENTS.sub("", text)
    while _QUALIFIER.search(text) and _QUALIFIER.sub("", text).strip():
        text = _QUALIFIER.sub("", text)
    text = _LEVEL.sub("", text).casefold().strip()
    text = _VERSION.sub("", text)
    text = _SKILLS_WORD.sub("", text)
    text = text.replace("&", "and")
    return _SEPARATORS.sub("", text)


def clean_skill_name(name: str) -> str:
    """Display form for a new standard skill: same words, minus endorsement
    counts, trailing qualifiers and levels ("Nagra (Basic)" -> "Nagra")."""
    text = unicodedata.normalize("NFKC", name).strip()
    text = _ENDORSEMENTS.sub("", text)
    while _QUALIFIER.search(text) and _QUALIFIER.sub("", text).strip():
        text = _QUALIFIER.sub("", text)
    text = _LEVEL.sub("", text)
    return re.sub(r"\s+", " ", text).strip()


class SkillCatalog:

    def __init__(self, canonical_names: Iterable[str], aliases: dict[str, str]):
        """aliases: alias -> standard name, e.g. {"postgres": "PostgreSQL"}."""
        self._lookup: dict[str, str] = {}
        self._canonical: dict[str, str] = {}
        for name in canonical_names:
            key = skill_match_key(name)
            if key in self._canonical and self._canonical[key] != name:
                raise ValueError(f"Skills '{self._canonical[key]}' and '{name}' have the same "
                                 f"match key '{key}'; keep one and make the other an alias")
            self._canonical[key] = name
        self._lookup.update(self._canonical)
        for alias, name in aliases.items():
            target = self._canonical.get(skill_match_key(name))
            if target is None:
                raise ValueError(f"Alias '{alias}' points to unknown skill '{name}'")
            self._lookup.setdefault(skill_match_key(alias), target)

    def lookup(self, name: str | None) -> str | None:
        """Standard name for `name`, or None if it is not a known skill."""
        if not name or not name.strip():
            return None
        return self._lookup.get(skill_match_key(name))

    def split_entry(self, name: str | None) -> list[str]:
        """Split one CV entry into the skills it names (N-SKILL-02).

        "React/Redux" is two skills, "CI/CD" is one. The whole entry is looked
        up first, so a standard name containing a separator is never split.
        Splitting only happens when every part is itself a known skill:
        otherwise the entry is left whole and goes to review as written, so a
        reviewer sees what the CV actually said (FR-062).
        """
        if not name or not name.strip():
            return []

        text = name.strip()
        if self.lookup(text):
            return [text]

        parts = [p.strip() for p in _COMBINED_ENTRY.split(text) if p.strip()]
        if len(parts) < 2:
            return [text]
        if all(self.lookup(p) for p in parts):
            return parts
        return [text]

    def resolve_fuzzy(self, name: str | None) -> str | None:
        """Standard name for a near-miss spelling, or None (N-SKILL-03).

        One edit is allowed for a match key of 5 to 8 characters and two from
        9 upwards; shorter keys are never fuzzy-matched. A misspelt known
        skill is not an unknown skill, so "Postgress" becomes PostgreSQL
        rather than going to a reviewer (FR-062).

        Still deterministic (FR-034): the distance rule is fixed, and when two
        different standard names tie at the best distance nothing is chosen,
        because picking one of them would be arbitrary.
        """
        if not name or not name.strip():
            return None

        key = skill_match_key(name)
        if len(key) < FUZZY_MIN_LENGTH:
            return None

        max_distance = 1 if len(key) <= 8 else 2
        best_distance, winners = max_distance + 1, set()

        for alias, canonical in self._lookup.items():
            distance = bounded_edit_distance(key, alias, max_distance)
            if distance is None or distance == 0:
                continue
            if distance < best_distance:
                best_distance, winners = distance, {canonical}
            elif distance == best_distance:
                winners.add(canonical)

        return winners.pop() if len(winners) == 1 else None

    def suggest(self, name: str | None) -> str | None:
        """Closest standard skill for an unknown name - a hint for the reviewer only."""
        if not name:
            return None
        key = skill_match_key(name)
        if not key:
            return None
        close = get_close_matches(key, list(self._lookup), n=1, cutoff=SUGGEST_CUTOFF)
        if close:
            return self._lookup[close[0]]
        contained = [k for k in self._canonical if len(k) >= MIN_CONTAINED_KEY and k in key]
        if contained:
            return self._canonical[max(contained, key=len)]
        return None


def union_skills(skill_lists: Iterable[Iterable[str]]) -> list[str]:
    """{React, Node} + {React, Node, Docker} = {React, Node, Docker} (FR-030).

    Keeps first-seen order; names with the same match key count once.
    """
    seen: dict[str, str] = {}
    for skills in skill_lists:
        for skill in skills:
            seen.setdefault(skill_match_key(skill), skill)
    return list(seen.values())


def bounded_edit_distance(left: str, right: str, max_distance: int) -> int | None:
    """The edit distance between two strings, or None once it exceeds the bound.

    Swapping two adjacent characters counts as one edit, not two, because that
    is how typing errors actually happen: "Pyhton" is one slip from "Python",
    and allowing a single edit for a short name only works if it is counted
    that way.

    Giving up early keeps lookups cheap: the rules never ask beyond distance 2.
    """
    if abs(len(left) - len(right)) > max_distance:
        return None
    if left == right:
        return 0

    before_previous: list[int] = []
    previous = list(range(len(right) + 1))

    for i, left_char in enumerate(left, start=1):
        current = [i] + [0] * len(right)
        for j, right_char in enumerate(right, start=1):
            cost = 0 if left_char == right_char else 1
            current[j] = min(previous[j] + 1,
                             current[j - 1] + 1,
                             previous[j - 1] + cost)
            if (i > 1 and j > 1
                    and left_char == right[j - 2] and left[i - 2] == right_char):
                current[j] = min(current[j], before_previous[j - 2] + 1)

        if min(current) > max_distance:
            return None
        before_previous, previous = previous, current

    distance = previous[-1]
    return distance if distance <= max_distance else None
