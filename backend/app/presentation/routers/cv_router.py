
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    File,
    UploadFile,
    HTTPException,
    status
)

from app.application.dto.RequestDto.upload_file_dto import UploadFileDTO
from app.application.services.file_service import FileService

from app.core.dependencies import get_file_service, require_permission

from app.core.exceptions import (
    InvalidFileTypeError,
    EmptyFileError,
    FileTooLargeError,
    InvalidFileContentError,
)

from app.domain.entities.user import User
from app.domain.permissions import Permission


router = APIRouter(
    prefix="/cv",
    tags=["CV"]
)


@router.post(
    "/upload",
    status_code=status.HTTP_201_CREATED
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

        # Step 4: Return result
        return {
            "file_id": result.file_id,
            "filename": result.filename,
            "size": result.size,
            "file_hash": result.file_hash,
            "message": "CV uploaded successfully"
        }

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
