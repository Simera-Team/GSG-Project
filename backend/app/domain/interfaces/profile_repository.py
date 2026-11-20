from abc import ABC, abstractmethod

from app.domain.entities.profile import Profile


class IProfileRepository(ABC):

    @abstractmethod
    def get_by_user_id(self, user_id: int) -> Profile | None:
        pass

    @abstractmethod
    def get_or_create_by_user_id(self, user_id: int) -> Profile:
        pass