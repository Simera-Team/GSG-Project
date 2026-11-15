
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class SourceFile:
    file_id: int | None
    profile_id: int
    file_type: str              # file format: pdf | docx | md | json
    original_name: str
    file_hash: str
    storage_path: str
    # FR-053: kind of source, separate from the format and set by the upload
    # route. Required, because a source without a kind is rejected.
    source_kind: str = "cv"     # cv | linkedin | vetting
    status: str = "uploaded"
    extraction_method: str | None = None
    ocr_confidence: float | None = None
    error_message: str | None = None
    llm_response: dict[str, Any] | None = None
    uploaded_at: datetime | None = None
    finished_at: datetime | None = None
    num_of_retries: int = 0
    rule: str | None = None
