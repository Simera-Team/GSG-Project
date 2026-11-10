from pydantic import BaseModel


class UploadCVResponse(BaseModel):
    file_id: int
    filename: str
    size: int
    status: str
    message: str