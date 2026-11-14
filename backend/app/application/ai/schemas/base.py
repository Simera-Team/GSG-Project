"""Shared Pydantic configuration for the AI module's schemas."""

from pydantic import BaseModel, ConfigDict


class AIBaseSchema(BaseModel):
    """Base configuration for AI-related schemas.

    ``extra="forbid"`` is what makes the field catalogue binding: an LLM answer
    carrying a key the model does not define fails validation as a whole (R-01),
    which is how protected traits such as ``age`` are kept out (R-04).
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )


class AIInputSchema(BaseModel):
    """Base configuration for payloads the backend hands to this module.

    Unknown keys are ignored rather than rejected, so the backend can add
    fields to its text-extraction output without breaking the AI module.
    """

    model_config = ConfigDict(
        extra="ignore",
        str_strip_whitespace=True,
    )
