"""The one LLM-backed step: document text to a validated schema instance.

Everything the model touches ends here. Normalization, evidence checking,
scoring and conflict resolution are all deterministic code, so the model never
decides between values; it only reports what one document says.
"""

import asyncio
import logging

from app.application.ai.errors import (
    LLMInvalidOutputError,
    LLMUnavailableError,
    NoUsableTextError,
)
from app.application.ai.extraction.prompts import SYSTEM_PROMPT, build_user_prompt
from app.application.ai.schemas.document_text import DocumentText
from app.application.ai.schemas.extracted_profile import ExtractedProfile
from app.application.ai.settings import AISettings
from app.application.interfaces.structured_output_generator import (
    IStructuredOutputGenerator,
)

logger = logging.getLogger(__name__)

#: Seconds to wait before each attempt. Index 0 is the first retry.
_BACKOFF_SECONDS = (1.0, 4.0, 9.0)


class ProfileExtractor:
    """Asks the model for one :class:`ExtractedProfile` per source.

    Retry budgets differ by failure: a provider timeout or rate limit usually
    spends few or no tokens, while an answer that fails schema validation costs
    a full call every time, so it gets fewer attempts.
    """

    def __init__(
        self,
        generator: IStructuredOutputGenerator,
        settings: AISettings | None = None,
    ) -> None:
        self._generator = generator
        self._settings = settings or AISettings()

    async def extract(self, document: DocumentText) -> ExtractedProfile:
        """Return the model's structured reading of ``document``.

        Raises :class:`NoUsableTextError` before spending any tokens on a
        source with no text, :class:`LLMUnavailableError` when the provider
        never answered, and :class:`LLMInvalidOutputError` when no attempt
        produced a valid answer.
        """
        if not document.has_usable_text():
            raise NoUsableTextError(
                f"Source {document.source_id} has no text on any page"
            )

        user_prompt = build_user_prompt(document)

        provider_attempts = 0
        invalid_attempts = 0
        last_error: Exception | None = None

        while True:
            try:
                return await self._generator.generate_structured_output(
                    system_prompt=SYSTEM_PROMPT,
                    user_prompt=user_prompt,
                    output_schema=ExtractedProfile,
                )

            except LLMUnavailableError as error:
                provider_attempts += 1
                last_error = error
                if provider_attempts >= self._settings.max_provider_attempts:
                    raise
                await self._backoff(provider_attempts)

            except LLMInvalidOutputError as error:
                invalid_attempts += 1
                last_error = error
                # Never log the answer itself: it holds the candidate's own
                # details, which must stay out of application logs (NFR-022).
                logger.warning(
                    "Schema validation failed for source %s on attempt %d",
                    document.source_id,
                    invalid_attempts,
                )
                if invalid_attempts >= self._settings.max_invalid_output_attempts:
                    raise LLMInvalidOutputError(
                        f"Source {document.source_id} failed schema validation "
                        f"on {invalid_attempts} attempts"
                    ) from last_error
                await self._backoff(invalid_attempts)

    async def _backoff(self, attempt: int) -> None:
        delay = _BACKOFF_SECONDS[min(attempt - 1, len(_BACKOFF_SECONDS) - 1)]
        await asyncio.sleep(delay)
