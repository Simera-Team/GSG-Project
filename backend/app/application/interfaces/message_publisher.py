from abc import ABC, abstractmethod


class IMessagePublisher(ABC):

    @abstractmethod
    async def publish_cv(self, file_id: int, trigger: str = "first_run") -> None:
        """Queue a stored file for processing. trigger: first_run or admin_rerun
        (an admin re-run is recorded but not counted toward the 3-try limit, FR-059)."""
        pass
