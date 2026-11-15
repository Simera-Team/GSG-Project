
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class SourceFile:
    file_id: int | None
    profile_id: int
    file_type: str
    original_name: str
    file_hash: str
    storage_path: str
    status: str = "uploaded"
    extraction_method: str | None = None
    ocr_confidence: float | None = None
    error_message: str | None = None
    llm_response: dict[str, Any] | None = None
    uploaded_at: datetime | None = None
    finished_at: datetime | None = None
    num_of_retries: int = 0
