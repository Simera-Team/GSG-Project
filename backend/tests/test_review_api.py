"""Review API end to end: HTTP -> router -> service -> PostgreSQL.

Runs only with TEST_DATABASE_URL pointing at a migrated *test* database
(see test_persistence_integration.py). The LLM is faked.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.security import create_access_token
from app.infrastructure.persistence.db.session import get_db
from app.main import app
from tests.helpers import CV_TEXT, answer, as_json, f
from tests.test_persistence_integration import db, make_profile, pytestmark, use_case  # noqa: F401
from tests.test_processing_service import FakeAI


@pytest.fixture
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def reviewer(db):
    from app.infrastructure.persistence.models import UserModel
    user = UserModel(name="Rania Reviewer", email="reviewer@test.local",
                     password_hash="x", role="reviewer")
    db.add(user)
    db.commit()
    return {"Authorization": f"Bearer {create_access_token(user.user_id)}"}, user.user_id


def candidate_headers(db):
    uid = db.execute(text("SELECT user_id FROM app_user WHERE role='candidate'")).scalar()
    return {"Authorization": f"Bearer {create_access_token(uid)}"}


def scalar(db, sql, **params):
    return db.execute(text(sql), params).scalar()


def process(db, file_id, data):
    use_case(db, FakeAI(as_json(data))).execute(file_id)


def items(client, headers, **params):
    r = client.get("/api/v1/review/items", headers=headers, params=params)
    assert r.status_code == 200, r.text
    return r.json()["items"]


def find(items_, field_name, reason=None):
    return next(i for i in items_ if i["field_name"] == field_name
                and (reason is None or reason in i["reasons"]))


# ---- access (FR-003, NFR-016) ----

def test_only_reviewers_can_use_the_queue(client, db, tmp_path, reviewer):
    make_profile(db, tmp_path, {"cv.md": CV_TEXT})
    assert client.get("/api/v1/review/items").status_code == 401
    r = client.get("/api/v1/review/items", headers=candidate_headers(db))
    assert r.status_code == 403
    assert client.get("/api/v1/review/items", headers=reviewer[0]).status_code == 200


# ---- queue contents (FR-041, FR-043) ----

def test_queue_shows_candidate_field_values_and_evidence(client, db, tmp_path, reviewer):
    _, [file_id] = make_profile(db, tmp_path, {"cv.md": CV_TEXT})
    process(db, file_id, answer())

    item = find(items(client, reviewer[0]), "name", "unknown_skill")
    assert item["candidate_name"] == "Rana" and item["file_name"] == "cv.md"
    assert item["entity"] == "skills[2]" and not item["is_failed_job"]
    option = item["options"][0]
    assert option["value"] == "Nagra" and option["evidence"] == "Nagra"
    assert option["field_id"] is not None

    one = client.get(f"/api/v1/review/items/{item['review_id']}", headers=reviewer[0])
    assert one.status_code == 200 and one.json()["options"] == item["options"]
    assert client.get("/api/v1/review/items/99999", headers=reviewer[0]).status_code == 404


# ---- skills (FR-062) ----

def test_approve_unknown_skill_as_new_standard_skill(client, db, tmp_path, reviewer):
    profile_id, [file_id] = make_profile(db, tmp_path, {"cv.md": CV_TEXT})
    process(db, file_id, answer())
    item = find(items(client, reviewer[0]), "name", "unknown_skill")

    r = client.post(f"/api/v1/review/items/{item['review_id']}/resolve", headers=reviewer[0],
                    json={"action": "option", "option_id": item["options"][0]["option_id"]})

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["resolved"] and body["resolution"] == "option"
    assert body["resolved_by_name"] == "Rania Reviewer" and body["resolved_at"]
    assert scalar(db, "SELECT count(*) FROM skill WHERE canonical_name='Nagra'") == 1
    skills = [r[0] for r in db.execute(text(
        "SELECT s.canonical_name FROM profile_skill JOIN skill s USING (skill_id) ORDER BY 1"))]
    assert skills == ["Nagra", "React"]
    # FR-063: the profile record points at the decision's field record
    decision = scalar(db, "SELECT resolved_field_id FROM review_item WHERE review_id=:r",
                      r=item["review_id"])
    assert decision in scalar(db, "SELECT ps.field_ids FROM profile_skill ps JOIN skill s "
                                  "USING (skill_id) WHERE s.canonical_name='Nagra'")
    assert scalar(db, "SELECT rule FROM extracted_field WHERE field_id=:d", d=decision) \
        == "review_decision"
    assert scalar(db, "SELECT reason FROM profile_change_log WHERE field_name='skills[2].name'") \
        == "review_decision"


def test_map_unknown_skill_to_existing_one_saves_alias(client, db, tmp_path, reviewer):
    text_ = CV_TEXT.replace("Nagra", "Postgres SQL")
    profile_id, [file_id] = make_profile(db, tmp_path, {"cv.md": text_})
    data = answer(skills=[{"name": f("Postgres SQL")}])
    process(db, file_id, data)
    item = find(items(client, reviewer[0]), "name", "unknown_skill")

    r = client.post(f"/api/v1/review/items/{item['review_id']}/resolve", headers=reviewer[0],
                    json={"action": "option", "option_id": item["options"][0]["option_id"],
                          "map_to_skill": "postgresql"})

    assert r.status_code == 200, r.text
    assert scalar(db, "SELECT s.canonical_name FROM skill_alias a JOIN skill s USING (skill_id) "
                      "WHERE a.alias_name='postgres sql'") == "PostgreSQL"
    assert scalar(db, "SELECT count(*) FROM skill WHERE canonical_name ILIKE 'postgres sql'") == 0
    assert scalar(db, "SELECT s.canonical_name FROM profile_skill JOIN skill s USING (skill_id)") \
        == "PostgreSQL"


# ---- conflicts (FR-033) + change history (FR-037) ----

def test_resolving_a_conflict_updates_profile_and_history(client, db, tmp_path, reviewer):
    linkedin = CV_TEXT.replace("Amman", "Irbid")
    profile_id, [cv, li] = make_profile(db, tmp_path, {"cv.md": CV_TEXT, "linkedin.md": linkedin})
    process(db, cv, answer())
    second = answer()
    second["personal_info"]["city"] = f("Irbid", "Irbid, Jordan 11942")
    process(db, li, second)
    assert scalar(db, "SELECT city FROM profile") is None

    conflict = find(items(client, reviewer[0]), "city", "source_conflict")
    irbid = next(o for o in conflict["options"] if o["value"] == "Irbid")
    assert irbid["file_name"] == "linkedin.md"

    r = client.post(f"/api/v1/review/items/{conflict['review_id']}/resolve",
                    headers=reviewer[0], json={"action": "option", "option_id": irbid["option_id"]})

    assert r.status_code == 200, r.text
    assert scalar(db, "SELECT city FROM profile") == "Irbid"
    # FR-037: the full story of the field - added from the CV, cleared by the
    # conflict, then set by the reviewer - with the file and person behind each step
    history = db.execute(text("SELECT old_value, new_value, changed_by, reason, file_id "
                              "FROM profile_change_log WHERE field_name='city' "
                              "ORDER BY change_id")).all()
    assert history == [(None, "Amman", None, "auto_merge", cv),
                       ("Amman", None, None, "auto_merge", li),
                       (None, "Irbid", reviewer[1], "review_decision", li)]
    # the conflict is not raised again by the rebuild
    assert not [i for i in items(client, reviewer[0]) if "source_conflict" in i["reasons"]]


# ---- custom values, rejection, validation ----

def test_custom_value_goes_through_the_date_rules(client, db, tmp_path, reviewer):
    profile_id, [file_id] = make_profile(db, tmp_path, {"cv.md": CV_TEXT})
    data = answer()
    data["work_experience"][0]["start_date"] = f("June 2023", "June 2023 - Present", confidence=0.3)
    process(db, file_id, data)
    item = find(items(client, reviewer[0]), "start_date", "low_confidence")
    url = f"/api/v1/review/items/{item['review_id']}/resolve"

    bad = client.post(url, headers=reviewer[0], json={"action": "custom", "value": "soon"})
    assert bad.status_code == 422 and "not a date" in bad.json()["detail"]

    ok = client.post(url, headers=reviewer[0], json={"action": "custom", "value": "May 2023"})
    assert ok.status_code == 200 and ok.json()["resolution"] == "custom"
    assert scalar(db, "SELECT start_date FROM work_experience") == "2023-05"


def test_reject_leaves_the_field_empty(client, db, tmp_path, reviewer):
    profile_id, [file_id] = make_profile(db, tmp_path, {"cv.md": CV_TEXT})
    data = answer()
    data["personal_info"]["last_name"] = f("Odeh", "Rana Odeh", confidence=0.4)
    process(db, file_id, data)
    item = find(items(client, reviewer[0]), "last_name")

    r = client.post(f"/api/v1/review/items/{item['review_id']}/resolve",
                    headers=reviewer[0], json={"action": "reject"})

    assert r.status_code == 200 and r.json()["resolution"] == "rejected"
    assert scalar(db, "SELECT last_name FROM profile") is None
    again = client.post(f"/api/v1/review/items/{item['review_id']}/resolve",
                        headers=reviewer[0], json={"action": "reject"})
    assert again.status_code == 409


def test_wrong_actions_are_refused(client, db, tmp_path, reviewer):
    profile_id, [file_id] = make_profile(db, tmp_path, {"cv.md": CV_TEXT})
    process(db, file_id, answer())
    item = find(items(client, reviewer[0]), "name", "unknown_skill")
    url = f"/api/v1/review/items/{item['review_id']}/resolve"

    assert client.post(url, headers=reviewer[0], json={"action": "dismiss"}).status_code == 422
    assert client.post(url, headers=reviewer[0], json={"action": "option"}).status_code == 422
    assert client.post(url, headers=reviewer[0],
                       json={"action": "option", "option_id": 99999}).status_code == 422
    assert client.post(url, headers=reviewer[0], json={"action": "guess"}).status_code == 422
    assert client.post(url, headers=candidate_headers(db),
                       json={"action": "reject"}).status_code == 403


# ---- failed jobs (FR-042) ----

def test_failed_job_can_only_be_dismissed(client, db, tmp_path, reviewer):
    from app.core.exceptions import LLMProviderError
    profile_id, [file_id] = make_profile(db, tmp_path, {"cv.md": CV_TEXT})
    use_case(db, FakeAI(*[LLMProviderError("503", retryable=True)] * 3)).execute(file_id)

    item = items(client, reviewer[0], reason="llm_failed")[0]
    assert item["is_failed_job"] and item["field_name"] is None and item["options"] == []
    url = f"/api/v1/review/items/{item['review_id']}/resolve"

    assert client.post(url, headers=reviewer[0],
                       json={"action": "custom", "value": "x"}).status_code == 422
    r = client.post(url, headers=reviewer[0], json={"action": "dismiss"})
    assert r.status_code == 200 and r.json()["resolution"] == "dismissed"


# ---- ask the candidate (FR-044) ----

def test_request_candidate_keeps_item_open(client, db, tmp_path, reviewer):
    profile_id, [file_id] = make_profile(db, tmp_path, {"cv.md": CV_TEXT})
    process(db, file_id, answer())
    item = find(items(client, reviewer[0]), "name", "unknown_skill")

    r = client.post(f"/api/v1/review/items/{item['review_id']}/request-candidate",
                    headers=reviewer[0])

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["candidate_email"] == "rana@test.local" and "Rana" in body["suggested_message"]
    assert body["item"]["assigned_to_candidate"] and body["item"]["sent_to_candidate_at"]
    assert not body["item"]["resolved"]
    waiting = items(client, reviewer[0], status="waiting_candidate")
    assert [i["review_id"] for i in waiting] == [item["review_id"]]
    assert scalar(db, "SELECT count(*) FROM profile_skill") == 1        # profile unchanged
