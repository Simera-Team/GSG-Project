import hashlib
import json
import logging
import zipfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import filetype

from app.application.dto.RequestDto.upload_file_dto import UploadFileDTO
from app.application.interfaces.file_storage import IFileStorage
from app.application.interfaces.message_publisher import IMessagePublisher
from app.application.interfaces.unit_of_work import IUnitOfWork

from app.domain.entities.source_file import SourceFile
from app.domain.interfaces.profile_repository import IProfileRepository
from app.domain.interfaces.source_file_repository import ISourceFileRepository

from app.core.exceptions import (
    InvalidFileTypeError,
    EmptyFileError,
    FileTooLargeError,
    InvalidFileContentError,
    DuplicateFileError,
    DuplicateSourceFileHashError,
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
    file_id: int          # also the job reference (one job per source file)
    filename: str
    storage_path: str
    size: int
    file_hash: str
    status: str
    queued: bool          # False when publishing to the worker queue failed


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

        # Step 1: Validate file and compute its SHA-256 hash
        validated_file = self.validate_file(file)

        storage_path: str | None = None

        try:
            # Step 2: Get or create user profile
            profile = self.profile_repository.get_or_create_by_user_id(
                user_id
            )

            if profile.profile_id is None:
                raise RuntimeError(
                    "Profile ID was not generated"
                )

            # Step 3: Duplicate detection (hash is unique per candidate).
            # Done before storing, so an identical upload changes nothing.
            existing = self.source_file_repository.get_by_profile_and_hash(
                profile.profile_id,
                validated_file.file_hash
            )

            if existing is not None:
                self._raise_duplicate(profile.profile_id, existing)

            # Step 4: Save the original file (write-once storage)
            storage_path = self.storage.save(
                validated_file.content,
                validated_file.extension
            )

            # Step 5: Create the job (a source_file with status 'uploaded')
            source_file = SourceFile(
                file_id=None,
                profile_id=profile.profile_id,
                file_type=validated_file.extension.lstrip("."),
                original_name=validated_file.filename,
                file_hash=validated_file.file_hash,
                storage_path=storage_path,
                status="uploaded"
            )

            try:
                saved_file = self.source_file_repository.create(
                    source_file
                )

            except DuplicateSourceFileHashError:
                # Another request with the same file won the race
                self.unit_of_work.rollback()
                self.storage.discard(storage_path)
                storage_path = None

                existing = (
                    self.source_file_repository.get_by_profile_and_hash(
                        profile.profile_id,
                        validated_file.file_hash
                    )
                )

                if existing is None:
                    raise

                self._raise_duplicate(profile.profile_id, existing)

            if saved_file.file_id is None:
                raise RuntimeError(
                    "File ID was not generated"
                )

            # Step 6: Commit transaction
            self.unit_of_work.commit()

        except DuplicateFileError:
            self.unit_of_work.rollback()
            raise

        except Exception:
            # Rollback all database changes and remove the file that never
            # became a source
            self.unit_of_work.rollback()

            if storage_path is not None:
                self.storage.discard(storage_path)

            raise

        # Step 7: Hand the job to the workers. The job is already saved, so a
        # broker failure must not fail the upload (NFR-010 / NFR-012); the job
        # stays 'uploaded' and can be picked up later.
        queued = True

        try:
            await self.message_publisher.publish_cv(saved_file.file_id)

        except Exception:
            queued = False
            logger.exception(
                "Could not enqueue job %s; it stays 'uploaded'",
                saved_file.file_id
            )

        # Step 8: Return the job reference immediately (FR-013)
        return UploadCVResult(
            file_id=saved_file.file_id,
            filename=validated_file.filename,
            storage_path=storage_path,
            size=validated_file.size,
            file_hash=validated_file.file_hash,
            status=saved_file.status,
            queued=queued
        )

    @staticmethod
    def _raise_duplicate(profile_id: int, existing: SourceFile) -> None:
        if existing.file_id is None:
            raise RuntimeError("Existing file has no ID")

        # FR-055: every blocked duplicate is logged
        logger.info(
            "Blocked duplicate upload: profile_id=%s existing_file_id=%s "
            "file_hash=%s",
            profile_id,
            existing.file_id,
            existing.file_hash
        )

        raise DuplicateFileError(
            existing_file_id=existing.file_id,
            existing_status=existing.status
        )
