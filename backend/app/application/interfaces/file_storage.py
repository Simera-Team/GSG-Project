from abc import ABC, abstractmethod


class IFileStorage(ABC):

    @abstractmethod
    def save(self, content: bytes, extension: str) -> str:
        pass


    @abstractmethod
    def delete(self, storage_path: str) -> None:
        pass

    @abstractmethod
    def read(self, storage_path: str) -> bytes:
        pass