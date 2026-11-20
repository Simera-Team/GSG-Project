from dataclasses import dataclass


@dataclass
class UploadFileDTO:
    filename: str
    content: bytes