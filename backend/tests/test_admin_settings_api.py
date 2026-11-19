"""The review limit, end to end: HTTP -> repository -> PostgreSQL -> a job.

`PUT /admin/settings/confidence-threshold` answered 200 with the new value
while the write was only flushed, so `get_db` closed the request's session and
rolled it back. The endpoint looked right and the setting was gone, which is
the worst shape a bug can take.

Two things are pinned here, and they are different claims:

* the value survives the request that set it (the fix), and
* the value that survived is the one a processing job runs under, recorded on
  the attempt (FR-046, FR-067) — a setting nothing reads is not a setting.

Runs only with TEST_DATABASE_URL pointing at a migrated *test* database, like
the other database-backed tests; see test_persistence_integration.py.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from app.core.security import create_access_token
from app.infrastructure.persistence.db.session import get_db
from app.infrastructure.persistence.repositories.settings_repository import (
    CONFIDENCE_THRESHOLD_KEY,
    SqlSettingsRepository,
)
from app.main import app
from tests.helpers import CV_TEXT, answer, as_json, f
from tests.test_persistence_integration import (  # noqa: F401  (fixtures)
    db,
    make_profile,
    pytestmark,
)
from tests.test_processing_service import FakeAI

ENDPOINT = "/api/v1/admin/settings/confidence-threshold"


@pytest.fixture
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def administrator(db):
    from app.infrastructure.persistence.models import UserModel
    user = UserModel(name="Amal Admin", email="admin@test.local",
                     password_hash="x", role="administrator")
    db.add(user)
    db.commit()
    return {"Authorization": f"Bearer {create_access_token(user.user_id)}"}, user.user_id


def fresh_session(db):
    """A session of its own, the way the next request gets one.

    The point of the test is what another request can see, so it must not share
    the session that did the writing: a flushed-but-uncommitted row is visible
    inside its own session and nowhere else.
    """
    return sessionmaker(bind=db.get_bind(), expire_on_commit=False)()


# ---- the fix: the write outlives the request -------------------------------

def test_the_endpoint_persists_the_limit_beyond_its_own_session(client, db, administrator):
    headers, user_id = administrator

    response = client.put(ENDPOINT, headers=headers, json={"value": 0.80})
    assert response.status_code == 200, response.text
    assert float(response.json()["value"]) == pytest.approx(0.80)

    # A new session, as the next request would have: the row must be there.
    reader = fresh_session(db)
    try:
        assert SqlSettingsRepository(reader).confidence_threshold() == pytest.approx(0.80)
        stored = reader.execute(
            text("SELECT value, updated_by FROM system_setting WHERE key = :k"),
            {"k": CONFIDENCE_THRESHOLD_KEY}).one()
        assert float(stored[0]) == pytest.approx(0.80)
        assert stored[1] == user_id            # FR-067: the change is attributable
    finally:
        reader.close()


def test_a_limit_outside_zero_to_one_is_still_refused(client, db, administrator):
    """The fix must not have loosened the validation."""
    headers, _ = administrator
    assert client.put(ENDPOINT, headers=headers, json={"value": 0.80}).status_code == 200

    for bad in (-0.1, 1.5):
        response = client.put(ENDPOINT, headers=headers, json={"value": bad})
        assert response.status_code in (400, 422), response.text

    reader = fresh_session(db)
    try:  # the rejected values changed nothing
        assert SqlSettingsRepository(reader).confidence_threshold() == pytest.approx(0.80)
    finally:
        reader.close()


# ---- the limit a job actually runs under ----------------------------------

#: A skill the source misspells, quoted with a snippet that is a near match:
#: 1.00 base x 0.85 near quote x 1.00 x 0.85 corrected spelling = 0.72.
#: That is under 0.80 and over 0.65, which is the whole point - the same field
#: has to land on either side of the limit depending only on the setting.
SKILL_TEXT = CV_TEXT + "\nPyhton, React\n"
STRADDLING_CONFIDENCE = 0.72


def answer_with_a_straddling_field():
    return answer(skills=[{"name": f("Pyhton", "Pyhton , React")}])


def process_under_the_stored_limit(db, file_id):
    """Run a job the way production does: on the limit that is stored now.

    `build_process_cv_use_case` reads the limit from this repository before it
    builds the use case; that read is what this reproduces, with a fake model
    in place of the real one.
    """
    from app.application.use_cases.process_cv import ProcessCVUseCase
    from app.infrastructure.file_processing.document_reader import StoredDocumentReader
    from app.infrastructure.persistence.repositories.catalog_repository import (
        SqlCatalogRepository,
    )
    from app.infrastructure.persistence.repositories.processing_repository import (
        SqlProcessingRepository,
    )
    from app.infrastructure.persistence.repositories.unit_of_work import SqlAlchemyUnitOfWork

    threshold = SqlSettingsRepository(db).confidence_threshold()
    use_case = ProcessCVUseCase(
        SqlProcessingRepository(db), SqlCatalogRepository(db), StoredDocumentReader(),
        FakeAI(as_json(answer_with_a_straddling_field())), SqlAlchemyUnitOfWork(db),
        confidence_threshold=threshold, sleep=lambda s: None,
    )
    use_case.execute(file_id)
    return threshold


def stored_skill(db):
    return db.execute(text(
        "SELECT confidence, review_status FROM extracted_field "
        "WHERE field_name = 'name' AND entity_type = 'skills' AND raw_value::text LIKE '%Pyhton%'"
    )).one()


def test_the_saved_limit_is_the_limit_the_job_runs_under(client, db, tmp_path, administrator):
    """FR-046 / FR-067, the claim the reviewer asked for: a limit set through
    the settings endpoint reaches the next job, is recorded on its attempt, and
    decides whether a 0.72 field waits for a person."""
    headers, _ = administrator
    _, [file_id] = make_profile(db, tmp_path, {"cv.md": SKILL_TEXT})

    # Raised to 0.80 through the endpoint, in its own request.
    assert client.put(ENDPOINT, headers=headers, json={"value": 0.80}).status_code == 200

    assert process_under_the_stored_limit(db, file_id) == pytest.approx(0.80)

    # The job records the limit it ran under, so the decision stays explainable
    # after the setting changes again (FR-067).
    assert db.execute(text(
        "SELECT confidence_threshold FROM processing_attempt "
        "ORDER BY attempt_id DESC LIMIT 1")).scalar() == pytest.approx(0.80)

    confidence, review_status = stored_skill(db)
    assert confidence == pytest.approx(STRADDLING_CONFIDENCE)
    assert review_status == "needs_review"      # 0.72 < 0.80

    # Lowered to 0.65 and run again: the same field, the same score, accepted.
    assert client.put(ENDPOINT, headers=headers, json={"value": 0.65}).status_code == 200
    db.execute(text("DELETE FROM extracted_field"))
    db.commit()

    assert process_under_the_stored_limit(db, file_id) == pytest.approx(0.65)
    assert db.execute(text(
        "SELECT confidence_threshold FROM processing_attempt "
        "ORDER BY attempt_id DESC LIMIT 1")).scalar() == pytest.approx(0.65)

    confidence, review_status = stored_skill(db)
    assert confidence == pytest.approx(STRADDLING_CONFIDENCE)
    assert review_status == "accepted"          # 0.72 >= 0.65
