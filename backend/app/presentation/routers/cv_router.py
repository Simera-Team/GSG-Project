
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    File,
    UploadFile,
    HTTPException,
    status
)

from app.presentation.schemas.file_schema import UploadCVResponse

from app.application.dto.RequestDto.upload_file_dto import UploadFileDTO
from app.application.services.file_service import FileService

from app.core.dependencies import get_file_service, require_permission

from app.core.exceptions import (
    InvalidFileTypeError,
    EmptyFileError,
    FileTooLargeError,
    InvalidFileContentError,
    DuplicateFileError,
)

from app.domain.entities.user import User
from app.domain.permissions import Permission


router = APIRouter(
    prefix="/cv",
    tags=["CV"]
)


@router.post(
    "/upload",
    response_model=UploadCVResponse,
    status_code=status.HTTP_202_ACCEPTED
)
async def upload_cv(
    file: Annotated[
        UploadFile,
        File()
    ],
    file_service: Annotated[
        FileService,
        Depends(get_file_service)
    ],
    user: Annotated[
        User,
        Depends(require_permission(Permission.SOURCE_UPLOAD))
    ]
):
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

        # Step 4: Return response
        return UploadCVResponse(
            file_id=result.file_id,
            job_id=result.file_id,
            filename=result.filename,
            size=result.size,
            file_hash=result.file_hash,
            status=result.status,
            message=(
                "CV uploaded successfully and queued for processing"
                if result.queued
                else "CV uploaded successfully; processing will start later"
            )
        )

    except DuplicateFileError as exc:
        # FR-012: identical source changes nothing; tell the user it
        # was already uploaded and point to the existing job
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "This file was already uploaded",
                "file_id": exc.existing_file_id,
                "job_id": exc.existing_file_id,
                "status": exc.existing_status
            }
        ) from exc

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
