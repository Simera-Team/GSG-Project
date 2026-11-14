"""The application's contract for generating a structured answer from an LLM.

Named after what it does rather than what it talks to: the application asks for
one validated instance of a schema it chose, and does not know which framework,
provider or model answers. Every LangChain detail lives behind the concrete
implementation in ``app.infrastructure.ai`` (NFR-035).
"""

from abc import ABC, abstractmethod
from typing import TypeVar

from pydantic import BaseModel


T = TypeVar("T", bound=BaseModel)


class IStructuredOutputGenerator(ABC):
    """Returns one instance of ``output_schema``, validated against it."""

    @abstractmethod
    async def generate_structured_output(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        output_schema: type[T],
    ) -> T:
        """Ask the model for ``output_schema`` and return the parsed result.

        Implementations raise
        :class:`~app.application.ai.errors.LLMUnavailableError` when the
        provider times out or rate-limits the call, and
        :class:`~app.application.ai.errors.LLMInvalidOutputError` when the
        answer cannot be validated against ``output_schema``.
        """
        ...
