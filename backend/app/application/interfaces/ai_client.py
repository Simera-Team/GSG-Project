from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass(frozen=True)
class LLMResponse:
    text: str | None              # raw answer (JSON text), saved on the attempt record
    provider: str                 # e.g. "gemini"
    model_version: str            # model that actually answered (NFR-035)
    status: str                   # provider finish status, e.g. "completed"
    usage: dict = field(default_factory=dict)


class IAIClient(ABC):
    """Any LLM provider. Swap providers by adding another implementation (NFR-035).

    One call = one attempt; retries are decided by the application service,
    so every try is recorded (FR-058).
    """

    provider: str
    model: str

    @abstractmethod
    def generate_structured(self, system_prompt: str, user_prompt: str,
                            json_schema: dict) -> LLMResponse:
        """Ask for an answer that follows `json_schema`.

        Raises LLMProviderError when no answer is obtained.
        """
