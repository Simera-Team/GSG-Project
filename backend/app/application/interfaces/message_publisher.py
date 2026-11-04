from abc import ABC, abstractmethod


class IMessagePublisher(ABC):
    """Hands an accepted source file (a job) to the background workers."""

    @abstractmethod
    async def publish_cv(self, file_id: int) -> None:
        pass
