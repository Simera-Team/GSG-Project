"""The review limit as a setting an administrator controls (FR-046, FR-067).

It used to be an environment variable, so changing it meant a redeploy and
nothing recorded who changed it. These tests cover the stored setting: its
default, that a change is attributable, and that a stored value which would
send everything (or nothing) to review is ignored.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.infrastructure.persistence.db.base import Base
from app.infrastructure.persistence.models.system_setting_model import SystemSettingModel
from app.infrastructure.persistence.repositories.settings_repository import (
    CONFIDENCE_THRESHOLD_KEY,
    DEFAULT_CONFIDENCE_THRESHOLD,
    SqlSettingsRepository,
)


@pytest.fixture
def engine():
    """A SQLite database holding only the settings table.

    The rest of the schema is PostgreSQL-specific, and this repository touches
    one table, so the table is created on its own. `StaticPool` keeps the one
    in-memory connection alive across sessions, so a second session reads the
    same database rather than an empty new one.
    """
    engine = create_engine("sqlite://", poolclass=StaticPool)
    SystemSettingModel.__table__.create(engine)
    return engine


@pytest.fixture
def db(engine):
    with Session(engine) as session:
        yield session


@pytest.fixture
def repo(db):
    return SqlSettingsRepository(db)


def test_the_default_limit_follows_the_rules_document(repo):
    assert DEFAULT_CONFIDENCE_THRESHOLD == 0.65


def test_an_empty_table_gives_the_default(repo):
    """A fresh database must behave like a migrated one."""
    assert repo.confidence_threshold() == DEFAULT_CONFIDENCE_THRESHOLD


def test_an_administrator_can_change_the_limit(repo):
    repo.set_confidence_threshold(0.8, user_id=7)
    assert repo.confidence_threshold() == pytest.approx(0.8)


def test_a_change_records_who_made_it(repo):
    """FR-067: the setting keeps who changed it and when."""
    updated = repo.set_confidence_threshold(0.5, user_id=7)
    assert updated.key == CONFIDENCE_THRESHOLD_KEY
    assert updated.updated_by == 7
    assert updated.updated_at is not None


def test_the_limit_survives_a_new_repository(repo, db):
    """FR-067: it is stored, not held in memory, so it survives a restart."""
    repo.set_confidence_threshold(0.42, user_id=1)
    assert SqlSettingsRepository(db).confidence_threshold() == pytest.approx(0.42)


def test_the_limit_survives_the_session_that_set_it(engine):
    """FR-067: it has to outlive the request, which is a different thing.

    A new repository on the *same* session sees an uncommitted write, because
    the row is already in that session. The question is whether the write was
    committed, and only a second session can answer it: `get_db` closes the
    request's session without committing, so a value that was merely flushed
    is rolled back while the endpoint has already answered 200 with it.
    """
    with Session(engine) as writing:
        SqlSettingsRepository(writing).set_confidence_threshold(0.42, user_id=1)

    with Session(engine) as reading:
        assert SqlSettingsRepository(reading).confidence_threshold() == pytest.approx(0.42)


@pytest.mark.parametrize("value", [-0.1, 1.1, 2.0])
def test_a_limit_outside_zero_to_one_is_refused(repo, value):
    with pytest.raises(ValueError):
        repo.set_confidence_threshold(value, user_id=1)


@pytest.mark.parametrize("stored", ["not a number", "", "2.5", "-1"])
def test_an_unusable_stored_value_falls_back_to_the_default(repo, db, stored):
    """A limit outside 0 to 1 would send every field, or no field, to review;
    the default is safer than honouring it."""
    db.add(SystemSettingModel(key=CONFIDENCE_THRESHOLD_KEY, value=stored))
    db.flush()
    assert repo.confidence_threshold() == DEFAULT_CONFIDENCE_THRESHOLD


@pytest.mark.parametrize("value", [0.0, 1.0])
def test_the_bounds_themselves_are_allowed(repo, value):
    repo.set_confidence_threshold(value, user_id=1)
    assert repo.confidence_threshold() == pytest.approx(value)


def test_the_setting_is_listed_for_the_administrator(repo):
    repo.set_confidence_threshold(0.7, user_id=3)
    listed = {s.key: s for s in repo.list_settings()}
    assert CONFIDENCE_THRESHOLD_KEY in listed
    assert listed[CONFIDENCE_THRESHOLD_KEY].updated_by == 3


# ---- the setting has to reach the thing it configures ---------------------

#: A skill the source misspells, quoted with a snippet that is a near match:
#: 1.00 base x 0.85 near quote x 1.00 x 0.85 corrected spelling = 0.72, which
#: sits between the two limits below. The same field therefore has to land on
#: either side of the line depending only on the stored setting.
STRADDLING_TEXT = ("Rana Odeh\nrana.odeh@example.com | Amman, Jordan 11942\n"
                   "SKILLS\nPyhton, React\n")
STRADDLING_CONFIDENCE = 0.72


def _skill_record(threshold: float):
    """Build the records for one CV under ``threshold`` and return the skill."""
    from app.application.dto.cv_extraction import CVExtraction
    from app.application.dto.extracted_document import ExtractedDocument
    from app.application.services.field_record_builder import (
        FieldRecordBuilder,
        FieldRecordSettings,
    )
    from app.domain.services.countries import CountryCatalog
    from app.infrastructure.reference_data import SEED_COUNTRIES, seed_skill_catalog
    from tests.helpers import answer, f

    builder = FieldRecordBuilder(
        CountryCatalog(SEED_COUNTRIES), seed_skill_catalog(),
        FieldRecordSettings(confidence_threshold=threshold),
    )
    extraction = CVExtraction.model_validate(
        answer(work_experience=[], skills=[{"name": f("Pyhton", "Pyhton , React")}]))
    outcome = builder.build(
        extraction, ExtractedDocument(source_name="cv.md", text=STRADDLING_TEXT))
    return next(r for r in outcome.records
                if r.entity_type == "skills" and r.field_name == "name")


@pytest.mark.parametrize("stored, needs_review", [(0.80, True), (0.65, False)])
def test_the_stored_limit_decides_whether_a_field_waits_for_a_person(
        engine, stored, needs_review):
    """FR-046: a setting nothing reads is not a setting.

    The limit is written through the repository, read back in a session of its
    own - as the next job would - and handed to the record builder. The field
    scores 0.72 either way; only the limit moves, and with it the decision.

    The database-backed half of this claim, that the limit also reaches a real
    job and is recorded on its attempt, is in test_admin_settings_api.py.
    """
    with Session(engine) as writing:
        SqlSettingsRepository(writing).set_confidence_threshold(stored, user_id=1)

    with Session(engine) as reading:
        in_force = SqlSettingsRepository(reading).confidence_threshold()
    assert in_force == pytest.approx(stored)

    record = _skill_record(in_force)
    assert record.value == "Python"
    assert record.confidence == pytest.approx(STRADDLING_CONFIDENCE)
    assert record.needs_review is needs_review
