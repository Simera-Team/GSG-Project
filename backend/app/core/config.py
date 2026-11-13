
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    # LLM field extraction
    LLM_PROVIDER: str = "gemini"
    GEMINI_API_KEY: str | None = None
    LLM_MODEL: str = "gemini-4-hydrogen"
    LLM_TIMEOUT_SECONDS: float = 120.0
    LLM_THINKING_LEVEL: str = "medium"        # minimal | low | medium | high
    LLM_MAX_ATTEMPTS: int = 3                 # FR-023
    LLM_RETRY_BASE_SECONDS: float = 2.0       # waits 2s, then 4s

    # Process uploads automatically after the response (until the RabbitMQ worker exists)
    PROCESS_UPLOADS_AUTOMATICALLY: bool = True

    # OCR threads: on laptops with fast + slow cores, 4 measured ~40% faster than all cores
    OCR_THREADS: int = 4

    # Fields below this confidence go to human review (FR-046, default 0.6)
    REVIEW_CONFIDENCE_THRESHOLD: float = 0.6

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore"
    )


settings = Settings()
