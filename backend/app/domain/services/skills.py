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
