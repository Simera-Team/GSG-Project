
from abc import ABC, abstractmethod


class IMessagePublisher(ABC):

    @abstractmethod
    async def publish_cv(self, file_id: int) -> None:
        pass
