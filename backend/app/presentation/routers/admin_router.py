"""Administrator endpoints: dashboard, job monitoring, re-runs, staff accounts.

Each action needs its permission from app/domain/permissions.py (FR-003, §2.10).
"""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from app.application.interfaces.read_repository import IReadRepository
from app.application.interfaces.message_publisher import IMessagePublisher
from app.core.dependencies import (
    get_message_publisher,
    get_read_repository,
    get_user_repository,
    require_permission,
)
from app.core.exceptions import EmailAlreadyExistsError
from app.core.security import hash_password
from app.domain.entities.user import User
from app.domain.enums.user_role import UserRole
from app.domain.permissions import Permission
from app.domain.interfaces.user_repository import IUserRepository
from app.presentation.schemas.file_schema import (
    AdminFileDetailOut,
    AdminFileListOut,
    AdminFileOut,
    AttemptOut,
    RerunOut,
)
from app.presentation.schemas.profile_schema import StaffUserIn, StaffUserOut

router = APIRouter(prefix="/admin", tags=["Admin"])

def _needs(permission: Permission):
    return Annotated[User, Depends(require_permission(permission))]


DashboardViewer = _needs(Permission.DASHBOARD_VIEW)
JobViewer = _needs(Permission.CANDIDATE_DATA_ACCESS_ANY)
JobRerunner = _needs(Permission.JOB_RERUN)
UserManager = _needs(Permission.USER_MANAGE)
Reader = Annotated[IReadRepository, Depends(get_read_repository)]
FileId = Annotated[int, Path(ge=1)]
ERRORS = {401: {"description": "Not logged in"},
          403: {"description": "Not an administrator"}}


@router.get("/dashboard", responses=ERRORS, summary="Processing and quality numbers")
def dashboard(admin: DashboardViewer, reader: Reader) -> dict:
    """Files by status (FR-047); LLM valid-on-first-try rate, average confidence
    and share of fields sent to review (FR-048); files that hit 3 attempts
    (FR-052); open and resolved reviews."""
    return reader.dashboard()


@router.get("/files", response_model=AdminFileListOut, responses=ERRORS,
            summary="All uploads, filterable by status")
def list_files(
    admin: JobViewer, reader: Reader,
    status_filter: Annotated[
        Literal["uploaded", "processing", "done", "needs_review", "failed"] | None,
        Query(alias="status", description="e.g. failed, to see jobs that need a re-run")] = None,
    profile_id: Annotated[int | None, Query(ge=1)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    """Job states, errors and attempt counts (FR-042, FR-052). Newest first."""
    total, files = reader.list_files(profile_id, status_filter, limit, offset)
    return AdminFileListOut(total=total, limit=limit, offset=offset,
                            items=[AdminFileOut.model_validate(f, from_attributes=True)
                                   for f in files])


@router.get("/files/{file_id}", response_model=AdminFileDetailOut,
            responses={**ERRORS, 404: {"description": "No such file"}},
            summary="One upload with every processing attempt")
def file_detail(file_id: FileId, admin: JobViewer, reader: Reader):
    """Status, errors and every attempt with trigger, outcome, model version and
    error (FR-050, FR-058)."""
    found = reader.get_file(file_id)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File not found")
    detail = AdminFileOut.model_validate(found, from_attributes=True).model_dump()
    return AdminFileDetailOut(**detail, attempts_detail=[
        AttemptOut.model_validate(a, from_attributes=True) for a in reader.file_attempts(file_id)])


@router.post("/files/{file_id}/rerun", response_model=RerunOut,
             status_code=status.HTTP_202_ACCEPTED,
             responses={**ERRORS, 404: {"description": "No such file"},
                        409: {"description": "The file is being processed right now"}},
             summary="Re-run a file from its stored original")
async def rerun(file_id: FileId, admin: JobRerunner, reader: Reader,
                publisher: Annotated[IMessagePublisher, Depends(get_message_publisher)]):
    """Queues the unchanged original again; the worker processes it as a new
    attempt (FR-045). Earlier attempts stay visible, and admin re-runs don't
    count toward the automatic 3-attempt limit (FR-059)."""
    found = reader.get_file(file_id)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File not found")
    if found.status == "processing":
        raise HTTPException(status.HTTP_409_CONFLICT, "The file is being processed right now")
    await publisher.publish_cv(file_id, trigger="admin_rerun")
    return RerunOut(file_id=file_id, status=found.status,
                    message="Re-run queued; follow it with GET /admin/files/{file_id}")


@router.post("/users", response_model=StaffUserOut, status_code=status.HTTP_201_CREATED,
             responses={**ERRORS, 409: {"description": "E-mail already registered"}},
             summary="Create a reviewer or administrator account")
def create_staff_user(body: StaffUserIn, admin: UserManager,
                      users: Annotated[IUserRepository, Depends(get_user_repository)]):
    """Public registration only creates candidates; staff accounts are created
    here, with e-mail and password (FR-068)."""
    try:
        user = users.create(User(user_id=None, name=body.name, email=body.email.lower(),
                                 password_hash=hash_password(body.password),
                                 role=UserRole(body.role)))
    except EmailAlreadyExistsError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    role = user.role.value if isinstance(user.role, UserRole) else str(user.role)
    return StaffUserOut(user_id=user.user_id, name=user.name, email=user.email, role=role)
