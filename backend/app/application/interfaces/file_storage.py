from abc import ABC, abstractmethod


class IFileStorage(ABC):
    """Write-once storage for original source files (FR-009).

    A stored file is never overwritten or modified. ``discard`` exists only
    to clean up a file whose database record could not be created, i.e. a
    file that never became a source.
    """

    @abstractmethod
    def save(self, content: bytes, extension: str) -> str:
        pass

    @abstractmethod
    def read(self, storage_path: str) -> bytes:
        pass

    @abstractmethod
    def discard(self, storage_path: str) -> None:
        pass
