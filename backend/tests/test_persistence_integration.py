"""End-to-end against a real PostgreSQL: use case + repositories + migrations.

Runs only when TEST_DATABASE_URL points to a migrated database whose name
contains "test" (the tests empty the data tables). Example:
    set TEST_DATABASE_URL=postgresql+psycopg://simera@127.0.0.1:54329/simera_test
    python -m pytest tests/test_persistence_integration.py
"""

import os

import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import sessionmaker

from app.domain.entities.processing_attempt import AttemptTrigger
from app.core.exceptions import LLMProviderError
from tests.helpers import CV_TEXT, answer, as_json, f
from tests.test_processing_service import FakeAI

URL = os.environ.get("TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif("test" not in URL.rsplit("/", 1)[-1],
                                reason="TEST_DATABASE_URL to a *test* database not set")

DATA_TABLES = ("profile_change_log, review_option, review_item, vetting_record, profile_skill, work_experience, "
               "education, certification, project, language, profile_link, extracted_field, "
               "processing_attempt, source_file, profile, app_user")


@pytest.fixture
def db():
    from app.infrastructure.persistence import models  # noqa: F401  (register models)
    from app.infrastructure.reference_data import SEED_SKILL_ALIASES, SEED_SKILLS
    engine = create_engine(URL)
    with engine.begin() as c:
        c.execute(text(f"TRUNCATE {DATA_TABLES} RESTART IDENTITY CASCADE"))
        # Reviews can add skills and aliases (FR-062): go back to the seed lists.
        c.execute(text("DELETE FROM skill_alias WHERE NOT (alias_name = ANY(:a))"),
                  {"a": list(SEED_SKILL_ALIASES)})
        c.execute(text("DELETE FROM skill WHERE NOT (canonical_name = ANY(:s))"),
                  {"s": SEED_SKILLS})
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    yield session
    session.close()
    engine.dispose()


def make_profile(db, tmp_path, texts: dict[str, str]):
    from app.infrastructure.persistence.models import ProfileModel, SourceFileModel, UserModel
    user = UserModel(name="Rana", email="rana@test.local", password_hash="x")
    db.add(user)
    db.flush()
    profile = ProfileModel(user_id=user.user_id)
    db.add(profile)
    db.flush()
    file_ids = []
    for i, (name, content) in enumerate(texts.items()):
        path = tmp_path / name
        path.write_text(content, encoding="utf-8")
        sf = SourceFileModel(profile_id=profile.profile_id, file_type="md", original_name=name,
                             file_hash=f"{i:064d}", storage_path=str(path))
        db.add(sf)
        db.flush()
        file_ids.append(sf.file_id)
    db.commit()
    return profile.profile_id, file_ids


def use_case(db, ai):
    from app.application.use_cases.process_cv import ProcessCVUseCase
    from app.infrastructure.file_processing.document_reader import StoredDocumentReader
    from app.infrastructure.persistence.repositories.catalog_repository import SqlCatalogRepository
    from app.infrastructure.persistence.repositories.processing_repository import SqlProcessingRepository
    from app.infrastructure.persistence.repositories.unit_of_work import SqlAlchemyUnitOfWork
    return ProcessCVUseCase(SqlProcessingRepository(db), SqlCatalogRepository(db),
                            StoredDocumentReader(), ai, SqlAlchemyUnitOfWork(db),
                            sleep=lambda s: None)


def scalar(db, sql, **params):
    return db.execute(text(sql), params).scalar()


def test_processing_saves_attempts_fields_reviews_and_profile(db, tmp_path):
    profile_id, [file_id] = make_profile(db, tmp_path, {"rana.md": CV_TEXT})

    result = use_case(db, FakeAI(as_json(answer()))).execute(file_id)

    assert result.status == "needs_review"                 # Nagra is an unknown skill
    assert scalar(db, "SELECT status FROM source_file WHERE file_id=:f", f=file_id) == "needs_review"
    assert scalar(db, "SELECT count(*) FROM processing_attempt WHERE file_id=:f", f=file_id) == 1
    assert scalar(db, "SELECT model_version FROM processing_attempt") == "fake-model-1-0612"

    # live profile written from field records, country matched to the country table
    row = db.execute(text("SELECT p.first_name, c.country_code, p.final_json->>'rule_version' "
                          "FROM profile p JOIN country c USING (country_id)")).one()
    assert row == ("Rana", "JO", "1.0")

    # FR-063: every child record points at stored field records
    job = db.execute(text("SELECT start_date, employment_status, field_ids FROM work_experience")).one()
    assert job[0] == "2023-06" and job[1] == "current"
    stored = {r[0] for r in db.execute(text("SELECT field_id FROM extracted_field"))}
    assert set(job[2]) <= stored
    skill = db.execute(text("SELECT s.canonical_name, ps.source_file_ids, ps.field_ids "
                            "FROM profile_skill ps JOIN skill s USING (skill_id)")).one()
    assert skill[0] == "React" and skill[1] == [file_id] and set(skill[2]) <= stored

    # unknown skill queued with its evidence and field record
    review = db.execute(text(
        "SELECT r.field_name, r.reasons, o.value, o.evidence, o.field_id FROM review_item r "
        "JOIN review_option o USING (review_id)")).one()
    assert review[0] == "name" and review[1] == ["unknown_skill"] and review[2] == "Nagra"
    assert review[4] in stored


def test_three_failures_save_attempts_but_no_profile_data(db, tmp_path):
    profile_id, [file_id] = make_profile(db, tmp_path, {"rana.md": CV_TEXT})
    ai = FakeAI(LLMProviderError("503", retryable=True), "not json",
                LLMProviderError("timeout", retryable=True))

    result = use_case(db, ai).execute(file_id)

    assert result.status == "failed"
    assert scalar(db, "SELECT count(*) FROM processing_attempt") == 3
    assert scalar(db, "SELECT count(*) FROM extracted_field") == 0
    assert scalar(db, "SELECT count(*) FROM work_experience") == 0
    assert scalar(db, "SELECT first_name FROM profile") is None
    item = db.execute(text("SELECT field_name, reasons, message FROM review_item")).one()
    assert item[0] is None and item[1] == ["llm_failed"] and "timeout" in item[2]
    assert "timeout" in scalar(db, "SELECT error_message FROM source_file")


def test_two_sources_union_skills_and_queue_conflicts(db, tmp_path):
    linkedin = CV_TEXT.replace("Amman", "Irbid") + "\nDocker\n"
    profile_id, [cv, li] = make_profile(db, tmp_path, {"cv.md": CV_TEXT, "linkedin.md": linkedin})

    use_case(db, FakeAI(as_json(answer()))).execute(cv)
    second = answer(skills=[{"name": f("React")}, {"name": f("Docker")}])
    second["personal_info"]["city"] = f("Irbid", "Irbid, Jordan 11942")
    use_case(db, FakeAI(as_json(second))).execute(li)

    skills = [r[0] for r in db.execute(text(
        "SELECT s.canonical_name FROM profile_skill JOIN skill s USING (skill_id) ORDER BY 1"))]
    assert skills == ["Docker", "React"]                         # FR-030: no repeats
    sources = scalar(db, "SELECT ps.source_file_ids FROM profile_skill ps "
                         "JOIN skill s USING (skill_id) WHERE s.canonical_name='React'")
    assert sources == [cv, li]

    # FR-033: Amman vs Irbid -> review with both values and their files; city left empty
    assert scalar(db, "SELECT city FROM profile") is None
    options = db.execute(text(
        "SELECT o.value, o.file_id FROM review_item r JOIN review_option o USING (review_id) "
        "WHERE 'source_conflict' = ANY(r.reasons) ORDER BY o.file_id")).all()
    assert options == [("Amman", cv), ("Irbid", li)]


def test_rerun_appends_attempts_and_does_not_duplicate(db, tmp_path):
    profile_id, [file_id] = make_profile(db, tmp_path, {"rana.md": CV_TEXT})
    use_case(db, FakeAI(as_json(answer()))).execute(file_id)
    use_case(db, FakeAI(as_json(answer()))).execute(file_id, AttemptTrigger.ADMIN_RERUN)

    attempts = db.execute(text(
        "SELECT attempt_number, trigger FROM processing_attempt ORDER BY 1")).all()
    assert attempts == [(1, "first_run"), (2, "admin_rerun")]
    assert scalar(db, "SELECT count(*) FROM work_experience") == 1      # rebuilt, not duplicated
    assert scalar(db, "SELECT count(*) FROM review_item WHERE resolved IS NOT TRUE") == 1
    # old field records are kept (audit trail); the profile uses the newest ones
    assert scalar(db, "SELECT count(DISTINCT attempt_id) FROM extracted_field") == 2
    newest = scalar(db, "SELECT max(attempt_id) FROM processing_attempt")
    used = scalar(db, "SELECT field_ids FROM work_experience")
    assert scalar(db, "SELECT bool_and(attempt_id = :a) FROM extracted_field "
                      "WHERE field_id = ANY(:ids)", a=newest, ids=used)


def test_unreadable_file_fails_with_review_item(db, tmp_path):
    profile_id, [file_id] = make_profile(db, tmp_path, {"rana.md": CV_TEXT})
    (tmp_path / "rana.md").unlink()                               # stored file missing

    result = use_case(db, FakeAI()).execute(file_id)

    assert result.status == "failed"
    assert scalar(db, "SELECT reasons FROM review_item") == ["no_text"]
    assert scalar(db, "SELECT count(*) FROM processing_attempt") == 0
