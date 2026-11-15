"""Builders for fake LLM answers used in the tests."""

import json


def f(value=None, evidence=None, confidence=0.95, page=None):
    """One extracted field."""
    if value is not None and evidence is None:
        evidence = value if isinstance(value, str) else None
    return {"value": value, "confidence": confidence, "evidence": evidence, "page": page}


def answer(**overrides) -> dict:
    data = {
        "personal_info": {
            "first_name": f("Rana", "Rana Odeh"),
            "last_name": f("Odeh", "Rana Odeh"),
            "email": f("rana.odeh@example.com"),
            "phone": f(),
            "city": f("Amman", "Amman, Jordan 11942"),
            "country": f("Jordan", "Amman, Jordan 11942"),
            "title": f(),
            "summary": f(),
        },
        "work_experience": [{
            "company": f("Zain Jordan"),
            "title": f("Sales Intern"),
            "location": f(),
            "start_date": f("June 2023", "June 2023 - Present"),
            "end_date": f(),
            "is_current": f(True, "June 2023 - Present"),
            "description": f(),
        }],
        "education": [],
        "skills": [{"name": f("reactjs")}, {"name": f("Nagra")}],
        "certifications": [],
        "projects": [],
        "languages": [],
        "links": [],
    }
    data.update(overrides)
    return data


CV_TEXT = """Rana Odeh
Amman, Jordan 11942 | rana.odeh@example.com
EXPERIENCE
Sales Intern
Zain Jordan
June 2023 - Present
SKILLS
reactjs, Nagra
"""


def as_json(data: dict) -> str:
    return json.dumps(data)
