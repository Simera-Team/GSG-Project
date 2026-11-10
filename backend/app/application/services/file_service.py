
import hashlib
import json
import zipfile
import logging
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from app.application.interfaces.message_publisher import IMessagePublisher
import filetype

from app.application.dto.RequestDto.upload_file_dto import UploadFileDTO
from app.application.interfaces.file_storage import IFileStorage
from app.application.interfaces.unit_of_work import IUnitOfWork

from app.domain.entities.source_file import SourceFile
from app.domain.interfaces.profile_repository import IProfileRepository
from app.domain.interfaces.source_file_repository import ISourceFileRepository

from app.core.exceptions import (
    InvalidFileTypeError,
    EmptyFileError,
    FileTooLargeError,
    InvalidFileContentError,
)

logger = logging.getLogger(__name__)

@dataclass
class ValidatedFile:
    filename: str
    extension: str
    size: int
    file_hash: str
    content: bytes


@dataclass
class UploadCVResult:
    file_id: int
    filename: str
    storage_path: str
    size: int
    file_hash: str


class FileService:

    MAX_FILE_SIZE = 10 * 1024 * 1024
    ALLOWED_EXTENSIONS = {".pdf", ".docx", ".md", ".json"}

    def __init__(
        self,
        storage: IFileStorage,
        source_file_repository: ISourceFileRepository,
        profile_repository: IProfileRepository,
        unit_of_work: IUnitOfWork,
        message_publisher: IMessagePublisher
    ):
        self.storage = storage
        self.source_file_repository = source_file_repository
        self.profile_repository = profile_repository
        self.unit_of_work = unit_of_work
        self.message_publisher = message_publisher

    def validate_file(
        self,
        file: UploadFileDTO
    ) -> ValidatedFile:

        # Step 1: Validate extension
        filename = Path(file.filename).name
        extension = Path(filename).suffix.lower()

        if extension not in self.ALLOWED_EXTENSIONS:
            raise InvalidFileTypeError(
                "Only PDF, DOCX, MD and JSON files are allowed"
            )

        # Step 2: Validate size
        content = file.content
        size = len(content)

        if size == 0:
            raise EmptyFileError(
                "File cannot be empty"
            )

        if size > self.MAX_FILE_SIZE:
            raise FileTooLargeError(
                "File size exceeds 10 MB"
            )

        # Step 3: Validate actual content
        self._validate_content(content, extension)

        # Step 4: Calculate SHA-256
        file_hash = hashlib.sha256(content).hexdigest()

        return ValidatedFile(
            filename=filename,
            extension=extension,
            size=size,
            file_hash=file_hash,
            content=content
        )

    def _validate_content(
        self,
        content: bytes,
        extension: str
    ) -> None:

        if extension == ".pdf":
            detected = filetype.guess(content)

            if detected is None or detected.extension != "pdf":
                raise InvalidFileContentError(
                    "Invalid PDF file"
                )

        elif extension == ".docx":
            try:
                with zipfile.ZipFile(BytesIO(content)) as archive:
                    names = set(archive.namelist())

                    required_files = {
                        "[Content_Types].xml",
                        "word/document.xml"
                    }

                    if not required_files.issubset(names):
                        raise InvalidFileContentError(
                            "Invalid DOCX structure"
                        )

                    if archive.testzip() is not None:
                        raise InvalidFileContentError(
                            "Corrupted DOCX file"
                        )

            except (
                zipfile.BadZipFile,
                RuntimeError,
                OSError,
                ValueError
            ) as exc:
                raise InvalidFileContentError(
                    "Invalid DOCX file"
                ) from exc

        elif extension in {".md", ".json"}:
            try:
                text = content.decode("utf-8-sig")

            except UnicodeDecodeError as exc:
                raise InvalidFileContentError(
                    "File must contain valid UTF-8 text"
                ) from exc

            if extension == ".json":
                try:
                    json.loads(text)

                except (json.JSONDecodeError, ValueError) as exc:
                    raise InvalidFileContentError(
                        "Invalid JSON content"
                    ) from exc

    async def upload_cv(
        self,
        file: UploadFileDTO,
        user_id: int
    ) -> UploadCVResult:

        # Step 1: Validate file
        validated_file = self.validate_file(file)

        # Step 2: Save file to storage
        storage_path = self.storage.save(
            validated_file.content,
            validated_file.extension
        )

        try:
            # Step 3: Get or create user profile
            profile = self.profile_repository.get_or_create_by_user_id(
                user_id
            )

            if profile.profile_id is None:
                raise RuntimeError(
                    "Profile ID was not generated"
                )

            # Step 4: Create SourceFile entity
            source_file = SourceFile(
                file_id=None,
                profile_id=profile.profile_id,
                file_type=validated_file.extension.lstrip("."),
                original_name=validated_file.filename,
                file_hash=validated_file.file_hash,
                storage_path=storage_path,
                status="uploaded"
            )

            # Step 5: Insert metadata into database
            saved_file = self.source_file_repository.create(
                source_file
            )

            if saved_file.file_id is None:
                raise RuntimeError(
                    "File ID was not generated"
                )

           
            # Step 6: Commit transaction
            self.unit_of_work.commit()

        except Exception:
            try:
                self.unit_of_work.rollback()
            finally:
                try:
                    self.storage.delete(storage_path)
                except Exception:
                    logger.exception(
                        "Failed to delete file after upload failure: %s",
                        storage_path
                    )
            raise

        # Step 7: Publish message after successful commit
        await self.message_publisher.publish_cv(
            saved_file.file_id
        )

        # Step 8: Return result
        return UploadCVResult(
            file_id=saved_file.file_id,
            filename=validated_file.filename,
            storage_path=storage_path,
            size=validated_file.size,
            file_hash=validated_file.file_hash
        )

      
      
