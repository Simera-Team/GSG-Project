"""Review queue API (FR-041 - FR-044, FR-062, FR-066).

Only reviewers and administrators can use it (FR-003); every request checks
the role in the database (NFR-016).
"""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from app.application.services.review_service import ReviewService
from app.core.auth_dependencies import require_reviewer
from app.core.dependencies import get_review_service
from app.core.exceptions import ReviewInputError, ReviewNotFoundError, ReviewStateError
from app.domain.entities.user import User
from app.presentation.schemas.review_schema import (
    CandidateRequestOut,
    ResolveRequest,
    ReviewItemOut,
    ReviewListOut,
)

router = APIRouter(prefix="/review", tags=["Review"])

Reviewer = Annotated[User, Depends(require_reviewer)]
Service = Annotated[ReviewService, Depends(get_review_service)]
ReviewId = Annotated[int, Path(ge=1)]

ERRORS = {
    401: {"description": "Not logged in"},
    403: {"description": "Not a reviewer or administrator"},
}


def _to_out(item) -> ReviewItemOut:
    return ReviewItemOut.model_validate(item, from_attributes=True)


def _http(exc: Exception) -> HTTPException:
    if isinstance(exc, ReviewNotFoundError):
        return HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    if isinstance(exc, ReviewStateError):
        return HTTPException(status.HTTP_409_CONFLICT, str(exc))
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc))


@router.get("/items", response_model=ReviewListOut, responses=ERRORS,
            summary="List the review queue")
def list_items(
    reviewer: Reviewer,
    service: Service,
    status_filter: Annotated[
        Literal["open", "waiting_candidate", "resolved", "all"],
        Query(alias="status", description="open = not resolved yet (default)")] = "open",
    reason: Annotated[str | None, Query(description="e.g. unknown_skill, llm_failed")] = None,
    profile_id: Annotated[int | None, Query(ge=1)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    """Each item shows the candidate, the field and every differing value with its
    source file, confidence and evidence (FR-041). Failed jobs appear with no
    field name and link to the source file only (FR-042). Oldest first."""
    total, items = service.list_items(status_filter, reason, profile_id, limit, offset)
    return ReviewListOut(total=total, limit=limit, offset=offset,
                         items=[_to_out(i) for i in items])


@router.get("/items/{review_id}", response_model=ReviewItemOut,
            responses={**ERRORS, 404: {"description": "No such item"}},
            summary="Open one review item")
def get_item(review_id: ReviewId, reviewer: Reviewer, service: Service):
    """The values side by side with their evidence snippet and page (FR-043)."""
    try:
        return _to_out(service.get_item(review_id))
    except ReviewNotFoundError as exc:
        raise _http(exc) from exc


@router.post("/items/{review_id}/resolve", response_model=ReviewItemOut,
             responses={**ERRORS, 404: {"description": "No such item"},
                        409: {"description": "Already resolved"},
                        422: {"description": "Decision not valid for this field"}},
             summary="Decide a review item")
def resolve(review_id: ReviewId, body: ResolveRequest, reviewer: Reviewer, service: Service):
    """Pick an option or type a corrected value; the decision is saved with the
    reviewer and time (FR-043, FR-066), applied to the live profile, and logged in
    the profile change history. For an unknown skill, picking it approves it as a
    new standard skill, or `map_to_skill` maps it to an existing one and saves the
    alias for next time (FR-062)."""
    try:
        return _to_out(service.resolve(review_id, reviewer, body.action, body.option_id,
                                       body.value, body.map_to_skill))
    except (ReviewNotFoundError, ReviewStateError, ReviewInputError) as exc:
        raise _http(exc) from exc


@router.post("/items/{review_id}/request-candidate", response_model=CandidateRequestOut,
             responses={**ERRORS, 404: {"description": "No such item"},
                        409: {"description": "Already resolved"}},
             summary="Ask the candidate for clarification")
def request_candidate(review_id: ReviewId, reviewer: Reviewer, service: Service):
    """Leave the item unresolved and record that the candidate was asked and when
    (FR-044). The live profile is not changed. No e-mail is sent by the server
    yet: the reviewer sends the suggested message to the returned address."""
    try:
        item = service.request_candidate(review_id, reviewer)
    except (ReviewNotFoundError, ReviewStateError) as exc:
        raise _http(exc) from exc

    what = f"'{item.field_name}' ({item.entity})" if item.field_name else "your uploaded file"
    message = (f"Hello {item.candidate_name}, while reviewing {item.file_name} we could not "
               f"confirm {what}. Could you reply with the correct value or a document that "
               f"shows it? Thank you.")
    return CandidateRequestOut(item=_to_out(item), candidate_email=item.candidate_email,
                               suggested_message=message)
