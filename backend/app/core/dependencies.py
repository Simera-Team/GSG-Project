
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

# Database
from app.infrastructure.persistence.db.session import get_db

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


# ==========================================
# Review Service Dependency (review queue API)
# ==========================================

def get_review_service(
    db: Annotated[Session, Depends(get_db)]
) -> "ReviewService":
    from app.application.services.review_service import ReviewService
    from app.infrastructure.persistence.repositories.catalog_repository import SqlCatalogRepository
    from app.infrastructure.persistence.repositories.processing_repository import (
        SqlProcessingRepository,
    )
    from app.infrastructure.persistence.repositories.review_repository import SqlReviewRepository

    return ReviewService(
        reviews=SqlReviewRepository(db),
        processing=SqlProcessingRepository(db),
        catalogs=SqlCatalogRepository(db),
        unit_of_work=SqlAlchemyUnitOfWork(db),
    )


# ==========================================
# Read Repository Dependency (profile, file status, admin views)
# ==========================================

def get_read_repository(
    db: Annotated[Session, Depends(get_db)]
):
    from app.infrastructure.persistence.repositories.read_repository import SqlReadRepository
    return SqlReadRepository(db)
