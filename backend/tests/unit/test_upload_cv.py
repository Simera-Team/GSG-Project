import asyncio
import hashlib
import os
import stat

import pytest

from app.application.dto.RequestDto.upload_file_dto import UploadFileDTO
from app.application.interfaces.message_publisher import IMessagePublisher
from app.application.interfaces.unit_of_work import IUnitOfWork
from app.application.services.file_service import FileService
from app.core.exceptions import DuplicateFileError, DuplicateSourceFileHashError
from app.domain.entities.profile import Profile
from app.domain.entities.source_file import SourceFile
from app.domain.interfaces.profile_repository import IProfileRepository
from app.domain.interfaces.source_file_repository import ISourceFileRepository
from app.infrastructure.storage.local_file_storage import LocalFileStorage


# ---------- fakes ----------

class FakeProfiles(IProfileRepository):
    def __init__(self):
        self.by_user: dict[int, Profile] = {}

    def get_by_user_id(self, user_id):
        return self.by_user.get(user_id)

    def get_or_create_by_user_id(self, user_id):
        if user_id not in self.by_user:
            self.by_user[user_id] = Profile(profile_id=user_id * 10, user_id=user_id)
        return self.by_user[user_id]


class FakeSourceFiles(ISourceFileRepository):
    def __init__(self):
        self.rows: list[SourceFile] = []
        self.pending: list[SourceFile] = []
        self.race_with: SourceFile | None = None

    def create(self, source_file):
        if self.race_with is not None:
            # simulate another request committing the same hash first
            self.rows.append(self.race_with)
            self.race_with = None
            raise DuplicateSourceFileHashError()
        source_file.file_id = len(self.rows) + len(self.pending) + 1
        self.pending.append(source_file)
        return source_file

    def get_by_id(self, file_id):
        return next((r for r in self.rows if r.file_id == file_id), None)

    def get_by_profile_and_hash(self, profile_id, file_hash):
        return next(
            (r for r in self.rows
             if r.profile_id == profile_id and r.file_hash == file_hash),
            None,
        )


class FakeUoW(IUnitOfWork):
    def __init__(self, files: FakeSourceFiles):
        self.files = files
        self.commits = 0
        self.rollbacks = 0

    def commit(self):
        self.files.rows.extend(self.files.pending)
        self.files.pending.clear()
        self.commits += 1

    def rollback(self):
        self.files.pending.clear()
        self.rollbacks += 1


class FakePublisher(IMessagePublisher):
    def __init__(self, fail=False):
        self.published: list[int] = []
        self.fail = fail

    async def publish_cv(self, file_id):
        if self.fail:
            raise ConnectionError("broker down")
        self.published.append(file_id)


# ---------- helpers ----------

MD = b"# Jane Doe\nPython developer\n"


@pytest.fixture
def env(tmp_path):
    files = FakeSourceFiles()
    storage = LocalFileStorage(tmp_path / "cvs")
    publisher = FakePublisher()
    uow = FakeUoW(files)
    service = FileService(
        storage=storage,
        source_file_repository=files,
        profile_repository=FakeProfiles(),
        unit_of_work=uow,
        message_publisher=publisher,
    )
    return service, files, storage, publisher, uow


def upload(service, content=MD, name="cv.md", user_id=1):
    return asyncio.run(
        service.upload_cv(UploadFileDTO(filename=name, content=content), user_id)
    )


def stored_files(storage):
    return sorted(storage.storage_path.iterdir())


# ---------- tests ----------

def test_upload_hashes_stores_and_creates_job(env):
    service, files, storage, publisher, uow = env

    result = upload(service)

    assert result.file_hash == hashlib.sha256(MD).hexdigest()
    assert result.status == "uploaded"
    assert result.queued is True
    assert publisher.published == [result.file_id]
    assert uow.commits == 1
    assert len(files.rows) == 1
    assert files.rows[0].file_hash == result.file_hash
    assert storage.read(result.storage_path) == MD


def test_stored_file_is_read_only_and_never_overwritten(env):
    service, _, storage, _, _ = env

    first = upload(service, MD)
    second = upload(service, MD + b"more\n")

    assert first.storage_path != second.storage_path
    mode = stat.S_IMODE(os.stat(first.storage_path).st_mode)
    assert mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH) == 0
    assert storage.read(first.storage_path) == MD


def test_same_candidate_same_file_is_blocked(env, caplog):
    service, files, storage, publisher, _ = env
    first = upload(service)

    with caplog.at_level("INFO"), pytest.raises(DuplicateFileError) as exc:
        upload(service, name="renamed.md")

    assert exc.value.existing_file_id == first.file_id
    assert exc.value.existing_status == "uploaded"
    assert len(files.rows) == 1
    assert len(stored_files(storage)) == 1      # nothing new stored
    assert publisher.published == [first.file_id]  # no new job
    assert "Blocked duplicate upload" in caplog.text


def test_similar_but_different_file_is_processed(env):
    service, files, _, publisher, _ = env

    upload(service, MD)
    upload(service, MD.replace(b"Python", b"Java"))

    assert len(files.rows) == 2
    assert len(publisher.published) == 2


def test_hash_is_unique_per_candidate_not_system_wide(env):
    service, files, _, publisher, _ = env

    a = upload(service, user_id=1)
    b = upload(service, user_id=2)

    assert a.file_hash == b.file_hash
    assert a.file_id != b.file_id
    assert len(files.rows) == 2
    assert len(publisher.published) == 2


def test_concurrent_duplicate_discards_file_and_reports_existing(env):
    service, files, storage, publisher, uow = env
    winner = SourceFile(
        file_id=99, profile_id=10, file_type="md", original_name="cv.md",
        file_hash=hashlib.sha256(MD).hexdigest(), storage_path="x",
        status="processing",
    )
    files.race_with = winner

    with pytest.raises(DuplicateFileError) as exc:
        upload(service)

    assert exc.value.existing_file_id == 99
    assert exc.value.existing_status == "processing"
    assert stored_files(storage) == []   # orphan file removed
    assert publisher.published == []
    assert uow.commits == 0


def test_broker_failure_does_not_fail_upload(env):
    service, files, _, publisher, _ = env
    publisher.fail = True

    result = upload(service)

    assert result.queued is False
    assert len(files.rows) == 1   # job saved, still 'uploaded'


def test_db_failure_rolls_back_and_removes_file(env):
    service, files, storage, publisher, uow = env

    def boom(_):
        raise RuntimeError("db down")

    files.create = boom

    with pytest.raises(RuntimeError):
        upload(service)

    assert uow.rollbacks == 1
    assert stored_files(storage) == []
    assert publisher.published == []


def test_storage_refuses_paths_outside_base(tmp_path):
    storage = LocalFileStorage(tmp_path / "cvs")
    outside = tmp_path / "secret.txt"
    outside.write_text("x")

    with pytest.raises(ValueError):
        storage.read(str(outside))
    with pytest.raises(ValueError):
        storage.discard(str(outside))
    assert outside.exists()
