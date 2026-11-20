
from app.application.dto.RequestDto.register_dto import RegisterRequest
from app.application.dto.RequestDto.login_dto import LoginRequest
from app.application.dto.ResponseDto.login_response import LoginResponse

from app.domain.entities.user import User
from app.domain.enums.user_role import UserRole
from app.domain.interfaces.user_repository import IUserRepository

from app.core.security import (
    hash_password,
    verify_password,
    create_access_token
)

from app.core.exceptions import (
    EmailAlreadyExistsError,
    InvalidCredentialsError
)


class AuthService:

    def __init__(self, user_repository: IUserRepository):
        self.user_repository = user_repository

    def login(self, data: LoginRequest) -> LoginResponse:
        email = str(data.email).strip().lower()

        user = self.user_repository.get_by_email(email)

        if user is None:
            raise InvalidCredentialsError(
                "Invalid email or password"
            )

        if not verify_password(
            data.password,
            user.password_hash
        ):
            raise InvalidCredentialsError(
                "Invalid email or password"
            )

        if user.user_id is None:
            raise ValueError("User ID is missing")

        access_token = create_access_token(user.user_id)

        return LoginResponse(
            access_token=access_token,
            token_type="bearer"
        )

    def register(self, data: RegisterRequest) -> User:
        email = str(data.email).strip().lower()

        existing_user = self.user_repository.get_by_email(email)

        if existing_user is not None:
            raise EmailAlreadyExistsError(
                "Email already registered"
            )

        user = User(
            user_id=None,
            name=data.name.strip(),
            email=email,
            password_hash=hash_password(data.password),
            role=UserRole.CANDIDATE
        )

        return self.user_repository.create(user)
