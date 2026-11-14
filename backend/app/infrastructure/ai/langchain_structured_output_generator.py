"""LangChain implementation of the structured-output contract.

This is the only module in the codebase that imports LangChain. The chat model
is injected, so no provider or model name is chosen here: the caller wiring the
container decides, and swapping providers touches nothing above this file
(NFR-035).
"""

from typing import TypeVar

from langchain_core.exceptions import OutputParserException
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, ValidationError

from app.application.ai.errors import LLMInvalidOutputError, LLMUnavailableError
from app.application.interfaces.structured_output_generator import (
    IStructuredOutputGenerator,
)


T = TypeVar("T", bound=BaseModel)


class LangChainStructuredOutputGenerator(IStructuredOutputGenerator):
    """Generates structured output through a LangChain chat model.

    ``with_structured_output`` hands the Pydantic schema to the provider's own
    structured-output or tool-calling mechanism, so the model is constrained by
    the schema rather than asked to produce JSON in prose.
    """

    def __init__(self, chat_model: BaseChatModel) -> None:
        self._chat_model = chat_model

    async def generate_structured_output(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        output_schema: type[T],
    ) -> T:
        structured_model = self._chat_model.with_structured_output(output_schema)
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]

        try:
            answer = await structured_model.ainvoke(messages)
        except (OutputParserException, ValidationError) as error:
            # The provider answered, but not with something the schema accepts.
            raise LLMInvalidOutputError(str(error)) from error
        except Exception as error:  # noqa: BLE001 - provider errors vary by SDK
            # Timeouts, rate limits and transport failures all land here; each
            # SDK raises its own types, so they are mapped by position in the
            # call rather than by class.
            raise LLMUnavailableError(str(error)) from error

        if not isinstance(answer, output_schema):
            raise LLMInvalidOutputError(
                f"Expected {output_schema.__name__}, got {type(answer).__name__}"
            )

        return answer
