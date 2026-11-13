from typing import Annotated

from fastapi import (
    APIRouter,
    BackgroundTasks,
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

from app.core.auth_dependencies import get_current_user_id
from app.core.background_processing import process_file_in_background
from app.core.config import settings
from app.core.dependencies import get_file_service, get_read_repository

from app.core.exceptions import (
    InvalidFileTypeError,
    EmptyFileError,
    FileTooLargeError,
    InvalidFileContentError,
)
from app.presentation.schemas.file_schema import FileListOut, FileOut, UploadOut


router = APIRouter(
    prefix="/cv",
    tags=["CV"]
)

Reader = Annotated[IReadRepository, Depends(get_read_repository)]
UserId = Annotated[int, Depends(get_current_user_id)]


@router.post(
    "/upload",
    response_model=UploadOut,
    status_code=status.HTTP_201_CREATED,
    responses={
        200: {"description": "You already uploaded this exact file; nothing new is created"},
        400: {"description": "Wrong type, empty or broken file"},
        401: {"description": "Not logged in"},
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
    user_id: UserId,
    background: BackgroundTasks,
    response: Response,
):
    """Stores the file unchanged and answers at once (FR-013). Processing - text
    extraction, OCR, Gemini, review checks, profile update - then runs in the
    background; follow it with `GET /cv/files/{file_id}`."""
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
            user_id=user_id
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

    # Step 4: Same file again -> no new job (FR-012)
    if result.duplicate:
        response.status_code = status.HTTP_200_OK
        return UploadOut(
            file_id=result.file_id, filename=result.filename, size=result.size,
            file_hash=result.file_hash, status="done", duplicate=True,
            message="You already uploaded this file; it was not processed again"
        )

    # Step 5: Process after the response is sent
    if settings.PROCESS_UPLOADS_AUTOMATICALLY:
        background.add_task(process_file_in_background, result.file_id)
        message = "CV uploaded; processing has started"
    else:
        message = "CV uploaded; processing is not automatic on this server"

    return UploadOut(
        file_id=result.file_id, filename=result.filename, size=result.size,
        file_hash=result.file_hash, status="uploaded", duplicate=False, message=message
    )


@router.get(
    "/files",
    response_model=FileListOut,
    responses={401: {"description": "Not logged in"}},
    summary="My uploads and their status",
)
def my_files(
    user_id: UserId,
    reader: Reader,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    """Each upload with its state: uploaded, processing, done, needs_review or
    failed (FR-014). Newest first."""
    profile_id = reader.profile_id_for_user(user_id)
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
def my_file(file_id: Annotated[int, Path(ge=1)], user_id: UserId, reader: Reader):
    """Poll this after uploading to see when processing has finished."""
    found = reader.get_file(file_id)
    # Someone else's file looks exactly like a missing one (FR-055, NFR-016).
    if found is None or found.user_id != user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File not found")
    return FileOut.model_validate(found)
