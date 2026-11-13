"""Unified candidate profile (FR-004) and its change history (FR-037)."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from app.application.interfaces.read_repository import IReadRepository, ProfileView
from app.core.auth_dependencies import get_current_user_id, require_reviewer
from app.core.dependencies import get_read_repository
from app.domain.entities.user import User
from app.presentation.schemas.file_schema import FileOut
from app.presentation.schemas.profile_schema import ChangeListOut, ChangeOut, ProfileOut

router = APIRouter(prefix="/profile", tags=["Profile"])

Reader = Annotated[IReadRepository, Depends(get_read_repository)]
Reviewer = Annotated[User, Depends(require_reviewer)]
ProfileId = Annotated[int, Path(ge=1)]


def _out(view: ProfileView) -> ProfileOut:
    return ProfileOut(
        profile_id=view.profile_id, candidate_name=view.candidate_name,
        candidate_email=view.candidate_email, updated_at=view.updated_at,
        open_reviews=view.open_reviews, profile=view.profile,
        files=[FileOut.model_validate(f) for f in view.files])


@router.get("/me", response_model=ProfileOut,
            responses={401: {"description": "Not logged in"},
                       404: {"description": "Nothing uploaded yet"}},
            summary="My unified profile")
def my_profile(user_id: Annotated[int, Depends(get_current_user_id)], reader: Reader):
    """Personal info, experience, education, skills, certifications, projects,
    languages and links, merged from all your uploads (FR-004). Values still
    waiting for a reviewer are not included yet (FR-040)."""
    profile_id = reader.profile_id_for_user(user_id)
    view = reader.get_profile(profile_id) if profile_id else None
    if view is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No profile yet: upload a CV first")
    return _out(view)


@router.get("/{profile_id}", response_model=ProfileOut,
            responses={401: {"description": "Not logged in"},
                       403: {"description": "Not a reviewer or administrator"},
                       404: {"description": "No such profile"}},
            summary="A candidate's profile (reviewers, administrators)")
def get_profile(profile_id: ProfileId, reviewer: Reviewer, reader: Reader):
    view = reader.get_profile(profile_id)
    if view is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Profile not found")
    return _out(view)


@router.get("/{profile_id}/history", response_model=ChangeListOut,
            responses={401: {"description": "Not logged in"},
                       403: {"description": "Not a reviewer or administrator"},
                       404: {"description": "No such profile"}},
            summary="Change history of a profile (reviewers, administrators)")
def profile_history(profile_id: ProfileId, reviewer: Reviewer, reader: Reader,
                    limit: Annotated[int, Query(ge=1, le=200)] = 100,
                    offset: Annotated[int, Query(ge=0)] = 0):
    """Every change with its old and new value, who made it (or 'system'), why,
    and which file caused it (FR-037). Newest first."""
    if reader.get_profile(profile_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Profile not found")
    total, items = reader.change_history(profile_id, limit, offset)
    return ChangeListOut(total=total, limit=limit, offset=offset,
                         items=[ChangeOut.model_validate(c) for c in items])
