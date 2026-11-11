class AppException(Exception):
    """Base exception for application errors."""
    pass


class EmailAlreadyExistsError(AppException):
    def __init__(self, message: str = "Email already registered"):
        super().__init__(message)


class InvalidCredentialsError(AppException):
    def __init__(self, message: str = "Invalid email or password"):
        super().__init__(message)


class PermissionDeniedError(AppException):
    def __init__(self, message: str = "You do not have access to this resource"):
        super().__init__(message)


class InvalidFileTypeError(Exception):
    pass


class EmptyFileError(Exception):
    pass


class FileTooLargeError(Exception):
    pass


class InvalidFileContentError(Exception):
    pass


class DuplicateFileError(Exception):
    """The same candidate already uploaded a file with this SHA-256 hash."""

    def __init__(self, existing_file_id: int, existing_status: str):
        self.existing_file_id = existing_file_id
        self.existing_status = existing_status
        super().__init__(
            "This file was already uploaded and is "
            f"'{existing_status}' (job {existing_file_id})"
        )


class DuplicateSourceFileHashError(Exception):
    """Raised by the repository when the (profile_id, file_hash) unique
    constraint rejects an insert (two identical uploads racing)."""
    pass
