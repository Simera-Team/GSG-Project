
from pathlib import Path
from uuid import uuid4

from app.application.interfaces.file_storage import IFileStorage


class LocalFileStorage(IFileStorage):

    def __init__(self):
        self.storage_path = Path("storage/cvs").resolve()
        self.storage_path.mkdir(parents=True, exist_ok=True)

    def save(self, content: bytes, extension: str) -> str:
        filename = f"{uuid4().hex}{extension}"
        file_path = self.storage_path / filename

        try:
            with open(file_path, "xb") as destination:
                destination.write(content)
        except Exception:
            file_path.unlink(missing_ok=True)
            raise

        return str(file_path)

    def delete(self, storage_path: str) -> None:
        path = Path(storage_path).resolve()

        if path.parent != self.storage_path:
            raise ValueError(
                "Cannot delete files outside the storage directory"
            )

        path.unlink(missing_ok=True)


    def read(self, storage_path: str) -> bytes:
        path = Path(storage_path).resolve()

        if path.parent != self.storage_path:
            raise ValueError(
                "Cannot read files outside the storage directory"
            )

        return path.read_bytes()    
