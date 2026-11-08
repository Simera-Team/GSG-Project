from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.application.services.file_service import FileService
from app.core.dependencies import get_file_service, require_permission
from app.core.exceptions import SourceFileNotFoundError
from app.domain.entities.user import User
from app.domain.permissions import Permission
from app.presentation.schemas.file_schema import UploadStatusResponse


router = APIRouter(
    prefix="/files",
    tags=["Files"]
)

FileServiceDep = Annotated[FileService, Depends(get_file_service)]
SourceViewer = Annotated[
    User,
    Depends(require_permission(Permission.SOURCE_VIEW_OWN))
]


@router.get("", response_model=list[UploadStatusResponse])
def list_upload_statuses(
    file_service: FileServiceDep,
    user: SourceViewer
):
    return file_service.list_upload_statuses(user.user_id)


@router.get("/{file_id}", response_model=UploadStatusResponse)
def get_upload_status(
    file_id: int,
    file_service: FileServiceDep,
    user: SourceViewer
):
    try:
        return file_service.get_upload_status(file_id, user)

    except SourceFileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc)
        ) from exc
