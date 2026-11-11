from pydantic import BaseModel


class UploadCVResponse(BaseModel):
    file_id: int
    job_id: int
    filename: str
    size: int
    file_hash: str
    status: str
    message: str
