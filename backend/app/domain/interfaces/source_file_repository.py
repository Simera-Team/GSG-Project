
from abc import ABC, abstractmethod

from app.domain.entities.source_file import SourceFile


class ISourceFileRepository(ABC):

    @abstractmethod
    def create(self, source_file: SourceFile) -> SourceFile:
        pass

    @abstractmethod
    def get_by_id(self, file_id: int) -> SourceFile | None:
        pass

    @abstractmethod
    def get_by_profile_and_hash(self, profile_id: int, file_hash: str) -> SourceFile | None:
        """This candidate's earlier upload of the identical file, if any (FR-012, FR-055)."""
        pass
