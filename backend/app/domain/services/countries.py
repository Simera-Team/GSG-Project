"""Country matching (FR-070) and city-based inference (N-GEO-02).

A country is matched by name or ISO 3166-1 alpha-2 code. A value that matches
nothing returns None; the caller leaves the country empty in the live profile
and queues the value for review.

Most CVs give a city and no country ("Ramallah", "Amman"), so a country the
profile needs would simply be missing. :data:`CITY_COUNTRIES` lists cities
that identify exactly one country; a city with more than one plausible
country is deliberately absent from it, so nothing is ever inferred from an
ambiguous name. The inference is recorded with its own rule so it is never
mistaken for a country the source actually stated (FR-035).
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


class GeoRule:
    """Identifier stored on the field record for the rule that set a country."""

    COUNTRY_LIST = "N-GEO-01"          # matched the country list by name or code
    INFERRED_FROM_CITY = "N-GEO-02"    # no country stated; read from the city


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

    def by_code(self, code: str | None) -> Country | None:
        """The country with this ISO 3166-1 alpha-2 code, or None."""
        if not code:
            return None
        return self._by_code.get(code.upper())

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


#: Cities that identify exactly one country (N-GEO-02). A city with more than
#: one match is deliberately absent, so no country is inferred from it.
CITY_COUNTRIES: dict[str, str] = {
    "ramallah": "PS",
    "nablus": "PS",
    "hebron": "PS",
    "bethlehem": "PS",
    "jenin": "PS",
    "tulkarm": "PS",
    "gaza city": "PS",
    "khan younis": "PS",
    "rafah": "PS",
    "amman": "JO",
    "irbid": "JO",
    "zarqa": "JO",
    "aqaba": "JO",
    "cairo": "EG",
    "alexandria": "EG",
    "giza": "EG",
    "riyadh": "SA",
    "jeddah": "SA",
    "dammam": "SA",
    "mecca": "SA",
    "medina": "SA",
    "dubai": "AE",
    "abu dhabi": "AE",
    "sharjah": "AE",
    "doha": "QA",
    "kuwait city": "KW",
    "manama": "BH",
    "muscat": "OM",
    "beirut": "LB",
    "damascus": "SY",
    "baghdad": "IQ",
    "erbil": "IQ",
    "istanbul": "TR",
    "ankara": "TR",
    "izmir": "TR",
    "berlin": "DE",
    "munich": "DE",
    "hamburg": "DE",
    "frankfurt": "DE",
    "paris": "FR",
    "lyon": "FR",
    "madrid": "ES",
    "barcelona": "ES",
    "rome": "IT",
    "milan": "IT",
    "amsterdam": "NL",
    "rotterdam": "NL",
    "brussels": "BE",
    "stockholm": "SE",
    "oslo": "NO",
    "copenhagen": "DK",
    "helsinki": "FI",
    "dublin": "IE",
    "warsaw": "PL",
    "lisbon": "PT",
    "zurich": "CH",
    "geneva": "CH",
    "vienna": "AT",
    "toronto": "CA",
    "vancouver": "CA",
    "montreal": "CA",
    "sydney": "AU",
    "melbourne": "AU",
    "auckland": "NZ",
    "mumbai": "IN",
    "bangalore": "IN",
    "bengaluru": "IN",
    "delhi": "IN",
    "new delhi": "IN",
    "hyderabad": "IN",
    "karachi": "PK",
    "lahore": "PK",
    "islamabad": "PK",
    "dhaka": "BD",
    "jakarta": "ID",
    "kuala lumpur": "MY",
    "manila": "PH",
    "beijing": "CN",
    "shanghai": "CN",
    "tokyo": "JP",
    "osaka": "JP",
    "seoul": "KR",
    "sao paulo": "BR",
    "rio de janeiro": "BR",
    "buenos aires": "AR",
    "mexico city": "MX",
    "santiago": "CL",
    "cape town": "ZA",
    "johannesburg": "ZA",
    "lagos": "NG",
    "nairobi": "KE",
    "casablanca": "MA",
    "rabat": "MA",
    "tunis": "TN",
    "algiers": "DZ",
    "khartoum": "SD",
    "sanaa": "YE",
    "london": "GB",
    "manchester": "GB",
    "birmingham": "GB",
    "edinburgh": "GB",
    "glasgow": "GB",
    "new york": "US",
    "san francisco": "US",
    "seattle": "US",
    "boston": "US",
    "chicago": "US",
    "austin": "US",
    "los angeles": "US",}

#: International dialling prefixes, used by
#: :func:`app.domain.services.contacts.normalize_phone` to put a local number
#: into E.164 form (N-PHONE-01).
DIAL_CODES: dict[str, str] = {
    "PS": "970",
    "JO": "962",
    "EG": "20",
    "SA": "966",
    "AE": "971",
    "QA": "974",
    "KW": "965",
    "BH": "973",
    "OM": "968",
    "LB": "961",
    "SY": "963",
    "IQ": "964",
    "TR": "90",
    "US": "1",
    "CA": "1",
    "GB": "44",
    "DE": "49",
    "FR": "33",
    "ES": "34",
    "IT": "39",
    "NL": "31",
    "BE": "32",
    "SE": "46",
    "NO": "47",
    "DK": "45",
    "FI": "358",
    "IE": "353",
    "PL": "48",
    "RO": "40",
    "PT": "351",
    "CH": "41",
    "AT": "43",
    "AU": "61",
    "NZ": "64",
    "IN": "91",
    "PK": "92",
    "BD": "880",
    "ID": "62",
    "MY": "60",
    "SG": "65",
    "PH": "63",
    "CN": "86",
    "JP": "81",
    "KR": "82",
    "BR": "55",
    "AR": "54",
    "MX": "52",
    "CL": "56",
    "ZA": "27",
    "NG": "234",
    "KE": "254",
    "MA": "212",
    "TN": "216",
    "DZ": "213",
    "LY": "218",
    "SD": "249",
    "YE": "967",}


def infer_country_code_from_city(city: str | None) -> str | None:
    """Return the ISO code of the one country ``city`` identifies, or None.

    Only an exact match on the cleaned name counts: guessing a country from a
    near-miss city would put a wrong country on a profile, and a missing
    country is the safer of the two.
    """
    if not city or not city.strip():
        return None
    return CITY_COUNTRIES.get(_key(city))
