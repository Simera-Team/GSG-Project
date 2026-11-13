
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import EmailAlreadyExistsError
from app.domain.entities.user import User
from app.domain.interfaces.user_repository import IUserRepository
from app.infrastructure.persistence.models.user_model import UserModel


class UserRepository(IUserRepository):

    def __init__(self, db: Session):
        self.db = db

    def create(self, user: User) -> User:
        user_model = UserModel(
            name=user.name,
            email=user.email,
            password_hash=user.password_hash,
            role=user.role
        )

        try:
            self.db.add(user_model)
            self.db.commit()
            self.db.refresh(user_model)

        except IntegrityError as exc:
            self.db.rollback()

            sqlstate = getattr(exc.orig, "sqlstate", None)

            if sqlstate == "23505":
                raise EmailAlreadyExistsError(
                    "Email already registered"
                ) from exc

            raise

        except Exception:
            self.db.rollback()
            raise

        return self._to_entity(user_model)

    def get_by_email(self, email: str) -> User | None:
        statement = select(UserModel).where(
            UserModel.email == email
        )

        user_model = self.db.scalar(statement)

        if user_model is None:
            return None

        return self._to_entity(user_model)

    def get_by_id(self, user_id: int) -> User | None:
        user_model = self.db.get(UserModel, user_id)

        if user_model is None:
            return None

        return self._to_entity(user_model)

    @staticmethod
    def _to_entity(model: UserModel) -> User:
        return User(
            user_id=model.user_id,
            name=model.name,
            email=model.email,
            password_hash=model.password_hash,
            role=model.role,
            created_at=model.created_at
        )
