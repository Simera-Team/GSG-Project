"""Google Gemini implementation of IAIClient.

One call per attempt: the SDK's own retries are turned off so the
application service controls retries and records every try (FR-023, FR-058).
Model, timeout and thinking level come from settings.
"""

import copy

from google import genai
from google.genai import _interactions as gemini_errors  # error classes of the Interactions API
from google.genai import types as genai_types

from app.application.interfaces.ai_client import IAIClient, LLMResponse
from app.core.exceptions import LLMConfigurationError, LLMProviderError

RATE_LIMIT_WAIT_SECONDS = 30.0   # free tier has per-minute request limits


class GeminiAIClient(IAIClient):

    provider = "gemini"

    def __init__(self, api_key: str | None, model: str,
                 timeout_seconds: float = 120.0, thinking_level: str = "medium"):
        if not api_key:
            raise LLMConfigurationError("GEMINI_API_KEY is not set in .env")
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.thinking_level = thinking_level
        self.client = genai.Client(
            api_key=api_key,
            http_options=genai_types.HttpOptions(
                retry_options=genai_types.HttpRetryOptions(attempts=1)
            ),
        )

    def generate_structured(self, system_prompt: str, user_prompt: str,
                            json_schema: dict) -> LLMResponse:
        try:
            interaction = self.client.interactions.create(
                model=self.model,
                system_instruction=system_prompt,
                input=user_prompt,
                response_format={
                    "type": "text",
                    "mime_type": "application/json",
                    "schema": to_gemini_schema(json_schema),
                },
                generation_config={"temperature": 0, "thinking_level": self.thinking_level},
                store=False,       # do not keep the CV on Google's side after the call
                timeout=self.timeout_seconds,
            )
        except gemini_errors.RateLimitError as exc:
            raise LLMProviderError("rate limit reached (429)", retryable=True,
                                   retry_after=RATE_LIMIT_WAIT_SECONDS) from exc
        except gemini_errors.APIStatusError as exc:
            # 4xx (bad key, unknown model, bad request): retrying will not help.
            raise LLMProviderError(f"{exc.status_code}: {_short(exc)}",
                                   retryable=exc.status_code >= 500) from exc
        except gemini_errors.APIConnectionError as exc:   # includes timeouts
            raise LLMProviderError(f"network error or timeout: {exc}", retryable=True) from exc

        usage = interaction.usage.model_dump(exclude_none=True) if interaction.usage else {}
        return LLMResponse(
            text=interaction.output_text,
            provider=self.provider,
            model_version=str(interaction.model or self.model),
            status=str(interaction.status),
            usage=usage,
        )


def to_gemini_schema(schema: dict) -> dict:
    """Simplify a Pydantic JSON schema for Gemini.

    - inlines $ref / $defs
    - turns `anyOf: [X, null]` into `type: [X, "null"]` (Gemini's nullable form)
    - drops keys Gemini does not use (title, default, additionalProperties);
      these rules are still enforced locally by the validator.
    """
    defs = schema.get("$defs", {})
    unused = {"$defs", "title", "default", "additionalProperties"}

    def walk(node):
        if isinstance(node, list):
            return [walk(n) for n in node]
        if not isinstance(node, dict):
            return node
        if "$ref" in node:
            target = copy.deepcopy(defs[node["$ref"].split("/")[-1]])
            extra = {k: v for k, v in node.items() if k != "$ref"}
            return walk({**target, **extra})

        node = {
            # "properties" maps field names -> schemas: keep every field name
            # (a field may itself be called "title").
            k: ({name: walk(sub) for name, sub in v.items()} if k == "properties" else walk(v))
            for k, v in node.items() if k not in unused
        }

        options = node.get("anyOf")
        if options and len(options) == 2 and {"type": "null"} in options:
            other = next(o for o in options if o != {"type": "null"})
            if isinstance(other.get("type"), str):
                node.pop("anyOf")
                node = {**other, **node, "type": [other["type"], "null"]}
                if "enum" in node:
                    node["enum"] = [*node["enum"], None]
        return node

    return walk(schema)


def _short(exc: Exception) -> str:
    text = str(exc)
    return text if len(text) <= 300 else text[:300] + "..."
