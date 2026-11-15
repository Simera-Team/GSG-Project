"""Country matching (FR-070): by name or ISO 3166-1 alpha-2 code.

A value that matches nothing returns None; the caller leaves the country
empty in the live profile and queues the value for review.
"""

import re
from dataclasses import dataclass

# Common ways CVs write a country that differ from the official list name.
DEFAULT_COUNTRY_ALIASES: dict[str, str] = {
    "uk": "GB", "u k": "GB", "great britain": "GB", "britain": "GB",
    "england": "GB", "scotland": "GB", "wales": "GB", "northern ireland": "GB",
    "usa": "US", "u s a": "US", "u s": "US", "united states of america": "US", "america": "US",
    "uae": "AE", "u a e": "AE", "emirates": "AE",
    "ksa": "SA", "kingdom of saudi arabia": "SA",
    "state of palestine": "PS", "palestinian territories": "PS",
    "palestinian authority": "PS",   # LinkedIn's location label for Palestine
    "hashemite kingdom of jordan": "JO",
}


@dataclass(frozen=True)
class Country:
    name: str
    code: str

    def to_dict(self) -> dict:
        return {"name": self.name, "code": self.code}


class CountryCatalog:

    def __init__(self, countries: list[tuple[str, str]],
                 aliases: dict[str, str] | None = None):
        self._by_code = {code.upper(): Country(name, code.upper()) for name, code in countries}
        self._by_name = {_key(c.name): c for c in self._by_code.values()}
        for alias, code in (aliases if aliases is not None else DEFAULT_COUNTRY_ALIASES).items():
            if code.upper() in self._by_code:
                self._by_name.setdefault(_key(alias), self._by_code[code.upper()])

    def match(self, text: str | None) -> Country | None:
        if not text:
            return None
        key = _key(text)
        if len(key) == 2 and key.upper() in self._by_code:
            return self._by_code[key.upper()]
        return self._by_name.get(key)


def _key(text: str) -> str:
    text = re.sub(r"[^\w\s]", " ", text.casefold())
    return re.sub(r"\s+", " ", text).strip()
