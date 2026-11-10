from typing import Annotated, Callable

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

# Database
from app.infrastructure.persistence.db.session import get_db

# Security
from app.core.security import decode_access_token

# Domain
from app.domain.entities.user import User
from app.domain.permissions import Permission, has_permission

# Domain Interfaces
from app.domain.interfaces.user_repository import IUserRepository
from app.domain.interfaces.profile_repository import IProfileRepository
from app.domain.interfaces.source_file_repository import ISourceFileRepository

# Application Interfaces
from app.application.interfaces.file_storage import IFileStorage
from app.application.interfaces.unit_of_work import IUnitOfWork

# Repositories
from app.infrastructure.persistence.repositories.user_repository import UserRepository
from app.infrastructure.persistence.repositories.profile_repository import ProfileRepository
from app.infrastructure.persistence.repositories.file_repository import SourceFileRepository

# Infrastructure
from app.infrastructure.storage.local_file_storage import LocalFileStorage
from app.infrastructure.persistence.repositories.unit_of_work import SqlAlchemyUnitOfWork

# Services
from app.application.services.auth_service import AuthService
from app.application.services.file_service import FileService


bearer_scheme = HTTPBearer(auto_error=False)


# ==========================================
# Authentication Dependencies
# ==========================================

def get_user_repository(
    db: Annotated[Session, Depends(get_db)]
) -> IUserRepository:
    return UserRepository(db)


def get_auth_service(
    user_repo: Annotated[
        IUserRepository,
        Depends(get_user_repository)
    ]
) -> AuthService:
    return AuthService(user_repo)


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"}
    )


def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme)
    ],
    user_repo: Annotated[
        IUserRepository,
        Depends(get_user_repository)
    ]
) -> User:
    """Return the user making the request, or respond 401."""
    if credentials is None:
        raise _unauthorized("Not authenticated")

    try:
        payload = decode_access_token(credentials.credentials)
        user_id = int(payload["sub"])
    except (jwt.InvalidTokenError, ValueError) as exc:
        raise _unauthorized("Invalid or expired token") from exc

    user = user_repo.get_by_id(user_id)

    if user is None:
        raise _unauthorized("Invalid or expired token")

    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_permission(*permissions: Permission) -> Callable[..., User]:
    """Role guard: respond 403 unless the user's role has every permission.

    Usage:
        @router.get("/review/queue")
        def queue(user: Annotated[User, Depends(require_permission(Permission.REVIEW_QUEUE))]):
            ...
    """
    def dependency(user: CurrentUser) -> User:
        if not all(has_permission(user.role, p) for p in permissions):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action"
            )
        return user

    return dependency


# ==========================================
# File Storage Dependency
# ==========================================

def get_file_storage() -> IFileStorage:
    return LocalFileStorage()


# ==========================================
# Profile Repository Dependency
# ==========================================

def get_profile_repository(
    db: Annotated[Session, Depends(get_db)]
) -> IProfileRepository:
    return ProfileRepository(db)


# ==========================================
# Source File Repository Dependency
# ==========================================

def get_source_file_repository(
    db: Annotated[Session, Depends(get_db)]
) -> ISourceFileRepository:
    return SourceFileRepository(db)


# ==========================================
# Unit Of Work Dependency
# ==========================================

def get_unit_of_work(
    db: Annotated[Session, Depends(get_db)]
) -> IUnitOfWork:
    return SqlAlchemyUnitOfWork(db)


# ==========================================
# File Service Dependency
# ==========================================

def get_file_service(
    file_storage: Annotated[
        IFileStorage,
        Depends(get_file_storage)
    ],
    source_file_repository: Annotated[
        ISourceFileRepository,
        Depends(get_source_file_repository)
    ],
    profile_repository: Annotated[
        IProfileRepository,
        Depends(get_profile_repository)
    ],
    unit_of_work: Annotated[
        IUnitOfWork,
        Depends(get_unit_of_work)
    ]
) -> FileService:

    return FileService(
        storage=file_storage,
        source_file_repository=source_file_repository,
        profile_repository=profile_repository,
        unit_of_work=unit_of_work
    )
