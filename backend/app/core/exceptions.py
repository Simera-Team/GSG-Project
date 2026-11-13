class AppException(Exception):
    """Base exception for application errors."""
    pass


class EmailAlreadyExistsError(AppException):
    def __init__(self, message: str = "Email already registered"):
        super().__init__(message)


class LLMProviderError(AppException):
    """One LLM call failed (network, rate limit, bad key, server error...).

    retryable: whether trying again can help (FR-023).
    retry_after: seconds the provider asked us to wait, if any.
    """

    def __init__(self, message: str, retryable: bool, retry_after: float | None = None):
        super().__init__(message)
        self.retryable = retryable
        self.retry_after = retry_after


class LLMConfigurationError(AppException):
    """The LLM client cannot be created (missing key, unknown provider)."""
    pass


class ReviewNotFoundError(AppException):
    pass


class ReviewStateError(AppException):
    """The item cannot be changed in its current state (e.g. already resolved)."""
    pass


class ReviewInputError(AppException):
    """The reviewer's decision is not valid for this field."""
    pass


class InvalidCredentialsError(AppException):
    def __init__(self, message: str = "Invalid email or password"):
        super().__init__(message)


class InvalidFileTypeError(Exception):
    pass


class EmptyFileError(Exception):
    pass


class FileTooLargeError(Exception):
    pass


class InvalidFileContentError(Exception):
    pass
