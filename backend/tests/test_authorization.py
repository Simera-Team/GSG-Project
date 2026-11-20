"""Authentication, role guard and ownership checks over HTTP (NFR-016)."""

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Annotated

import jwt
import pytest
from fastapi import Depends
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app.application.authorization import ensure_can_access
from app.application.dto.RequestDto.upload_file_dto import UploadFileDTO
from app.application.services.file_service import FileService
from app.core.config import settings
from app.core.dependencies import (
    CurrentUser,
    get_current_user,
    get_file_service,
    get_user_repository,
    require_permission,
)
from app.core.exceptions import InvalidFileTypeError
from app.domain.entities.user import User
from app.domain.enums.user_role import UserRole
from app.domain.permissions import Permission
from app.main import app
from tests.conftest import auth_header


# Test-only routes that exercise the guards the way real endpoints will.
@app.get("/_test/review-queue")
def _review_queue(
    user: Annotated[User, Depends(require_permission(Permission.REVIEW_QUEUE))]
):
    return {"ok": True}


@app.get("/_test/dashboard")
def _dashboard(
    user: Annotated[User, Depends(require_permission(Permission.DASHBOARD_VIEW))]
):
    return {"ok": True}


@app.get("/_test/candidates/{owner_id}/profile")
def _candidate_profile(owner_id: int, user: CurrentUser):
    ensure_can_access(user, owner_id)
    return {"ok": True}


@pytest.fixture
def client(user_repo):
    app.dependency_overrides[get_user_repository] = lambda: user_repo
    yield TestClient(app)
    app.dependency_overrides.clear()


def _token(**overrides) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": "1", "iat": now, "exp": now + timedelta(minutes=5), "type": "access"}
    payload.update(overrides)
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


# --- get_current_user -------------------------------------------------------

def test_me_returns_current_user(client, make_user):
    user = make_user(UserRole.CANDIDATE)
    response = client.get("/api/v1/auth/me", headers=auth_header(user))
    assert response.status_code == 200
    body = response.json()
    assert body["user_id"] == user.user_id
    assert body["role"] == "candidate"
    assert "password_hash" not in body


def test_missing_token_is_401(client):
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize("token", [
    "not-a-jwt",
    _token(exp=datetime.now(timezone.utc) - timedelta(minutes=1)),   # expired
    _token(type="refresh"),                                          # wrong type
    _token(sub="abc"),                                               # bad subject
    jwt.encode({"sub": "1", "iat": datetime.now(timezone.utc),
                "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
                "type": "access"}, "wrong-secret-wrong-secret-wrong-secret",
               algorithm="HS256"),                                   # wrong signature
], ids=["garbage", "expired", "wrong-type", "bad-sub", "wrong-signature"])
def test_invalid_token_is_401(client, make_user, token):
    make_user(UserRole.CANDIDATE)
    response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_token_for_deleted_user_is_401(client):
    response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {_token(sub='999')}"})
    assert response.status_code == 401


# --- role guard -------------------------------------------------------------

@pytest.mark.parametrize("role, path, expected", [
    (UserRole.CANDIDATE, "/_test/review-queue", 403),
    (UserRole.REVIEWER, "/_test/review-queue", 200),
    (UserRole.ADMINISTRATOR, "/_test/review-queue", 200),   # admin inherits reviewer
    (UserRole.CANDIDATE, "/_test/dashboard", 403),
    (UserRole.REVIEWER, "/_test/dashboard", 403),
    (UserRole.ADMINISTRATOR, "/_test/dashboard", 200),
])
def test_role_guard(client, make_user, role, path, expected):
    user = make_user(role)
    assert client.get(path, headers=auth_header(user)).status_code == expected


def test_role_guard_requires_login(client):
    assert client.get("/_test/review-queue").status_code == 401


# --- ownership --------------------------------------------------------------

def test_candidate_can_access_own_data(client, make_user):
    me = make_user(UserRole.CANDIDATE)
    response = client.get(f"/_test/candidates/{me.user_id}/profile", headers=auth_header(me))
    assert response.status_code == 200


def test_candidate_cannot_access_other_candidates_data(client, make_user):
    me = make_user(UserRole.CANDIDATE)
    other = make_user(UserRole.CANDIDATE)
    response = client.get(f"/_test/candidates/{other.user_id}/profile", headers=auth_header(me))
    assert response.status_code == 403


def test_reviewer_cannot_access_candidate_data_directly(client, make_user):
    reviewer = make_user(UserRole.REVIEWER)
    candidate = make_user(UserRole.CANDIDATE)
    response = client.get(f"/_test/candidates/{candidate.user_id}/profile", headers=auth_header(reviewer))
    assert response.status_code == 403


def test_administrator_can_access_any_candidates_data(client, make_user):
    admin = make_user(UserRole.ADMINISTRATOR)
    candidate = make_user(UserRole.CANDIDATE)
    response = client.get(f"/_test/candidates/{candidate.user_id}/profile", headers=auth_header(admin))
    assert response.status_code == 200


# --- real endpoints ---------------------------------------------------------

class FakeFileService:
    """Records uploads so tests can prove a denied request stored nothing."""

    def __init__(self) -> None:
        self.uploaded_for: list[int] = []
        self.kinds: list[str | None] = []

    async def upload_cv(self, file, user_id: int, source_kind=None) -> SimpleNamespace:
        self.uploaded_for.append(user_id)
        self.kinds.append(source_kind)
        return SimpleNamespace(
            file_id=1,
            filename=file.filename,
            size=len(file.content),
            file_hash="fake",
            status="uploaded",
            queued=True,
        )


@pytest.fixture
def file_service():
    service = FakeFileService()
    app.dependency_overrides[get_file_service] = lambda: service
    yield service


def _upload(client, headers=None):
    return client.post(
        "/api/v1/cv/upload",
        files={"file": ("cv.md", b"# CV", "text/markdown")},
        headers=headers or {},
    )


def test_candidate_can_upload_cv_as_themselves(client, file_service, make_user):
    candidate = make_user(UserRole.CANDIDATE)
    response = _upload(client, auth_header(candidate))
    assert response.status_code == 202      # accepted and queued for processing (FR-013)
    assert file_service.uploaded_for == [candidate.user_id]


@pytest.mark.parametrize("role", [UserRole.REVIEWER, UserRole.ADMINISTRATOR])
def test_only_candidates_can_upload_cv(client, file_service, make_user, role):
    response = _upload(client, auth_header(make_user(role)))
    assert response.status_code == 403
    assert file_service.uploaded_for == []


VETTING_JSON = b'{"skills": [{"name": "Python", "level": 5}]}'


def _upload_vetting(client, user_id, headers=None):
    return client.post(
        f"/api/v1/admin/candidates/{user_id}/vetting",
        files={"file": ("vetting.json", VETTING_JSON, "application/json")},
        headers=headers or {},
    )


def test_candidate_upload_never_sets_a_source_kind(client, file_service, make_user):
    candidate = make_user(UserRole.CANDIDATE)
    _upload(client, auth_header(candidate))
    assert file_service.kinds == [None]


def test_admin_can_upload_vetting_for_a_candidate(client, file_service, make_user):
    candidate = make_user(UserRole.CANDIDATE)
    admin = make_user(UserRole.ADMINISTRATOR)
    response = _upload_vetting(client, candidate.user_id, auth_header(admin))
    assert response.status_code == 202
    assert file_service.uploaded_for == [candidate.user_id]
    assert file_service.kinds == ["vetting"]


@pytest.mark.parametrize("role", [UserRole.CANDIDATE, UserRole.REVIEWER])
def test_only_admins_can_upload_vetting(client, file_service, make_user, role):
    candidate = make_user(UserRole.CANDIDATE)
    caller = candidate if role == UserRole.CANDIDATE else make_user(role)
    response = _upload_vetting(client, candidate.user_id, auth_header(caller))
    assert response.status_code == 403
    assert file_service.uploaded_for == []


@pytest.mark.parametrize("target", [UserRole.REVIEWER, None])
def test_vetting_needs_an_existing_candidate(client, file_service, make_user, target):
    admin = make_user(UserRole.ADMINISTRATOR)
    user_id = make_user(target).user_id if target else 999
    response = _upload_vetting(client, user_id, auth_header(admin))
    assert response.status_code == 404
    assert file_service.uploaded_for == []


def test_candidate_json_upload_is_refused():
    service = FileService(None, None, None, None, None)
    dto = UploadFileDTO(filename="vetting.json", content=VETTING_JSON)
    with pytest.raises(InvalidFileTypeError):
        asyncio.run(service.upload_cv(dto, user_id=1))


def test_vetting_must_be_a_json_file():
    service = FileService(None, None, None, None, None)
    dto = UploadFileDTO(filename="skills.md", content=b"# Skills")
    with pytest.raises(InvalidFileTypeError):
        asyncio.run(service.upload_cv(dto, user_id=1, source_kind="vetting"))


def test_upload_requires_login(client, file_service):
    assert _upload(client).status_code == 401
    assert file_service.uploaded_for == []


PUBLIC_ROUTES = {
    "/",                # redirects to the Swagger page, returns no data
    "/health",
    "/health/db",
    "/api/v1/auth/register",
    "/api/v1/auth/login",
}


def _depends_on_login(dependant: Dependant) -> bool:
    return any(
        d.call is get_current_user or _depends_on_login(d)
        for d in dependant.dependencies
    )


def test_every_route_requires_login_unless_listed_as_public():
    """A new endpoint fails here until it is guarded or listed as public."""
    unguarded = {
        route.path
        for route in app.routes
        if isinstance(route, APIRoute)
        and route.path not in PUBLIC_ROUTES
        and not _depends_on_login(route.dependant)
    }
    assert unguarded == set()
