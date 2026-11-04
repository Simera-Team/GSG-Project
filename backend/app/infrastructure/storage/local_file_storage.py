import os
import stat
from pathlib import Path
from uuid import uuid4

from app.application.interfaces.file_storage import IFileStorage


class LocalFileStorage(IFileStorage):
    """Immutable local storage.

    - Every upload gets a new random name, so a new version never replaces
      an old one.
    - Files are created with exclusive mode ("xb"), so an existing file can
      never be overwritten.
    - Content is flushed to disk before the path is returned, so the database
      never points to a half-written file.
    - The finished file is made read-only.
    """

    READ_ONLY = stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH  # 0o444

    def __init__(self, base_path: str | Path = "storage/cvs"):
        self.storage_path = Path(base_path).resolve()
        self.storage_path.mkdir(parents=True, exist_ok=True)

    def save(self, content: bytes, extension: str) -> str:
        filename = f"{uuid4().hex}{extension}"
        file_path = self.storage_path / filename

        try:
            with open(file_path, "xb") as destination:
                destination.write(content)
                destination.flush()
                os.fsync(destination.fileno())

            os.chmod(file_path, self.READ_ONLY)
        except Exception:
            file_path.unlink(missing_ok=True)
            raise

        return str(file_path)

    def read(self, storage_path: str) -> bytes:
        return self._resolve(storage_path).read_bytes()

    def discard(self, storage_path: str) -> None:
        self._resolve(storage_path).unlink(missing_ok=True)

    def _resolve(self, storage_path: str) -> Path:
        path = Path(storage_path).resolve()

        if not path.is_relative_to(self.storage_path):
            raise ValueError("Path is outside the storage directory")

        return path
