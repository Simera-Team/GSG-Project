"""The review limit as a setting an administrator controls (FR-046, FR-067).

It used to be an environment variable, so changing it meant a redeploy and
nothing recorded who changed it. These tests cover the stored setting: its
default, that a change is attributable, and that a stored value which would
send everything (or nothing) to review is ignored.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.infrastructure.persistence.db.base import Base
from app.infrastructure.persistence.models.system_setting_model import SystemSettingModel
from app.infrastructure.persistence.repositories.settings_repository import (
    CONFIDENCE_THRESHOLD_KEY,
    DEFAULT_CONFIDENCE_THRESHOLD,
    SqlSettingsRepository,
)


@pytest.fixture
def db():
    """A SQLite database holding only the settings table.

    The rest of the schema is PostgreSQL-specific, and this repository touches
    one table, so the table is created on its own.
    """
    engine = create_engine("sqlite://")
    SystemSettingModel.__table__.create(engine)
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
