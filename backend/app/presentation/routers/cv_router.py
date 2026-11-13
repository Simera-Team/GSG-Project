from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Path,
    Query,
    Response,
    UploadFile,
    status
)

from app.application.dto.RequestDto.upload_file_dto import UploadFileDTO
from app.application.interfaces.read_repository import IReadRepository
from app.application.services.file_service import FileService
from app.core.dependencies import get_file_service, get_read_repository, require_permission
from app.core.exceptions import (
    InvalidFileTypeError,
    EmptyFileError,
    FileTooLargeError,
    InvalidFileContentError,
)
from app.domain.entities.user import User
from app.domain.permissions import Permission
from app.presentation.schemas.file_schema import FileListOut, FileOut, UploadCVResponse


router = APIRouter(
    prefix="/cv",
    tags=["CV"]
)

Reader = Annotated[IReadRepository, Depends(get_read_repository)]
SourceViewer = Annotated[User, Depends(require_permission(Permission.SOURCE_VIEW_OWN))]


@router.post(
    "/upload",
    response_model=UploadCVResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        200: {"description": "You already uploaded this exact file; nothing new is queued"},
        400: {"description": "Wrong type, empty or broken file"},
        401: {"description": "Not logged in"},
        403: {"description": "Not allowed to upload"},
        413: {"description": "Larger than 10 MB"},
    },
    summary="Upload a CV or LinkedIn export",
)
async def upload_cv(
    file: Annotated[
        UploadFile,
        File(description="PDF or Word CV, LinkedIn Markdown export (.md), max 10 MB")
    ],
    file_service: Annotated[
        FileService,
        Depends(get_file_service)
    ],
    user: Annotated[
        User,
        Depends(require_permission(Permission.SOURCE_UPLOAD))
    ],
    response: Response,
):
    """Stores the file unchanged, queues it for processing and answers at once
    (FR-013). The CV worker then extracts the text (OCR for scans), reads the
    fields with the LLM, checks them and updates the profile; follow it with
    `GET /cv/files/{file_id}`."""
    try:
        # Step 1: Read file (maximum 10 MB + 1 byte)
        content = await file.read(
            FileService.MAX_FILE_SIZE + 1
        )

        # Step 2: Create DTO
        upload_dto = UploadFileDTO(
            filename=file.filename or "",
            content=content
        )

        # Step 3: Upload CV using authenticated user ID
        result = await file_service.upload_cv(
            file=upload_dto,
            user_id=user.user_id
        )

    except FileTooLargeError as exc:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=str(exc)
        ) from exc

    except (
        InvalidFileTypeError,
        EmptyFileError,
        InvalidFileContentError
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc)
        ) from exc

    finally:
        await file.close()

    # Step 4: Same file again from this candidate -> nothing new queued (FR-012)
    if getattr(result, "duplicate", False):
        response.status_code = status.HTTP_200_OK
        return UploadCVResponse(
            file_id=result.file_id,
            filename=result.filename,
            size=result.size,
            status="duplicate",
            duplicate=True,
            message="You already uploaded this file; it was not processed again"
        )

    # Step 5: Return response
    return UploadCVResponse(
        file_id=result.file_id,
        filename=result.filename,
        size=result.size,
        status="uploaded",
        message="CV uploaded successfully and queued for processing"
    )


@router.get(
    "/files",
    response_model=FileListOut,
    responses={401: {"description": "Not logged in"}},
    summary="My uploads and their status",
)
def my_files(
    user: SourceViewer,
    reader: Reader,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    """Each upload with its state: uploaded, processing, done, needs_review or
    failed (FR-014). Newest first."""
    profile_id = reader.profile_id_for_user(user.user_id)
    if profile_id is None:
        return FileListOut(total=0, limit=limit, offset=offset, items=[])
    total, files = reader.list_files(profile_id, None, limit, offset)
    return FileListOut(total=total, limit=limit, offset=offset,
                       items=[FileOut.model_validate(f) for f in files])


@router.get(
    "/files/{file_id}",
    response_model=FileOut,
    responses={401: {"description": "Not logged in"},
               404: {"description": "No such file among your uploads"}},
    summary="One of my uploads",
)
def my_file(file_id: Annotated[int, Path(ge=1)], user: SourceViewer, reader: Reader):
    """Poll this after uploading to see when processing has finished."""
    found = reader.get_file(file_id)
    # Someone else's file looks exactly like a missing one (FR-055, NFR-016).
    if found is None or found.user_id != user.user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File not found")
    return FileOut.model_validate(found)
