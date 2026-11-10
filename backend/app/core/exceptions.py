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
