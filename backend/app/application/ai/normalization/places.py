"""Country normalization and the country reference data (N-GEO-01 to N-GEO-03).

Countries are stored as ISO 3166-1 alpha-2 codes so that every spelling of the
same country compares as equal. The interface shows the full English name
instead; candidates and clients never see the codes.

The tables below are a seed, large enough for the sample CVs. An unknown
country becomes a system decision (R-09), and an approved mapping is added to
the shared table, so the same spelling never reaches review twice.
"""

from typing import Final

from app.application.ai.rules import RuleId
from app.application.ai.schemas.normalization import NormalizationOutcome
from app.application.ai.text_matching import bounded_edit_distance, canonical_text

#: English names and common aliases to ISO 3166-1 alpha-2.
COUNTRY_ALIASES: Final[dict[str, str]] = {
    "palestine": "PS",
    "palestinian territories": "PS",
    "state of palestine": "PS",
    "west bank": "PS",
    "gaza": "PS",
    "jordan": "JO",
    "hashemite kingdom of jordan": "JO",
    "egypt": "EG",
    "saudi arabia": "SA",
    "ksa": "SA",
    "kingdom of saudi arabia": "SA",
    "united arab emirates": "AE",
    "uae": "AE",
    "emirates": "AE",
    "qatar": "QA",
    "kuwait": "KW",
    "bahrain": "BH",
    "oman": "OM",
    "lebanon": "LB",
    "syria": "SY",
    "iraq": "IQ",
    "turkey": "TR",
    "turkiye": "TR",
    "united states": "US",
    "united states of america": "US",
    "usa": "US",
    "us": "US",
    "america": "US",
    "united kingdom": "GB",
    "uk": "GB",
    "great britain": "GB",
    "england": "GB",
    "germany": "DE",
    "france": "FR",
    "spain": "ES",
    "italy": "IT",
    "netherlands": "NL",
    "the netherlands": "NL",
    "belgium": "BE",
    "sweden": "SE",
    "norway": "NO",
    "denmark": "DK",
    "finland": "FI",
    "ireland": "IE",
    "poland": "PL",
    "romania": "RO",
    "portugal": "PT",
    "switzerland": "CH",
    "austria": "AT",
    "canada": "CA",
    "australia": "AU",
    "new zealand": "NZ",
    "india": "IN",
    "pakistan": "PK",
    "bangladesh": "BD",
    "indonesia": "ID",
    "malaysia": "MY",
    "singapore": "SG",
    "philippines": "PH",
    "china": "CN",
    "japan": "JP",
    "south korea": "KR",
    "korea": "KR",
    "brazil": "BR",
    "argentina": "AR",
    "mexico": "MX",
    "chile": "CL",
    "south africa": "ZA",
    "nigeria": "NG",
    "kenya": "KE",
    "morocco": "MA",
    "tunisia": "TN",
    "algeria": "DZ",
    "libya": "LY",
    "sudan": "SD",
    "yemen": "YE",
}

#: City names that identify exactly one country (N-GEO-02). A city with more
#: than one match is deliberately absent, so no country is inferred from it.
CITY_COUNTRIES: Final[dict[str, str]] = {
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
    "los angeles": "US",
}

#: International dialling prefixes, used to put a local number into E.164.
DIAL_CODES: Final[dict[str, str]] = {
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
    "YE": "967",
}

#: Every code the tables know, so an already-coded value can be recognised.
KNOWN_COUNTRY_CODES: Final[frozenset[str]] = frozenset(COUNTRY_ALIASES.values())

_FUZZY_MIN_LENGTH = 5


def normalize_country(
    raw_value: str,
    *,
    fuzzy_mapping_factor: float = 0.85,
) -> NormalizationOutcome:
    """Map a country name or alias to its ISO 3166-1 alpha-2 code (N-GEO-01).

    An unknown country is kept as a system decision (N-GEO-03 / R-09) rather
    than guessed, and is left empty in the live profile until the decision is
    made.
    """
    text = canonical_text(raw_value)
    if not text:
        return NormalizationOutcome.rejected(RuleId.R_02, "Empty country")

    if len(text) == 2 and text.upper() in KNOWN_COUNTRY_CODES:
        return NormalizationOutcome.ok(text.upper(), RuleId.N_GEO_01)

    if code := COUNTRY_ALIASES.get(text):
        return NormalizationOutcome.ok(code, RuleId.N_GEO_01)

    if match := _fuzzy_country(text):
        return NormalizationOutcome.mapped(match, RuleId.N_GEO_01, fuzzy_mapping_factor)

    return NormalizationOutcome(
        value=None,
        rule=RuleId.N_GEO_03,
        rejected_by=RuleId.R_09,
        detail=f"No country matches {raw_value!r}",
        needs_system_decision=True,
    )


def normalize_city(raw_value: str) -> NormalizationOutcome:
    """Keep a city as its trimmed English name.

    The city list is only used to infer a country; a city that is not in it is
    still a perfectly good city name.
    """
    text = " ".join(raw_value.split())
    if not text:
        return NormalizationOutcome.rejected(RuleId.R_02, "Empty city")
    return NormalizationOutcome.ok(text)


def infer_country_from_city(
    city: str,
    *,
    fuzzy_mapping_factor: float = 0.85,
) -> NormalizationOutcome | None:
    """Infer a country from a city with exactly one match (N-GEO-02).

    Returns ``None`` when the city is unknown, which leaves the country absent
    rather than guessed.
    """
    text = canonical_text(city)
    code = CITY_COUNTRIES.get(text)
    if code is None:
        return None
    return NormalizationOutcome.mapped(code, RuleId.N_GEO_02, fuzzy_mapping_factor)


def _fuzzy_country(text: str) -> str | None:
    """Match a country alias within the edit distance the length allows."""
    if len(text) < _FUZZY_MIN_LENGTH:
        return None

    max_distance = 1 if len(text) <= 8 else 2
    best: tuple[int, str] | None = None

    for alias, code in COUNTRY_ALIASES.items():
        distance = bounded_edit_distance(text, alias, max_distance)
        if distance is None or distance == 0:
            continue
        if best is None or distance < best[0]:
            best = (distance, code)

    return best[1] if best else None
