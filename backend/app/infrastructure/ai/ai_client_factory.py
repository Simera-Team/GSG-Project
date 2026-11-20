from app.application.interfaces.ai_client import IAIClient
from app.core.exceptions import LLMConfigurationError


def create_ai_client(settings) -> IAIClient:
    """Pick the LLM provider from settings (LLM_PROVIDER), so it can be
    replaced without touching the processing code (NFR-035)."""
    provider = settings.LLM_PROVIDER.lower()

    if provider == "gemini":
        from app.infrastructure.ai.gemini_client import GeminiAIClient
        return GeminiAIClient(
            api_key=settings.GEMINI_API_KEY,
            model=settings.LLM_MODEL,
            timeout_seconds=settings.LLM_TIMEOUT_SECONDS,
            thinking_level=settings.LLM_THINKING_LEVEL,
        )

    raise LLMConfigurationError(f"Unknown LLM_PROVIDER '{settings.LLM_PROVIDER}'")
