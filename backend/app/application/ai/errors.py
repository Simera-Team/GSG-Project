"""Typed errors the AI module raises, so the caller knows whether to retry.

The contract fixes both the meaning and the retry budget of each error, so the
budget lives on the class instead of in the calling worker.
"""

from app.core.exceptions import AppException


class AIModuleError(AppException):
    """Base class for every error raised by the AI module."""

    #: Whether retrying the same call can plausibly succeed.
    retryable: bool = False

    #: How many attempts the caller should make in total, including the first.
    max_attempts: int = 1


class LLMUnavailableError(AIModuleError):
    """Provider timed out or rate-limited the call.

    A timeout or rate limit usually spends few or no tokens, so the caller
    retries with backoff.
    """

    retryable = True
    max_attempts = 3

    def __init__(self, message: str = "LLM provider is unavailable") -> None:
        super().__init__(message)


class LLMInvalidOutputError(AIModuleError):
    """The answer failed schema validation (R-01).

    Each retry is a full LLM call and costs the same tokens again, so the
    budget is smaller than for provider errors. After the last attempt the
    whole file goes to the review queue as a failed job and no fields are
    saved from it.
    """

    retryable = True
    max_attempts = 2

    def __init__(self, message: str = "LLM answer failed schema validation") -> None:
        super().__init__(message)


class NoUsableTextError(AIModuleError):
    """No text on any page, even after OCR. Never retried."""

    retryable = False
    max_attempts = 1

    def __init__(self, message: str = "Source has no usable text") -> None:
        super().__init__(message)


class UnsupportedLanguageError(AIModuleError):
    """Source text is not English, so it is rejected before the LLM call.

    Only English-language sources are accepted, and the rejection happens
    before extraction so no tokens are spent on it.
    """

    retryable = False
    max_attempts = 1

    def __init__(self, message: str = "Only English-language sources are accepted") -> None:
        super().__init__(message)
