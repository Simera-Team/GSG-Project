from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class UploadStatusResponse(BaseModel):
    file_id: int
    filename: str
    status: Literal["processing", "success", "needs_review", "error"]
    message: str
    uploaded_at: datetime | None
    finished_at: datetime | None
