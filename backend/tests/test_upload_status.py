"""Upload status API: state mapping and owner-only visibility (FR-014, NFR-016)."""

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.application.services.file_service import FileService
from app.core.dependencies import get_file_service, get_user_repository
from app.domain.entities.profile import Profile
from app.domain.entities.source_file import SourceFile
from app.domain.enums.user_role import UserRole
from app.domain.interfaces.profile_repository import IProfileRepository
from app.domain.interfaces.source_file_repository import ISourceFileRepository
from app.main import app
from tests.conftest import auth_header


class FakeProfiles(IProfileRepository):

    def __init__(self) -> None:
        self.profiles: dict[int, Profile] = {}

    def add(self, user_id: int) -> Profile:
        profile = Profile(profile_id=len(self.profiles) + 1, user_id=user_id)
        self.profiles[profile.profile_id] = profile
        return profile

    def get_by_id(self, profile_id: int) -> Profile | None:
        return self.profiles.get(profile_id)

    def get_by_user_id(self, user_id: int) -> Profile | None:
        return next(
            (p for p in self.profiles.values() if p.user_id == user_id),
            None
        )

    def get_or_create_by_user_id(self, user_id: int) -> Profile:
        raise AssertionError("Reading a status must not create a profile")


class FakeSourceFiles(ISourceFileRepository):

    def __init__(self) -> None:
        self.files: dict[int, SourceFile] = {}

    def add(self, profile: Profile, status: str = "uploaded", **fields) -> SourceFile:
        file_id = len(self.files) + 1
        self.files[file_id] = SourceFile(
            file_id=file_id,
            profile_id=profile.profile_id,
            file_type="pdf",
            original_name=f"cv-{file_id}.pdf",
            file_hash="a" * 64,
            storage_path=f"storage/secret-{file_id}.pdf",
            status=status,
            uploaded_at=datetime(2026, 11, 1, 10, file_id),
            **fields
        )
        return self.files[file_id]

    def create(self, source_file: SourceFile) -> SourceFile:
        raise AssertionError("Reading a status must not create a file")

    def get_by_id(self, file_id: int) -> SourceFile | None:
        return self.files.get(file_id)

    def list_by_profile_id(self, profile_id: int) -> list[SourceFile]:
        owned = [f for f in self.files.values() if f.profile_id == profile_id]
        return sorted(owned, key=lambda f: f.uploaded_at, reverse=True)


@pytest.fixture
def profiles() -> FakeProfiles:
    return FakeProfiles()


@pytest.fixture
def files() -> FakeSourceFiles:
    return FakeSourceFiles()


@pytest.fixture
def client(user_repo, profiles, files):
    service = FileService(
        storage=None,
        source_file_repository=files,
        profile_repository=profiles,
        unit_of_work=None
    )
    app.dependency_overrides[get_user_repository] = lambda: user_repo
    app.dependency_overrides[get_file_service] = lambda: service
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def candidate(make_user):
    return make_user(UserRole.CANDIDATE)


@pytest.mark.parametrize(
    ("stored", "shown"),
    [
        ("uploaded", "processing"),
        ("processing", "processing"),
        ("done", "success"),
        ("needs_review", "needs_review"),
        ("failed", "error"),
    ],
)
def test_stored_status_is_shown_as_fr_014_state(
    client, candidate, profiles, files, stored, shown
):
    source = files.add(profiles.add(candidate.user_id), status=stored)

    response = client.get(
        f"/api/v1/files/{source.file_id}",
        headers=auth_header(candidate)
    )

    assert response.status_code == 200
    body = response.json()
    assert body["file_id"] == source.file_id
    assert body["filename"] == source.original_name
    assert body["status"] == shown
    assert body["message"]


def test_response_hides_internal_details(client, candidate, profiles, files):
    source = files.add(
        profiles.add(candidate.user_id),
        status="failed",
        error_message="psycopg.OperationalError: connection to 10.0.0.5 refused"
    )

    response = client.get(
        f"/api/v1/files/{source.file_id}",
        headers=auth_header(candidate)
    )

    assert "psycopg" not in response.text
    assert source.storage_path not in response.text
    assert source.file_hash not in response.text


def test_other_candidates_file_looks_like_a_missing_file(
    client, candidate, make_user, profiles, files
):
    profiles.add(candidate.user_id)
    other = make_user(UserRole.CANDIDATE)
    source = files.add(profiles.add(other.user_id))
    headers = auth_header(candidate)

    denied = client.get(f"/api/v1/files/{source.file_id}", headers=headers)
    missing = client.get("/api/v1/files/999", headers=headers)

    assert denied.status_code == 404
    assert denied.json() == missing.json()


def test_list_returns_only_own_uploads_newest_first(
    client, candidate, make_user, profiles, files
):
    own_profile = profiles.add(candidate.user_id)
    older = files.add(own_profile, status="done")
    files.add(profiles.add(make_user(UserRole.CANDIDATE).user_id))
    newer = files.add(own_profile, status="failed")

    response = client.get("/api/v1/files", headers=auth_header(candidate))

    assert response.status_code == 200
    assert [item["file_id"] for item in response.json()] == [
        newer.file_id,
        older.file_id,
    ]


def test_list_is_empty_before_first_upload(client, candidate):
    response = client.get("/api/v1/files", headers=auth_header(candidate))

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.parametrize("path", ["/api/v1/files", "/api/v1/files/1"])
@pytest.mark.parametrize("role", [UserRole.REVIEWER, UserRole.ADMINISTRATOR])
def test_status_is_visible_only_to_candidates(client, make_user, path, role):
    response = client.get(path, headers=auth_header(make_user(role)))

    assert response.status_code == 403


@pytest.mark.parametrize("path", ["/api/v1/files", "/api/v1/files/1"])
def test_status_requires_login(client, path):
    assert client.get(path).status_code == 401
